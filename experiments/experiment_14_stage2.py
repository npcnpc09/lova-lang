"""Experiment 14 -- The Stage-2 surface, built and measured (Q37).

Stage 2 has been on the roadmap since the first design document and has
never existed.  Every number quoted for it -- including the 3.2x vs
sympy-Python in the README -- came from a *projection*: Experiment 11
counted AST nodes and assumed a fine-tuned vocabulary would reach one
token per node.  Experiment 12 then showed that projection running in
the wrong direction on algorithmic programs (480 estimated tokens
against 471 actually measured for Stage 1), and Experiment 13 localised
61% of the density gap in s-expression syntax, which no change to the
token table can reach.

So the residual has one instrument and it had never been built.  This
experiment builds it (`core/surface2.py`) and measures it.

The design follows from a fact that was always true and never used:
**the integer encoding has no delimiters.**  ``core.tokens.decode``
recovers the tree from the byte stream alone, because arity is known
from the signature.  Stage 1's parentheses re-state something the
substrate already knows.  Stage 2 is therefore the same sequence the
encoder emits, one printable character per byte -- which makes it
stage-coherent by construction (Axiom 10) rather than a second syntax.

Four parts:

  1. **Losslessness.**  ``parse(render(t)) == t`` over every corpus and
     over 1000 generated programs, with evaluation compared as well.  A
     projection that loses information is not a projection.
  2. **Density on algorithmic tasks.**  The measurement Exp 12 and 13
     were pointing at.
  3. **Density on LOVABench v2**, against the same pure-Python and
     sympy-Python baselines Exp 11 used -- so the projection Exp 11 made
     can be checked against the thing itself.
  4. **Where the remaining tokens go**, since the answer determines
     whether anything is left to win.
"""

from __future__ import annotations

import collections
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core import surface2
from core.generator import constrained_random
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import LIT_INT, decode, encode
from corpus.tasks import TASKS as BENCH_TASKS

try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # noqa: BLE001
    ENC = None


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _ntok(text: str) -> int:
    return len(ENC.encode(text)) if ENC is not None else 0


def _bench_source(task) -> str:
    return re.sub(r"\{(\w+)\}", "7", task.template)


def _algorithmic():
    from experiments.experiment_12_abstraction import TASKS, _instantiate
    for task in TASKS:
        yield task, _instantiate(task, task.inputs[0])


def _apps():
    apps_dir = os.path.join(_ROOT, "apps")
    for name in sorted(os.listdir(apps_dir)):
        if not name.endswith(".lova"):
            continue
        with open(os.path.join(apps_dir, name), encoding="utf-8") as handle:
            text = handle.read()
        yield name, re.sub(r'\{(\w+)\}', '"ab"' if "{s}" in text else "7", text)


# --- part 1: losslessness ----------------------------------------------------

def part_1_losslessness() -> dict:
    _hr("1. Losslessness -- a projection that loses information is not one")

    checked = failed = 0
    value_checked = 0

    def check(tree, label: str) -> None:
        nonlocal checked, failed, value_checked
        for pack in (False, True):
            checked += 1
            try:
                text = surface2.render(tree, pack_refs=pack)
                back = surface2.parse(text)
                assert back == tree, f"{label}: tree changed"
                # The bytes must be identical too, not merely an equal tree.
                assert encode(back) == encode(tree), f"{label}: bytes changed"
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAIL {label} (pack={pack}): {exc}")

    for task in BENCH_TASKS:
        check(parse(_bench_source(task)), task.id)
    for task, src in _algorithmic():
        check(parse(src), task.id)
    for name, src in _apps():
        check(parse(src), name)

    # Generated programs reach shapes nobody writes by hand.
    for seed in range(1000):
        tree = decode(constrained_random(seed=seed, max_depth=6))
        check(tree, f"seed{seed}")

    # And the projection must not change what a program does.
    for task, src in _algorithmic():
        tree = parse(src)
        expected = evaluate(tree, Runtime())
        got = evaluate(surface2.parse(surface2.render(tree)), Runtime())
        assert got == expected, task.id
        value_checked += 1

    print(f"  round-trips checked:  {checked} "
          f"({len(BENCH_TASKS)} bench + 10 algorithmic + "
          f"{len(list(_apps()))} apps + 1000 generated, x2 for the digram)")
    print(f"  failures:             {failed}")
    print(f"  evaluated after the round-trip: {value_checked}/10 identical")
    return {"checked": checked, "failed": failed}


