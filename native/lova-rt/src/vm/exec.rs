//! The dispatch loop (`spec/vm.md` §3, §4).
//!
//! One Rust frame per LOVA activation, not per node: the loop runs a
//! unit's instructions over a value stack of its own, and a call goes
//! through `rt::call` -- the same `_call` the tree-walker uses, so the
//! `hot` bookkeeping, the depth ceiling, the `LoopFn` rounds and the
//! tail-call loop have one implementation.
//!
//! Steps are charged per straight-line run.  A run whose whole batch
//! fits under both ceilings is charged at its head and costs nothing
//! per node; a run that would cross one is charged node by node from
//! each instruction's `ticks`, because a batch that oversteps cannot
//! tell a `StepTrap` at node *j* from a `DomainTrap` at node *i < j*.

use super::*;
use crate::int::Int;
use crate::rt::{self, as_int, as_map, map_key, require_capability, Budget, Rt};
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;
use std::cell::{Cell, RefCell};
use std::rc::Rc;

const POOL: usize = 256;

/// A `when-anomaly` body's handler and everything it must put back.
struct TryRec {
    handler: u32,
    stack: usize,
    budget: usize,
    bounds: usize,
    caps: u32,
    enclosed: bool,
}

/// Where this activation's slots live.
enum Slots {
    Heap(Rc<Frame>),
    /// The first `nslots` entries of the activation's own value stack.
    Stack,
}

// --- frames -----------------------------------------------------------------

fn take_frame(
    rt: &mut Rt,
    unit: &Rc<Unit>,
    env: Option<Rc<Frame>>,
    parent_mask: u32,
) -> Rc<Frame> {
    let n = unit.nslots as usize;
    while let Some(mut free) = rt.vm.frame_pool.pop() {
        if let Some(f) = Rc::get_mut(&mut free) {
            f.parent = env;
            f.unit = unit.clone();
            f.parent_mask.set(parent_mask);
            f.slots.get_mut().reset(n);
            return free;
        }
    }
    let mut slots = SlotBox::new();
    slots.reset(n);
    Rc::new(Frame {
        slots: RefCell::new(slots),
        unit: unit.clone(),
        parent: env,
        parent_mask: Cell::new(parent_mask),
    })
}

fn give_frame(rt: &mut Rt, mut frame: Rc<Frame>) {
    if rt.vm.frame_pool.len() < POOL && Rc::strong_count(&frame) == 1 {
        if let Some(f) = Rc::get_mut(&mut frame) {
            f.parent = None;
            // Emptied now, not on the way out: a pooled frame must not
            // keep a world alive.
            f.slots.get_mut().reset(0);
            rt.vm.frame_pool.push(frame);
        }
    }
}

/// `depth` frames up the captured chain; 1 is the nearest enclosing
/// heap frame.
#[inline]
fn frame_up(env: &Option<Rc<Frame>>, depth: u16) -> Option<&Rc<Frame>> {
    let mut f = env.as_ref()?;
    for _ in 1..depth {
        f = f.parent.as_ref()?;
    }
    Some(f)
}

// --- entry points -----------------------------------------------------------

/// Run a program: compile it, then evaluate it in a frame of its own.
pub fn run_program(a: &mut Arena, rt: &mut Rt, root: u32) -> R<Value> {
    let unit = compile::compile(a, root);
    enter(a, rt, &unit, &None, MASK_ALL, None)
}

/// Apply a VM closure.  `rt::call` has already done the `hot`
/// bookkeeping, the depth check and the caps swap.
pub fn enter_closure(a: &mut Arena, rt: &mut Rt, cl: &Rc<ClosureData>, arg: Value) -> R<Value> {
    let code = cl.vm.as_ref().expect("a VM closure");
    // The closure is alive for the whole call, so the unit and the
    // captured chain are borrowed rather than cloned.
    enter(a, rt, &code.unit, &code.frame, code.parent_mask, Some(arg))
}

