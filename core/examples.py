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

import time
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
        rt = Runtime(**kwargs)
        try:
            compiled, _ = build(with_body(expr_text), prelude=prelude)
            got = evaluate(compiled, rt)
        except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
            anomaly = getattr(exc, "anomaly", None) or {"kind": "error", "message": str(exc)}
            anomaly = dict(anomaly)
            anomaly.pop("_enriched", None)
            try:
                from core.cli import name_anomaly
                name_anomaly(anomaly, getattr(compiled, "symbols", None) if "compiled" in dir() else None)
            except Exception:      # noqa: BLE001 -- the hint is a courtesy
                pass
            result.update(passed=False, anomaly=anomaly, expected=_shown(want), steps=rt.steps)
        else:
            if same(got, want):
                result.update(passed=True, value=got, steps=rt.steps)
            else:
                # A miss is an anomaly like any other: the same kind the
                # conservation contract raised when an example was one.
                result.update(passed=False, expected=_shown(want), got=_shown(got),
                              steps=rt.steps,
                              anomaly={"kind": "conservation-violated",
                                       "detail": {"entry": _shown(want), "exit": _shown(got)},
                                       "span": [a, b]})
        # Which of the program's own defs this example ran through: the
        # coverage a located edit is scored against (Exp 28: "fixes all 3
        # examples" said nothing about how many of them reached the def).
        symbols = getattr(compiled, "symbols", None) if "compiled" in dir() else None
        reached = set()
        for c in getattr(rt, "named", []):
            s = getattr(c.body, "span", None)
            if c.calls > 0 and s is not None and s[0] is not None and s[1] is not None and s[1] <= len(source):
                name = symbols.name_of(c.name) if symbols is not None and c.name is not None else None
                if name:
                    reached.add(name)
        result["reaches"] = sorted(reached)
        results.append(result)

    # A miss and a trap alike: the example that trapped in `(nth powers k)`
    # has its fault three defs upstream in `(range 0 10)` (Exp 29, ttt-b),
    # and an edit that makes it produce the stated value is a fix either way.
    failed = [r for r in results if not r["passed"] and ("got" in r or "expected" in r)]
    if failed and locate_budget_s > 0:
        _locate_all(results, failed, exprs, wants, source, with_body, prelude, kwargs, locate_budget_s,
                    body_span[0], expr_spans)
    return results


