//! The VM against the tree-walker, node for node (`spec/vm.md` §8.1).
//!
//! Every case builds a tree, runs it on both evaluators with the same
//! ceilings, and compares the whole outcome: the value, the step count,
//! and on a trap the kind, the derived `position_path`, its ordinals
//! and the detail.  A test that only checked the value would miss the
//! three things the VM actually changes.

use super::exec;
use crate::int::Int;
use crate::rt::{self, Rt};
use crate::tokens::*;
use crate::trap::Fault;
use crate::value::format_value;

fn lit(a: &mut Arena, v: i64) -> u32 {
    a.push(node(LIT_INT, Vec::new(), Some(Int::from_i64(v)), None))
}

fn op(a: &mut Arena, code: u8, kids: Vec<u32>) -> u32 {
    a.push(node(code, kids, None, None))
}

/// `(deviation a b)` is what the surface spells `sub`.
fn sub(a: &mut Arena, x: u32, y: u32) -> u32 {
    op(a, DEVIATION, vec![x, y])
}

fn outcome(build: &dyn Fn(&mut Arena) -> u32, max_steps: u64, vm: bool) -> String {
    let mut a = Arena::new();
    let root = build(&mut a);
    let mut rt = Rt::new(max_steps, 10_000, 0, "");
    rt.ordinals = std::rc::Rc::new(preorder_ordinals(&a, root));
    rt.vm.on = vm;
    let out = if vm {
        exec::run_program(&mut a, &mut rt, root)
    } else {
        rt::eval(&mut a, &mut rt, root, false)
    };
    match out {
        Ok(v) => format!("value {} steps {}", format_value(&a, &v), rt.steps),
        Err(Fault::Trap(t)) => format!(
            "{} path {:?} nodes {:?} op {:?} steps {} detail {:?}",
            t.anomaly.kind,
            t.anomaly.position_path,
            t.anomaly.position_nodes,
            t.anomaly.offending_op,
            rt.steps,
            t.anomaly.detail
        ),
        Err(Fault::NotImplemented(m)) => format!("not implemented: {}", m),
    }
}

/// The two evaluators on one tree: the same outcome, whatever it is.
fn same(name: &str, build: &dyn Fn(&mut Arena) -> u32, max_steps: u64) -> String {
    let tree = outcome(build, max_steps, false);
    let vm = outcome(build, max_steps, true);
    assert_eq!(tree, vm, "{} @{} steps", name, max_steps);
    tree
}

fn same_everywhere(name: &str, build: &dyn Fn(&mut Arena) -> u32) {
    for ceiling in [1u64, 2, 3, 5, 9, 17, 40, 200, 1_000, 100_000] {
        same(name, build, ceiling);
    }
}

// --- §4.3, the let chain ----------------------------------------------------

/// letrec: the closure in the value slot sees the name it is bound to.
#[test]
fn letrec_self_recursion() {
    let build = |a: &mut Arena| {
        // (let 0 (lambda 1 (if (ref 1) (apply (ref 0) (sub (ref 1) 1)) 42))
        //      (apply (ref 0) 3))
        let n0 = lit(a, 0);
        let n1 = lit(a, 1);
        let param = lit(a, 1);
        let test = op(a, REF, vec![n1]);
        let one = lit(a, 1);
        let r1 = lit(a, 1);
        let refn = op(a, REF, vec![r1]);
        let less = sub(a, refn, one);
        let f0 = lit(a, 0);
        let reff = op(a, REF, vec![f0]);
        let recurse = op(a, APPLY, vec![reff, less]);
        let base = lit(a, 42);
        let body = op(a, IF_SURPRISE, vec![test, recurse, base]);
        let lam = op(a, LAMBDA, vec![param, body]);
        let c0 = lit(a, 0);
        let head = op(a, REF, vec![c0]);
        let three = lit(a, 3);
        let call = op(a, APPLY, vec![head, three]);
        op(a, LET, vec![n0, lam, call])
    };
    assert!(same("letrec", &build, 100_000).starts_with("value 42"));
    same_everywhere("letrec", &build);
}

