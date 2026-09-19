//! The bytecode VM (`spec/vm.md`): the second evaluator.
//!
//! The tree is compiled once, per unit (the program's root and each
//! lambda body), into a flat instruction stream with variables resolved
//! to slots, step charges batched per straight-line run, and no
//! per-node path push.  Everything an operator *does* is
//! the tree-walker's (`rt.rs`, `text.rs`, `nt.rs`, ...); only
//! evaluation is new.
//!
//! The parts: `compile` (tree -> `Unit`), `exec` (the dispatch loop),
//! `ops` (operator work over popped values), `path` (`position_path`
//! derived from the node table and the frame stack on a trap).

pub mod compile;
pub mod exec;
pub mod ops;
pub mod path;
#[cfg(test)]
mod tests;

use crate::value::Value;
use std::cell::{Cell, RefCell};
use std::rc::Rc;

/// A coercion the reference performs on an operand *before* the next
/// operand is evaluated, so the VM must perform it at the same moment
/// rather than inside the operator's work.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum CK {
    Int,
    Text,
    Fn,
    List,
    Map,
}

/// The instruction set.  One value stack per activation; every node's
/// instructions leave exactly one value on it.
#[derive(Clone, Copy, Debug)]
pub enum Ins {
    /// Charge the run's node ticks (spec §4).  The payload is the run
    /// index; the run's node list gives `k` and, on a crossing, the
    /// node that crossed.
    Tick(u32),
    /// Push `unit.consts[i]`.
    Const(u32),
    /// Push this activation's slot.
    Load(u32),
    /// Push a slot of an enclosing activation; `depth` frames up the
    /// captured chain (1 = the nearest enclosing heap frame).
    LoadUp { depth: u16, slot: u16 },
    /// A load whose slot may not have been written yet (a letrec name
    /// read from a closure applied inside its own binding group).  On
    /// `Unset` it falls back to `unit.alts[alt]`, which is what the
    /// reference's name walk would have found one frame out.
    LoadChecked { depth: u16, slot: u16, alt: u32 },
    /// The reference's `unbound-ref`, with the names the resolver saw.
    Unbound(u32),
    /// Pop, name the closure if it has none (`_n_let`), write the slot.
    Store(u32),
    /// Forget the slots of a region that has closed, so that
    /// `bound_names` and a flattened environment see what the
    /// reference's popped `Scope` would have.
    Clear { from: u32, to: u32 },
    /// Build a closure over `unit.children[i]`, capturing this
    /// activation's frame (or, for a stack frame, its parent).  The
    /// second word is the live-slot set of *this* unit at the point the
    /// closure is made: what a delegated subtree inside it may see by
    /// name (§4.3's popped `Scope`).  `MASK_INHERIT` for a stack unit,
    /// whose slots are not in the captured chain at all.
    MakeClosure(u32, u32),
    Pop,
    Jump(u32),
    /// Pop an already-coerced integer; jump when it is zero.
    JumpZero(u32),
    /// Coerce the top of the stack; the context name is the operator's.
    Coerce(CK, u8),
    /// The operator's work over the top `n` values (`ops::work`).
    Work(u8, u8),
    /// A binary operator whose operands need no instruction of their
    /// own: a slot, a constant, or (for the first) what is already on
    /// the stack.  `spec/vm.md` §5's superinstruction.
    Bin(u8, u32, u32),
    /// The same for a one-operand operator.
    Un(u8, u32),
    /// Pop the argument and the function, apply (`rt::call`).
    Call,
    /// `_n_apply_tail`: the head must be callable before the last
    /// argument is evaluated.
    CheckCallable,
    /// Pop the argument and the function, return the tail marker.
    TailApply,
    Ret,
    /// Pop the key and the map; on a hit push the value and jump, on a
    /// miss fall through to the default's instructions.
    MapGetHit(u32),
    BudgetPush,
    BudgetPop,
    /// `external-boundary`: the declared mask, checked before the body.
    BoundaryPush(u32),
    BoundaryPop,
    /// The capability check an effect makes before evaluating its
    /// operands.
    RequireCap(u32, u8),
    /// `when-anomaly`: install a handler over the body.
    TryPush(u32),
    /// Leave the body without a fault: drop the handler, jump past it.
    TryPop(u32),
    /// In the handler: pop the handler function, apply it to the code.
    HandlerCall,
    /// The list family (0x50-0x57), which calls and charges per element.
    ListOp(u8),
    /// `quote`: a deep copy of the node, which is *not* evaluated.
    Quote(u32),
    /// This node's whole subtree is evaluated by the tree-walker, over
    /// a `Scope` flattened out of the VM's frames and with the derived
    /// path pushed underneath it (spec §2.4's dynamic fallback,
    /// widened: `eval`, `conserve`, `trace`, the Evolution and Meta
    /// families).  The tree-walker charges every one of those nodes,
    /// so the VM does not tick them.  The second word is the live-slot
    /// set the flattened environment is filtered by.
    Delegate(u32, u32),
    /// A slot the reference only rejects when the node is evaluated.
    Malformed(u8),
    /// `END` has no handler: `NotImplementedError`, not an anomaly.
    NotImplemented,
}

