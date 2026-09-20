"""How much of the program its examples can see (M40, Q121).

A well-typed program with a wrong value in it has no diagnostic: the
substrate cannot know what "right" is, only the examples say.  So the
question a writer needs answered before trusting a program is not "do
the examples pass" but "would they notice if this def were wrong".
``strength`` answers it by asking the locator's question backwards:
the locator tries every single-node edit of a def to make a failing
example pass; this tries the same edits on a passing program and
counts the ones no example catches.

An edit that no example notices is a *survivor*, and a def whose edits
mostly survive is unguarded: whatever it computes, the examples are
not looking.  A def no example runs through at all is reported apart,
because its count would be nought of nought.

The machinery is the locator's (``core/locate.py``): the examples are
built once as one program, so every def's closure exists in one frame;
a def's closure is rebuilt with the edited body and installed under
its own name, the examples that reach the def are evaluated again in
that frame, and the closure is put back.  A probe costs one evaluation
of each example that reaches the def, so a time budget bounds it and
the report says what fraction was tried.  Edits go round-robin across
the defs, so a budget that runs out leaves every def with some
coverage rather than the first few with all of it.

The edits are the locator's exact-spelling classes -- operands or
branches swapped, a minus or a `not` dropped, a comparison or an
operator for its sibling, a literal nudged, a reference for another
name in scope -- and not the wider "add a minus anywhere" and "wrap in
a call" classes, which double the count and mostly change a value
every example sees.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.examples import _prepared, same
from core.locate import (
    _degenerate, _edits, _replace, _scopes, _span, _walk, data_literals,
    deepest_frame, example_expression, user_closures,
)
from core.runtime import Closure, Node, Runtime, StepTrap, evaluate
from core.surface import line_col, prelude_names
from core.tokens import LAMBDA, LET, LIT_INT, MERGE, MUL

_EXACT = ("swap-operands", "swap-branches", "drop-minus", "drop-not",
          "compare", "operator", "literal", "ref")


def strength(source: str, *, prelude: bool = True, max_steps: Optional[int] = None,
             max_call_depth: Optional[int] = None, granted: int = 0,
             budget_s: float = 20.0, only: Optional[List[str]] = None,
             kinds: Tuple[str, ...] = _EXACT) -> Dict[str, Any]:
    """Every def of the program by how many of its single-node edits the
    examples catch.  Returns ``{"defs": [...], "unreached": [...],
    "examples": n, "probes": n, "tried": n, "total": n, "seconds": s}``;
    each def is ``{"name", "line", "col", "examples", "tried", "total",
    "killed", "survived", "survivors": [{"kind", "edit", "excerpt",
    "line", "col"}]}``, unguarded first."""
    from core.cli import build

    prepared, examples, with_body, body_span = _prepared(source, prelude)
    if not examples:
        return {"defs": [], "unreached": [], "examples": 0, "probes": 0,
                "tried": 0, "total": 0, "seconds": 0.0}
    kwargs = {k: v for k, v in (("max_steps", max_steps), ("max_call_depth", max_call_depth))
              if v is not None}
    kwargs["granted"] = granted
    # The examples' expressions and what they state, each as one program
    # over the same defs: the defs are the same text, so the closures of
    # the first run and the values of the second agree on every name.
    order = [i for i, ex in enumerate(examples) if ex["span"] is not None]
    exprs = {i: prepared[examples[i]["expr"].span[0]:examples[i]["expr"].span[1]] for i in order}
    wants_text = {i: prepared[examples[i]["expected"].span[0]:examples[i]["expected"].span[1]]
                  for i in order}
    compiled, _ = build(with_body("(list " + " ".join(exprs[i] for i in order) + ")"), prelude=prelude)
    stated, _ = build(with_body("(list " + " ".join(wants_text[i] for i in order) + ")"), prelude=prelude)
    started = time.perf_counter()
    rt = Runtime(**kwargs)
    try:
        evaluate(compiled, rt)
    except Exception:          # noqa: BLE001 -- an example that traps is checked by `check`, not here
        pass
    wants_rt = Runtime(**kwargs)
    want_values = _as_list(evaluate(stated, wants_rt))
    nodes = _as_nodes(example_expression(compiled))
    if len(nodes) != len(order) or len(want_values) != len(order):
        raise ValueError("strength: an example does not evaluate; run `check` first")
    closures_all = user_closures(rt, len(prepared), prelude_names(), called=False)
    frame = deepest_frame(closures_all)
    if frame is None:
        raise ValueError("strength: the program has no defs of its own")
    symbols = getattr(compiled, "symbols", None)
    name_of = (lambda i: symbols.name_of(i)) if symbols else (lambda i: None)

    def text(node: Node) -> Optional[str]:
        s = _span(node)
        return prepared[s[0]:s[1]] if s and s[0] is not None and s[1] is not None and s[1] <= len(prepared) else None

    def run(node: Node, cap: Optional[int] = None) -> Any:
        r = Runtime(**dict(kwargs, max_steps=cap or kwargs.get("max_steps") or 1_000_000))
        r.env = frame
        return evaluate(node, r), r.steps

    # Which defs each example runs through, and what each costs alone:
    # the calls counter of every closure before and after.
    named = [c for c in closures_all if c.name is not None]
    reaches: Dict[int, set] = {}
    baseline: Dict[int, int] = {}
    wants: Dict[int, Any] = {}
    for k, i in enumerate(order):
        before = {id(c): c.calls for c in named}
        try:
            value, steps = run(nodes[k])
        except Exception:      # noqa: BLE001
            value, steps = None, 0
        reaches[i] = {c.name for c in named if c.calls != before[id(c)]}
        baseline[i] = steps
        wants[i] = want_values[k]
        if value is None or not same(value, wants[i]):
            raise ValueError(f"strength: example {i + 1} does not pass; run `check` first")

    # Targets: every def with a body in the source -- a closure, or a
    # constant (a zero-parameter def) whose value node is its body.
    constants: Dict[int, Node] = {}
    node = compiled
    while node.op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
        cname, cvalue = int(node.args[0].args[0]), node.args[1]
        if isinstance(cvalue, Node) and cvalue.op != LAMBDA and text(cvalue) is not None:
            constants[cname] = cvalue
        node = node.args[2]
    wanted = set(only) if only else None
    targets: List[Tuple[Any, int, Node]] = []
    seen = set()
    for c in named:
        if c.name in seen or (wanted and name_of(c.name) not in wanted):
            continue
        seen.add(c.name)
        targets.append((c, c.name, c.body))
    for cname, cvalue in constants.items():
        if cname in seen or (wanted and name_of(cname) not in wanted):
            continue
        seen.add(cname)
        targets.append((("const", cname), cname, cvalue))
    literals = data_literals(nodes)
    wrappers = None

    def frame_of(name_id: int) -> Any:
        env = frame
        while env is not None:
            if name_id in env.keys():
                return env
            env = getattr(env, "parent", None)
        return None

    def install(target: Any, body: Node) -> Optional[Callable[[], None]]:
        if isinstance(target, Closure):
            rebuilt = Closure(param=target.param, body=body, env=target.env,
                              caps=target.caps, enclosed=target.enclosed, owner=target.owner)
            rebuilt.name = target.name
            target.env[target.name] = rebuilt
            return lambda: target.env.__setitem__(target.name, target)
        name_id = target[1]
        env = frame_of(name_id)
        if env is None:
            return None
        old = env[name_id]
        try:
            env[name_id] = run(body)[0]
        except Exception:      # noqa: BLE001 -- the edited constant does not evaluate
            env[name_id] = old
            return None
        return lambda: env.__setitem__(name_id, old)

    # The plan: every def's edits, the def's examples beside them.
    plans: List[Dict[str, Any]] = []
    unreached: List[Dict[str, Any]] = []
    # A constant is not called, so the calls counter says nothing of it:
    # an example reaches a constant when a def it ran through, or its
    # own expression, mentions the constant by name.
    from core.tokens import REF

    def mentions(n: Node, out: set) -> None:
        if n.op == REF and n.args and isinstance(n.args[0], Node) and n.args[0].op == LIT_INT:
            out.add(int(n.args[0].args[0]))
        for x in n.args:
            if isinstance(x, Node):
                mentions(x, out)
    refs_of: Dict[int, set] = {}
    for c in named:
        acc: set = set()
        mentions(c.body, acc)
        refs_of[c.name] = acc
    for cname, cvalue in constants.items():
        acc = set()
        mentions(cvalue, acc)
        refs_of[cname] = acc
    for k, i in enumerate(order):
        own: set = set()
        mentions(nodes[k], own)
        seen_c: set = set(reaches[i]) | own
        grown = True
        while grown:          # a constant a reached constant mentions is reached too
            grown = False
            for c_id in list(seen_c):
                for r in refs_of.get(c_id, ()):
                    if r in constants and r not in seen_c:
                        seen_c.add(r)
                        grown = True
        reaches[i] = {n for n in seen_c if n in constants or n in reaches[i]}
    # A def nothing mentions is not in the compiled program at all
    # (`drop-unused`), so it has no closure to probe: it is unreached by
    # construction, and said so from the parse.
    try:
        from core.query import defs as source_defs
        listed = source_defs(with_body("0"))
    except Exception:      # noqa: BLE001 -- then only the compiled defs are reported
        listed = []
    present = {name_of(n) for _, n, _ in targets} | {name_of(c.name) for c in named}
    for d in listed:
        if d["name"] not in present and (wanted is None or d["name"] in wanted):
            unreached.append({"name": d["name"], "line": d["line"], "col": d["col"]})
    for target, name_id, body in targets:
        name = name_of(name_id) or str(name_id)
        s = _span(body)
        line, col = line_col(prepared, s[0]) if s and s[0] is not None else (0, 0)
        mine = [i for i in order if name_id in reaches[i]]
        if not mine:
            unreached.append({"name": name, "line": line, "col": col})
            continue
        params = [target.param] if isinstance(target, Closure) else []
        walked: List[Any] = []
        _walk(body, (), 0, walked)
        scopes = _scopes(body)
        edits: List[Any] = []
        for path, node_, depth, anchor in walked:
            # Only the author's own nodes: a node a macro synthesised --
            # the field id inside `(get w base)`, the `deviation` inside
            # `eq` -- is not a place the author could have been wrong in.
            if anchor is None or _span(node_) is None:
                continue
            for edit in _edits(node_, scopes.get(id(node_), []), params, name_of, text, literals, wrappers):
                if edit[0] not in kinds:
                    continue
                # `merge` and `mul` commute: the operands swapped is the
                # same program, which no example could ever tell apart.
                if edit[0] == "swap-operands" and node_.op in (MERGE, MUL):
                    continue
                edits.append((path, node_, anchor, edit))
        plans.append({"target": target, "name": name, "line": line, "col": col, "examples": mine,
                      "edits": edits, "next": 0, "killed": 0, "survived": 0,
                      "survivors": [], "def_id": name_id})

    probes = 0

    def probe(plan: Dict[str, Any]) -> None:
        nonlocal probes
        path, node_, anchor, edit = plan["edits"][plan["next"]]
        plan["next"] += 1
        kind, why, replacement, new, key = edit
        edited = _replace(plan["target"].body if isinstance(plan["target"], Closure)
                          else constants[plan["def_id"]], path, new)
        if kind == "ref" and _degenerate(edited, path):
            return
        undo = install(plan["target"], edited)
        if undo is None:
            plan["killed"] += 1        # a constant the edit breaks: an example would trap on it
            return
        probes += 1
        caught = False
        try:
            for i in plan["examples"]:
                k = order.index(i)
                try:
                    value, _steps = run(nodes[k], max(50_000, baseline[i] * 4))
                except StepTrap:
                    caught = True
                    break
                except Exception:      # noqa: BLE001 -- a trap is the example noticing
                    caught = True
                    break
                if not same(value, wants[i]):
                    caught = True
                    break
        finally:
            undo()
        if caught:
            plan["killed"] += 1
        else:
            plan["survived"] += 1
            if len(plan["survivors"]) < 4:
                s = _span(anchor)
                l, c = line_col(prepared, s[0]) if s and s[0] is not None else (0, 0)
                plan["survivors"].append({"kind": kind, "edit": why, "excerpt": text(anchor),
                                          "line": l, "col": c,
                                          "replacement": replacement if _span(node_) is not None else None})

    # Round-robin over the defs, one edit each, until the budget or the end.
    live = [p for p in plans if p["edits"]]
    while live and time.perf_counter() - started < budget_s:
        for plan in list(live):
            if plan["next"] >= len(plan["edits"]):
                live.remove(plan)
                continue
            probe(plan)
            if time.perf_counter() - started >= budget_s:
                break

    defs = []
    for plan in plans:
        tried = plan["killed"] + plan["survived"]
        defs.append({"name": plan["name"], "line": plan["line"], "col": plan["col"],
                     "examples": len(plan["examples"]), "tried": tried, "total": len(plan["edits"]),
                     "killed": plan["killed"], "survived": plan["survived"],
                     "survivors": plan["survivors"]})
    defs.sort(key=lambda d: (-(d["survived"] / d["tried"]) if d["tried"] else 0.0, -d["survived"], d["line"]))
    return {"defs": defs, "unreached": unreached, "examples": len(order), "probes": probes,
            "tried": sum(d["tried"] for d in defs), "total": sum(d["total"] for d in defs),
            "seconds": round(time.perf_counter() - started, 2)}


def summary(report: Dict[str, Any], show: int = 6) -> str:
    """The report as the CLI prints it: one line a def, the least guarded
    first, with the edits the examples miss under the weakest `show`;
    then the defs no example reaches."""
    lines: List[str] = []
    defs = report["defs"]
    if not defs and not report["unreached"]:
        return "  no defs to probe"
    tried = [d for d in defs if d["tried"]]
    untried = [d for d in defs if not d["tried"]]
    for n, d in enumerate(tried):
        part = "" if d["tried"] == d["total"] else f" ({d['total']} in all)"
        ex = f"{d['examples']} example{'s' if d['examples'] != 1 else ''}"
        if d["survived"]:
            lines.append(f"  {d['name']:<16} {d['survived']:>3} of {d['tried']:>3} edits unseen{part}  ({ex})")
            if n < show:
                for s_ in d["survivors"][:3]:
                    where = f"{s_['line']}:{s_['col']}" if s_["line"] else "?"
                    excerpt = (s_["excerpt"] or "").splitlines()[0] if s_["excerpt"] else ""
                    if len(excerpt) > 48:
                        excerpt = excerpt[:45] + "..."
                    lines.append(f"      {where:<9} {excerpt}  -- {s_['edit']}")
        else:
            lines.append(f"  {d['name']:<16}   every edit caught, {d['tried']:>3}{part}  ({ex})")
    if untried:
        lines.append(f"  not tried (budget): {', '.join(d['name'] for d in untried)}")
    if report["unreached"]:
        lines.append(f"  no example reaches: {', '.join(u['name'] for u in report['unreached'])}")
    lines.append(f"  {report['tried']} of {report['total']} edits tried in {report['seconds']} s"
                 f" over {report['examples']} example{'s' if report['examples'] != 1 else ''}")
    return chr(10).join(lines)


def _as_list(value: Any) -> List[Any]:
    from core.runtime import Cons
    out = []
    while isinstance(value, Cons):
        out.append(value.head)
        value = value.tail
    return out


def _as_nodes(body: Node) -> List[Node]:
    from core.tokens import CONS
    out = []
    node = body
    while node is not None and node.op == CONS and len(node.args) == 2:
        out.append(node.args[0])
        node = node.args[1]
    return out