/// A binding group: two `let`s in a chain share a frame, so each sees
/// the other (mutual recursion).
#[test]
fn binding_group_is_mutually_recursive() {
    let build = |a: &mut Arena| {
        // (let 0 (lambda 2 (if (ref 2) (apply (ref 1) (sub (ref 2) 1)) 1))
        //   (let 1 (lambda 2 (if (ref 2) (apply (ref 0) (sub (ref 2) 1)) 0))
        //     (apply (ref 0) 7)))
        let make = |a: &mut Arena, other: i64| {
            let param = lit(a, 2);
            let t = lit(a, 2);
            let test = op(a, REF, vec![t]);
            let r = lit(a, 2);
            let refn = op(a, REF, vec![r]);
            let one = lit(a, 1);
            let less = sub(a, refn, one);
            let o = lit(a, other);
            let refo = op(a, REF, vec![o]);
            let recurse = op(a, APPLY, vec![refo, less]);
            let base = lit(a, if other == 1 { 1 } else { 0 });
            let body = op(a, IF_SURPRISE, vec![test, recurse, base]);
            op(a, LAMBDA, vec![param, body])
        };
        let even = make(a, 1);
        let odd = make(a, 0);
        let n0 = lit(a, 0);
        let n1 = lit(a, 1);
        let c0 = lit(a, 0);
        let head = op(a, REF, vec![c0]);
        let seven = lit(a, 7);
        let call = op(a, APPLY, vec![head, seven]);
        let inner = op(a, LET, vec![n1, odd, call]);
        op(a, LET, vec![n0, even, inner])
    };
    // 7 is odd, so `even?` says 0.
    assert!(same("group", &build, 100_000).starts_with("value 0"));
    same_everywhere("group", &build);
}

/// Shadowing breaks the chain: the value of the inner `let` is
/// evaluated before its own binding exists, so it sees the outer one.
#[test]
fn shadowing_breaks_the_chain() {
    let build = |a: &mut Arena| {
        // (let 0 1 (let 0 (merge (ref 0) 10) (ref 0)))
        let n0 = lit(a, 0);
        let one = lit(a, 1);
        let n0b = lit(a, 0);
        let r = lit(a, 0);
        let outer = op(a, REF, vec![r]);
        let ten = lit(a, 10);
        let value = op(a, MERGE, vec![outer, ten]);
        let r2 = lit(a, 0);
        let body = op(a, REF, vec![r2]);
        let inner = op(a, LET, vec![n0b, value, body]);
        op(a, LET, vec![n0, one, inner])
    };
    assert!(same("shadow", &build, 100_000).starts_with("value 11"));
    same_everywhere("shadow", &build);
}

/// A `let` in an argument position opens a frame of its own and is not
/// part of any chain.
#[test]
fn let_in_an_argument_position() {
    let build = |a: &mut Arena| {
        // (merge (let 0 5 (ref 0)) (let 0 6 (ref 0)))
        let region = |a: &mut Arena, v: i64| {
            let name = lit(a, 0);
            let value = lit(a, v);
            let r = lit(a, 0);
            let body = op(a, REF, vec![r]);
            op(a, LET, vec![name, value, body])
        };
        let left = region(a, 5);
        let right = region(a, 6);
        op(a, MERGE, vec![left, right])
    };
    assert!(same("argument let", &build, 100_000).starts_with("value 11"));
    same_everywhere("argument let", &build);
}

// --- §4, the tick batch -----------------------------------------------------

/// A literal takes no position-path entry: `(merge 1 1)` at two steps
/// reports the `merge` (spec §6.2, `tests/test_compiled.py`).
#[test]
fn a_literal_takes_no_position() {
    let build = |a: &mut Arena| {
        let x = lit(a, 1);
        let y = lit(a, 1);
        op(a, MERGE, vec![x, y])
    };
    let out = same("merge 1 1", &build, 2);
    assert!(out.starts_with("step-limit-exceeded path [3]"), "{}", out);
    assert!(out.contains("steps 3"), "{}", out);
}

/// A fault inside a batched run reports the steps of *its* node, not
/// the whole run's: the batch is rewound.
#[test]
fn a_trap_inside_a_run_rewinds_the_batch() {
    let build = |a: &mut Arena| {
        // (merge (div 1 0) (mul 2 3)) -- the div traps at step 4 of 7
        let one = lit(a, 1);
        let zero = lit(a, 0);
        let bad = op(a, DIV, vec![one, zero]);
        let two = lit(a, 2);
        let three = lit(a, 3);
        let good = op(a, MUL, vec![two, three]);
        op(a, MERGE, vec![bad, good])
    };
    let out = same("div by zero in a run", &build, 100_000);
    assert!(out.starts_with("domain-error"), "{}", out);
    assert!(out.contains("steps 4"), "{}", out);
    same_everywhere("div by zero in a run", &build);
}