fn enter(
    a: &mut Arena,
    rt: &mut Rt,
    unit: &Rc<Unit>,
    env: &Option<Rc<Frame>>,
    parent_mask: u32,
    arg: Option<Value>,
) -> R<Value> {
    #[cfg(feature = "prof")]
    crate::prof::mark(crate::prof::R_VM_ENTER);
    let mut st: Vec<Value> = rt.vm.pool.pop().unwrap_or_default();
    let slots = if unit.heap {
        let frame = take_frame(rt, unit, env.clone(), parent_mask);
        if let Some(v) = arg {
            frame.set(0, v);
        }
        Slots::Heap(frame)
    } else {
        st.resize(unit.nslots as usize, Value::Unset);
        if let Some(v) = arg {
            st[0] = v;
        }
        Slots::Stack
    };

    let budget0 = rt.budget_stack.len();
    let caps0 = rt.caps;
    let enclosed0 = rt.enclosed;
    rt.vm.frames.push(FrameRec {
        unit: Rc::as_ptr(unit),
        site: u32::MAX,
        site_exclusive: false,
        path_len: rt.path.len(),
    });

    let out = run(a, rt, unit, &slots, env, parent_mask, &mut st);
    #[cfg(feature = "prof")]
    crate::prof::mark(crate::prof::R_VM_EXIT);

    rt.vm.frames.pop();
    if out.is_err() {
        rt.budget_stack.truncate(budget0);
        rt.caps = caps0;
        rt.enclosed = enclosed0;
    }
    if let Slots::Heap(frame) = slots {
        give_frame(rt, frame);
    }
    #[cfg(feature = "prof")]
    crate::prof::mark(crate::prof::R_VM_DROP);
    st.clear();
    #[cfg(feature = "prof")]
    crate::prof::mark(crate::prof::R_VM_EXIT);
    if rt.vm.pool.len() < POOL {
        rt.vm.pool.push(st);
    }
    out
}

// --- the loop ---------------------------------------------------------------

