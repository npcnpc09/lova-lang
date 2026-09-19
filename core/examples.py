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


def _prepared(source: str, prelude: bool):
    """The source as the parser saw it, its examples, and how to put an
    expression where the program's own body was.

    Shared by the Python check and the native one, because the two must
    run the same text: a native pass that ran a different program would
    be worth nothing.
    """
    # A `(use "name")` is textual inclusion, and the spans the parser
    # records are offsets into the included text -- so a library's own
    # examples run too, once the source is what the parser saw.
    source = expand_uses(source)
    tree = parse_with_prelude(source) if prelude else parse(source)
    examples = list(getattr(tree, "examples", []))
    body_span = getattr(tree, "body_span", None)
    if not examples:
        return source, [], None, None
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

    return source, examples, with_body, body_span


def check(source: str, *, prelude: bool = True, max_steps: Optional[int] = None,
          max_call_depth: Optional[int] = None, granted: int = 0,
          locate_budget_s: float = 2.0,
          runtime: str = "python") -> List[Dict[str, Any]]:
    """Run every example; one result per example, in source order.

    ``runtime="native"`` runs them on a native runtime (one process for
    the whole check, because an example is a small tree run twice and
    starting a binary per example costs more than the example).  It is
    the fast answer to "do they all pass": the moment one misses, or
    traps, or the program is outside the native runtime's phase, the
    whole check is re-run in Python, because the located fault, the
    reach sets and the named anomaly are the Python side's and a
    half-native report would be two reports.
    """
    from core.cli import build, format_value

    if runtime == "native":
        fast = _check_native(source, prelude=prelude, max_steps=max_steps,
                             max_call_depth=max_call_depth, granted=granted)
        if fast is not None:
            return fast
    elif runtime != "python":
        raise ValueError(f"check: runtime is 'python' or 'native', not {runtime!r}")

    source, examples, with_body, body_span = _prepared(source, prelude)
    results: List[Dict[str, Any]] = []
    if not examples:
        return results

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