/// The budget is charged node by node too, and the trap lands on the
/// node that crossed.
#[test]
fn a_budget_crossing_inside_a_run() {
    let build = |a: &mut Arena| {
        // (budget 4 (merge 1 (merge 2 3)))
        let limit = lit(a, 4);
        let one = lit(a, 1);
        let two = lit(a, 2);
        let three = lit(a, 3);
        let inner = op(a, MERGE, vec![two, three]);
        let body = op(a, MERGE, vec![one, inner]);
        op(a, BUDGET, vec![limit, body])
    };
    let out = same("budget", &build, 100_000);
    assert!(out.starts_with("budget-exceeded"), "{}", out);
    for k in [1u64, 2, 3, 4, 5, 6, 7, 20] {
        same("budget", &build, k);
    }
}

// --- §6, the derived path ---------------------------------------------------

/// One entry per `let` in a chain: the reference keeps a frame for each
/// of them while the group's body runs.
#[test]
fn a_let_chain_is_one_entry_per_let() {
    let build = |a: &mut Arena| {
        // (let 0 1 (let 1 2 (let 2 3 (head (nil)))))
        let empty = op(a, NIL, vec![]);
        let bad = op(a, HEAD, vec![empty]);
        let wrap = |a: &mut Arena, name: i64, v: i64, body: u32| {
            let n = lit(a, name);
            let value = lit(a, v);
            op(a, LET, vec![n, value, body])
        };
        let l3 = wrap(a, 2, 3, bad);
        let l2 = wrap(a, 1, 2, l3);
        wrap(a, 0, 1, l2)
    };
    let out = same("let chain path", &build, 100_000);
    assert!(out.contains("path [46, 46, 46, 5]"), "{}", out);
}

/// A call contributes the `apply` that made it, and the callee's body
/// nodes; a tail call contributes nothing (its frame was replaced).
#[test]
fn a_call_contributes_its_apply() {
    let build = |a: &mut Arena| {
        // (let 0 (lambda 1 (merge 1 (apply (ref 0) (ref 1)))) (apply (ref 0) 0))
        let name = lit(a, 0);
        let param = lit(a, 1);
        let one = lit(a, 1);
        let f = lit(a, 0);
        let reff = op(a, REF, vec![f]);
        let x = lit(a, 1);
        let refx = op(a, REF, vec![x]);
        let inner = op(a, APPLY, vec![reff, refx]);
        let body = op(a, MERGE, vec![one, inner]);
        let lam = op(a, LAMBDA, vec![param, body]);
        let f2 = lit(a, 0);
        let head = op(a, REF, vec![f2]);
        let zero = lit(a, 0);
        let call = op(a, APPLY, vec![head, zero]);
        op(a, LET, vec![name, lam, call])
    };
    // Runaway recursion: the depth ceiling, with one MERGE/APPLY pair
    // per kept frame (spec §6.2).
    let mut a = Arena::new();
    let root = build(&mut a);
    let mut rt = Rt::new(1_000_000, 5, 0, "");
    rt.ordinals = std::rc::Rc::new(preorder_ordinals(&a, root));
    let tree = match rt::eval(&mut a, &mut rt, root, false) {
        Err(Fault::Trap(t)) => t.anomaly.position_path.clone(),
        other => panic!("expected a depth trap, got {:?}", other.is_ok()),
    };
    let mut a2 = Arena::new();
    let root2 = build(&mut a2);
    let mut rt2 = Rt::new(1_000_000, 5, 0, "");
    rt2.ordinals = std::rc::Rc::new(preorder_ordinals(&a2, root2));
    rt2.vm.on = true;
    let vm = match exec::run_program(&mut a2, &mut rt2, root2) {
        Err(Fault::Trap(t)) => t.anomaly.position_path.clone(),
        other => panic!("expected a depth trap, got {:?}", other.is_ok()),
    };
    assert_eq!(tree, vm);
    assert_eq!(tree.len(), 2 + 2 * 5, "LET, APPLY, then MERGE/APPLY per frame");
}