#[allow(clippy::too_many_arguments)]
fn run(
    a: &mut Arena,
    rt: &mut Rt,
    unit: &Rc<Unit>,
    slots: &Slots,
    env: &Option<Rc<Frame>>,
    parent_mask: u32,
    st: &mut Vec<Value>,
) -> R<Value> {
    // The stack comes empty from the pool: a stack-framed unit's slots
    // are its first `nslots` entries, and the operand stack is above.
    let base = 0usize;
    let ins = &unit.ins[..];
    let mut pc: usize = 0;
    let mut tries: Vec<TryRec> = Vec::new();
    let mut bounds: Vec<(u32, bool)> = Vec::new();
    // The open run's accounting (spec §4).
    let mut run_idx: usize = usize::MAX;
    let mut run_steps: u64 = rt.steps;
    let mut run_spent: i64 = 0;
    let mut charged: u32 = 0;
    let mut slow = false;

    macro_rules! slot_get {
        ($i:expr) => {
            match slots {
                Slots::Heap(f) => f.slots.borrow().get($i as usize).clone(),
                Slots::Stack => st[base + $i as usize].clone(),
            }
        };
    }
    /// A fused operand: a slot of this activation, or a constant.
    macro_rules! src_get {
        ($s:expr) => {
            if $s & 3 == 1 {
                slot_get!($s >> 2)
            } else {
                unit.consts[($s >> 2) as usize].clone()
            }
        };
    }
    macro_rules! slot_set {
        ($i:expr, $v:expr) => {
            match slots {
                Slots::Heap(f) => f.slots.borrow_mut().set($i as usize, $v),
                Slots::Stack => st[base + $i as usize] = $v,
            }
        };
    }

    // A fault: put the counters back where the reference would have
    // them, derive the path, then look for a `when-anomaly`.  The work
    // is out of line (`on_fault`): inlining it at twenty sites made the
    // loop spill registers it needs on the path that matters.
    macro_rules! fail {
        ($fault:expr, $ipc:expr, $node:expr, $rewind:expr) => {{
            let mut f = $fault;
            match on_fault(
                a, rt, unit, $ipc, $node, $rewind, &mut f, run_steps, run_spent, st,
                &mut tries, &mut bounds,
            ) {
                Some(handler) => {
                    pc = handler as usize;
                    continue;
                }
                None => return Err(f),
            }
        }};
    }
    macro_rules! ok {
        ($e:expr, $ipc:expr, $node:expr) => {
            match $e {
                Ok(v) => v,
                Err(f) => fail!(f, $ipc, $node, true),
            }
        };
    }
    /// A call, a walker, a delegated subtree: `rt.steps` has moved on
    /// and is already what the reference would have.
    macro_rules! ok_exact {
        ($e:expr, $ipc:expr, $node:expr) => {
            match $e {
                Ok(v) => v,
                Err(f) => fail!(f, $ipc, $node, false),
            }
        };
    }

    loop {
        #[cfg(feature = "prof")]
        crate::prof::mark(crate::prof::R_VMLOOP);
        let ipc = pc;
        let op = ins[pc];
        pc += 1;
        if slow {
            let m = unit.meta[ipc];
            if m.ticks != NO_REWIND && m.ticks > charged {
                let from = charged;
                charged = m.ticks;
                let (start, len) = unit.runs[run_idx];
                let nodes = &unit.run_nodes[start as usize..(start + len) as usize];
                if let Err((f, node)) = charge_slow(rt, nodes, from, charged) {
                    fail!(f, ipc, node, false);
                }
            }
        }
        match op {
            Ins::Tick(r) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_TICK);
                run_idx = r as usize;
                run_steps = rt.steps;
                run_spent = rt.budget_stack.last().map(|b| b.spent).unwrap_or(0);
                let k = unit.runs[run_idx].1 as u64;
                let fits = rt.steps + k <= rt.max_steps && budget_fits(rt, k);
                if fits {
                    rt.steps += k;
                    if let Some(b) = rt.budget_stack.last_mut() {
                        b.spent += k as i64;
                    }
                    slow = false;
                    charged = k as u32;
                } else {
                    slow = true;
                    charged = 0;
                }
            }
            Ins::Const(i) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_LOAD);
                st.push(unit.consts[i as usize].clone())
            }
            Ins::Load(slot) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_LOAD);
                st.push(slot_get!(slot))
            }
            Ins::LoadUp { depth, slot } => match frame_up(env, depth) {
                Some(f) => st.push(f.slots.borrow().get(slot as usize).clone()),
                None => {
                    // The compiler counts the chain it built; a short
                    // one would be a compiler fault, never a program's.
                    debug_assert!(false, "captured chain shorter than the compiler's depth");
                    let node = unit.meta[ipc].node;
                    fail!(rt::unbound_with(0, &[]), ipc, node, true);
                }
            },
            Ins::LoadChecked { depth, slot, alt } => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_LOAD);
                let got = match frame_up(env, depth) {
                    Some(f) => f.slots.borrow().get(slot as usize).clone(),
                    None => Value::Unset,
                };
                if !matches!(got, Value::Unset) {
                    st.push(got);
                } else {
                    let (value, miss) = match &unit.alts[alt as usize] {
                        Alt::Slot { depth: d2, slot: s2, miss } => {
                            let v = if *d2 == 0 {
                                slot_get!(*s2)
                            } else {
                                match frame_up(env, *d2) {
                                    Some(f) => f.slots.borrow().get(*s2 as usize).clone(),
                                    None => Value::Unset,
                                }
                            };
                            (v, *miss)
                        }
                        Alt::Unbound(i) => (Value::Unset, *i),
                    };
                    if matches!(value, Value::Unset) {
                        let u = &unit.unbounds[miss as usize];
                        let (name, mask) = (u.name, u.mask);
                        let names = bound_names(slots, env, st, base, unit, mask, parent_mask);
                        let node = unit.meta[ipc].node;
                        fail!(rt::unbound_with(name, &names), ipc, node, true);
                    }
                    st.push(value);
                }
            }
            Ins::Unbound(i) => {
                let u = &unit.unbounds[i as usize];
                let (name, mask) = (u.name, u.mask);
                let names = bound_names(slots, env, st, base, unit, mask, parent_mask);
                let node = unit.meta[ipc].node;
                fail!(rt::unbound_with(name, &names), ipc, node, true);
            }
            Ins::Store(slot) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_STACK);
                let v = st.pop().unwrap();
                if let Value::Closure(c) = &v {
                    if c.name.get().is_none() {
                        c.name.set(Some(unit.names[slot as usize]));
                        rt.named.push(c.clone());
                    }
                }
                slot_set!(slot, v);
            }
            Ins::Clear { from, to } => {
                for i in from..to {
                    slot_set!(i, Value::Unset);
                }
            }
            Ins::MakeClosure(i, mask) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_CLOSURE);
                let child = unit.children[i as usize].clone();
                let captured = match slots {
                    Slots::Heap(f) => Some(f.clone()),
                    Slots::Stack => env.clone(),
                };
                let param = child.param;
                let body = child.root;
                let captured_mask = if mask == MASK_INHERIT { parent_mask } else { mask };
                st.push(Value::Closure(Rc::new(ClosureData {
                    param,
                    body,
                    env: rt.empty_env.clone(),
                    caps: rt.caps,
                    enclosed: rt.enclosed,
                    name: Cell::new(None),
                    calls: Cell::new(0),
                    own: Cell::new(0),
                    owner: Cell::new(rt.current),
                    vm: Some(VmCode { unit: child, frame: captured, parent_mask: captured_mask }),
                })));
            }
            Ins::Pop => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_STACK);
                st.pop();
            }
            Ins::Jump(to) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_STACK);
                pc = to as usize;
            }
            Ins::JumpZero(to) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_STACK);
                let v = st.pop().unwrap();
                let zero = match &v {
                    Value::Int(i) => i.is_zero(),
                    other => {
                        // The `Coerce` before this one settles it; a
                        // value that is still not an integer is the
                        // reference's type fault, not a false test.
                        let node = unit.meta[ipc].node;
                        ok!(as_int(a, other, "if-surprise"), ipc, node).is_zero()
                    }
                };
                if zero {
                    pc = to as usize;
                }
            }
            Ins::Coerce(ck, cop) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_STACK);
                // The operand is nearly always of the kind already, and
                // then the reference's coercion is the identity.
                let settled = matches!(
                    (ck, st.last()),
                    (CK::Int, Some(Value::Int(_)))
                        | (CK::Text, Some(Value::Text(_)))
                        | (CK::Map, Some(Value::Map(_)))
                        | (CK::Fn, Some(Value::Closure(_)))
                        | (CK::Fn, Some(Value::Loop(_)))
                        | (CK::List, Some(Value::Nil))
                        | (CK::List, Some(Value::Cons(_)))
                );
                if !settled {
                    let v = st.pop().unwrap();
                    let node = unit.meta[ipc].node;
                    let out = ok!(ops::coerce(a, v, ck, cop), ipc, node);
                    st.push(out);
                }
            }
            Ins::Bin(bop, sa, sb) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(bop as u32);
                let y = src_get!(sb);
                let x = if sa == SRC_STACK { st.pop().unwrap() } else { src_get!(sa) };
                if let (Value::Int(Int::S(p)), Value::Int(Int::S(q))) = (&x, &y) {
                    let (p, q) = (*p, *q);
                    let got = match bop {
                        MERGE => p.checked_add(q),
                        DEVIATION => p.checked_sub(q),
                        MUL => p.checked_mul(q),
                        DIV | MOD => {
                            if q != 0 && !(p == i64::MIN && q == -1) {
                                let r = p % q;
                                Some(if bop == DIV {
                                    let d = p / q;
                                    if r != 0 && ((r < 0) != (q < 0)) { d - 1 } else { d }
                                } else if r != 0 && ((r < 0) != (q < 0)) {
                                    r + q
                                } else {
                                    r
                                })
                            } else {
                                None
                            }
                        }
                        _ => None,
                    };
                    if let Some(v) = got {
                        st.push(Value::Int(Int::S(v)));
                        continue;
                    }
                } else if bop == CONS && matches!(y, Value::Nil | Value::Cons(_)) {
                    st.push(Value::Cons(Rc::new(ConsCell { head: x, tail: y })));
                    continue;
                }
                let node = unit.meta[ipc].node;
                let args = [x, y];
                let out = ok!(ops::work(a, rt, bop, &args), ipc, node);
                st.push(out);
            }
            Ins::Un(uop, sa) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(uop as u32);
                let x = src_get!(sa);
                match uop {
                    IDENTITY => {
                        st.push(x);
                        continue;
                    }
                    THRESHOLD => {
                        if let Value::Int(Int::S(v)) = &x {
                            st.push(Value::Int(Int::S(i64::from(*v > 0))));
                            continue;
                        }
                    }
                    HEAD => {
                        if let Value::Cons(c) = &x {
                            st.push(c.head.clone());
                            continue;
                        }
                    }
                    TAIL => {
                        if let Value::Cons(c) = &x {
                            st.push(c.tail.clone());
                            continue;
                        }
                    }
                    IS_NIL => match &x {
                        Value::Nil => {
                            st.push(Value::Int(Int::S(1)));
                            continue;
                        }
                        Value::Cons(_) => {
                            st.push(Value::Int(Int::S(0)));
                            continue;
                        }
                        _ => {}
                    },
                    _ => {}
                }
                let node = unit.meta[ipc].node;
                let args = [x];
                let out = ok!(ops::work(a, rt, uop, &args), ipc, node);
                st.push(out);
            }
            Ins::Work(wop, n) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(wop as u32);
                // The operators a program spends its time in, in place:
                // no call, no `Int` clone, no drop glue.  Every one of
                // them falls through to `ops::work`, which is the
                // reference's own sequence, the moment an operand is
                // not the shape the fast path knows.
                let len = st.len();
                match wop {
                    MERGE | DEVIATION | MUL => {
                        if let (Value::Int(Int::S(x)), Value::Int(Int::S(y))) =
                            (&st[len - 2], &st[len - 1])
                        {
                            let got = match wop {
                                MERGE => x.checked_add(*y),
                                DEVIATION => x.checked_sub(*y),
                                _ => x.checked_mul(*y),
                            };
                            if let Some(v) = got {
                                st.pop();
                                st[len - 2] = Value::Int(Int::S(v));
                                continue;
                            }
                        }
                    }
                    DIV | MOD => {
                        if let (Value::Int(Int::S(x)), Value::Int(Int::S(y))) =
                            (&st[len - 2], &st[len - 1])
                        {
                            let (x, y) = (*x, *y);
                            if y != 0 && !(x == i64::MIN && y == -1) {
                                // Python's floor division and modulo.
                                let r = x % y;
                                let v = if wop == DIV {
                                    let q = x / y;
                                    if r != 0 && ((r < 0) != (y < 0)) { q - 1 } else { q }
                                } else if r != 0 && ((r < 0) != (y < 0)) {
                                    r + y
                                } else {
                                    r
                                };
                                st.pop();
                                st[len - 2] = Value::Int(Int::S(v));
                                continue;
                            }
                        }
                    }
                    THRESHOLD => {
                        if let Value::Int(Int::S(x)) = &st[len - 1] {
                            let v = i64::from(*x > 0);
                            st[len - 1] = Value::Int(Int::S(v));
                            continue;
                        }
                    }
                    CONS => {
                        if matches!(&st[len - 1], Value::Nil | Value::Cons(_)) {
                            let tail = st.pop().unwrap();
                            let head = st.pop().unwrap();
                            st.push(Value::Cons(Rc::new(ConsCell { head, tail })));
                            continue;
                        }
                    }
                    HEAD => {
                        if let Value::Cons(c) = &st[len - 1] {
                            let head = c.head.clone();
                            st[len - 1] = head;
                            continue;
                        }
                    }
                    TAIL => {
                        if let Value::Cons(c) = &st[len - 1] {
                            let tail = c.tail.clone();
                            st[len - 1] = tail;
                            continue;
                        }
                    }
                    IS_NIL => {
                        let v = match &st[len - 1] {
                            Value::Nil => Some(1i64),
                            Value::Cons(_) => Some(0),
                            _ => None,
                        };
                        if let Some(v) = v {
                            st[len - 1] = Value::Int(Int::S(v));
                            continue;
                        }
                    }
                    IDENTITY => continue,
                    NIL => {
                        st.push(Value::Nil);
                        continue;
                    }
                    _ => {}
                }
                let at = st.len() - n as usize;
                let node = unit.meta[ipc].node;
                let out = {
                    let args = &st[at..];
                    ops::work(a, rt, wop, args)
                };
                let out = ok!(out, ipc, node);
                st.truncate(at);
                st.push(out);
            }
            Ins::ListOp(lop) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(lop as u32);
                let n = match lop {
                    LIST_FOLD => 3,
                    LIST_REVERSE => 1,
                    _ => 2,
                };
                let at = st.len() - n;
                let node = unit.meta[ipc].node;
                if let Some(f) = rt.vm.frames.last_mut() {
                    f.site = node;
                    f.site_exclusive = false;
                }
                let mut args: [Value; 3] = [Value::Unset, Value::Unset, Value::Unset];
                for (i, v) in st.drain(at..).enumerate() {
                    args[i] = v;
                }
                let out = ok_exact!(ops::list_op(a, rt, lop, &args[..n]), ipc, node);
                st.push(out);
            }
            Ins::Call => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_CALL);
                let arg = st.pop().unwrap();
                let f = st.pop().unwrap();
                let node = unit.meta[ipc].node;
                if let Some(fr) = rt.vm.frames.last_mut() {
                    fr.site = node;
                    fr.site_exclusive = false;
                }
                let out = ok_exact!(rt::call(a, rt, f, arg), ipc, node);
                st.push(out);
            }
            Ins::CheckCallable => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_CALL);
                if !matches!(st.last(), Some(Value::Closure(_)) | Some(Value::Loop(_))) {
                    let f = st.last().cloned().unwrap_or(Value::Unset);
                    let node = unit.meta[ipc].node;
                    fail!(rt::not_callable(a, &f), ipc, node, true);
                }
            }
            Ins::TailApply => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_CALL);
                let arg = st.pop().unwrap();
                let f = st.pop().unwrap();
                // The marker the tree-walker allocates an `Rc` for goes
                // in the runtime instead: a tail call is a loop in
                // `rt::call` and the pair never escapes it.
                rt.vm.tail = Some((f, arg));
                return Ok(Value::Unset);
            }
            Ins::Ret => {
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_RET);
                let out = st.pop().unwrap();
                debug_assert!(!matches!(out, Value::Unset), "an unwritten slot escaped as a value");
                return Ok(out);
            }
            Ins::MapGetHit(end) => {
                #[cfg(feature = "prof")]
                crate::prof::mark(MAP_GET as u32);
                let key = st.pop().unwrap();
                let m = st.pop().unwrap();
                let node = unit.meta[ipc].node;
                let table = ok!(as_map(a, &m, "map-get"), ipc, node);
                let hashed = ok!(map_key(a, &key, "map-get"), ipc, node);
                #[cfg(feature = "prof")]
                crate::prof::mark(crate::prof::R_VM_MAPGET);
                if let Some(e) = table.get(&hashed) {
                    st.push(e.val);
                    pc = end as usize;
                }
            }
            Ins::BudgetPush => {
                let v = st.pop().unwrap();
                let node = unit.meta[ipc].node;
                let limit = ok!(as_int(a, &v, "budget"), ipc, node);
                rt.budget_stack.push(Budget { limit, spent: 0 });
            }
            Ins::BudgetPop => {
                rt.budget_stack.pop();
            }
            Ins::BoundaryPush(declared) => {
                let node = unit.meta[ipc].node;
                if let Err(f) = check_boundary(rt, declared) {
                    fail!(f, ipc, node, true);
                }
                bounds.push((rt.caps, rt.enclosed));
                rt.caps = declared;
                rt.enclosed = true;
            }
            Ins::BoundaryPop => {
                if let Some((c, e)) = bounds.pop() {
                    rt.caps = c;
                    rt.enclosed = e;
                }
            }
            Ins::RequireCap(bit, cop) => {
                let node = unit.meta[ipc].node;
                if let Err(f) = require_capability(rt, bit, op_name(cop)) {
                    fail!(f, ipc, node, true);
                }
            }
            Ins::TryPush(handler) => tries.push(TryRec {
                handler,
                stack: st.len(),
                budget: rt.budget_stack.len(),
                bounds: bounds.len(),
                caps: rt.caps,
                enclosed: rt.enclosed,
            }),
            Ins::TryPop(end) => {
                tries.pop();
                pc = end as usize;
            }
            Ins::HandlerCall => {
                let handler = st.pop().unwrap();
                let code = st.pop().unwrap();
                let node = unit.meta[ipc].node;
                if let Some(fr) = rt.vm.frames.last_mut() {
                    fr.site = node;
                    fr.site_exclusive = false;
                }
                let out = ok_exact!(rt::call(a, rt, handler, code), ipc, node);
                st.push(out);
            }
            Ins::Quote(kid) => {
                let copy = a.deep_copy(kid);
                st.push(Value::Program(copy));
            }
            Ins::Delegate(node, mask) => {
                let flat = flatten_here(slots, env, st, base, unit, mask, parent_mask);
                let scope = Scope::root();
                for (k, v) in flat {
                    scope.set(k, v);
                }
                if let Some(fr) = rt.vm.frames.last_mut() {
                    fr.site = node;
                    fr.site_exclusive = true;
                }
                let saved = std::mem::replace(&mut rt.env, scope);
                let out = rt::eval(a, rt, node, false);
                rt.env = saved;
                if let Some(fr) = rt.vm.frames.last_mut() {
                    fr.site_exclusive = false;
                }
                let v = ok_exact!(out, ipc, node);
                st.push(v);
            }
            Ins::Malformed(mop) => {
                let node = unit.meta[ipc].node;
                fail!(malformed(mop), ipc, node, true);
            }
            Ins::NotImplemented => {
                return Err(Fault::NotImplemented(
                    "operator end (family struct) not implemented in Milestone 1 runtime".into(),
                ))
            }
        }
    }
}

