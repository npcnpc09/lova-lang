"""A program carries its examples (M26).

    (def fact [n] (if n (mul n (fact (sub n 1))) 1))
    (example (fact 5) 120)
    (example (fact 0) 1)
    (fact {n})

An ``(example expr expected)`` form may stand wherever a `def` may.
It is not part of the program -- `hash`, `explain` and the run ignore
it -- it is what the program says about itself, and ``check`` runs it:
each example becomes the program with its own expression replaced by
``(conserve expected expr)``, built and evaluated like any run, so a
miss is the conservation anomaly the substrate already reports, with
the sub-expression at fault (`body_offender`) when the probe finds
one, and the example's own span.

Why text and not the tree: the examples must see the program's
definitions, and the compiler drops the definitions the expression
does not use -- so the check is run per example, from source, with
the example forms blanked to spaces (spans stay put) and the
expression swapped for the contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, evaluate
from core.surface import line_col, parse, parse_with_prelude


def examples_of(source: str, prelude: bool = True) -> List[Dict[str, Any]]:
    """The examples a source declares, with their spans."""
    tree = parse_with_prelude(source) if prelude else parse(source)
    return list(getattr(tree, "examples", []))


def check(source: str, *, prelude: bool = True, max_steps: Optional[int] = None,
          max_call_depth: Optional[int] = None, granted: int = 0) -> List[Dict[str, Any]]:
    """Run every example; one result per example, in source order."""
    from core.cli import build
    tree = parse_with_prelude(source) if prelude else parse(source)
    examples = list(getattr(tree, "examples", []))
    body_span = getattr(tree, "body_span", None)
    results: List[Dict[str, Any]] = []
    if not examples:
        return results
    if body_span is None:
        raise ValueError("check: the program's expression has no source span")
    # Blank every example form: same length, so every other span holds.
    blanked = list(source)
    for ex in examples:
        if ex["span"] is not None:
            a, b = ex["span"]
            blanked[a:b] = [" "] * (b - a)
    blanked_source = "".join(blanked)
    for index, ex in enumerate(examples):
        if ex["span"] is None:
            continue
        a, b = ex["span"]
        # `(example expr expected)` -> the two texts, by their spans.
        expr_span, expected_span = ex["expr"].span, ex["expected"].span
        expr_text = source[expr_span[0]:expr_span[1]]
        expected_text = source[expected_span[0]:expected_span[1]]
        contract = f"(conserve {expected_text} {expr_text})"
        program = blanked_source[:body_span[0]] + contract + blanked_source[body_span[1]:]
        result: Dict[str, Any] = {"index": index, "span": [a, b],
                                  "excerpt": source[a:b],
                                  "line": line_col(source, a)[0], "col": line_col(source, a)[1]}
        try:
            compiled, _ = build(program, prelude=prelude)
            kwargs: Dict[str, Any] = {"granted": granted}
            if max_steps is not None:
                kwargs["max_steps"] = max_steps
            if max_call_depth is not None:
                kwargs["max_call_depth"] = max_call_depth
            value = evaluate(compiled, Runtime(**kwargs))
        except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
            anomaly = getattr(exc, "anomaly", None) or {"kind": "error", "message": str(exc)}
            anomaly = dict(anomaly)
            anomaly.pop("_enriched", None)
            if anomaly.get("kind") == "conservation-violated":
                detail = anomaly.get("detail", {})
                result["expected"] = detail.get("entry")
                result["got"] = detail.get("exit")
            result.update(passed=False, anomaly=anomaly)
        else:
            result.update(passed=True, value=value)
        results.append(result)
    return results


def summary(results: List[Dict[str, Any]]) -> str:
    """One line per example, then the count."""
    lines = []
    for r in results:
        if r["passed"]:
            lines.append(f"  ok    {r['line']}:{r['col']}  {r['excerpt']}")
        else:
            a = r.get("anomaly", {})
            why = (f"expected {r['expected']}, got {r['got']}" if "expected" in r
                   else a.get("kind", "error"))
            lines.append(f"  FAIL  {r['line']}:{r['col']}  {r['excerpt']}  -- {why}")
            hint = a.get("body_offender")
            if hint:
                lines.append(f"        offender: {hint.get('op_name')} at depth {hint.get('depth')}, "
                             f"observed {hint.get('observed')}, needed {hint.get('needed')}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"  {passed}/{len(results)} examples pass")
    return chr(10).join(lines)