/// A tail call replaces its frame, so a tail recursion of a thousand
/// rounds shows a short path and no depth trap.
#[test]
fn a_tail_call_keeps_no_frame() {
    let build = |a: &mut Arena| {
        // (let 0 (lambda 1 (if (ref 1) (apply (ref 0) (sub (ref 1) 1)) (head (nil))))
        //      (apply (ref 0) 50))
        let name = lit(a, 0);
        let param = lit(a, 1);
        let t = lit(a, 1);
        let test = op(a, REF, vec![t]);
        let r = lit(a, 1);
        let refn = op(a, REF, vec![r]);
        let one = lit(a, 1);
        let less = sub(a, refn, one);
        let f = lit(a, 0);
        let reff = op(a, REF, vec![f]);
        let recurse = op(a, APPLY, vec![reff, less]);
        let empty = op(a, NIL, vec![]);
        let bad = op(a, HEAD, vec![empty]);
        let body = op(a, IF_SURPRISE, vec![test, recurse, bad]);
        let lam = op(a, LAMBDA, vec![param, body]);
        let f2 = lit(a, 0);
        let head = op(a, REF, vec![f2]);
        let fifty = lit(a, 50);
        let call = op(a, APPLY, vec![head, fifty]);
        op(a, LET, vec![name, lam, call])
    };
    let out = same("tail call path", &build, 100_000);
    // LET, APPLY (the call site), IF, HEAD -- one frame, not fifty.
    assert!(out.contains("path [46, 45, 42, 5]"), "{}", out);
}

/// A closure made inside a `let` region outlives it, and still reads
/// what that region bound: the region cannot be forgotten on the way
/// out.  The `conserve` is there to make the unit keep a walkable
/// environment, which is when the forgetting happens at all.
#[test]
fn a_closure_outlives_the_region_that_made_it() {
    let build = |a: &mut Arena| {
        // (seq (conserve 1 1) (let 0 (let 1 5 (lambda 2 (merge (ref 2) (ref 1))))
        //                          (apply (ref 0) 1)))
        let one = lit(a, 1);
        let two = lit(a, 1);
        let contract = op(a, CONSERVE, vec![one, two]);
        let g = lit(a, 1);
        let five = lit(a, 5);
        let param = lit(a, 2);
        let rx = lit(a, 2);
        let refx = op(a, REF, vec![rx]);
        let rg = lit(a, 1);
        let refg = op(a, REF, vec![rg]);
        let body = op(a, MERGE, vec![refx, refg]);
        let lam = op(a, LAMBDA, vec![param, body]);
        let inner = op(a, LET, vec![g, five, lam]);
        let f = lit(a, 0);
        let rf = lit(a, 0);
        let head = op(a, REF, vec![rf]);
        let arg = lit(a, 1);
        let call = op(a, APPLY, vec![head, arg]);
        let outer = op(a, LET, vec![f, inner, call]);
        op(a, SEQ, vec![contract, outer])
    };
    assert!(same("escaping closure", &build, 100_000).starts_with("value 6"));
    same_everywhere("escaping closure", &build);
}


/// `(ref n)`.
fn rf(a: &mut Arena, name: i64) -> u32 {
    let slot = lit(a, name);
    op(a, REF, vec![slot])
}

/// `(let name value body)`.
fn let_(a: &mut Arena, name: i64, value: u32, body: u32) -> u32 {
    let slot = lit(a, name);
    op(a, LET, vec![slot, value, body])
}

/// `(lambda param body)`.
fn lam(a: &mut Arena, param: i64, body: u32) -> u32 {
    let slot = lit(a, param);
    op(a, LAMBDA, vec![slot, body])
}

/// `(quote x)` -- the operand is not evaluated.
fn quoted(a: &mut Arena, inner: u32) -> u32 {
    op(a, QUOTE, vec![inner])
}

// --- F1: a region that closed, and a closure that kept it -------------------

/// The names of a closed region are gone for the code after it, even
/// when a closure holds the region's slots alive: a delegated subtree
/// (`conserve` here) must flatten the live bindings only.
#[test]
fn a_closed_region_is_invisible_by_name() {
    let build = |a: &mut Arena| {
        // (let 1 5 (seq (let 1 1 (lambda 2 (ref 1))) (conserve 10 (merge (ref 1) (ref 1)))))
        let one = lit(a, 1);
        let inner_ref = rf(a, 1);
        let closure = lam(a, 2, inner_ref);
        let shadow = let_(a, 1, one, closure);
        let x = rf(a, 1);
        let y = rf(a, 1);
        let sum = op(a, MERGE, vec![x, y]);
        let ten = lit(a, 10);
        let contract = op(a, CONSERVE, vec![ten, sum]);
        let body = op(a, SEQ, vec![shadow, contract]);
        let five = lit(a, 5);
        let_(a, 1, five, body)
    };
    // The outer binding is 5, so the body is 10 and the contract holds.
    assert!(same("closed region", &build, 100_000).starts_with("value 10"));
    same_everywhere("closed region", &build);
}

