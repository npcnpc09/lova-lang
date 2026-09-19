//! The compiler (`spec/vm.md` §2): tree -> units, names -> slots,
//! straight-line runs -> one `Tick`.
//!
//! Two passes.  The first resolves every `ref` against the lexical
//! chain, allocates a slot per binding, decides the `let` chain rule of
//! the semantics' §4.3 statically, and records which units are
//! captured.  The second emits instructions, turning a resolution into
//! a `Load` / `LoadUp` / `LoadChecked` with the depth counted in *heap*
//! frames.
//!
//! Compilation cannot fail: a malformed slot is compiled into the
//! instruction that raises the reference's anomaly when the node is
//! reached, because the reference only raises it when the node is
//! evaluated (spec §1).
//!
//! Operators whose environment is not their lexical chain, or whose
//! work is long and cold -- `eval`, `conserve`, `trace`, the Evolution
//! and Meta families -- are compiled to one `Delegate`, which runs the
//! whole subtree on the tree-walker over a flattened environment.  That
//! is spec §2.4's dynamic fallback, widened: the same evaluator, so the
//! same values, the same steps and the same anomaly.

use super::*;
use crate::fx::FxMap;
use crate::int::Int;
use crate::tokens::*;
use crate::value::Value;
use std::rc::Rc;

// --- pass 1: scope ----------------------------------------------------------

struct UnitInfo {
    root: u32,
    param: i64,
    is_lambda: bool,
    parent: Option<usize>,
    names: Vec<i64>,
    captured: bool,
    /// Which slots a nested unit reads: a closure can hold them after
    /// the region that bound them has closed, so they must not be
    /// forgotten when it does.
    held: Vec<bool>,
    heap: bool,
    /// Heap frames strictly enclosing this unit.
    above: usize,
}

#[derive(Clone)]
enum Target {
    Slot { unit: usize, slot: u32 },
    /// No binder covers the name here; `bound_names` is derived from
    /// the frame chain when the fault actually happens.
    Unbound,
}

struct RefRes {
    primary: Target,
    alt: Option<Target>,
}

struct LetInfo {
    slot: u32,
    /// This `let` writes into the frame the enclosing one opened: the
    /// "extend" case of §4.3.
    extend: bool,
}

struct Binder {
    name: i64,
    unit: usize,
    slot: u32,
    /// The value is being compiled: the binding is not written yet, so
    /// code in the same unit cannot see it, but a closure made in the
    /// value can (letrec).
    pending: bool,
}

struct Info {
    units: Vec<UnitInfo>,
    binders: Vec<Binder>,
    refs: FxMap<u32, RefRes>,
    lets: FxMap<u32, LetInfo>,
    lambdas: FxMap<u32, usize>,
    /// The program hands a subtree to the tree-walker somewhere, so
    /// every frame must be walkable by name.
    needs_env: bool,
}

/// An operator the VM hands to the tree-walker whole.
pub fn delegated(op: u8) -> bool {
    matches!(op, CONSERVE | EVAL | READ)
        || (DEFPOP..=RETIRE).contains(&op)
        || (LINEAGE_QUERY..=GENERATION).contains(&op)
        || op == NET_SEND
        || op == NET_RECV
}

fn lit_id(a: &Arena, id: u32) -> Option<i64> {
    if a.op(id) != LIT_INT {
        return None;
    }
    match &a.get(id).ival {
        Some(Int::S(v)) => Some(*v),
        Some(other) => Some(other.to_i64().unwrap_or(i64::MIN)),
        None => Some(i64::MIN),
    }
}

impl Info {
    fn new() -> Info {
        Info {
            units: Vec::new(),
            binders: Vec::new(),
            refs: FxMap::default(),
            lets: FxMap::default(),
            lambdas: FxMap::default(),
            needs_env: false,
        }
    }

    /// A binder is invisible to code in its own unit while its value is
    /// being evaluated; a closure made there sees it, because the
    /// closure runs later.
    fn visible(&self, b: &Binder, unit: usize) -> bool {
        !(b.pending && b.unit == unit)
    }

