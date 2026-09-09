"""Experiment 16 -- Scope-aware generation: Axiom 3 at the name level.

Axiom 3 says the set of well-typed next tokens is computable at every
position, so ill-typed programs are not representable.  From M2 to M15
that held at the *operator* level only.  A name id lives in a LIT_INT
payload the generation state machine never inspected, so it could not
know which names were bound; `ref` was offered everywhere on the chance
that one was, and an unbound reference was a compile-time error rather
than an unrepresentable one (Exp 08; Exp 12, F4).  Exp 13 then found the
depth-biased sampler filling `Fn` slots with references -- most of them
to nothing (Q54).

M16 passes payloads to `step`.  The machine keeps scope: a LET or
LAMBDA opens a frame, its binder names it, the binding's first token
types it, and the frame closes when the form's subtree completes.
`ref` is offered only where a bound, type-compatible name exists.

This experiment measures what that changed, by generating the same
programs both ways -- `track_scope=False` is the pre-M16 machine --
and running each through the compiler's scope pass and the runtime:

  1. How many generated programs contained an unbound reference.
  2. How many compiled at all.
  3. How many ran without a trap.
  4. What now fills an `Fn` slot.

And one boundary the machine cannot cross: mutual recursion.  A
left-to-right generator cannot emit a reference to a name bound later,
so `validates` now rejects the mutually recursive `def` chains the
compiler (M12) accepts.  That gap is measured too, so it is a number
and not a surprise.
"""

from __future__ import annotations

import collections
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.compiler import CompileError, compile as lova_compile
from core.conservation import BudgetTrap, DeltaTrap, DomainTrap, StepTrap
from core.generator import GenState, constrained_random, validates
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import APPLY, LAMBDA, LIT_INT, LOOP_UNTIL, REF, decode, encode

N = 1000


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _count(node, op) -> int:
    if node.op == LIT_INT:
        return 0
    return (node.op == op) + sum(_count(c, op) for c in node.args)


def _classify(tree) -> str:
    """unbound / compile-error / trap / ok."""
    try:
        compiled, _ = lova_compile(tree)
    except CompileError as exc:
        return "unbound" if exc.anomaly["kind"] == "unbound-ref" else "compile-error"
    try:
        evaluate(compiled, Runtime(max_steps=20_000, max_call_depth=50))
    except StepTrap:
        return "trap"
    except (BudgetTrap, DeltaTrap, DomainTrap):
        return "trap"
    return "ok"


def measure(track_scope: bool) -> dict:
    outcomes = collections.Counter()
    refs = fn_slot_refs = fn_slot_lambdas = 0
    for seed in range(N):
        tree = decode(constrained_random(seed=seed, max_depth=6,
                                         track_scope=track_scope))
        outcomes[_classify(tree)] += 1
        refs += _count(tree, REF)
        # What fills the head of an apply?
        stack = [tree]
        while stack:
            node = stack.pop()
            if node.op == LIT_INT:
                continue
            if node.op == APPLY and node.args:
                head = node.args[0]
                fn_slot_refs += head.op == REF
                fn_slot_lambdas += head.op in (LAMBDA, LOOP_UNTIL)
            stack.extend(node.args)
    return {"outcomes": outcomes, "refs": refs,
            "fn_refs": fn_slot_refs, "fn_lambdas": fn_slot_lambdas}


def part_1_before_after() -> dict:
    _hr(f"1. {N} generated programs, with and without scope tracking")
    before = measure(track_scope=False)
    after = measure(track_scope=True)
    rows = [("unbound reference (compile error)", "unbound"),
            ("other compile error", "compile-error"),
            ("compiles, traps at run time", "trap"),
            ("compiles and runs", "ok")]
    print(f"  {'outcome':<36s} {'pre-M16':>9s} {'M16':>9s}")
    print("  " + "-" * 58)
    for label, key in rows:
        b, a = before["outcomes"][key], after["outcomes"][key]
        print(f"  {label:<36s} {b:>5d} {b / N:>3.0%} {a:>5d} {a / N:>3.0%}")
    print("  " + "-" * 58)
    print(f"  {'references emitted':<36s} {before['refs']:>9d} {after['refs']:>9d}")
    print()
    print("  An unbound reference is now unrepresentable by generation, as")
    print("  Axiom 3 always said ill-typed programs were.  The compiler's")
    print("  scope pass still exists, for trees that did not come from the")
    print("  generator: hand-written, mutated, or read back from text.")
    return {"before": before, "after": after}


def part_2_fn_slots(results: dict) -> None:
    _hr("2. What fills an `Fn` slot (Q54)")
    b, a = results["before"], results["after"]
    print(f"  {'apply head is':<28s} {'pre-M16':>9s} {'M16':>9s}")
    print("  " + "-" * 50)
    print(f"  {'a reference':<28s} {b['fn_refs']:>9d} {a['fn_refs']:>9d}")
    print(f"  {'a lambda / loop-until':<28s} {b['fn_lambdas']:>9d} {a['fn_lambdas']:>9d}")
    print()
    print("  Before, a reference in an Fn slot named whatever the sampler")
    print("  drew -- almost never a bound function.  After, it names a bound")
    print("  function or is not offered, so the depth bias reaches for")
    print("  `lambda` instead and the program closes.")


def part_3_boundary() -> None:
    _hr("3. The boundary: what the compiler accepts that generation cannot reach")
    cases = [
        ("self recursion",
         "(defn f [n] (if n (f (sub n 1)) 0))(f 3)"),
        ("nested lets, later sees earlier",
         "(let 0 1 (let 1 (merge (ref 0) 1) (ref 1)))"),
        ("shadowing",
         "(let 0 1 (let 0 2 (ref 0)))"),
        ("mutual recursion (M12 chain)",
         "(def ev [n] (if n (od (sub n 1)) 1))(def od [n] (if n (ev (sub n 1)) 0))(ev 4)"),
    ]
    print(f"  {'program shape':<36s} {'compiles':>9s} {'validates':>10s}")
    print("  " + "-" * 60)
    gap = 0
    for label, src in cases:
        tree = parse(src)
        try:
            lova_compile(tree)
            compiles = True
        except CompileError:
            compiles = False
        valid = validates(encode(tree))
        gap += compiles and not valid
        print(f"  {label:<36s} {str(compiles):>9s} {str(valid):>10s}")
    print()
    print("  A left-to-right machine cannot emit a reference to a name bound")
    print("  later, so a mutually recursive def chain -- legal since M12 --")
    print("  is compilable but not generatable.  The generator is strictly")
    print("  more conservative than the compiler, which is the safe direction;")
    print(f"  the gap is {gap} shape(s) in this set, and it is Q64.")


def run() -> None:
    print("LOVA Experiment 16 -- scope-aware generation (M16)")
    results = part_1_before_after()
    part_2_fn_slots(results)
    part_3_boundary()

    _hr("Experiment 16 -- summary")
    b, a = results["before"]["outcomes"], results["after"]["outcomes"]
    print(f"  unbound references in generated programs: "
          f"{b['unbound']}/{N} -> {a['unbound']}/{N}")
    print(f"  programs that compile and run:            "
          f"{b['ok']}/{N} -> {a['ok']}/{N}")
    print("  Axiom 3 now holds at the name level for generated programs;")
    print("  the compiler's scope pass remains the check for everything else.")


if __name__ == "__main__":
    run()