# --- density helpers ---------------------------------------------------------

def _measure(sources) -> dict:
    totals = collections.Counter()
    rows = []
    for label, src, python_variants in sources:
        tree = parse(src)
        s1 = _ntok(src)
        s2_plain = _ntok(surface2.render(tree, pack_refs=False))
        s2 = _ntok(surface2.render(tree))
        row = {"label": label, "s1": s1, "s2_plain": s2_plain, "s2": s2,
               "bytes": len(encode(tree))}
        row.update({name: _ntok(text) for name, text in python_variants.items()})
        rows.append(row)
        for key, value in row.items():
            if key != "label":
                totals[key] += value
    return {"rows": rows, "totals": totals}


# --- part 2: algorithmic tasks ----------------------------------------------

def part_2_algorithmic() -> dict:
    _hr("2. Density on algorithmic tasks (no built-in shortcut on either side)")
    if ENC is None:
        print("  tiktoken not installed -- skipping")
        return {}

    sources = [
        (task.id, src, {"python": task.py_src})
        for task, src in _algorithmic()
    ]
    result = _measure(sources)
    totals = result["totals"]

    print(f"  {'task':<24s} {'S1':>5s} {'S2':>5s} {'S2+ref':>7s} {'Py':>5s}")
    print("  " + "-" * 52)
    for row in result["rows"]:
        print(f"  {row['label']:<24s} {row['s1']:>5d} {row['s2_plain']:>5d} "
              f"{row['s2']:>7d} {row['python']:>5d}")
    print("  " + "-" * 52)
    print(f"  {'TOTAL':<24s} {totals['s1']:>5d} {totals['s2_plain']:>5d} "
          f"{totals['s2']:>7d} {totals['python']:>5d}")

    py = totals["python"]
    print()
    print(f"  {'surface':<40s} {'tokens':>8s} {'vs Python':>11s}")
    print("  " + "-" * 62)
    print(f"  {'Stage 1 (s-expressions)':<40s} {totals['s1']:>8d} "
          f"{py / totals['s1']:>10.2f}x")
    print(f"  {'Stage 1 + best possible table change':<40s} {409:>8d} "
          f"{py / 409:>10.2f}x   (Exp 13)")
    print(f"  {'Stage 2 (one char per byte)':<40s} {totals['s2_plain']:>8d} "
          f"{py / totals['s2_plain']:>10.2f}x")
    print(f"  {'Stage 2 + reference digram':<40s} {totals['s2']:>8d} "
          f"{py / totals['s2']:>10.2f}x")
    print()
    if totals["s2"] < py:
        print("  **LOVA is denser than Python on algorithmic code for the")
        print("    first time.**  Exp 12 measured 0.66x and Exp 13 showed the")
        print("    token table could not get past 0.76x; the surface did.")
    return result


# --- part 3: LOVABench, against Exp 11's projection --------------------------