def _locate_all(results, failed, exprs, wants, source, with_body, prelude, kwargs, budget_s,
                body_start, expr_spans) -> None:
    """One combined run holds every def any example uses; probe in it."""
    from core.cli import build
    from core.locate import data_literals, deepest_frame, example_expression, locate, user_closures
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
    trapped = False
    try:
        evaluate(compiled, rt)
    except Exception:          # noqa: BLE001 -- a trap in one example; the defs still exist
        trapped = True
    # The example expressions, as the nodes of the list the body builds.
    body = example_expression(compiled)
    nodes: List[Any] = []
    node = body
    while node is not None and node.op == 4 and len(node.args) == 2:     # CONS
        nodes.append(node.args[0])
        node = node.args[1]
    if len(nodes) != len(order):
        return
    frame = deepest_frame(user_closures(rt, len(source), prelude_names(), called=False))
    if frame is None:
        return
    if trapped:
        # The list stopped at the first trap, so the examples after it
        # never ran and the defs only they reach show no calls.  Run each
        # on its own in the same frame; the counters are cumulative.
        for n in nodes:
            again = Runtime(**kwargs)
            again.env = frame
            try:
                evaluate(n, again)
            except Exception:  # noqa: BLE001
                pass
    closures = user_closures(rt, len(source), prelude_names())
    if not closures:
        return
    by_index = dict(zip(order, nodes))
    literals = data_literals(nodes)
    # The defs in the order to probe them: the ones the failing examples
    # reach and the passing ones reach least, first (Ochiai over the
    # per-example `reaches`); a def every example runs through -- `cell`
    # in Exp 29's noughts and crosses, 51 653 calls -- is the least likely
    # place for a fault that spares five examples of eight.
    symbols = getattr(compiled, "symbols", None)
    passing = [x for x in results if x["passed"]]
    failing = [x for x in results if not x["passed"]]

    def suspicion(c) -> float:
        name = symbols.name_of(c.name) if symbols is not None and c.name is not None else None
        ef = sum(1 for x in failing if name in x.get("reaches", []))
        ep = sum(1 for x in passing if name in x.get("reaches", []))
        if ef == 0:
            return 0.0
        return ef / ((len(failing) * (ef + ep)) ** 0.5)

    closures.sort(key=lambda c: (-suspicion(c), c.calls))
    ceiling = kwargs.get("max_steps") or Runtime(**kwargs).max_steps
    longest_pass = max([x.get("steps", 0) for x in passing] or [0])
    # The cheapest failing example first: a fix found on it that passes
    # every other example is the other failures' fix too, unprobed.
    failed = sorted(failed, key=lambda x: x.get("steps", 0))
    # One budget for the check, not one a failing example: the edits
    # probed are the same for every example, so a search that found no
    # fix on the first would find none on the second, and a search cut
    # short would be cut at the same place (Exp 29: three searches of
    # 60 s each on the same forty probes).
    deadline = time.perf_counter() + budget_s
    longest_known = max([x.get("steps", 0) for x in results] or [0])
    for r in failed:
        if r.get("fault"):
            continue
        i = r["index"]
        want = wants[i]
        others = [(by_index[j], (lambda v, w=wants[j]: same(v, w))) for j in order if j != i]
        # A probe runs the example again; a runaway edit is bounded at
        # twice the longest run any example has needed, not at the
        # program's ceiling (Exp 29: six such probes cost 73 s of 74);
        # the locator retries a probe that hit the cap with more room.
        cap = 2 * max(r.get("steps", 0), longest_known) + 10_000
        max_steps = min(cap, ceiling) if ceiling else cap
        left = deadline - time.perf_counter()
        if left <= 0:
            r["fault"] = {"kind": "budget", "probes": 0}
            continue
        found = locate(compiled, combined, by_index[i], lambda v, w=want: same(v, w), others,
                       frame, closures, max_steps=max_steps, budget_s=left,
                       literals=literals, ceiling=ceiling)
        if found and found.get("span") and found.get("def") is None:
            # A fault in the expression itself: back to the example's text.
            delta = expr_spans[i][0] - starts[i]
            found["span"] = [found["span"][0] + delta, found["span"][1] + delta]
            found["in"] = "the example's expression"
        if found and found.get("span"):
            a = found["span"][0]
            found["line"], found["col"] = line_col(source, a)
            found["excerpt"] = source[found["span"][0]:found["span"][1]]
            if found.get("def"):
                found["reached_by"] = sum(1 for x in results if found["def"] in x.get("reaches", []))
                found["examples"] = len(results)
            r["fault"] = found
            if isinstance(r.get("anomaly"), dict):
                rep = f" -> {found['replacement']}" if found.get("replacement") else ""
                r["anomaly"]["repair_hint"] = (f"{found['edit']} at {found['line']}:{found['col']} "
                                               f"`{found['excerpt']}`{rep}")
                r["anomaly"]["fault"] = found
            if found.get("def") and found.get("others_passing") == found.get("others") and found.get("others"):
                # It fixed every other example, the other failures among
                # them: theirs is the same fault, and the search is saved.
                for x in failed:
                    if x is not r and not x.get("fault"):
                        x["fault"] = dict(found)
                        if isinstance(x.get("anomaly"), dict):
                            x["anomaly"]["repair_hint"] = r["anomaly"].get("repair_hint") if isinstance(r.get("anomaly"), dict) else None
                            x["anomaly"]["fault"] = found
        elif found:
            r["fault"] = found
            if found.get("kind") in ("budget", "none"):
                # The same edits would be probed again for the other
                # failures, with the same answer.
                for x in failed:
                    if x is not r and not x.get("fault"):
                        x["fault"] = dict(found)


def _first_line(text: str) -> str:
    """An example as its first line: a session reads every character of
    the report, and Exp 28's were eleven thousand a session of reprinted
    expressions."""
    head, sep, _ = text.partition(chr(10))
    return head + " ..." if sep else head