    fn find(&self, name: i64, unit: usize, skip: usize) -> Option<(usize, u32)> {
        let mut left = skip;
        for b in self.binders.iter().rev() {
            if b.name == name && self.visible(b, unit) {
                if left == 0 {
                    return Some((b.unit, b.slot));
                }
                left -= 1;
            }
        }
        None
    }

    /// `Scope.bound`: what the reference's frame chain holds when the
    /// `let` runs.
    fn bound(&self, name: i64, unit: usize) -> bool {
        self.find(name, unit, 0).is_some()
    }

    fn target(&self, name: i64, unit: usize, skip: usize) -> Target {
        match self.find(name, unit, skip) {
            Some((u, slot)) => Target::Slot { unit: u, slot },
            None => Target::Unbound,
        }
    }

    fn scan_unit(
        &mut self,
        a: &Arena,
        body: u32,
        parent: Option<usize>,
        param: i64,
        is_lambda: bool,
    ) -> usize {
        let ix = self.units.len();
        self.units.push(UnitInfo {
            root: body,
            param,
            is_lambda,
            parent,
            names: if is_lambda { vec![param] } else { Vec::new() },
            captured: false,
            held: if is_lambda { vec![false] } else { Vec::new() },
            heap: false,
            above: 0,
        });
        if is_lambda {
            self.binders.push(Binder { name: param, unit: ix, slot: 0, pending: false });
        }
        self.scan(a, body, ix);
        if is_lambda {
            self.binders.pop();
        }
        ix
    }

    fn scan(&mut self, a: &Arena, node: u32, unit: usize) {
        let op = a.op(node);
        if delegated(op) {
            // The subtree is the tree-walker's; its `ref`s are looked
            // up by name in a flattened copy of this frame chain.
            self.needs_env = true;
            return;
        }
        match op {
            LIT_INT | LIT_TEXT => {}
            QUOTE => {} // its operand is not evaluated
            REF => {
                let kids = a.kids(node);
                if kids.is_empty() {
                    return;
                }
                let name = match lit_id(a, kids[0]) {
                    Some(n) => n,
                    None => return, // malformed, raised when reached
                };
                let primary = self.target(name, unit, 0);
                let alt = match &primary {
                    Target::Slot { unit: u, slot } if *u != unit => {
                        self.units[*u].captured = true;
                        self.units[*u].held[*slot as usize] = true;
                        Some(self.target(name, unit, 1))
                    }
                    _ => None,
                };
                self.refs.insert(node, RefRes { primary, alt });
            }
            LAMBDA => {
                let kids = a.kids(node);
                if kids.len() != 2 {
                    return;
                }
                let (slot, body) = (kids[0], kids[1]);
                let param = match lit_id(a, slot) {
                    Some(p) => p,
                    None => return,
                };
                let child = self.scan_unit(a, body, Some(unit), param, true);
                self.lambdas.insert(node, child);
            }
            LET => {
                self.scan_let(a, node, unit);
            }
            _ => {
                for i in 0..a.kids(node).len() {
                    let k = a.kids(node)[i];
                    self.scan(a, k, unit);
                }
            }
        }
    }

