"""A program carries its examples (M26; any value, and a located fault,
since the audit of 2026-09-18).

    (def fact [n] (if n (mul n (fact (sub n 1))) 1))
    (example (fact 5) 120)
    (example (digits 120) (list 1 2 0))
    (fact {n})

An ``(example expr expected)`` form may stand wherever a `def` may.
It is not part of the program -- `hash`, `explain` and the run ignore
it -- it is what the program says about itself, and ``check`` runs it:
each example becomes the program with its own expression in place of
the body, built and evaluated like any run, and what it produced is
compared with what the example states, which may be a number, a text,
a list or a record.  A miss reports expected and got, the example's
own span, and -- new -- where in the program's own defs a single edit
makes the example pass (`core/locate.py`): the span, the text there,
the edit in words, and the replacement text where there is one.

Why text and not the tree: the examples must see the program's
definitions, and the compiler drops the definitions the expression
does not use -- so the check is run per example, from source, with
the example forms blanked to spaces (spans stay put) and the
expression swapped in.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, evaluate
from core.surface import expand_uses, line_col, parse, parse_with_prelude, prelude_names


def examples_of(source: str, prelude: bool = True) -> List[Dict[str, Any]]:
    """The examples a source declares, with their spans."""
    tree = parse_with_prelude(source) if prelude else parse(source)
    return list(getattr(tree, "examples", []))


def same(a: Any, b: Any) -> bool:
    """Structural equality of two LOVA values, as the report prints them."""
    from core.cli import format_value
    if a.__class__ is int and b.__class__ is int:
        return a == b
    return format_value(a) == format_value(b)


def _shown(value: Any) -> Any:
    """A number as itself, anything else as the report prints it."""
    if value.__class__ is int:
        return value
    from core.cli import format_value
    return format_value(value)


def check(source: str, *, prelude: bool = True, max_steps: Optional[int] = None,
          max_call_depth: Optional[int] = None, granted: int = 0,
          locate_budget_s: float = 2.0) -> List[Dict[str, Any]]:
    """Run every example; one result per example, in source order."""
    from core.cli import build, format_value
    # A `(use "name")` is textual inclusion, and the spans the parser
    # records are offsets into the included text -- so a library's own
    # examples run too, once the source is what the parser saw.
    source = expand_uses(source)
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

    def with_body(text: str) -> str:
        return blanked_source[:body_span[0]] + text + blanked_source[body_span[1]:]

    kwargs: Dict[str, Any] = {"granted": granted}
    if max_steps is not None:
        kwargs["max_steps"] = max_steps
    if max_call_depth is not None:
        kwargs["max_call_depth"] = max_call_depth

    wants: Dict[int, Any] = {}
    exprs: Dict[int, str] = {}
    expr_spans: Dict[int, Any] = {}
    for index, ex in enumerate(examples):
        if ex["span"] is None:
            continue
        a, b = ex["span"]
        # `(example expr expected)` -> the two texts, by their spans.
        expr_span, expected_span = ex["expr"].span, ex["expected"].span
        expr_text = source[expr_span[0]:expr_span[1]]
        expected_text = source[expected_span[0]:expected_span[1]]
        exprs[index] = expr_text
        expr_spans[index] = expr_span
        result: Dict[str, Any] = {"index": index, "span": [a, b],
                                  "excerpt": source[a:b],
                                  "line": line_col(source, a)[0], "col": line_col(source, a)[1]}
        try:
            compiled, _ = build(with_body(expected_text), prelude=prelude)
            want = evaluate(compiled, Runtime(**kwargs))
        except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
            anomaly = getattr(exc, "anomaly", None) or {"kind": "error", "message": str(exc)}
            result.update(passed=False, anomaly=dict(anomaly),
                          note="what the example states does not evaluate")
            results.append(result)
            continue
        wants[index] = want
        try:
            compiled, _ = build(with_body(expr_text), prelude=prelude)
            rt = Runtime(**kwargs)
            got = evaluate(compiled, rt)
        except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
            anomaly = getattr(exc, "anomaly", None) or {"kind": "error", "message": str(exc)}
            anomaly = dict(anomaly)
            anomaly.pop("_enriched", None)
            result.update(passed=False, anomaly=anomaly, expected=_shown(want))
        else:
            if same(got, want):
                result.update(passed=True, value=got)
            else:
                # A miss is an anomaly like any other: the same kind the
                # conservation contract raised when an example was one.
                result.update(passed=False, expected=_shown(want), got=_shown(got),
                              steps=rt.steps,
                              anomaly={"kind": "conservation-violated",
                                       "detail": {"entry": _shown(want), "exit": _shown(got)},
                                       "span": [a, b]})
        results.append(result)

    failed = [r for r in results if not r["passed"] and "got" in r]
    if failed and locate_budget_s > 0:
        _locate_all(results, failed, exprs, wants, source, with_body, prelude, kwargs, locate_budget_s,
                    body_span[0], expr_spans)
    return results


def _locate_all(results, failed, exprs, wants, source, with_body, prelude, kwargs, budget_s,
                body_start, expr_spans) -> None:
    """One combined run holds every def any example uses; probe in it."""
    from core.cli import build
    from core.locate import example_expression, locate, user_closures
    from core.runtime import Cons, NIL_VALUE
    order = [i for i in sorted(exprs) if i in wants]
    listed = "(list " + " ".join(exprs[i] for i in order) + ")"
    combined = with_body(listed)
    # Where each example's expression begins in the combined text, so a
    # fault found in it can be reported in the example's own text.
    starts: Dict[int, int] = {}
    at = body_start + len("(list ")
    for i in order:
        starts[i] = at
        at += len(exprs[i]) + 1
    try:
        compiled, _ = build(combined, prelude=prelude)
    except Exception:          # noqa: BLE001 -- then there is nothing to probe
        return
    rt = Runtime(**kwargs)
    try:
        evaluate(compiled, rt)
    except Exception:          # noqa: BLE001 -- a trap in one example; the defs still exist
        pass
    closures = user_closures(rt, len(source), prelude_names())
    if not closures:
        return
    # The example expressions, as the nodes of the list the body builds.
    body = example_expression(compiled)
    nodes: List[Any] = []
    node = body
    while node is not None and node.op == 4 and len(node.args) == 2:     # CONS
        nodes.append(node.args[0])
        node = node.args[1]
    if len(nodes) != len(order):
        return
    by_index = dict(zip(order, nodes))
    max_steps = max(kwargs.get("max_steps", 0) or 0, rt.steps * 10 + 10_000)
    for r in failed:
        i = r["index"]
        want = wants[i]
        others = [(by_index[j], (lambda v, w=wants[j]: same(v, w))) for j in order if j != i]
        found = locate(compiled, combined, by_index[i], lambda v, w=want: same(v, w), others,
                       closures[0].env, closures, max_steps=max_steps, budget_s=budget_s)
        if found and found.get("span") and found.get("def") is None:
            # A fault in the expression itself: back to the example's text.
            delta = expr_spans[i][0] - starts[i]
            found["span"] = [found["span"][0] + delta, found["span"][1] + delta]
            found["in"] = "the example's expression"
        if found and found.get("span"):
            a = found["span"][0]
            found["line"], found["col"] = line_col(source, a)
            found["excerpt"] = source[found["span"][0]:found["span"][1]]
            r["fault"] = found
            if isinstance(r.get("anomaly"), dict):
                rep = f" -> {found['replacement']}" if found.get("replacement") else ""
                r["anomaly"]["repair_hint"] = (f"{found['edit']} at {found['line']}:{found['col']} "
                                               f"`{found['excerpt']}`{rep}")
                r["anomaly"]["fault"] = found
        elif found:
            r["fault"] = found


def summary(results: List[Dict[str, Any]]) -> str:
    """One line per example, then the count."""
    lines = []
    for r in results:
        if r["passed"]:
            lines.append(f"  ok    {r['line']}:{r['col']}  {r['excerpt']}")
        else:
            a = r.get("anomaly", {})
            if "got" in r:
                why = f"expected {r['expected']}, got {r['got']}"
            elif r.get("note"):
                why = r["note"] + ": " + a.get("kind", "error")
            else:
                why = a.get("kind", "error") + (f", expected {r['expected']}" if "expected" in r else "")
            lines.append(f"  FAIL  {r['line']}:{r['col']}  {r['excerpt']}  -- {why}")
            fault = r.get("fault")
            if fault and fault.get("span"):
                n, m = fault.get("others_passing", 0), fault.get("others", 0)
                score = ("" if not m else
                         "  [fixes every example]" if n == m else
                         f"  [fixes this and {n} of {m} other examples; the fault may be elsewhere]")
                if fault.get("budget"):
                    score += "  (search cut short by the time budget)"
                rep = f"  -> {fault['replacement']}" if fault.get("replacement") else ""
                lines.append(f"        fault: {fault['line']}:{fault['col']}  {fault['excerpt']}  "
                             f"-- {fault['edit']}{rep}{score}")
            elif fault and fault.get("kind") == "budget":
                lines.append(f"        fault: not found within the time budget ({fault['probes']} probes)")
            hint = a.get("body_offender")
            if hint and not fault:
                lines.append(f"        offender: {hint.get('op_name')} at depth {hint.get('depth')}, "
                             f"observed {hint.get('observed')}, needed {hint.get('needed')}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"  {passed}/{len(results)} examples pass")
    return chr(10).join(lines)