/// Everything a fault costs, out of the dispatch loop's way.  Returns
/// the handler to jump to when a `when-anomaly` catches it.
#[cold]
#[inline(never)]
#[allow(clippy::too_many_arguments)]
fn on_fault(
    a: &Arena,
    rt: &mut Rt,
    unit: &Rc<Unit>,
    ipc: usize,
    node: u32,
    rewind: bool,
    f: &mut Fault,
    run_steps: u64,
    run_spent: i64,
    st: &mut Vec<Value>,
    tries: &mut Vec<TryRec>,
    bounds: &mut Vec<(u32, bool)>,
) -> Option<u32> {
    let t = match f {
        Fault::Trap(t) => t,
        Fault::NotImplemented(_) => return None,
    };
    if !t.anomaly.enriched {
        if rewind {
            let m = unit.meta[ipc];
            if m.ticks != NO_REWIND {
                let target = run_steps + m.ticks as u64;
                if rt.steps > target {
                    rt.steps = target;
                }
                if let Some(b) = rt.budget_stack.last_mut() {
                    let want = run_spent + m.ticks as i64;
                    if b.spent > want {
                        b.spent = want;
                    }
                }
            }
        }
        let derived = path::full(a, rt, Some(node));
        rt::enrich_with(rt, t, &derived);
    }
    if t.class == Class::Step {
        return None;
    }
    let rec = tries.pop()?;
    st.truncate(rec.stack);
    rt.budget_stack.truncate(rec.budget);
    bounds.truncate(rec.bounds);
    rt.caps = rec.caps;
    rt.enclosed = rec.enclosed;
    let code = anomaly_code(&t.anomaly);
    // A handled fault is still observed (spec §5.4).
    rt.emit(&Int::zero(), &Int::from_i64(code));
    st.push(Value::Int(Int::from_i64(code)));
    Some(rec.handler)
}