    /// A `let` and every `let` that, by §4.3, writes into the same
    /// frame: one region, every name allocated before any value is
    /// compiled, so that the group is mutually recursive.
    fn scan_let(&mut self, a: &Arena, node: u32, unit: usize) {
        let mut members: Vec<(u32, i64)> = Vec::new();
        let mut cur = node;
        loop {
            let kids = a.kids(cur);
            if kids.len() != 3 {
                return;
            }
            let name = match lit_id(a, kids[0]) {
                Some(n) => n,
                // A malformed name slot: the node traps when it is
                // reached and nothing below it is evaluated.
                None => break,
            };
            members.push((cur, name));
            let body = a.kids(cur)[2];
            if a.op(body) == LET && a.kids(body).len() == 3 {
                if let Some(bname) = lit_id(a, a.kids(body)[0]) {
                    let shadows_group = members.iter().any(|(_, n)| *n == bname);
                    if !shadows_group && !self.bound(bname, unit) {
                        cur = body;
                        continue;
                    }
                }
            }
            break;
        }
        if members.is_empty() {
            return;
        }

        let base = self.binders.len();
        for (i, (ln, name)) in members.iter().enumerate() {
            let slot = self.units[unit].names.len() as u32;
            self.units[unit].names.push(*name);
            self.units[unit].held.push(false);
            self.lets.insert(*ln, LetInfo { slot, extend: i > 0 });
            self.binders.push(Binder { name: *name, unit, slot, pending: true });
        }
        for (i, (ln, _)) in members.iter().enumerate() {
            let value = a.kids(*ln)[1];
            self.scan(a, value, unit);
            self.binders[base + i].pending = false;
        }
        let body = a.kids(members[members.len() - 1].0)[2];
        self.scan(a, body, unit);
        self.binders.truncate(base);
    }

    /// Heapness, then the depth every unit's captured chain has.
    fn settle(&mut self) {
        for i in 0..self.units.len() {
            self.units[i].heap = self.units[i].captured || self.needs_env || ALWAYS_HEAP;
        }
        for i in 0..self.units.len() {
            let above = match self.units[i].parent {
                None => 0,
                Some(p) => self.units[p].above + usize::from(self.units[p].heap),
            };
            self.units[i].above = above;
        }
    }
}

/// A frame is on the heap only when something can hold it after the
/// activation returns (spec §2.2).  Setting this forces every frame
/// there, which is how a difference between the two tiers is bisected.
const ALWAYS_HEAP: bool = false;

// --- the coercions the reference performs between operands ------------------

/// `Some(kind)` when the reference coerces child `i` *before* it
/// evaluates child `i + 1`, so the trap order depends on it.
fn coerce_after(op: u8, i: usize) -> Option<CK> {
    match (op, i) {
        (MERGE, 0) | (MUL, 0) | (MOD, 0) | (DIV, 0) | (GCD, 0) => Some(CK::Int),
        (SURPRISE, 0) | (LIST_RANGE, 0) => Some(CK::Int),
        (TEXT_SLICE, 1) => Some(CK::Int),
        (TEXT_FIND, 0) | (TEXT_SPLIT, 0) | (FS_WRITE, 0) => Some(CK::Text),
        (TEXT_MATCH, 0) | (TEXT_MATCH_ALL, 0) => Some(CK::Text),
        (MAP_PUT, 0) | (MAP_GET, 0) => Some(CK::Map),
        (LIST_ZIP, 0) => Some(CK::List),
        (LIST_MAP, 0) | (LIST_FILTER, 0) | (LIST_ANY, 0) | (LIST_SORT_BY, 0) => Some(CK::Fn),
        (LIST_FOLD, 0) => Some(CK::Fn),
        _ => None,
    }
}

/// The capability an effect requires before it evaluates its operands.
fn required_cap(op: u8) -> Option<(u32, u8)> {
    match op {
        FS_READ => Some((CAP_FS_READ, op)),
        FS_WRITE => Some((CAP_FS_WRITE, op)),
        CLOCK => Some((CAP_CLOCK, op)),
        _ => None,
    }
}

/// An operator whose work can call or charge Rule-2 steps: the
/// straight-line run ends there (spec §4).
fn breaks_run(op: u8) -> bool {
    is_list_op(op) || op == TEXT_MATCH_ALL
}

/// The operators a fused instruction can run: their work is short, and
/// their operands are read left to right with no trap between them.
fn fusable(op: u8) -> bool {
    matches!(
        op,
        MERGE
            | DEVIATION
            | MUL
            | DIV
            | MOD
            | GCD
            | CONS
            | THRESHOLD
            | HEAD
            | TAIL
            | IS_NIL
            | PARTITION
            | IDENTITY
            | TEXT_LEN
            | IS_TEXT
            | INT_TEXT
    )
}