/// Per-instruction bookkeeping, read only on the trap path.
#[derive(Clone, Copy)]
pub struct Meta {
    /// The arena node this instruction belongs to: the trap's position.
    pub node: u32,
    /// How many of the run's nodes have begun when this instruction
    /// runs.  `NO_REWIND` when no run is open (the steps are exact).
    pub ticks: u32,
}

pub const NO_REWIND: u32 = u32::MAX;

/// Every slot of the unit is visible: a mask that was not recorded.
pub const MASK_ALL: u32 = u32::MAX;
/// A closure made in a stack-framed unit carries the mask its own
/// activation was entered with, because its captured frame is the one
/// above.
pub const MASK_INHERIT: u32 = u32::MAX - 1;

/// An operand a fused instruction reads for itself: the value already
/// on the stack, a slot of this activation, or a constant.
pub const SRC_STACK: u32 = 0;

#[inline]
pub fn src_slot(i: u32) -> u32 {
    1 | (i << 2)
}

#[inline]
pub fn src_const(i: u32) -> u32 {
    2 | (i << 2)
}

/// What a `LoadChecked` falls back to when its slot is unwritten.
/// `miss` is the `unbound-ref` to raise when the fallback slot is
/// unwritten as well -- which carries the name, so the anomaly is the
/// reference's and not a fabricated one.
#[derive(Clone)]
pub enum Alt {
    Slot { depth: u16, slot: u16, miss: u32 },
    Unbound(u32),
}

/// A name no binder covers, or whose slots are all unwritten: the id,
/// and the live-slot set at that point.  `bound_names` is derived from
/// the frame chain at the moment of the fault -- the names actually
/// written -- because a binder the resolver can see is not yet a
/// binding (spec §5.6).
pub struct UnboundRef {
    pub name: i64,
    pub mask: u32,
}

/// One compiled unit: a lambda body, or the program's root.
pub struct Unit {
    pub ins: Vec<Ins>,
    pub meta: Vec<Meta>,
    /// Run index -> where its nodes are in `run_nodes`, in tick order.
    pub runs: Vec<(u32, u32)>,
    /// Every run's nodes, back to back: a `Vec` per run was thousands
    /// of allocations on a program of any size.
    pub run_nodes: Vec<u32>,
    pub consts: Vec<Value>,
    /// Nested units, in the order `MakeClosure` names them.
    pub children: Vec<Rc<Unit>>,
    pub nslots: u32,
    /// slot -> name id, for a name walk and for `bound_names`.
    pub names: Vec<i64>,
    pub alts: Vec<Alt>,
    pub unbounds: Vec<UnboundRef>,
    /// Live-slot sets, one bit per slot, interned: which of this
    /// unit's bindings a flattened environment may see at a given
    /// point.  A region that has closed is not among them, even when
    /// its slots stay written for a closure that captured them.
    pub masks: Vec<Vec<u64>>,
    /// The unit's root node (a lambda's body, or the program).
    pub root: u32,
    /// The parameter's name id; `i64::MIN` for a unit that is not a
    /// lambda body.
    pub param: i64,
    /// A lambda body, whose slot 0 is the parameter.
    #[allow(dead_code)]
    pub is_lambda: bool,
    /// The frame is heap-allocated: something can hold it after the
    /// activation returns, or the program needs a walkable environment.
    pub heap: bool,
}

/// An activation's slots.  Four of them live in the frame itself: a
/// `Vec` behind the `Rc` was a second allocation and a second cache
/// miss for every captured activation, and almost every unit binds a
/// parameter and one or two names.
pub struct SlotBox {
    inline: [Value; INLINE],
    spill: Vec<Value>,
}

pub const INLINE: usize = 4;

impl SlotBox {
    pub fn new() -> SlotBox {
        SlotBox {
            inline: [Value::Unset, Value::Unset, Value::Unset, Value::Unset],
            spill: Vec::new(),
        }
    }

    #[inline]
    pub fn get(&self, i: usize) -> &Value {
        if i < INLINE {
            &self.inline[i]
        } else {
            &self.spill[i - INLINE]
        }
    }

    #[inline]
    pub fn set(&mut self, i: usize, v: Value) {
        if i < INLINE {
            self.inline[i] = v;
        } else {
            self.spill[i - INLINE] = v;
        }
    }