def summary(results: List[Dict[str, Any]], *, verbose: bool = False) -> str:
    """The failures, one fault line per distinct fault, and the count.
    A session reads every character of this (Exp 28 run 2: 4 093 a
    session against 558-1 645 of program), so the passing examples are
    a count unless `verbose`."""
    lines = []
    seen_faults: Dict[str, int] = {}
    for r in results:
        if r["passed"]:
            if verbose:
                lines.append(f"  ok    {r['line']}:{r['col']}  {_first_line(r['excerpt'])}")
            continue
        a = r.get("anomaly", {})
        if "got" in r:
            why = f"expected {r['expected']}, got {r['got']}"
        elif r.get("note"):
            why = r["note"] + ": " + a.get("kind", "error")
        else:
            why = a.get("kind", "error") + (f", expected {r['expected']}" if "expected" in r else "")
        lines.append(f"  FAIL  {r['line']}:{r['col']}  {_first_line(r['excerpt'])}  -- {why}")
        fault = r.get("fault")
        if "got" not in r and a.get("repair_hint"):
            located = bool(fault and fault.get("span"))
            if not located:
                lines.append(f"        {a.get('kind', 'trap')}: {a['repair_hint']}")
            if a.get("span") and a.get("kind") not in ("conservation-violated",):
                lines.append(f"        {'trapped at' if located else 'at'} [{a['span'][0]}, {a['span'][1]})"
                             + (f"  {a['excerpt']}" if located and a.get("excerpt") else ""))
        if fault and fault.get("span"):
            n, m = fault.get("others_passing", 0), fault.get("others", 0)
            score = ("" if not m else
                     f"  [fixes all {m + 1} examples]" if n == m else
                     f"  [fixes this and {n} of {m} other examples; the fault may be elsewhere]")
            if fault.get("budget"):
                score += "  (search cut short by the time budget)"
            if "impact" in fault:
                score += f"  [changes the answer on {fault['impact']} of {fault['nearby']} nearby inputs]"
            if fault.get("def") and "reached_by" in fault:
                score += f"  [def {fault['def']} is reached by {fault['reached_by']} of {fault['examples']} examples]"
            rep = f"  -> {fault['replacement']}" if fault.get("replacement") else ""
            a0, b0 = fault["span"]
            # An edit that fixes every example is a fault line; one that
            # fixes some is a lead, and says so in its label (Exp 29: two
            # of three sessions asked that a partial not wear the same
            # dress as a repair).
            label = "fault" if not m or n == m else "lead "
            line = (f"        {label}: {fault['line']}:{fault['col']} [{a0}, {b0})  {fault['excerpt']}  "
                    f"-- {fault['edit']}{rep}{score}")
            if fault.get("tied_with"):
                places = ", ".join(f"{t['excerpt']} [{t['span'][0]}, {t['span'][1]})" for t in fault["tied_with"])
                line += (f"{chr(10)}        or the same edit at: {places} -- the examples cannot tell "
                         f"these places apart")
            if fault.get("also"):
                others = "; ".join(f"{a['replacement']} ({a['impact']})" for a in fault["also"] if a.get("replacement"))
                if others:
                    line += f"{chr(10)}        runners-up, by nearby inputs changed: {others}"
            if line in seen_faults:
                lines.append(f"        {label}: the same as at {seen_faults[line]}:{r['col']} above")
            else:
                seen_faults[line] = r["line"]
                lines.append(line)
        elif fault and fault.get("kind") == "budget":
            lines.append(f"        fault: not found within the time budget ({fault['probes']} probes)")
        elif fault and fault.get("kind") == "none":
            reaches = ", ".join(r.get("reaches", [])) or "no def of the program"
            lines.append(f"        fault: no single edit of a def makes this example pass "
                         f"({fault['probes']} probes); the fix is more than one token. "
                         f"This example reaches: {reaches}")
        hint = a.get("body_offender")
        if hint and not fault and "got" in r:
            lines.append(f"        offender: {hint.get('op_name')} at depth {hint.get('depth')}, "
                         f"observed {hint.get('observed')}, needed {hint.get('needed')}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"  {passed}/{len(results)} examples pass")
    return chr(10).join(lines)
