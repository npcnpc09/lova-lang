"""Experiment 09 -- Body-scanning DeltaTrap (Q20, M6 Day 2).

Before Q20: when a ``(conserve E B)`` fires a Δ-trap, ``offending_op``
named the outer ``CONSERVE`` operator — telling the AI that conservation
was violated without saying *where inside B* the deviation was
introduced.  Consumers had to re-scan the body themselves.

After Q20: the anomaly carries an additional ``body_offender`` dict —
``{op, op_name, path, depth, observed, needed, correction}`` — pointing
at the deepest sub-expression whose single-node replacement restores
the invariant.  The repair_hint now names that exact operator and its
needed correction.

Three demonstrations:

  1. **Canonical shapes.**  Five hand-picked Δ-trap cases spanning
     flat / nested / multi-violate structures.  For each we show the
     old signal (outer op) vs the new body_offender (precise subtree).

  2. **Fuzz precision.**  50 random ``(conserve N (merge ... (violate
     X) ...))`` programs where exactly one VIOLATE is the structural
     culprit.  Measure: does the scanner identify that VIOLATE node in
     every case?

  3. **Closed-loop repair.**  Take an anomaly, apply the scanner's
     suggested correction (replace the offender's value with
     ``needed``), re-evaluate.  Confirm conservation now holds.  This
     is the full AI-preference loop: trap -> anomaly -> patch -> pass.
"""

from __future__ import annotations

import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.conservation import DeltaTrap
from core.runtime import _clone_with_replacement, evaluate
from core.surface import parse
from core.tokens import LIT_INT, Node, SIGNATURES, VIOLATE


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


# --- demo 1: canonical shapes ------------------------------------------------

CANONICAL = [
    ("(conserve 77 (violate 77))",
     "flat: VIOLATE at body root"),
    ("(conserve 10 (merge 7 4))",
     "no VIOLATE: MERGE result off-by-one"),
    ("(conserve 10 (merge (violate 3) 4))",
     "nested: VIOLATE inside MERGE left arg"),
    ("(conserve 5 (violate (violate 2)))",
     "chain: two VIOLATEs, deepest picked"),
    ("(conserve 10 7)",
     "degenerate: body is a bare literal"),
]


def demo_canonical_shapes() -> None:
    _hr("Demo 1 -- canonical Δ-trap shapes: old outer-op vs new body_offender")
    print()
    print(f"  {'program':<42s}  {'dev':>4s}  {'offender':<32s}  {'correction':>10s}")
    print(f"  {'-'*42}  {'-'*4}  {'-'*32}  {'-'*10}")
    for src, note in CANONICAL:
        try:
            evaluate(parse(src))
            print(f"  {src:<42s}  no trap")
            continue
        except DeltaTrap as t:
            a = t.anomaly
            dev = a["detail"]["deviation"]
            bo = a["body_offender"]
            if bo is None:
                offender = "(scan found no single-node fix)"
                corr = "-"
            else:
                offender = f"{bo['op_name']} @ path={bo['path']} d={bo['depth']}"
                corr = f"{bo['correction']:+d}"
            print(f"  {src:<42s}  {dev:>+4d}  {offender:<32s}  {corr:>10s}")
    print()
    print(f"  Old signal in all five: offending_op == CONSERVE (the trap-raising")
    print(f"  frame -- uniform across every case, hence uninformative).")
    print(f"  New signal: specific sub-expression + correction value.")


# --- demo 2: fuzz precision --------------------------------------------------

def _random_violate_conserve(rng: random.Random) -> str:
    """Generate a (conserve E body) where body contains exactly one VIOLATE
    at a random structural position and everything else is pure MERGE of
    literals.  Returns the source; caller knows the invariant will be
    violated by exactly +1 (VIOLATE's contribution)."""
    # Pick two literals a, b, plus which side the VIOLATE wraps.
    a = rng.randint(1, 20)
    b = rng.randint(1, 20)
    side = rng.choice(("left", "right", "root"))
    if side == "root":
        # body = (violate (merge a b))
        body = f"(violate (merge {a} {b}))"
        expected = a + b  # body actually returns a+b+1
    elif side == "left":
        body = f"(merge (violate {a}) {b})"
        expected = a + b
    else:
        body = f"(merge {a} (violate {b}))"
        expected = a + b
    return f"(conserve {expected} {body})", side


def demo_fuzz_precision(n: int = 50, seed: int = 42) -> None:
    _hr(f"Demo 2 -- fuzz precision: {n} random single-VIOLATE programs")

    rng = random.Random(seed)
    hits = 0
    misses = []
    for i in range(n):
        src, expected_side = _random_violate_conserve(rng)
        try:
            evaluate(parse(src))
            misses.append((src, "no trap (unexpected)"))
            continue
        except DeltaTrap as t:
            bo = t.anomaly["body_offender"]
            if bo is None:
                misses.append((src, "scan returned None"))
                continue
            if bo["op"] == VIOLATE:
                hits += 1
            else:
                misses.append((src, f"wrong op: {bo['op_name']}"))

    print()
    print(f"  seed={seed}, N={n}")
    print(f"  scanner correctly pinpoints VIOLATE:  {hits}/{n}  ({hits/n:.0%})")
    if misses:
        print(f"  misses ({len(misses)}):")
        for src, reason in misses[:5]:
            print(f"    - {src}   -- {reason}")
        if len(misses) > 5:
            print(f"    ... (+{len(misses)-5} more)")


# --- demo 3: closed-loop repair ----------------------------------------------

def demo_closed_loop_repair() -> None:
    _hr("Demo 3 -- closed-loop repair using body_offender.needed")
    print()
    print("  Loop: eval -> DeltaTrap -> anomaly -> apply suggested patch -> eval -> pass")
    for src, note in CANONICAL:
        print(f"\n  program: {src}")
        tree = parse(src)
        body = tree.args[1]  # CONSERVE's args[1] is the body
        try:
            evaluate(tree)
            print(f"    no trap (skip)")
            continue
        except DeltaTrap as t:
            bo = t.anomaly["body_offender"]
            if bo is None:
                print(f"    no body_offender -- cannot auto-patch")
                continue
            # Patch: replace offender subtree with LIT_INT(needed)
            patched_body = _clone_with_replacement(
                body, bo["path"], Node(op=LIT_INT, args=[bo["needed"]])
            )
            patched_tree = Node(op=tree.op, args=[tree.args[0], patched_body])
            try:
                result = evaluate(patched_tree)
                print(f"    patched offender `{bo['op_name']}` @ path {bo['path']}: "
                      f"{bo['observed']} -> {bo['needed']}")
                print(f"    patched program evaluates to {result} (conservation holds)")
            except DeltaTrap as t2:
                print(f"    STILL TRAPPING after patch: {t2.anomaly['detail']}")


# --- main --------------------------------------------------------------------

def run() -> None:
    print("LOVA M6 Day 2 -- body-scanning DeltaTrap (Q20)")
    demo_canonical_shapes()
    demo_fuzz_precision()
    demo_closed_loop_repair()
    _hr("Experiment 09 -- complete")
    print("  Δ-traps now ship with a body_offender field pointing at the")
    print("  deepest sub-expression whose single-node replacement closes")
    print("  the deviation.  The outer CONSERVE frame is still recorded in")
    print("  offending_op (for back-compat); body_offender is the signal")
    print("  an AI repair loop actually uses.")


if __name__ == "__main__":
    run()