fn is_list_op(op: u8) -> bool {
    (LIST_MAP..=LIST_ZIP).contains(&op)
}

// --- pass 2: emit -----------------------------------------------------------

struct Emitter<'a> {
    a: &'a Arena,
    info: &'a Info,
    unit: usize,
    ins: Vec<Ins>,
    meta: Vec<Meta>,
    runs: Vec<(u32, u32)>,
    run_nodes: Vec<u32>,
    consts: Vec<Value>,
    children: Vec<Rc<Unit>>,
    alts: Vec<Alt>,
    unbounds: Vec<UnboundRef>,
    run_open: Option<usize>,
    open_nodes: Vec<u32>,
    /// The slots of this unit whose region is open here: what a
    /// delegated subtree, or an `unbound-ref`'s `bound_names`, may see.
    live: Vec<u64>,
    masks: Vec<Vec<u64>>,
}

impl<'a> Emitter<'a> {
    fn new(a: &'a Arena, info: &'a Info, unit: usize) -> Emitter<'a> {
        Emitter {
            a,
            info,
            unit,
            ins: Vec::new(),
            meta: Vec::new(),
            runs: Vec::new(),
            run_nodes: Vec::new(),
            consts: Vec::new(),
            children: Vec::new(),
            alts: Vec::new(),
            unbounds: Vec::new(),
            run_open: None,
            open_nodes: Vec::new(),
            live: Vec::new(),
            masks: Vec::new(),
        }
    }

    fn here(&self) -> u32 {
        self.ins.len() as u32
    }

    fn live_set(&mut self, slot: u32, on: bool) {
        let word = slot as usize / 64;
        while self.live.len() <= word {
            self.live.push(0);
        }
        let bit = 1u64 << (slot % 64);
        if on {
            self.live[word] |= bit;
        } else {
            self.live[word] &= !bit;
        }
    }

    /// The live set as it stands, interned.
    fn live_mask(&mut self) -> u32 {
        if let Some(found) = self.masks.iter().position(|m| *m == self.live) {
            return found as u32;
        }
        self.masks.push(self.live.clone());
        (self.masks.len() - 1) as u32
    }

    fn push(&mut self, ins: Ins, node: u32) {
        let ticks = match self.run_open {
            Some(_) => self.open_nodes.len() as u32,
            None => NO_REWIND,
        };
        self.ins.push(ins);
        self.meta.push(Meta { node, ticks });
    }

    /// An instruction that ends the straight-line run: it carries the
    /// whole run's tick count, and what follows starts a new one.
    fn push_break(&mut self, ins: Ins, node: u32) {
        self.push(ins, node);
        self.close_run();
    }

    /// The node ticks: it joins the open run, opening one if needed.
    fn tick(&mut self, node: u32) {
        if self.run_open.is_none() {
            let idx = self.runs.len();
            self.runs.push((0, 0));
            self.ins.push(Ins::Tick(idx as u32));
            self.meta.push(Meta { node, ticks: NO_REWIND });
            self.run_open = Some(idx);
        }
        self.open_nodes.push(node);
    }

    fn close_run(&mut self) {
        if let Some(idx) = self.run_open.take() {
            let start = self.run_nodes.len() as u32;
            self.run_nodes.extend_from_slice(&self.open_nodes);
            self.runs[idx] = (start, self.open_nodes.len() as u32);
            self.open_nodes.clear();
        }
    }

    fn constant(&mut self, v: Value) -> u32 {
        self.consts.push(v);
        (self.consts.len() - 1) as u32
    }

    /// The parent is not recorded: a trap walks the arena for the chain
    /// (`vm/path.rs`), which is cold and saves a hash insert per node.
    fn kid(&mut self, _parent: u32, child: u32, tail: bool) {
        self.emit(child, tail);
    }

    /// The depth, in heap frames, from this unit to `unit`.
    fn depth_to(&self, unit: usize) -> u16 {
        let here = &self.info.units[self.unit];
        let there = &self.info.units[unit];
        (here.above - there.above) as u16
    }

    fn alt_of(&mut self, other: &Target) -> Alt {
        match other {
            Target::Slot { unit, slot } => {
                let depth = if *unit == self.unit { 0 } else { self.depth_to(*unit) };
                // The fallback slot can be unwritten too, and then the
                // reference still names this reference's name (F2).
                let mask = self.live_mask();
                self.unbounds.push(UnboundRef { name: 0, mask });
                let miss = (self.unbounds.len() - 1) as u32;
                Alt::Slot { depth, slot: *slot as u16, miss }
            }
            Target::Unbound => {
                let mask = self.live_mask();
                self.unbounds.push(UnboundRef { name: 0, mask });
                Alt::Unbound((self.unbounds.len() - 1) as u32)
            }
        }
    }

    fn target_ins(&mut self, t: &Target, alt: Option<&Target>) -> Ins {
        match t {
            Target::Slot { unit, slot } if *unit == self.unit => Ins::Load(*slot),
            Target::Slot { unit, slot } => {
                let depth = self.depth_to(*unit);
                match alt {
                    None => Ins::LoadUp { depth, slot: *slot as u16 },
                    Some(other) => {
                        let fallback = self.alt_of(other);
                        self.alts.push(fallback);
                        Ins::LoadChecked {
                            depth,
                            slot: *slot as u16,
                            alt: (self.alts.len() - 1) as u32,
                        }
                    }
                }
            }
            Target::Unbound => {
                let mask = self.live_mask();
                self.unbounds.push(UnboundRef { name: 0, mask });
                Ins::Unbound((self.unbounds.len() - 1) as u32)
            }
        }
    }

    fn emit(&mut self, node: u32, tail: bool) {
        let op = self.a.op(node);
        if delegated(op) {
            let mask = self.live_mask();
            self.push_break(Ins::Delegate(node, mask), node);
            return;
        }
        match op {
            LIT_INT => {
                self.tick(node);
                let v = Value::Int(self.a.get(node).ival.clone().unwrap());
                let i = self.constant(v);
                self.push(Ins::Const(i), node);
            }
            LIT_TEXT => {
                self.tick(node);
                let v = Value::Text(self.a.get(node).sval.clone().unwrap());
                let i = self.constant(v);
                self.push(Ins::Const(i), node);
            }
            REF => self.emit_ref(node),
            LET => self.emit_let(node, tail),
            LAMBDA => self.emit_lambda(node),
            SEQ => self.emit_seq(node, tail),
            IF_SURPRISE => self.emit_if(node, tail),
            APPLY => self.emit_apply(node, tail),
            MAP_GET => self.emit_map_get(node),
            BUDGET => self.emit_budget(node),
            WHEN_ANOMALY => self.emit_when(node),
            EXTERNAL_BOUNDARY => self.emit_boundary(node),
            QUOTE => {
                self.tick(node);
                let kids = self.a.kids(node);
                if kids.is_empty() {
                    self.push(Ins::Malformed(QUOTE), node);
                } else {
                    self.push(Ins::Quote(kids[0]), node);
                }
            }
            END => {
                self.tick(node);
                self.push(Ins::NotImplemented, node);
            }
            _ => self.emit_simple(node, op),
        }
    }

    /// Every operator whose children are all evaluated left to right and
    /// whose work happens at the end.
    fn emit_simple(&mut self, node: u32, op: u8) {
        self.tick(node);
        if let Some((bit, name)) = required_cap(op) {
            self.push(Ins::RequireCap(bit, name), node);
        }
        let kids = self.a.kids(node);
        // Only the first two operands can be folded, and nothing else
        // needs the marks: a vector per operator node was an allocation
        // per node of every program.
        let mut marks: [u32; 2] = [0, 0];
        for (i, k) in kids.iter().enumerate() {
            if i < 2 {
                marks[i] = self.here();
            }
            self.kid(node, *k, false);
            if let Some(ck) = coerce_after(op, i) {
                self.push(Ins::Coerce(ck, op), node);
            }
        }
        if !is_list_op(op)
            && !breaks_run(op)
            && kids.len() <= 2
            && self.fuse(node, op, &marks[..kids.len()])
        {
            return;
        }
        let ins = if is_list_op(op) {
            Ins::ListOp(op)
        } else {
            Ins::Work(op, kids.len() as u8)
        };
        if breaks_run(op) {
            self.push_break(ins, node);
        } else {
            self.push(ins, node);
        }
    }

    /// An operand that costs no instruction: `Load` and `Const` read
    /// something that cannot trap and cannot be observed changing, so
    /// the operator can read it itself (`spec/vm.md` §5).
    fn pure_src(ins: Ins) -> Option<u32> {
        match ins {
            Ins::Load(slot) if slot < (1 << 29) => Some(src_slot(slot)),
            Ins::Const(i) if i < (1 << 29) => Some(src_const(i)),
            _ => None,
        }
    }

    /// Fold an operator and its simple operands into one instruction.
    /// Returns false when the shape does not allow it.
    fn fuse(&mut self, node: u32, op: u8, marks: &[u32]) -> bool {
        if !fusable(op) {
            return false;
        }
        let coerced = coerce_after(op, 0).is_some();
        let end = self.here();
        if marks.len() == 1 {
            let m0 = marks[0] as usize;
            if end as usize != m0 + 1 {
                return false;
            }
            let src = match Self::pure_src(self.ins[m0]) {
                Some(s) => s,
                None => return false,
            };
            self.rewind_to(m0 as u32);
            self.push(Ins::Un(op, src), node);
            return true;
        }
        if marks.len() != 2 {
            return false;
        }
        let (m0, m1) = (marks[0] as usize, marks[1] as usize);
        // The second operand must be the one instruction that reads it.
        if end as usize != m1 + 1 {
            return false;
        }
        let b = match Self::pure_src(self.ins[m1]) {
            Some(s) => s,
            None => return false,
        };
        // The first operand can be folded in only when the operator
        // does not coerce it before the second is evaluated: that
        // coercion traps with one fewer node charged, and the fused
        // instruction could not say so.  Where it does coerce, the
        // `Coerce` stays and the first operand comes off the stack.
        let first_len = m1 - m0 - usize::from(coerced);
        let a = if !coerced && first_len == 1 {
            match Self::pure_src(self.ins[m0]) {
                Some(s) => s,
                None => SRC_STACK,
            }
        } else {
            SRC_STACK
        };
        let from = if a == SRC_STACK { m1 } else { m0 };
        self.rewind_to(from as u32);
        self.push(Ins::Bin(op, a, b), node);
        true
    }

    /// Drop the instructions from `mark` on; they are folded into what
    /// comes next.
    fn rewind_to(&mut self, mark: u32) {
        self.ins.truncate(mark as usize);
        self.meta.truncate(mark as usize);
    }

    fn emit_ref(&mut self, node: u32) {
        self.tick(node);
        let kids = self.a.kids(node);
        let name = match kids.first().and_then(|k| lit_id(self.a, *k)) {
            Some(n) => n,
            None => {
                self.push(Ins::Malformed(REF), node);
                return;
            }
        };
        let (primary, alt) = match self.info.refs.get(&node) {
            Some(r) => (r.primary.clone(), r.alt.clone()),
            None => (Target::Unbound, None),
        };
        let ins = self.target_ins(&primary, alt.as_ref());
        // The name is what an `unbound-ref` reports.
        match ins {
            Ins::Unbound(i) => self.unbounds[i as usize].name = name,
            Ins::LoadChecked { alt, .. } => match self.alts[alt as usize] {
                Alt::Unbound(i) | Alt::Slot { miss: i, .. } => {
                    self.unbounds[i as usize].name = name
                }
            },
            _ => {}
        }
        self.push(ins, node);
    }

    fn emit_lambda(&mut self, node: u32) {
        self.tick(node);
        let child = match self.info.lambdas.get(&node) {
            Some(c) => *c,
            None => {
                self.push(Ins::Malformed(LAMBDA), node);
                return;
            }
        };
        let compiled = emit_unit(self.a, self.info, child);
        self.children.push(compiled);
        // A stack-framed unit is not in the captured chain, so what a
        // closure made there inherits is its own activation's mask.
        let mask = if self.info.units[self.unit].heap {
            self.live_mask()
        } else {
            MASK_INHERIT
        };
        self.push(Ins::MakeClosure((self.children.len() - 1) as u32, mask), node);
    }

    fn emit_let(&mut self, node: u32, tail: bool) {
        // The whole group: every member writes into the same region.
        let mut members: Vec<u32> = Vec::new();
        let mut cur = node;
        while self.info.lets.contains_key(&cur) {
            members.push(cur);
            let body = self.a.kids(cur)[2];
            let continues = self.a.op(body) == LET
                && self.info.lets.get(&body).map(|l| l.extend).unwrap_or(false);
            if continues {
                cur = body;
            } else {
                break;
            }
        }
        if members.is_empty() {
            // A malformed name slot: charge the node, then refuse it.
            self.tick(node);
            self.push(Ins::Malformed(LET), node);
            return;
        }
        let first_slot = self.info.lets[&members[0]].slot;
        let mut last_slot = first_slot;
        for m in members.clone() {
            let slot = self.info.lets[&m].slot;
            self.live_set(slot, true);
        }
        for m in members.clone() {
            let slot = self.info.lets[&m].slot;
            last_slot = slot;
            self.tick(m);
            let value = self.a.kids(m)[1];
            self.kid(m, value, false);
            self.push(Ins::Store(slot), m);
        }
        let last = members[members.len() - 1];
        let body = self.a.kids(last)[2];
        self.kid(last, body, tail);
        // A region that has closed is forgotten: the reference pops the
        // `Scope` there, so its values die there, and holding them to
        // the end of the activation would both show through a
        // flattened environment and keep whole lists alive.  A closure
        // made inside the region can outlive it and still read those
        // slots, so a region something closed over is kept.
        // `held` counts the references the resolver placed; a
        // delegated subtree reads by name and can be anywhere below,
        // so a program that delegates at all keeps its regions' values
        // and relies on the mask alone to hide the names (F1).
        let held = &self.info.units[self.unit].held;
        let free = !self.info.needs_env && (first_slot..=last_slot).all(|i| !held[i as usize]);
        if free {
            self.push(Ins::Clear { from: first_slot, to: last_slot + 1 }, last);
        }
        // Whether or not the values go, the names do: the region has
        // closed, and nothing that flattens this environment from here
        // on may see them, though a closure that captured them still
        // reads their slots (F1).
        for slot in first_slot..=last_slot {
            self.live_set(slot, false);
        }
    }

    fn emit_seq(&mut self, node: u32, tail: bool) {
        self.tick(node);
        let kids = self.a.kids(node);
        if kids.is_empty() {
            let i = self.constant(Value::Int(Int::zero()));
            self.push(Ins::Const(i), node);
            return;
        }
        for (i, k) in kids.iter().enumerate() {
            let last = i + 1 == kids.len();
            self.kid(node, *k, tail && last);
            if !last {
                self.push(Ins::Pop, node);
            }
        }
    }

    fn emit_if(&mut self, node: u32, tail: bool) {
        self.tick(node);
        let kids = self.a.kids(node);
        self.kid(node, kids[0], false);
        self.push(Ins::Coerce(CK::Int, IF_SURPRISE), node);
        let jz = self.here();
        self.push_break(Ins::JumpZero(0), node);
        self.kid(node, kids[1], tail);
        self.close_run();
        let jmp = self.here();
        self.push(Ins::Jump(0), node);
        let else_pc = self.here();
        self.kid(node, kids[2], tail);
        self.close_run();
        let end = self.here();
        self.ins[jz as usize] = Ins::JumpZero(else_pc);
        self.ins[jmp as usize] = Ins::Jump(end);
    }

    fn emit_apply(&mut self, node: u32, tail: bool) {
        self.tick(node);
        let kids = self.a.kids(node);
        if kids.is_empty() {
            self.push(Ins::Malformed(APPLY), node);
            return;
        }
        self.kid(node, kids[0], false);
        let n = kids.len();
        if n == 1 {
            // `(apply f)` yields the head, callable or not (quirk 32).
            return;
        }
        for (i, kid) in kids.iter().enumerate().skip(1) {
            let last = i + 1 == n;
            if tail && last {
                self.push_break(Ins::CheckCallable, node);
                self.kid(node, *kid, false);
                self.push_break(Ins::TailApply, node);
                return;
            }
            self.kid(node, *kid, false);
            self.push_break(Ins::Call, node);
        }
    }

    fn emit_map_get(&mut self, node: u32) {
        self.tick(node);
        let kids = self.a.kids(node);
        self.kid(node, kids[0], false);
        self.push(Ins::Coerce(CK::Map, MAP_GET), node);
        self.kid(node, kids[1], false);
        let hit = self.here();
        self.push_break(Ins::MapGetHit(0), node);
        self.kid(node, kids[2], false);
        self.close_run();
        let end = self.here();
        self.ins[hit as usize] = Ins::MapGetHit(end);
    }

    fn emit_budget(&mut self, node: u32) {
        self.tick(node);
        let kids = self.a.kids(node);
        self.kid(node, kids[0], false);
        self.push(Ins::Coerce(CK::Int, BUDGET), node);
        self.push_break(Ins::BudgetPush, node);
        self.kid(node, kids[1], false);
        self.close_run();
        self.push(Ins::BudgetPop, node);
    }

    fn emit_when(&mut self, node: u32) {
        self.tick(node);
        let kids = self.a.kids(node);
        let tp = self.here();
        self.push_break(Ins::TryPush(0), node);
        self.kid(node, kids[0], false);
        self.close_run();
        let done = self.here();
        self.push(Ins::TryPop(0), node);
        let handler = self.here();
        self.kid(node, kids[1], false);
        self.push_break(Ins::HandlerCall, node);
        let end = self.here();
        self.ins[tp as usize] = Ins::TryPush(handler);
        self.ins[done as usize] = Ins::TryPop(end);
    }

    fn emit_boundary(&mut self, node: u32) {
        self.tick(node);
        let kids = self.a.kids(node);
        let declared = match lit_id(self.a, kids[0]) {
            Some(v) => v as u32,
            None => {
                self.push(Ins::Malformed(EXTERNAL_BOUNDARY), node);
                return;
            }
        };
        self.push_break(Ins::BoundaryPush(declared), node);
        self.kid(node, kids[1], false);
        self.close_run();
        self.push(Ins::BoundaryPop, node);
    }
}

fn emit_unit(a: &Arena, info: &Info, ix: usize) -> Rc<Unit> {
    let mut em = Emitter::new(a, info, ix);
    let u = &info.units[ix];
    if u.is_lambda {
        // The parameter is bound for the whole body.
        em.live_set(0, true);
    }
    em.emit(u.root, u.is_lambda);
    em.close_run();
    em.push(Ins::Ret, u.root);
    Rc::new(Unit {
        ins: em.ins,
        meta: em.meta,
        runs: em.runs,
        run_nodes: em.run_nodes,
        consts: em.consts,
        children: em.children,
        nslots: u.names.len() as u32,
        names: u.names.clone(),
        alts: em.alts,
        unbounds: em.unbounds,
        masks: em.masks,
        root: u.root,
        param: u.param,
        is_lambda: u.is_lambda,
        heap: u.heap,
    })
}

/// Compile a program to its root unit; nested lambda bodies hang off it
/// as `children`.
pub fn compile(a: &Arena, root: u32) -> Rc<Unit> {
    let mut info = Info::new();
    info.scan_unit(a, root, None, i64::MIN, false);
    info.settle();
    emit_unit(a, &info, 0)
}
