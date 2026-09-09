"""Experiment 08 -- Compiler passes (static checks + constant folding).

Three things to demonstrate:

  1. **Scope errors move from runtime to compile-time.**  An unbound
     `(ref 99)` previously caused `ValueError: unbound ref: 99` at
     runtime; now `compile()` raises `CompileError[unbound-ref]` with
     structured anomaly BEFORE execution.  One more error class moves
     out of the AI's runtime surface.

  2. **Constant folding compresses programs.**  Pure subtrees with
     literal arguments evaluate at compile time.  Measured:
     LOVABench v1 tasks, bytes before vs after compile.

  3. **Compile errors share L2 anomaly shape.**  `CompileError.anomaly`
     has the same `kind / position_path / offending_op /
     valid_alternatives / repair_hint` fields as `BudgetTrap` /
     `DeltaTrap`, so a single AI handler processes both.

Together: **the error surface shrinks further**.  After M5 LOVA's
error classes were {conservation, unbound-ref, semantic}; after M6
they become {conservation, semantic, compile-{unbound-ref,
type-mismatch}}.  The new compile-* classes fire at a known phase
(before any execution), making them trivially catchable.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.compiler import CompileError, compile
from core.runtime import evaluate
from core.surface import parse, pretty
from core.tokens import decode, encode
from corpus.tasks import TASKS


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


# --- demo 1: compile-time scope detection ---------------------------------

def demo_scope_detection() -> None:
    _hr("Demo 1 -- compile-time unbound-ref detection")

    # This program was accepted by parse / type-check but fails at runtime.
    src = "(merge (p 12) (ref 99))"
    print(f"  program: {src}")

    # Before M6: runtime error.
    print("\n  Before M6 (runtime):")
    try:
        evaluate(parse(src))
    except ValueError as e:
        print(f"    ValueError at runtime: {e}")

    # After M6: compile-time error, structured.
    print("\n  After M6 (compile-time):")
    try:
        compile(parse(src))
    except CompileError as e:
        print(f"    CompileError caught BEFORE execution.")
        print(f"    anomaly:")
        for k, v in e.anomaly.items():
            print(f"      {k:<22s}  {v!r}")


# --- demo 2: constant folding compresses LOVABench --------------------

def demo_constant_folding() -> None:
    _hr("Demo 2 -- constant folding on LOVABench v1 (20 tasks)")

    # For each task, substitute the first test case and compile.
    # Measure: original node count, compiled node count, byte size delta.
    print(f"\n  {'task':>5s}  {'original':>10s}  {'compiled':>9s}  "
          f"{'orig B':>7s}  {'fold B':>7s}  {'saved':>5s}")
    total_orig_n = total_comp_n = 0
    total_orig_b = total_comp_b = 0
    for task in TASKS:
        inputs = task.tests[0][0]
        src = task.template.format(**inputs)
        tree = parse(src)
        try:
            compiled, report = compile(tree)
        except CompileError:
            # shouldn't happen on LOVABench v1 (all reference templates
            # are scope-valid)
            continue
        orig_b = len(encode(tree))
        comp_b = len(encode(compiled))
        total_orig_n += report.original_nodes
        total_comp_n += report.compiled_nodes
        total_orig_b += orig_b
        total_comp_b += comp_b
        saved = (1 - comp_b / max(orig_b, 1)) * 100
        print(f"  {task.id:>5s}  {report.original_nodes:>10d}  "
              f"{report.compiled_nodes:>9d}  {orig_b:>7d}  "
              f"{comp_b:>7d}  {saved:>4.0f}%")
    total_saved = (1 - total_comp_b / max(total_orig_b, 1)) * 100
    print()
    print(f"  total nodes:   {total_orig_n} -> {total_comp_n}  "
          f"(compression {1 - total_comp_n / max(total_orig_n, 1):.1%})")
    print(f"  total bytes:   {total_orig_b} -> {total_comp_b}  "
          f"(saved {total_saved:.1f}%)")


# --- demo 3: errors share L2 anomaly shape ------------------------------

def demo_error_shape_unification() -> None:
    _hr("Demo 3 -- compile errors and runtime traps share L2 anomaly shape")

    common_fields = ("kind", "detail", "position_path", "offending_op",
                      "valid_alternatives", "repair_hint")

    # Trigger a CompileError
    try:
        compile(parse("(ref 42)"))
    except CompileError as ce:
        ce_keys = set(ce.anomaly.keys())

    # Trigger a runtime BudgetTrap
    from core.conservation import BudgetTrap
    try:
        evaluate(parse("(budget 1 (merge (p 3) (tau 12)))"))
    except BudgetTrap as bt:
        bt_keys = set(bt.anomaly.keys())

    # Trigger a runtime DeltaTrap
    from core.conservation import DeltaTrap
    try:
        evaluate(parse("(conserve 77 (violate 77))"))
    except DeltaTrap as dt:
        dt_keys = set(dt.anomaly.keys())

    print()
    print(f"  L2 anomaly fields expected: {common_fields}")
    print()
    print(f"  CompileError keys:  {sorted(ce_keys)}")
    print(f"  BudgetTrap keys:    {sorted(bt_keys)}")
    print(f"  DeltaTrap keys:     {sorted(dt_keys)}")

    # Intersection (fields all three share)
    intersection = ce_keys & bt_keys & dt_keys
    print()
    print(f"  shared by all 3:    {sorted(intersection)}")
    # Ensure the L2 spec fields all appear
    for f in common_fields:
        assert f in intersection, f"expected `{f}` in all three anomalies"
    print(f"  OK -- all L2 spec fields present in compile + runtime errors.")
    print(f"  AI handler can switch on `stage` (compile/runtime) and")
    print(f"  `kind`; everything else is uniform.")


# --- main ----------------------------------------------------------------

def run() -> None:
    print("LOVA M6 Day 1 -- compiler passes (scope-check + fold)")
    demo_scope_detection()
    demo_constant_folding()
    demo_error_shape_unification()
    _hr("Experiment 08 -- complete")
    print("  Compile pipeline catches scope errors before execution,")
    print("  folds pure subtrees to literals, shares L2 error shape with")
    print("  runtime traps.  Error surface after M6:")
    print("    compile:  { unbound-ref, type-mismatch }")
    print("    runtime:  { budget-exceeded, conservation-violated, semantic }")
    print("  All error classes are machine-actionable (anomaly schema).")


if __name__ == "__main__":
    run()