    /// Empty the box and give it room for `n` slots, all unwritten.
    pub fn reset(&mut self, n: usize) {
        for v in self.inline.iter_mut() {
            *v = Value::Unset;
        }
        self.spill.clear();
        if n > INLINE {
            self.spill.resize(n - INLINE, Value::Unset);
        }
    }

    pub fn iter(&self, n: usize) -> impl Iterator<Item = &Value> {
        self.inline.iter().take(n.min(INLINE)).chain(self.spill.iter())
    }
}

impl Default for SlotBox {
    fn default() -> Self {
        SlotBox::new()
    }
}

/// A heap frame: one activation's slots, and the chain out.
pub struct Frame {
    pub slots: RefCell<SlotBox>,
    pub unit: Rc<Unit>,
    pub parent: Option<Rc<Frame>>,
    /// The live-slot set of `parent`, as it stood where this frame's
    /// closure was made: an index into `parent.unit.masks`.
    pub parent_mask: Cell<u32>,
}

/// Is slot `i` of `unit` visible under `mask`?
pub fn slot_visible(unit: &Unit, mask: u32, i: usize) -> bool {
    if mask == MASK_ALL || mask == MASK_INHERIT {
        return true;
    }
    match unit.masks.get(mask as usize) {
        None => true,
        Some(bits) => bits.get(i / 64).map(|w| (w >> (i % 64)) & 1 == 1).unwrap_or(false),
    }
}

impl Frame {
    pub fn set(&self, slot: u32, v: Value) {
        self.slots.borrow_mut().set(slot as usize, v);
    }

    /// The chain's bindings by name, inner frames winning and a closed
    /// region left out: what `flatten_env` gives (spec §4.2).  `mask`
    /// is this frame's live set; every frame above carries the one its
    /// own closure recorded.
    pub fn flatten_masked(
        self: &Rc<Frame>,
        mask: u32,
        out: &mut std::collections::HashMap<i64, Value>,
    ) {
        let mut chain: Vec<(&Rc<Frame>, u32)> = Vec::new();
        let mut cur = Some(self);
        let mut here = mask;
        while let Some(f) = cur {
            chain.push((f, here));
            here = f.parent_mask.get();
            cur = f.parent.as_ref();
        }
        for (frame, m) in chain.iter().rev() {
            let slots = frame.slots.borrow();
            let names = &frame.unit.names;
            for (i, v) in slots.iter(names.len()).enumerate() {
                if !matches!(v, Value::Unset) && slot_visible(&frame.unit, *m, i) {
                    out.insert(names[i], v.clone());
                }
            }
        }
    }
}

/// What a closure carries when the VM compiled it: its unit and the
/// frame chain it captured.
#[derive(Clone)]
pub struct VmCode {
    pub unit: Rc<Unit>,
    pub frame: Option<Rc<Frame>>,
    /// The live-slot set of `frame` where this closure was made.
    pub parent_mask: u32,
}

/// The VM's own state on the runtime.
pub struct VmState {
    /// One record per live activation, for `position_path` (spec §6).
    pub frames: Vec<FrameRec>,
    /// Value stacks, kept for the next activation.
    pub pool: Vec<Vec<Value>>,
    /// Heap frames nothing closed over.
    pub frame_pool: Vec<Rc<Frame>>,
    /// Whether the VM is the evaluator for this run.
    pub on: bool,
    /// The function and argument of a tail call in flight: `rt::call`
    /// takes it the moment a unit returns the marker.
    pub tail: Option<(Value, Value)>,
}

pub struct FrameRec {
    /// The unit this activation is running.  A borrowed pointer, not an
    /// `Rc`: the activation's own frame holds the unit alive for as long
    /// as the record exists (the closure that named it, or the caller's
    /// `children`), and a refcount pair per call is a cost the call path
    /// cannot afford.
    pub unit: *const Unit,
    /// The node that made the nested call: an `apply`, a list-family
    /// walker, a delegated subtree.  Its chain is this activation's
    /// live path.  `u32::MAX` while nothing is nested.
    pub site: u32,
    /// The site is a delegated node, whose own entry the tree-walker
    /// pushes on `rt.path`: the chain stops just above it.
    pub site_exclusive: bool,
    /// How long `rt.path` was when this activation started, so that a
    /// tree-walk it is nested in interleaves correctly (vm/path.rs).
    pub path_len: usize,
}

impl VmState {
    pub fn new() -> VmState {
        VmState {
            frames: Vec::new(),
            pool: Vec::new(),
            frame_pool: Vec::new(),
            on: false,
            tail: None,
        }
    }
}

impl Default for VmState {
    fn default() -> Self {
        VmState::new()
    }
}