// --- helpers ----------------------------------------------------------------

fn budget_fits(rt: &Rt, k: u64) -> bool {
    match rt.budget_stack.last() {
        None => true,
        Some(b) => match b.limit.to_i64() {
            Some(l) => b.spent + k as i64 <= l,
            None => !b.limit.is_negative(),
        },
    }
}

/// A run that would cross a ceiling is charged node by node, so the
/// trap lands on the node the reference would have trapped at.
fn charge_slow(rt: &mut Rt, run: &[u32], from: u32, to: u32) -> Result<(), (Fault, u32)> {
    for j in from..to {
        if !rt.budget_stack.is_empty() {
            let (over, limit, spent) = {
                let b = rt.budget_stack.last_mut().unwrap();
                b.spent += 1;
                let over = match b.limit.to_i64() {
                    Some(l) => b.spent > l,
                    None => Int::from_i64(b.spent) > b.limit,
                };
                (over, b.limit.clone(), b.spent)
            };
            if over {
                return Err((budget_trap(&limit, spent), run[j as usize]));
            }
        }
        rt.steps += 1;
        if rt.steps > rt.max_steps {
            return Err((step_trap(rt.steps, rt.max_steps), run[j as usize]));
        }
    }
    Ok(())
}

fn check_boundary(rt: &Rt, declared: u32) -> R<()> {
    let excess = declared & !rt.caps;
    if rt.enclosed && excess != 0 {
        return Err(domain(
            "capability-denied",
            format!(
                "external-boundary: nested boundary declares {} beyond the enclosing {}",
                py_name_list(&capability_names(excess)),
                py_name_list(&capability_names(rt.caps))
            ),
            detail(vec![
                ("operator", J::from("external-boundary")),
                ("declared", J::from(capability_names(declared))),
                ("enclosing", J::from(capability_names(rt.caps))),
                ("excess", J::from(capability_names(excess))),
            ]),
            "a nested boundary may only narrow; declare it in the enclosing one",
        ));
    }
    let missing = declared & !rt.granted;
    if missing != 0 {
        let granted = capability_names(rt.granted);
        let shown = if granted.is_empty() {
            "nothing".to_string()
        } else {
            py_name_list(&granted)
        };
        return Err(domain(
            "capability-denied",
            format!(
                "external-boundary: declares {} but the host granted {}",
                py_name_list(&capability_names(declared)),
                shown
            ),
            detail(vec![
                ("operator", J::from("external-boundary")),
                ("declared", J::from(capability_names(declared))),
                ("granted", J::from(capability_names(rt.granted))),
                ("missing", J::from(capability_names(missing))),
            ]),
            &format!(
                "run with `--allow {}`, or declare less",
                capability_names(missing).join(",")
            ),
        ));
    }
    Ok(())
}