def _check_native(source: str, *, prelude: bool, max_steps: Optional[int],
                  max_call_depth: Optional[int],
                  granted: int) -> Optional[List[Dict[str, Any]]]:
    """Every example on a native runtime, or ``None``.

    ``None`` means "Python has to do this one": no native runtime on the
    machine, a program outside its phase, or -- the load-bearing case --
    an example that did not pass, whose report is worth more than the
    speed.  Nothing here compares values: the protocol carries the
    printed form, so what is compared is the two strings, which is what
    the golden set guarantees the Python runtime would have printed.
    """
    from core.cli import build
    from core.native import (
        NativeUnavailable, NativeUnsupported, default_runtime, supports,
    )

    prepared_source, examples, with_body, _body_span = _prepared(source, prelude)
    if not examples:
        return []
    native = default_runtime()
    if native is None:
        return None
    limits = {"max_steps": max_steps if max_steps is not None else 1_000_000,
              "max_call_depth": max_call_depth if max_call_depth is not None else 10_000}
    results: List[Dict[str, Any]] = []
    try:
        for index, ex in enumerate(examples):
            if ex["span"] is None:
                continue
            a, b = ex["span"]
            expr_span, expected_span = ex["expr"].span, ex["expected"].span
            expr_text = prepared_source[expr_span[0]:expr_span[1]]
            expected_text = prepared_source[expected_span[0]:expected_span[1]]
            try:
                want_tree, _ = build(with_body(expected_text), prelude=prelude)
                got_tree, _ = build(with_body(expr_text), prelude=prelude)
            except Exception:              # noqa: BLE001 -- Python reports it
                return None
            # Screened against *this* runtime's list, which its `ping`
            # gave us, not against a copy of a phase's scope kept here.
            if not (supports(want_tree, native) and supports(got_tree, native)):
                return None
            want = native.run(want_tree, allow=granted, **limits)
            got = native.run(got_tree, allow=granted, **limits)
            if got.value_text != want.value_text:
                return None
            results.append({
                "index": index, "span": [a, b], "excerpt": prepared_source[a:b],
                "line": line_col(prepared_source, a)[0],
                "col": line_col(prepared_source, a)[1],
                "passed": True, "value": got.value_text, "steps": got.steps,
                "reaches": [],
            })
    except (NativeUnavailable, NativeUnsupported):
        return None
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError):
        return None                        # a trap: the report is Python's
    finally:
        native.close()
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
    # What the search does not find, the reach sets still say (Exp 29,
    # L2 and L5): the defs the failing examples reach, by how few of
    # the passing ones reach them -- or that every one is reached by
    # every passing example, which is what g2048-a's failure looks like.
    suspects = []
    for c in closures:
        name = symbols.name_of(c.name) if symbols is not None and c.name is not None else None
        ef = sum(1 for x in failing if name in x.get("reaches", []))
        ep = sum(1 for x in passing if name in x.get("reaches", []))
        if name and ef:
            suspects.append({"def": name, "failing": ef, "passing": ep})
    discriminating = [x for x in suspects if x["passing"] < len(passing)]
    for x in failed:
        x["suspects"] = discriminating[:6]
        x["suspects_total"] = len(suspects)
        x["passing_total"] = len(passing)
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
            if found.get("def") and not found.get("constant"):
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
    # Identical failures are one entry: the first in full, the rest by
    # their lines (Exp 29: seven examples trapping at one place cost
    # 1 257 characters, and the Python control read less in all).
    groups: Dict[str, Dict[str, Any]] = {}
    order_keys: List[str] = []
    for r in results:
        if r["passed"]:
            if verbose:
                lines.append(f"  ok    {r['line']}:{r['col']}  {_first_line(r['excerpt'])}")
            continue
        entry = _failure_lines(r, seen_faults)
        # The same trap and the same fault line make one entry whatever
        # each example expected; a bare miss is its own.
        key = chr(10).join(entry["detail"]) if entry["detail"] else entry["head"]
        if key in groups:
            groups[key]["more"].append(f"{r['line']}:{r['col']}")
        else:
            groups[key] = {"head": entry["head"], "detail": entry["detail"], "more": []}
            order_keys.append(key)
    for key in order_keys:
        g = groups[key]
        lines.append(g["head"])
        lines.extend(g["detail"])
        if g["more"]:
            lines.append(f"        and {len(g['more'])} more example{'s' if len(g['more']) > 1 else ''} "
                         f"fail{'s' if len(g['more']) == 1 else ''} the same way, at {', '.join(g['more'])}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"  {passed}/{len(results)} examples pass")
    return chr(10).join(lines)


def _suspects_line(r: Dict[str, Any]) -> Optional[str]:
    if "suspects" not in r:
        return None
    if r["suspects"]:
        named = ", ".join(f"{x['def']} ({x['passing']} of {r['passing_total']} passing reach it)" for x in r["suspects"])
        return f"        defs the failing examples reach that fewer passing ones do: {named}"
    return (f"        every def this example reaches ({r['suspects_total']}) is reached by every passing "
            f"example too; the reach sets do not separate them")


def _failure_lines(r: Dict[str, Any], seen_faults: Dict[str, int]) -> Dict[str, Any]:
    """One failing example's lines: the head, the detail, and its `why`."""
    lines: List[str] = []
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
        # A swapped branch's excerpt is the whole form: the first line
        # of it, and the replacement only when it fits on one.
        rep = ""
        if fault.get("replacement"):
            r_text = fault["replacement"]
            rep = (f"  -> {r_text}" if chr(10) not in r_text and len(r_text) <= 120
                   else "  (the replacement is several lines; lova_patch has it)")
        where = ""
        if fault.get("def"):
            where = f"  in {fault['def']}" + (", a constant" if fault.get("constant") else "")
        ctx = fault.get("context")
        if ctx and ctx != fault.get("excerpt"):
            where += f"  within {ctx}"
        a0, b0 = fault["span"]
        # An edit that fixes every example is a fault line; one that
        # fixes some is a lead, and says so in its label (Exp 29: two
        # of three sessions asked that a partial not wear the same
        # dress as a repair).
        label = "fault" if not m or n == m else "lead "
        shown = _first_line(fault["excerpt"] or "")
        line = (f"        {label}: {fault['line']}:{fault['col']} [{a0}, {b0})  {shown}{where}  "
                f"-- {fault['edit']}{rep}{score}")
        if fault.get("tied_with"):
            places = ", ".join(f"{t['excerpt']} [{t['span'][0]}, {t['span'][1]})" for t in fault["tied_with"])
            line += (f"{chr(10)}        or the same edit at: {places} -- the examples cannot tell "
                     f"these places apart")
        if fault.get("also"):
            def _place(a):
                at = f" for {a['excerpt']}" if a.get("excerpt") else ""
                if a.get("span"):
                    at += f" [{a['span'][0]}, {a['span'][1]})"
                if a.get("def"):
                    at += f" in {a['def']}"
                return f"{a['replacement']}{at} ({a['impact']})"
            others = "; ".join(_place(a) for a in fault["also"] if a.get("replacement"))
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
    if not (fault and fault.get("span") and fault.get("others_passing") == fault.get("others")):
        sus = _suspects_line(r)
        if sus:
            lines.append(sus)
    return {"head": lines[0], "detail": lines[1:], "why": why}
