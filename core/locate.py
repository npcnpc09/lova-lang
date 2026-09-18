"""Where a failed example's fault is (2026-09-18, the audit).

An ``(example expr expected)`` that misses used to report ``offender:
apply at depth 0`` -- the example's own call, never the line inside the
def that the call reached, because the body scanner of M6 probes the
expression it was given and a def's body is behind a closure.  Exp 21
found that at twenty to forty lines a fault is found by reading, so the
anomaly never spoke; this is the anomaly speaking.

``locate`` takes the compiled program, the frame its defs live in, the
example's expression node and what it should have produced, and tries
every single-node edit on every node of every user def the example
ran through, deepest first: swap the operands, swap the branches, add
or drop a minus, add or drop a `not`, nudge a literal, exchange a
reference for another name in scope, swap an operator within its
family.  An edit that makes this example pass -- and is then scored
against the other examples -- is reported with the span of the node,
its source text, a one-line description, and where the edit can be
written as text, the replacement for ``lova_patch``.

The probing is on the tree, not the text: a def's closure is rebuilt
with the edited body and installed in the letrec frame under its own
name, so recursive and sibling calls see the edit, and the example's
expression is evaluated again in that frame.  A probe costs one
evaluation of the example; a program of three hundred nodes and eight
edits a node is a couple of thousand evaluations, so a time budget
bounds it and a miss says so.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.runtime import Closure, Node, Runtime, evaluate
from core.tokens import (
    DEVIATION, IF_SURPRISE, LAMBDA, LET, LIT_INT, LIT_TEXT, MERGE, MUL, REF,
    SIGNATURES, THRESHOLD,
)

from core.surface import _macro_eq, _macro_ge, _macro_gt, _macro_le, _macro_lt, _macro_ne

_COMPARE = {"lt": _macro_lt, "gt": _macro_gt, "le": _macro_le,
            "ge": _macro_ge, "eq": _macro_eq, "ne": _macro_ne}


def _compare_operands(root: Node, name: str):
    """(a, b) of a comparison macro's expansion at `root`, or None."""
    try:
        if name in ("lt", "gt"):
            dev = root.args[0]
        elif name in ("le", "ge"):
            dev = root.args[0].args[0]
        else:
            dev = root.args[0]
        if dev.op != DEVIATION or len(dev.args) != 2:
            return None
        a, b = dev.args
        if name in ("lt", "ge"):
            a, b = b, a
        return a, b
    except (AttributeError, IndexError):
        return None


# When two edits fix the same examples, the one to report: an exact
# spelling (a comparison or operator for its sibling, a name for a name)
# before a nudge, a nudge before a structural change.
_PRIORITY = {"compare": 6, "operator": 6, "ref": 5, "literal": 4,
             "swap-operands": 3, "swap-branches": 3,
             "drop-minus": 2, "add-minus": 2, "drop-not": 2, "add-not": 2}

# Operators whose two operands may be swapped by a plausible mistake.
_BINARY = {MERGE, MUL, DEVIATION}
# Where the compiled tree keeps the surface span of a node.
_span = lambda n: getattr(n, "span", None)  # noqa: E731


def _walk(node: Node, path: Tuple[int, ...], depth: int, out: List[Tuple[Tuple[int, ...], Node, int]],
          anchor: Optional[Node] = None) -> None:
    """Every node with its path and depth; `anchor` is the nearest node at
    or above it that carries a source span, which is where an edit of a
    macro-synthesised node is reported."""
    if _span(node) is not None:
        anchor = node
    out.append((path, node, depth, anchor))
    for i, arg in enumerate(node.args):
        if isinstance(arg, Node):
            _walk(arg, path + (i,), depth + 1, out, anchor)


def _replace(node: Node, path: Tuple[int, ...], new: Node) -> Node:
    if not path:
        return new
    args = list(node.args)
    args[path[0]] = _replace(args[path[0]], path[1:], new)
    copy = Node(op=node.op, args=args)
    if _span(node) is not None:
        copy.span = node.span
    return copy