fn malformed(op: u8) -> Fault {
    let (message, slot, hint) = match op {
        LET => ("LET: name slot must be a literal integer id", Some(0), "put a literal integer in LET's first slot"),
        LAMBDA => ("LAMBDA: param slot must be a literal integer id", Some(0), "put a literal integer in LAMBDA's first slot"),
        REF => ("REF: name slot must be a literal integer id", Some(0), "put a literal integer in REF's slot"),
        APPLY => ("APPLY: missing function in head slot", None, "give `apply` a function to call"),
        EXTERNAL_BOUNDARY => (
            "external-boundary: capability slot must be a literal",
            Some(0),
            "put a literal capability mask in the first slot",
        ),
        _ => ("malformed node", None, "rebuild the node"),
    };
    let mut d = vec![("operator", J::from(op_name(op)))];
    if let Some(s) = slot {
        d.push(("slot", J::from(s)));
    }
    domain("malformed", message.to_string(), detail(d), hint)
}

/// Every binding this activation can see, inner frames winning: what
/// `flatten_env` gives the tree-walker for a delegated subtree.
///
/// A `let` region that has closed is not among them even when its slots
/// are still written -- they are kept for a closure that captured them,
/// and the reference popped that `Scope` (F1).  `mask` is this unit's
/// live set at the point that asks; every frame above answers with the
/// mask its own closure recorded.
#[allow(clippy::too_many_arguments)]
fn flatten_here(
    slots: &Slots,
    env: &Option<Rc<Frame>>,
    st: &[Value],
    base: usize,
    unit: &Rc<Unit>,
    mask: u32,
    parent_mask: u32,
) -> std::collections::HashMap<i64, Value> {
    let mut out = std::collections::HashMap::new();
    match slots {
        Slots::Heap(f) => f.flatten_masked(mask, &mut out),
        Slots::Stack => {
            if let Some(f) = env {
                f.flatten_masked(parent_mask, &mut out);
            }
            for (i, name) in unit.names.iter().enumerate() {
                let v = &st[base + i];
                if !matches!(v, Value::Unset) && slot_visible(unit, mask, i) {
                    out.insert(*name, v.clone());
                }
            }
        }
    }
    out
}

/// `bound_names`: the names actually written and still in scope, sorted
/// -- `flatten_env`'s key set (F3).
#[allow(clippy::too_many_arguments)]
fn bound_names(
    slots: &Slots,
    env: &Option<Rc<Frame>>,
    st: &[Value],
    base: usize,
    unit: &Rc<Unit>,
    mask: u32,
    parent_mask: u32,
) -> Vec<i64> {
    let flat = flatten_here(slots, env, st, base, unit, mask, parent_mask);
    let mut names: Vec<i64> = flat.keys().copied().collect();
    names.sort_unstable();
    names
}