def part_3_bench() -> dict:
    _hr("3. LOVABench v2 -- the projection Exp 11 made, against the thing")
    if ENC is None:
        print("  tiktoken not installed -- skipping")
        return {}

    from experiments.experiment_11_token_density import (
        PYTHON_PURE_ALL, SYMPY_SOLUTIONS_ALL, _stage2_tokens,
    )

    sources = []
    projected = 0
    for task in BENCH_TASKS:
        src = _bench_source(task)
        sources.append((task.id, src, {
            "pure": PYTHON_PURE_ALL[task.id].strip(),
            "sympy": SYMPY_SOLUTIONS_ALL[task.id].strip(),
        }))
        projected += _stage2_tokens(parse(src))

    result = _measure(sources)
    totals = result["totals"]

    print(f"  {'measure':<40s} {'tokens':>8s}")
    print("  " + "-" * 50)
    print(f"  {'Stage 1 (measured)':<40s} {totals['s1']:>8d}")
    print(f"  {'Stage 2 estimate (Exp 11 projection)':<40s} {projected:>8d}")
    print(f"  {'Stage 2 (measured, one char per byte)':<40s} "
          f"{totals['s2_plain']:>8d}")
    print(f"  {'Stage 2 (measured, + reference digram)':<40s} {totals['s2']:>8d}")
    print(f"  {'Python, pure':<40s} {totals['pure']:>8d}")
    print(f"  {'Python, sympy':<40s} {totals['sympy']:>8d}")
    print()
    print(f"  {'ratio':<40s} {'vs sympy':>10s} {'vs pure':>9s}")
    print("  " + "-" * 62)
    for name, count in (("Stage 1", totals["s1"]),
                        ("Stage 2 estimate (Exp 11)", projected),
                        ("Stage 2 measured", totals["s2"])):
        print(f"  {name:<40s} {totals['sympy'] / count:>9.2f}x "
              f"{totals['pure'] / count:>8.2f}x")

    print()
    error = (projected - totals["s2"]) / totals["s2"]
    print(f"  Exp 11 projected {projected} tokens where the built surface "
          f"needs {totals['s2']}:")
    print(f"  it overestimated the token count by {abs(error):.0%}, which "
          "means it *understated*")
    print("  Stage 2's density by that much.  Node count is a poor proxy in")
    print("  both directions -- Exp 12 found it erring the other way on")
    print("  algorithmic programs.")
    return {"totals": totals, "projected": projected}


# --- part 4: where the tokens go now -----------------------------------------

def part_4_residual(algorithmic: dict) -> None:
    _hr("4. Where the remaining tokens go")
    if ENC is None or not algorithmic:
        print("  tiktoken not installed -- skipping")
        return

    cat = collections.Counter()
    for _task, src in _algorithmic():
        for token in ENC.encode(surface2.render(parse(src))):
            piece = ENC.decode([token])
            stripped = piece.strip()
            if not stripped:
                cat["separators"] += 1
            elif stripped.lstrip("-").isdigit():
                cat["literals"] += 1
            elif all(ch in surface2.REF_SYMBOLS for ch in stripped):
                cat["references"] += 1
            else:
                cat["operators"] += 1
    total = sum(cat.values())
    print(f"  {'class':<16s} {'tokens':>7s} {'share':>7s}")
    print("  " + "-" * 34)
    for name, count in cat.most_common():
        print(f"  {name:<16s} {count:>7d} {count / total:>6.0%}")
    print("  " + "-" * 34)
    print(f"  {'TOTAL':<16s} {total:>7d}")
    print()
    print("  Parentheses are gone entirely -- they were 25% of Stage 1.")
    print("  What is left is the program: an operator per node and a")
    print("  literal per constant.  Further compression means naming more")
    print("  frequent subtrees, which fits the surface to the corpus that")
    print("  motivated it (Q46), or a fine-tuned vocabulary, which is M8.")


# --- main --------------------------------------------------------------------

def run() -> None:
    print("LOVA Experiment 14 -- the Stage-2 surface, built and measured")
    lossless = part_1_losslessness()
    algorithmic = part_2_algorithmic()
    bench = part_3_bench()
    part_4_residual(algorithmic)

    _hr("Experiment 14 -- summary")
    print(f"  losslessness:   {lossless['checked'] - lossless['failed']}"
          f"/{lossless['checked']} round-trips exact")
    if algorithmic:
        totals = algorithmic["totals"]
        py = totals["python"]
        print(f"  algorithmic:    Stage 1 {py / totals['s1']:.2f}x -> "
              f"Stage 2 {py / totals['s2']:.2f}x vs Python "
              f"({totals['s1']} -> {totals['s2']} tokens)")
    if bench:
        totals = bench["totals"]
        print(f"  LOVABench v2:   Stage 2 measured "
              f"{totals['sympy'] / totals['s2']:.2f}x vs sympy, "
              f"{totals['pure'] / totals['s2']:.2f}x vs pure Python")
        print(f"                  (Exp 11 projected "
              f"{totals['sympy'] / bench['projected']:.2f}x / "
              f"{totals['pure'] / bench['projected']:.2f}x)")


if __name__ == "__main__":
    run()