/// The other half: the closure made inside that region still reads it,
/// by name as well -- its own `eval` sees the binding it captured.
#[test]
fn a_closure_still_reads_the_region_it_captured() {
    let build = |a: &mut Arena| {
        // (let 1 5 (let 3 (let 1 1 (lambda 2 (eval (quote (ref 1))))) (apply (ref 3) 0)))
        let inner_ref = rf(a, 1);
        let program = quoted(a, inner_ref);
        let run = op(a, EVAL, vec![program]);
        let closure = lam(a, 2, run);
        let one = lit(a, 1);
        let shadow = let_(a, 1, one, closure);
        let head = rf(a, 3);
        let zero = lit(a, 0);
        let call = op(a, APPLY, vec![head, zero]);
        let body = let_(a, 3, shadow, call);
        let five = lit(a, 5);
        let_(a, 1, five, body)
    };
    assert!(same("captured region", &build, 100_000).starts_with("value 1 "));
    same_everywhere("captured region", &build);
}

/// With no outer binding at all, the same shape is an `unbound-ref`
/// rather than the closed region's value.
#[test]
fn a_closed_region_does_not_answer_a_later_eval() {
    let build = |a: &mut Arena| {
        // (seq (let 1 1 (lambda 2 (ref 1))) (eval (quote (ref 1))))
        let one = lit(a, 1);
        let inner_ref = rf(a, 1);
        let closure = lam(a, 2, inner_ref);
        let shadow = let_(a, 1, one, closure);
        let target = rf(a, 1);
        let program = quoted(a, target);
        let run = op(a, EVAL, vec![program]);
        op(a, SEQ, vec![shadow, run])
    };
    let out = same("closed region eval", &build, 100_000);
    assert!(out.starts_with("unbound-ref"), "{}", out);
    same_everywhere("closed region eval", &build);
}

// --- F2 / F3: what an unbound reference says --------------------------------

/// A letrec hole: the closure runs before its group finished writing,
/// and the fallback slot is unwritten too.  The anomaly is the
/// reference's -- the name that was asked for, and the names that are
/// written -- not a fabricated `unbound ref: 0`.
#[test]
fn an_unwritten_fallback_still_names_the_reference() {
    let build = |a: &mut Arena| {
        // (let 5 (let 4 (lambda 6 (merge (ref 6) (ref 5)))
        //          (let 5 (apply (ref 4) 1) 1)) (ref 5))
        let px = rf(a, 6);
        let g1 = rf(a, 5);
        let sum = op(a, MERGE, vec![px, g1]);
        let f = lam(a, 6, sum);
        let head = rf(a, 4);
        let one = lit(a, 1);
        let call = op(a, APPLY, vec![head, one]);
        let inner_one = lit(a, 1);
        let inner = let_(a, 5, call, inner_one);
        let value = let_(a, 4, f, inner);
        let outer_ref = rf(a, 5);
        let_(a, 5, value, outer_ref)
    };
    let out = same("letrec hole", &build, 100_000);
    assert!(out.starts_with("unbound-ref"), "{}", out);
    // The name asked for is `5`, and the names offered are the ones
    // that are written -- `4` and the parameter `6` -- never an empty
    // list under the name 0.
    assert!(out.contains("\"name_id\": Number(5)"), "{}", out);
    assert!(out.contains("Number(4), Number(6)"), "{}", out);
    assert!(!out.contains("Number(5)]"), "{}", out);
    same_everywhere("letrec hole", &build);
}