def _lit(value: int) -> Node:
    return Node(op=LIT_INT, args=[value])


def _scopes(body: Node) -> Dict[int, List[int]]:
    """For each node (by id) inside `body`, the name ids bound around it
    by lambdas and lets within the body -- what a `ref` there may name
    besides the group's own defs."""
    out: Dict[int, List[int]] = {}

    def go(node: Node, bound: List[int]) -> None:
        out[id(node)] = bound
        if node.op == LAMBDA and node.args and node.args[0].op == LIT_INT:
            inner = bound + [int(node.args[0].args[0])]
            for arg in node.args[1:]:
                if isinstance(arg, Node):
                    go(arg, inner)
            return
        if node.op == LET and node.args and node.args[0].op == LIT_INT:
            inner = bound + [int(node.args[0].args[0])]
            for arg in node.args[1:]:
                if isinstance(arg, Node):
                    go(arg, inner)
            return
        for arg in node.args:
            if isinstance(arg, Node):
                go(arg, bound)

    go(body, [])
    return out


def data_literals(exprs: List[Node], limit: int = 24) -> List[int]:
    """The numbers the examples mention and the codepoints of the
    characters in their texts, most frequent first: what a wrong
    constant is most likely meant to be (Exp 28, h02: `39` for `46`,
    and `.` was in the example's input)."""
    counts: Dict[int, int] = {}

    def go(node: Node) -> None:
        if node.op == LIT_INT:
            v = int(node.args[0])
            counts[v] = counts.get(v, 0) + 1
        elif node.op == LIT_TEXT:
            for ch in str(node.args[0]):
                counts[ord(ch)] = counts.get(ord(ch), 0) + 1
        for arg in node.args:
            if isinstance(arg, Node):
                go(arg)

    for e in exprs:
        go(e)
    return [v for v, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _edits(node: Node, in_scope: List[int], params: List[int],
           name_of: Callable[[int], Optional[str]], text: Callable[[Node], Optional[str]],
           literals: Optional[List[int]] = None):
    """The single-node edits worth trying at `node`, each as
    (kind, description, replacement-source-or-None, new-node, key)."""
    src = text(node)
    edits = []
    a = node.args
    if node.op in _BINARY and len(a) == 2 and isinstance(a[0], Node) and isinstance(a[1], Node):
        swapped = Node(op=node.op, args=[a[1], a[0]])
        rep = None
        if src is not None and text(a[0]) is not None and text(a[1]) is not None:
            s0, s1 = a[0].span, a[1].span
            base = node.span[0]
            rep = (src[:s0[0] - base] + text(a[1]) + src[s0[1] - base:s1[0] - base]
                   + text(a[0]) + src[s1[1] - base:])
        edits.append(("swap-operands", "the two operands are the wrong way round", rep, swapped, "swap-operands"))
    if node.op == IF_SURPRISE and len(a) == 3 and all(isinstance(x, Node) for x in a):
        swapped = Node(op=node.op, args=[a[0], a[2], a[1]])
        rep = None
        if src is not None and text(a[1]) is not None and text(a[2]) is not None:
            s1, s2 = a[1].span, a[2].span
            base = node.span[0]
            rep = (src[:s1[0] - base] + text(a[2]) + src[s1[1] - base:s2[0] - base]
                   + text(a[1]) + src[s2[1] - base:])
        edits.append(("swap-branches", "the two branches are the wrong way round", rep, swapped, "swap-branches"))
    if node.op == LIT_INT:
        v = int(a[0])
        what = f"the literal {v}" if src is not None else f"a value {v} computed here"
        tries = [(v + 1, f"{what} should be {v + 1}"),
                 (v - 1, f"{what} should be {v - 1}"),
                 (-v, f"{what} should be {-v}")]
        if src is not None and literals:
            tries += [(lv, f"{what} should be {lv}" + (f" (`{chr(lv)}`)" if 32 < lv < 127 else ""))
                      for lv in literals if lv not in (v, v + 1, v - 1, -v)]
        for nv, why in tries:
            if nv != v:
                edits.append(("literal", why, str(nv) if src is not None else None, _lit(nv),
                              ("literal", "neg" if nv == -v else nv - v)))
    if node.op == REF and a and a[0].op == LIT_INT:
        here = int(a[0].args[0])
        for other in list(dict.fromkeys(params + in_scope)):
            if other != here and name_of(other) and name_of(here):
                edits.append(("ref", f"`{name_of(here)}` here should be `{name_of(other)}`",
                              name_of(other), Node(op=REF, args=[_lit(other)]), ("ref", other)))
    # A minus added or dropped: (mul -1 x) <-> x.
    if node.op == MUL and len(a) == 2 and a[0].op == LIT_INT and int(a[0].args[0]) == -1 and isinstance(a[1], Node):
        inner = a[1]
        edits.append(("drop-minus", "the minus sign should not be there", text(inner), inner, "drop-minus"))
    elif node.op != LIT_INT and node.op != LAMBDA:
        edits.append(("add-minus", "this should be negated",
                      f"(neg {src})" if src else None, Node(op=MUL, args=[_lit(-1), node]), "add-minus"))
    # A `not` added or dropped: (if-surprise x 0 1) <-> x.
    if (node.op == IF_SURPRISE and len(a) == 3 and a[1].op == LIT_INT and a[2].op == LIT_INT
            and int(a[1].args[0]) == 0 and int(a[2].args[0]) == 1 and isinstance(a[0], Node)):
        edits.append(("drop-not", "this condition is negated and should not be", text(a[0]), a[0], "drop-not"))
    elif node.op not in (LIT_INT, LIT_TEXT, LAMBDA):
        edits.append(("add-not", "this condition should be negated",
                      f"(not {src})" if src else None,
                      Node(op=IF_SURPRISE, args=[node, _lit(0), _lit(1)]), "add-not"))
    # A comparison for another of its family: `(lt a b)` expands to
    # `threshold (deviation b a)`, and the parser's own macros rebuild
    # the sibling forms from the operands, so the replacement text is
    # exact.  Exp 21 planted three of its eight faults here.
    if src is not None and src.startswith("(") and src.split(" ", 1)[0][1:] in _COMPARE:
        mine = src.split(" ", 1)[0][1:]
        operands = _compare_operands(node, mine)
        if operands is not None:
            left, right = operands
            for other, make in _COMPARE.items():
                if other == mine:
                    continue
                rep = None
                if text(left) is not None and text(right) is not None:
                    rep = f"({other} {text(left)} {text(right)})"
                edits.append(("compare", f"`{mine}` should be `{other}`", rep, make([left, right], None),
                              ("compare", other)))
    # `(sub a b)` is `(merge a (mul -1 b))`: the two for each other.
    if node.op == MERGE and len(a) == 2 and isinstance(a[0], Node) and isinstance(a[1], Node) and src is not None:
        b = a[1]
        if src.startswith("(sub ") and b.op == MUL and len(b.args) == 2 and b.args[0].op == LIT_INT \
                and int(b.args[0].args[0]) == -1 and isinstance(b.args[1], Node):
            inner = b.args[1]
            rep = f"(merge {text(a[0])} {text(inner)})" if text(a[0]) and text(inner) else None
            edits.append(("operator", "`sub` should be `merge`", rep, Node(op=MERGE, args=[a[0], inner]), "sub>merge"))
        elif src.startswith("(sub ") and b.op == LIT_INT and int(b.args[0]) < 0:
            rep = f"(merge {text(a[0])} {-int(b.args[0])})" if text(a[0]) else None
            edits.append(("operator", "`sub` should be `merge`", rep,
                          Node(op=MERGE, args=[a[0], _lit(-int(b.args[0]))]), "sub>merge"))
        elif src.startswith("(merge "):
            rep = f"(sub {text(a[0])} {text(b)})" if text(a[0]) and text(b) else None
            edits.append(("operator", "`merge` should be `sub`", rep,
                          Node(op=MERGE, args=[a[0], Node(op=MUL, args=[_lit(-1), b])]), "merge>sub"))
    # An operator for another of its family.
    from core.observability import suggest_alternatives
    for alt in suggest_alternatives(node.op):
        alt_name = SIGNATURES[alt]["name"]
        mine = SIGNATURES[node.op]["name"]
        rep = None
        if src is not None and src.startswith("(" + mine + " "):
            rep = "(" + alt_name + src[len(mine) + 1:]
        edits.append(("operator", f"`{mine}` should be `{alt_name}`", rep,
                      Node(op=alt, args=list(a)), ("operator", alt)))
    return edits


def _degenerate(body: Node, path: Tuple[int, ...]) -> bool:
    """True when the edit at `path` left an ancestor within three levels
    with two structurally identical operands -- `(lt x x)` -- which is
    how an exchanged reference passes a few examples by making a test
    constant."""
    for up in (1, 2, 3):
        if len(path) < up:
            break
        parent = _at(body, path[:-up])
        if parent is None:
            continue
        kids = [k for k in parent.args if isinstance(k, Node)]
        if len(kids) == 2 and repr(kids[0]) == repr(kids[1]):
            return True
    return False


def _at(node: Node, path: Tuple[int, ...]) -> Optional[Node]:
    for i in path:
        if not isinstance(node, Node) or i >= len(node.args) or not isinstance(node.args[i], Node):
            return None
        node = node.args[i]
    return node


def _perturbed(expr: Node, limit_per_literal: int = 8) -> List[Node]:
    """Nearby inputs: the expression with one of its literal arguments
    changed -- a character deleted, a digit / space / `.` inserted, a
    number nudged."""
    out: List[Node] = []
    spots: List[Tuple[Tuple[int, ...], Node]] = []

    def find(node: Node, path: Tuple[int, ...]) -> None:
        for i, arg in enumerate(node.args):
            if isinstance(arg, Node):
                if arg.op in (LIT_INT, LIT_TEXT) and _span(arg) is not None:
                    spots.append((path + (i,), arg))
                else:
                    find(arg, path + (i,))

    find(expr, ())
    for path, lit in spots:
        variants: List[Node] = []
        if lit.op == LIT_INT:
            v = int(lit.args[0])
            for nv in (v + 1, v - 1, 0, -v, v * 2, v // 2):
                if nv != v:
                    variants.append(_lit(nv))
        else:
            t = str(lit.args[0])
            n = len(t)
            # Where an insertion tells edits apart: at the ends of words --
            # the end of the text and before the first two separators.
            ends = [n] + [i for i, ch in enumerate(t) if ch in " ,;:" + chr(10)][:2]
            for i in ends:
                for ins in ("1", ".", "-", "a"):
                    variants.append(Node(op=LIT_TEXT, args=[t[:i] + ins + t[i:]]))    # one inserted at a word's end
            for i in sorted({0, n // 2, max(n - 1, 0)}):
                if n:
                    variants.append(Node(op=LIT_TEXT, args=[t[:i] + t[i + 1:]]))       # a character deleted
        for v in variants[:limit_per_literal + 6]:
            out.append(_replace(expr, path, v))
    return out


def locate(compiled: Node, source: str, expr: Node, passes: Callable[[Any], bool],
           others: List[Tuple[Node, Callable[[Any], bool]]], frame: Any,
           closures: List[Closure], *, max_steps: int, budget_s: float = 2.0,
           literals: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
    """The single-node edit -- of a user def the example ran through, or
    of the example's own expression -- that makes `expr` satisfy
    `passes` and the most of `others` besides.  Deepest first; the search
    stops at an edit that fixes every example, or at the budget, and
    reports the best it found."""
    symbols = getattr(compiled, "symbols", None)
    name_of = (lambda i: symbols.name_of(i)) if symbols else (lambda i: None)

    def text(node: Node) -> Optional[str]:
        s = _span(node)
        return source[s[0]:s[1]] if s and s[0] is not None and s[1] is not None and s[1] <= len(source) else None

    def run(node: Node) -> Any:
        rt = Runtime(max_steps=max_steps)
        rt.env = frame
        return evaluate(node, rt)

    started = time.perf_counter()
    probes = 0
    best: Optional[Dict[str, Any]] = None

    full: List[Dict[str, Any]] = []          # every edit that fixes all the examples

    def rank(found: Dict[str, Any]) -> Tuple[int, int, int, int]:
        return (found["others_passing"], 1 if found.get("replacement") else 0,
                -found.get("impact", 0), _PRIORITY.get(found["kind"], 0))

    def consider(found: Dict[str, Any]) -> bool:
        nonlocal best
        if best is None or rank(found) > rank(best):
            best = found
        if found["others_passing"] == len(others) and found.get("replacement"):
            full.append(found)
        # Q115: the search does not stop at the first full fix; every one is
        # scored by impact at the end.  Eight are enough to choose from.
        return len(full) >= 64

    # Nearby inputs, and what the program answers on them now.
    nearby = _perturbed(expr) + [p for other_expr, _ in others for p in _perturbed(other_expr)]
    nearby = nearby[:48]
    baseline: List[Any] = []

    # Targets: each called user def's body, then the expression itself.
    targets: List[Tuple[Optional[Closure], Node, Any]] = [(c, c.body, c.env) for c in closures if c.name is not None]
    if not targets:
        targets.append((None, expr, frame))

    for closure, body, scope_frame in targets:
        params = [closure.param] if closure is not None else []
        nodes: List[Any] = []
        _walk(body, (), 0, nodes)
        scopes = _scopes(body)
        nodes.sort(key=lambda c: (-c[2], c[0]))
        for path, node, depth, anchor in nodes:
            if anchor is None:
                continue
            for kind, why, replacement, new, key in _edits(node, scopes.get(id(node), []), params, name_of, text, literals):
                if _span(node) is None:
                    # A node the parser synthesised inside a macro: the edit
                    # is reported at the macro form, and its text is a lead,
                    # not a replacement, unless the edit made one itself.
                    if kind not in ("drop-minus", "drop-not", "ref", "literal"):
                        replacement = None
                if time.perf_counter() - started > budget_s:
                    if best is not None:
                        best["budget"] = True
                        return best
                    return {"kind": "budget", "probes": probes}
                probes += 1
                fixed_others = 0
                if closure is not None:
                    name = closure.name
                    if name not in scope_frame:
                        continue
                    edited_body = _replace(body, path, new)
                    if kind == "ref" and _degenerate(edited_body, path):
                        continue
                    probe = Closure(param=closure.param, body=edited_body, env=closure.env,
                                    caps=closure.caps, enclosed=closure.enclosed, owner=closure.owner)
                    probe.name = name
                    scope_frame[name] = probe
                    try:
                        try:
                            value = run(expr)
                        except Exception:      # noqa: BLE001 -- a probe that faults is not a fix
                            continue
                        if not passes(value):
                            continue
                        for other_expr, other_passes in others:
                            try:
                                if other_passes(run(other_expr)):
                                    fixed_others += 1
                            except Exception:  # noqa: BLE001
                                pass
                    finally:
                        scope_frame[name] = closure
                else:
                    edited = _replace(body, path, new)
                    try:
                        value = run(edited)
                    except Exception:          # noqa: BLE001
                        continue
                    if not passes(value):
                        continue
                    # The other examples are the same expression with other
                    # inputs: the same edit at the same path, where the shape agrees.
                    for other_expr, other_passes in others:
                        there = _at(other_expr, path)
                        if there is None or there.op != node.op:
                            continue
                        again = [e for e in _edits(there, _scopes(other_expr).get(id(there), []), params, name_of, text, literals)
                                 if e[4] == key]
                        if not again:
                            continue
                        try:
                            if other_passes(run(_replace(other_expr, path, again[0][3]))):
                                fixed_others += 1
                        except Exception:      # noqa: BLE001
                            pass
                found = {
                    "kind": kind, "edit": why, "replacement": replacement,
                    "def": name_of(closure.name) if closure is not None else None,
                    "span": list(_span(anchor)),
                    "excerpt": text(anchor),
                    "within": _span(node) is None,
                    "others_passing": fixed_others, "others": len(others), "probes": probes,
                    "_closure": closure, "_body": edited_body if closure is not None else None,
                }
                if consider(found):
                    break
            else:
                continue
            break
        else:
            continue
        break

    # Q115: score every full fix by how many nearby inputs it changes the
    # answer on, and report the smallest.
    if full and nearby:
        for p in nearby:
            try:
                baseline.append(run(p))
            except Exception:      # noqa: BLE001
                baseline.append(("trap",))
        for found in full:
            closure, edited = found["_closure"], found["_body"]
            if closure is None or edited is None:
                continue
            probe = Closure(param=closure.param, body=edited, env=closure.env,
                            caps=closure.caps, enclosed=closure.enclosed, owner=closure.owner)
            probe.name = closure.name
            closure.env[closure.name] = probe
            changed = 0
            try:
                for p, before in zip(nearby, baseline):
                    try:
                        after = run(p)
                    except Exception:      # noqa: BLE001
                        after = ("trap",)
                    if not _same_value(before, after):
                        changed += 1
            finally:
                closure.env[closure.name] = closure
            found["impact"] = changed
            found["nearby"] = len(nearby)
        best = max(full, key=rank)
        # The runner-up edits, for a reader who wants to see the choice
        # (Exp 28 run 2, one session's ask).
        ranked = sorted(full, key=rank, reverse=True)
        tied = [f for f in ranked[1:] if rank(f) == rank(best) and f["kind"] == best["kind"]
                and f.get("replacement") == best.get("replacement") and f.get("excerpt") != best.get("excerpt")]
        if tied:
            best["tied_with"] = [{"excerpt": f.get("excerpt"), "span": f.get("span"), "def": f.get("def")}
                                 for f in tied[:6]]
        best["also"] = [{"edit": f["edit"], "replacement": f.get("replacement"), "impact": f.get("impact"),
                         "kind": f["kind"], "excerpt": f.get("excerpt")}
                        for f in ranked[1:4] if f not in tied]
    if best is not None:
        best.pop("_closure", None); best.pop("_body", None)
        return best
    return {"kind": "none", "probes": probes}


def _same_value(a: Any, b: Any) -> bool:
    if a.__class__ is int and b.__class__ is int:
        return a == b
    if isinstance(a, tuple) or isinstance(b, tuple):
        return a == b
    from core.cli import format_value
    try:
        return format_value(a) == format_value(b)
    except Exception:      # noqa: BLE001
        return False


def user_closures(rt: Runtime, source_len: int, library: Any) -> List[Closure]:
    """The named closures of a run that were defined in the user's source
    and were called, most-called first."""
    out = []
    for c in rt.named:
        s = _span(c.body)
        if c.calls <= 0 or s is None or s[0] is None or s[1] is None or s[1] > source_len:
            continue
        out.append(c)
    out.sort(key=lambda c: -c.calls)
    return out


def example_expression(compiled: Node) -> Node:
    """The innermost body of the program's let chain: the expression."""
    node = compiled
    while node.op == LET and len(node.args) == 3 and isinstance(node.args[2], Node):
        node = node.args[2]
    return node
