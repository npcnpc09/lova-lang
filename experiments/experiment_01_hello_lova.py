"""Experiment 01 — Hello LOVA (Milestone 1 end-to-end demo).

Verifies four things end-to-end:

1. **Round-trip losslessness.**  A surface program compiles to integer
   bytes, decodes back to a tree, pretty-prints to a surface form, and
   the re-parsed tree is structurally identical to the original.
   (Axiom 1: text is a projection; the integer form is canonical.)

2. **Number-theoretic primitives execute correctly.**  Check that
   ``(p 12) = 77``, ``(tau 12) = 6``, ``(gcd 12 18) = 6``, etc.

3. **Conservation catches a budget overrun.**  A ``(budget k body)``
   form with ``k`` smaller than the body's operator count raises
   ``BudgetTrap`` with structured anomaly metadata.  (Axiom 4.)

4. **Surprise emits a structured trace.**  A ``(surprise predicted actual)``
   form returns ``|predicted - actual|`` AND appends a structured event
   to the runtime's surprise log.  (Axiom 7.)

This is the simplest experiment that exercises all four load-bearing
axioms in one run.  Success means the MVP substrate is real: we have a
language where programs are integers, text is a projection, budgets
are contracts, and surprise is observable.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, evaluate
from core.surface import parse, pretty
from core.tokens import decode, encode


# --- helpers -----------------------------------------------------------------

def _hr(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _round_trip(src: str) -> None:
    """Parse → encode → decode → pretty, asserting no semantic loss."""
    tree = parse(src)
    data = encode(tree)
    back_tree = decode(data)
    back_src = pretty(back_tree)
    reparsed = parse(back_src)
    assert reparsed == tree, (
        f"ROUND-TRIP MISMATCH:\n  in:   {src}\n  out:  {back_src}"
    )
    print(f"  {src:<44s}  ->  {len(data):3d} B  ->  {back_src}")


# --- tests -------------------------------------------------------------------

def test_round_trip() -> None:
    _hr("Test 1 -- round-trip losslessness (surface <-> integer sequence)")
    programs = [
        "(p 12)",
        "(tau 12)",
        "(sigma 12)",
        "(gcd 12 18)",
        "(merge (p 3) (tau 12))",
        "(seq (p 3) (p 4) (p 5))",
        "(let 1 12 (p (ref 1)))",
        "(budget 100 (p 12))",
        "(conserve 77 (p 12))",
        "(surprise 10 (p 12))",
        "(if-surprise (surprise 10 (p 12)) 999 0)",
    ]
    for src in programs:
        _round_trip(src)
    print("  OK -- round-trip lossless on all programs")


def test_number_theory() -> None:
    _hr("Test 2 -- number-theoretic primitives")
    cases = [
        ("(p 12)", 77, "12th partition number"),
        ("(tau 12)", 6, "divisor count of 12"),
        ("(sigma 12)", 28, "divisor sum of 12"),
        ("(gcd 12 18)", 6, "gcd of 12 and 18"),
        ("(mobius 30)", -1, "mu(30) -- 30 = 2*3*5, three primes -> -1"),
        ("(merge (p 3) (tau 12))", 9, "p(3)=3, tau(12)=6, merge = 9"),
        ("(seq (p 3) (p 4) (p 5))", 7, "sequential; last value = p(5) = 7"),
        ("(let 1 12 (p (ref 1)))", 77, "let-bind 12 as id 1, compute p"),
    ]
    for src, expected, note in cases:
        got = evaluate(parse(src))
        status = "OK" if got == expected else "FAIL"
        print(f"  {status} {src:<40s} = {got:<4d}  ({note})")
        assert got == expected, f"expected {expected}, got {got}"
    print("  OK -- all number-theoretic primitives return reference values")


def test_conservation_budget_trap() -> None:
    _hr("Test 3 -- conservation catches budget overrun (Delta trap)")

    # At Milestone 1 every node visit costs 1 unit.  `(merge (p 3) (tau 12))`
    # visits 5 nodes (merge, p, lit-3, tau, lit-12), so a budget of 3
    # overruns partway through.
    src_overrun = "(budget 3 (merge (p 3) (tau 12)))"
    print(f"  program: {src_overrun}")
    try:
        evaluate(parse(src_overrun))
    except BudgetTrap as t:
        print(f"  OK -- BudgetTrap raised: {t}")
        print(f"    anomaly metadata: {t.anomaly}")
    else:
        raise AssertionError("expected BudgetTrap but none raised")

    # And a happy-path run that stays under budget.
    src_ok = "(budget 100 (p 12))"
    out = evaluate(parse(src_ok))
    print(f"  program: {src_ok:<30s} = {out}  (within budget)")
    assert out == 77

    # Δ-trap: conserve declares expected=77, violate bumps it to 78.
    src_delta = "(conserve 77 (violate 77))"
    print(f"  program: {src_delta}")
    try:
        evaluate(parse(src_delta))
    except DeltaTrap as t:
        print(f"  OK -- DeltaTrap raised: {t}")
        print(f"    anomaly metadata: {t.anomaly}")
    else:
        raise AssertionError("expected DeltaTrap but none raised")

    print("  OK -- both traps surface structured anomaly metadata")


def test_surprise_trace() -> None:
    _hr("Test 4 -- surprise emits structured trace")

    rt = Runtime()
    # Predict 10, actual will be p(12)=77, deviation 67.
    deviation = evaluate(parse("(surprise 10 (p 12))"), rt)
    print(f"  (surprise 10 (p 12))  ->  deviation = {deviation}")
    assert deviation == 67
    assert len(rt.surprise.events) == 1
    event = rt.surprise.events[0]
    print(f"    event: predicted={event['predicted']}  "
          f"actual={event['actual']}  deviation={event['deviation']}")

    # A second surprise to show the log accumulates.
    evaluate(parse("(surprise 3 (p 3))"), rt)   # p(3)=3, deviation 0
    evaluate(parse("(surprise 100 (tau 12))"), rt)   # τ(12)=6, deviation 94
    print()
    print(rt.surprise.summary())

    assert len(rt.surprise.events) == 3
    print("  OK -- surprise trace accumulates ordered, structured events")


def demonstrate_integer_form() -> None:
    _hr("Demonstration -- a program IS an integer")

    src = "(merge (p 3) (tau 12))"
    tree = parse(src)
    data = encode(tree)

    # The canonical representation: a single integer.  (Axiom 1.)
    as_int = int.from_bytes(data, "big", signed=False)
    print(f"  surface form:     {src}")
    print(f"  byte sequence:    {data.hex(' ')}")
    print(f"  canonical integer: {as_int}")
    print(f"  byte count:       {len(data)}")
    print()
    print("  This integer IS the program.  The surface text is a Stage-1")
    print("  projection; the integer is the substrate's canonical form.")


def run() -> None:
    test_round_trip()
    test_number_theory()
    test_conservation_budget_trap()
    test_surprise_trace()
    demonstrate_integer_form()

    _hr("Experiment 01 -- ALL TESTS PASSED")
    print("  Milestone 1 substrate is operational.")
    print("  Next: Milestone 2 (type-directed generation constraints)")


if __name__ == "__main__":
    run()