/// `bound_names` is what is written, not what the resolver can see: a
/// binder whose value is still being evaluated is not a binding.
#[test]
fn bound_names_are_the_written_ones() {
    let build = |a: &mut Arena| {
        // (let 4 (lambda 6 (merge (ref 6) (ref 7))) (let 7 (apply (ref 4) 1) (ref 7)))
        let px = rf(a, 6);
        let later = rf(a, 7);
        let sum = op(a, MERGE, vec![px, later]);
        let f = lam(a, 6, sum);
        let head = rf(a, 4);
        let one = lit(a, 1);
        let call = op(a, APPLY, vec![head, one]);
        let tail_ref = rf(a, 7);
        let inner = let_(a, 7, call, tail_ref);
        let_(a, 4, f, inner)
    };
    let out = same("pending binder", &build, 100_000);
    assert!(out.starts_with("unbound-ref"), "{}", out);
    assert!(out.contains("\"name_id\": Number(7)"), "{}", out);
    // `7` is the name that is missing: the resolver can see the binder
    // but nothing is written there, so it is not offered as bound.
    assert!(out.contains("Number(4), Number(6)"), "{}", out);
    assert!(!out.contains("Number(7),"), "{}", out);
    same_everywhere("pending binder", &build);
}

// --- F6: a fault is a fault, not a branch -----------------------------------

/// A test that is not an integer is the reference's type fault; it must
/// not be read as "take the else branch".
#[test]
fn a_test_that_is_not_an_integer_traps() {
    let build = |a: &mut Arena| {
        // (if (nil) 1 2)
        let test = op(a, NIL, vec![]);
        let then = lit(a, 1);
        let other = lit(a, 2);
        op(a, IF_SURPRISE, vec![test, then, other])
    };
    let out = same("non-integer test", &build, 100_000);
    assert!(out.starts_with("type-violation"), "{}", out);
    same_everywhere("non-integer test", &build);
}

// --- the shapes the review asked to be kept ---------------------------------

/// A `when-anomaly` that catches a trap raised inside a batched run,
/// and a program that goes on afterwards.
#[test]
fn a_catch_inside_a_batched_run_resumes() {
    let build = |a: &mut Arena| {
        // (merge 1 (when-anomaly (merge 2 (div 1 0)) (lambda 3 (merge (ref 3) 100))))
        let one = lit(a, 1);
        let zero = lit(a, 0);
        let bad = op(a, DIV, vec![one, zero]);
        let two = lit(a, 2);
        let body = op(a, MERGE, vec![two, bad]);
        let code = rf(a, 3);
        let hundred = lit(a, 100);
        let sum = op(a, MERGE, vec![code, hundred]);
        let handler = lam(a, 3, sum);
        let caught = op(a, WHEN_ANOMALY, vec![body, handler]);
        let outer = lit(a, 1);
        op(a, MERGE, vec![outer, caught])
    };
    assert!(same("catch in a run", &build, 100_000).starts_with("value 105"));
    same_everywhere("catch in a run", &build);
}

/// A tail call whose last argument traps: the callee is checked before
/// the argument is evaluated, and the trap is the argument's.
#[test]
fn a_tail_call_whose_last_argument_traps() {
    let build = |a: &mut Arena| {
        // (let 4 (lambda 5 (lambda 6 (merge (ref 5) (ref 6))))
        //   (let 7 (lambda 8 (apply (ref 4) (ref 8) (div 1 0)))
        //     (apply (ref 7) 1)))
        let x = rf(a, 5);
        let y = rf(a, 6);
        let sum = op(a, MERGE, vec![x, y]);
        let inner = lam(a, 6, sum);
        let f = lam(a, 5, inner);
        let head = rf(a, 4);
        let arg = rf(a, 8);
        let one = lit(a, 1);
        let zero = lit(a, 0);
        let bad = op(a, DIV, vec![one, zero]);
        let call = op(a, APPLY, vec![head, arg, bad]);
        let g = lam(a, 8, call);
        let ghead = rf(a, 7);
        let seed = lit(a, 1);
        let outer = op(a, APPLY, vec![ghead, seed]);
        let inner_let = let_(a, 7, g, outer);
        let_(a, 4, f, inner_let)
    };
    let out = same("tail argument traps", &build, 100_000);
    assert!(out.starts_with("domain-error"), "{}", out);
    same_everywhere("tail argument traps", &build);
}

/// `eval` of a quoted program that reads a name bound after the `eval`
/// site: the reference cannot see it, and neither may the VM.
#[test]
fn eval_cannot_see_a_name_bound_after_it() {
    let build = |a: &mut Arena| {
        // (let 4 (eval (quote (ref 5))) (let 5 2 (ref 4)))
        let target = rf(a, 5);
        let program = quoted(a, target);
        let run = op(a, EVAL, vec![program]);
        let two = lit(a, 2);
        let use_a = rf(a, 4);
        let inner = let_(a, 5, two, use_a);
        let_(a, 4, run, inner)
    };
    let out = same("eval before the binding", &build, 100_000);
    assert!(out.starts_with("unbound-ref"), "{}", out);
    same_everywhere("eval before the binding", &build);
}

/// Three frames deep, each reading the one above.
#[test]
fn a_three_deep_capture_chain() {
    let build = |a: &mut Arena| {
        // (apply (apply (apply (lambda 1 (lambda 2 (lambda 3
        //     (merge (ref 1) (merge (ref 2) (ref 3)))))) 1) 2) 3)
        let x = rf(a, 1);
        let y = rf(a, 2);
        let z = rf(a, 3);
        let inner_sum = op(a, MERGE, vec![y, z]);
        let sum = op(a, MERGE, vec![x, inner_sum]);
        let l3 = lam(a, 3, sum);
        let l2 = lam(a, 2, l3);
        let l1 = lam(a, 1, l2);
        let one = lit(a, 1);
        let two = lit(a, 2);
        let three = lit(a, 3);
        let c1 = op(a, APPLY, vec![l1, one]);
        let c2 = op(a, APPLY, vec![c1, two]);
        op(a, APPLY, vec![c2, three])
    };
    assert!(same("three deep", &build, 100_000).starts_with("value 6"));
    same_everywhere("three deep", &build);
}

/// A lambda inside a `quote`, inside a branch that is not taken, and
/// inside a list callback: none of them may fool the analysis that
/// decides which frames escape.
#[test]
fn lambdas_that_do_not_escape() {
    let build = |a: &mut Arena| {
        // (let 1 5 (seq (quote (lambda 2 (ref 1)))
        //               (seq (if 0 (lambda 2 (ref 1)) 0)
        //                    (seq (map (lambda 2 (merge (ref 2) (ref 1)))
        //                              (cons 1 (cons 2 (nil))))
        //                         (eval (quote (ref 1)))))))
        let qref = rf(a, 1);
        let qlam = lam(a, 2, qref);
        let quote_it = quoted(a, qlam);
        let bref = rf(a, 1);
        let blam = lam(a, 2, bref);
        let test = lit(a, 0);
        let zero = lit(a, 0);
        let branch = op(a, IF_SURPRISE, vec![test, blam, zero]);
        let p = rf(a, 2);
        let outer = rf(a, 1);
        let sum = op(a, MERGE, vec![p, outer]);
        let cb = lam(a, 2, sum);
        let empty = op(a, NIL, vec![]);
        let two = lit(a, 2);
        let c2 = op(a, CONS, vec![two, empty]);
        let one = lit(a, 1);
        let list = op(a, CONS, vec![one, c2]);
        let walked = op(a, LIST_MAP, vec![cb, list]);
        let target = rf(a, 1);
        let program = quoted(a, target);
        let run = op(a, EVAL, vec![program]);
        let s3 = op(a, SEQ, vec![walked, run]);
        let s2 = op(a, SEQ, vec![branch, s3]);
        let s1 = op(a, SEQ, vec![quote_it, s2]);
        let five = lit(a, 5);
        let_(a, 1, five, s1)
    };
    assert!(same("lambdas that stay", &build, 100_000).starts_with("value 5"));
    same_everywhere("lambdas that stay", &build);
}

// --- the operators ----------------------------------------------------------


/// A walk over the families the VM evaluates itself, at ceilings that
/// make roughly half of them trap.
#[test]
fn the_families_agree() {
    let cases: Vec<(&str, Box<dyn Fn(&mut Arena) -> u32>)> = vec![
        (
            "text",
            Box::new(|a: &mut Arena| {
                let t = a.push(node(LIT_TEXT, Vec::new(), None, Some(std::rc::Rc::new(
                    "hello world".to_string(),
                ))));
                let start = lit(a, 2);
                let end = lit(a, 7);
                let slice = op(a, TEXT_SLICE, vec![t, start, end]);
                op(a, TEXT_LEN, vec![slice])
            }),
        ),
        (
            "list",
            Box::new(|a: &mut Arena| {
                let zero = lit(a, 0);
                let ten = lit(a, 10);
                let range = op(a, LIST_RANGE, vec![zero, ten]);
                let param = lit(a, 1);
                let r = lit(a, 1);
                let refn = op(a, REF, vec![r]);
                let two = lit(a, 2);
                let double = op(a, MUL, vec![refn, two]);
                let lam = op(a, LAMBDA, vec![param, double]);
                op(a, LIST_MAP, vec![lam, range])
            }),
        ),
        (
            "map",
            Box::new(|a: &mut Arena| {
                let empty = op(a, NIL, vec![]);
                let k = lit(a, 7);
                let v = lit(a, 11);
                let put = op(a, MAP_PUT, vec![empty, k, v]);
                let k2 = lit(a, 7);
                let d = lit(a, 0);
                op(a, MAP_GET, vec![put, k2, d])
            }),
        ),
        (
            "map miss evaluates the default",
            Box::new(|a: &mut Arena| {
                let empty = op(a, NIL, vec![]);
                let k = lit(a, 1);
                let x = lit(a, 2);
                let y = lit(a, 3);
                let d = op(a, MERGE, vec![x, y]);
                op(a, MAP_GET, vec![empty, k, d])
            }),
        ),
        (
            "when-anomaly catches",
            Box::new(|a: &mut Arena| {
                let one = lit(a, 1);
                let zero = lit(a, 0);
                let bad = op(a, DIV, vec![one, zero]);
                let param = lit(a, 3);
                let r = lit(a, 3);
                let refc = op(a, REF, vec![r]);
                let hundred = lit(a, 100);
                let sum = op(a, MERGE, vec![refc, hundred]);
                let handler = op(a, LAMBDA, vec![param, sum]);
                op(a, WHEN_ANOMALY, vec![bad, handler])
            }),
        ),
        (
            "seq and stdout",
            Box::new(|a: &mut Arena| {
                let t = a.push(node(LIT_TEXT, Vec::new(), None, Some(std::rc::Rc::new(
                    "out\n".to_string(),
                ))));
                let write = op(a, STDOUT, vec![t]);
                let v = lit(a, 9);
                op(a, SEQ, vec![write, v])
            }),
        ),
        (
            "loop-until",
            Box::new(|a: &mut Arena| {
                // (apply (loop-until (lambda 1 (threshold (sub (ref 1) 5)))
                //                    (lambda 1 (merge (ref 1) 1))) 0)
                let p = lit(a, 1);
                let r = lit(a, 1);
                let refn = op(a, REF, vec![r]);
                let five = lit(a, 5);
                let d = sub(a, refn, five);
                let th = op(a, THRESHOLD, vec![d]);
                let pred = op(a, LAMBDA, vec![p, th]);
                let p2 = lit(a, 1);
                let r2 = lit(a, 1);
                let refn2 = op(a, REF, vec![r2]);
                let one = lit(a, 1);
                let inc = op(a, MERGE, vec![refn2, one]);
                let step = op(a, LAMBDA, vec![p2, inc]);
                let lf = op(a, LOOP_UNTIL, vec![pred, step]);
                let seed = lit(a, 0);
                op(a, APPLY, vec![lf, seed])
            }),
        ),
        (
            "a boundary the host did not grant",
            Box::new(|a: &mut Arena| {
                let mask = lit(a, 1);
                let t = a.push(node(LIT_TEXT, Vec::new(), None, Some(std::rc::Rc::new(
                    "x.txt".to_string(),
                ))));
                let read = op(a, FS_READ, vec![t]);
                op(a, EXTERNAL_BOUNDARY, vec![mask, read])
            }),
        ),
        (
            "sort-by",
            Box::new(|a: &mut Arena| {
                let cell = |a: &mut Arena, v: i64, rest: u32| {
                    let x = lit(a, v);
                    op(a, CONS, vec![x, rest])
                };
                let empty = op(a, NIL, vec![]);
                let c1 = cell(a, 2, empty);
                let c2 = cell(a, 5, c1);
                let c3 = cell(a, 1, c2);
                let c4 = cell(a, 4, c3);
                // (lambda 1 (lambda 2 (threshold (sub (ref 2) (ref 1)))))
                let p1 = lit(a, 1);
                let p2 = lit(a, 2);
                let r2 = lit(a, 2);
                let b = op(a, REF, vec![r2]);
                let r1 = lit(a, 1);
                let x = op(a, REF, vec![r1]);
                let d = sub(a, b, x);
                let th = op(a, THRESHOLD, vec![d]);
                let inner = op(a, LAMBDA, vec![p2, th]);
                let less = op(a, LAMBDA, vec![p1, inner]);
                op(a, LIST_SORT_BY, vec![less, c4])
            }),
        ),
    ];
    for (name, build) in cases {
        same_everywhere(name, build.as_ref());
    }
}
