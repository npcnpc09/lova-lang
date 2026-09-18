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

from core.runtime import Closure, Node, Runtime, StepTrap, evaluate
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
           literals: Optional[List[int]] = None, ceiling: Optional[int] = None) -> Optional[Dict[str, Any]]:
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

    def run(node: Node, cap: Optional[int] = None) -> Any:
        rt = Runtime(max_steps=cap or max_steps)
        rt.env = frame
        return evaluate(node, rt)

    started = time.perf_counter()
    probes = 0
    best: Optional[Dict[str, Any]] = None

    full: List[Dict[str, Any]] = []          # every edit that fixes all the examples

    def rank(found: Dict[str, Any]) -> Tuple[int, int, int, int]:
        return (found["others_passing"], 1 if found.get("replacement") else 0,
                -found.get("impact", 0), _PRIORITY.get(found["kind"], 0))

    first_full: Optional[float] = None

    def consider(found: Dict[str, Any]) -> bool:
        nonlocal best, first_full
        if best is None or rank(found) > rank(best):
            best = found
        if found["others_passing"] == len(others) and found.get("replacement"):
            full.append(found)
            if first_full is None:
                first_full = time.perf_counter()
        # Q115: the search does not stop at the first full fix; every one is
        # scored by impact at the end.  Eight are enough to choose from --
        # and a quarter of the budget more is enough to look for them,
        # where a probe costs a second (Exp 29).
        return len(full) >= 64

    # Nearby inputs, and what the program answers on them now.
    nearby = _perturbed(expr) + [p for other_expr, _ in others for p in _perturbed(other_expr)]
    nearby = nearby[:48]
    baseline: List[Any] = []

    # A zero-parameter def is a value computed once, with the defs as
    # they were: g2048's `all-cells` holds the keys `ckey` made before
    # the probe changed `ckey`, so a probe that fixes `ckey` still fails
    # (Exp 29, Q120).  The constants of the let chain that reference
    # the probed def, directly or through another constant, are
    # recomputed while the probe is installed and restored after.
    constants: Dict[int, Node] = {}
    node = compiled
    while node.op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
        cname, cvalue = int(node.args[0].args[0]), node.args[1]
        if isinstance(cvalue, Node) and cvalue.op != LAMBDA:
            constants[cname] = cvalue
        node = node.args[2]
    refs_of: Dict[int, set] = {}

    def refs(n: Node, out: set) -> None:
        if n.op == REF and n.args and isinstance(n.args[0], Node) and n.args[0].op == LIT_INT:
            out.add(int(n.args[0].args[0]))
        for a in n.args:
            if isinstance(a, Node):
                refs(a, out)

    for cname, cvalue in constants.items():
        acc: set = set()
        refs(cvalue, acc)
        refs_of[cname] = acc

    def dependents(name_id: int) -> List[int]:
        """The constants that reach `name_id`, in let order."""
        hit = {name_id}
        changed = True
        while changed:
            changed = False
            for cname in constants:
                if cname not in hit and refs_of[cname] & hit:
                    hit.add(cname)
                    changed = True
        return [c for c in constants if c in hit and c != name_id]

    def frame_of(name_id: int) -> Any:
        env = frame
        while env is not None:
            if name_id in env.keys():
                return env
            env = getattr(env, "parent", None)
        return None

    def install(closure: Any, body: Node):
        """Install a rebuilt closure -- or, for a ("const", name) target,
        the constant recomputed from its edited value -- and recompute the
        constants that depend on it; the returned function undoes all."""
        saved: List[Tuple[Any, int, Any]] = []
        if isinstance(closure, Closure):
            rebuilt = Closure(param=closure.param, body=body, env=closure.env,
                              caps=closure.caps, enclosed=closure.enclosed, owner=closure.owner)
            rebuilt.name = closure.name
            name_id = closure.name
            closure.env[name_id] = rebuilt

            def restore() -> None:
                closure.env[name_id] = closure
        else:
            name_id = closure[1]
            env = frame_of(name_id)
            old_value = env[name_id]
            try:
                env[name_id] = run(body, max_steps)
            except Exception:  # noqa: BLE001 -- the edited constant does not evaluate: no fix
                env[name_id] = old_value
                return lambda: None

            def restore() -> None:
                env[name_id] = old_value
        try:
            for cname in dependents(name_id):
                cenv = frame_of(cname)
                if cenv is None:
                    continue
                saved.append((cenv, cname, cenv[cname]))
                cenv[cname] = run(constants[cname], max_steps)
        except Exception:      # noqa: BLE001 -- a constant the probe breaks: the probe is no fix
            pass

        def undo() -> None:
            for cenv, cname, was in reversed(saved):
                cenv[cname] = was
            restore()
        return undo

    # Targets: each called user def's body (in the order given: the most
    # suspect first), then the expression itself.  Within a def the edits
    # go by kind, the kinds with the fewest candidates first -- operands
    # or branches swapped, a minus or a `not` dropped, a comparison or
    # an operator for its sibling, a literal nudged, and only then a name
    # for another in scope (every ref times every name) -- deepest first
    # within a kind; and a minus or a `not` added at every node, two
    # probes a node, come last of all, across every def.  Under a budget
    # this is the order that finds a fault of any kind soonest when a
    # probe is dear (Exp 29: a probe of the noughts-and-crosses search
    # is a second, and the budget went on refs before the comparison).
    targets: List[Tuple[Any, Node, Any]] = [(c, c.body, c.env) for c in closures if c.name is not None]
    # A zero-parameter def is a constant, not a closure, and its fault
    # is in the value it was computed from -- ttt's `powers` with one
    # power of three off by one (Exp 29, Q120).  Its value node is a
    # target like a def's body: edited, re-evaluated in its frame, the
    # constants that depend on it recomputed, and the example run.
    # Constants come first: their edits are few and cheap to try.
    targets = ([(("const", cname), cvalue, frame_of(cname)) for cname, cvalue in constants.items()
                if text(cvalue) is not None and frame_of(cname) is not None] + targets)
    if not targets:
        targets.append((None, expr, frame))
    _ORDER = {"swap-operands": 0, "swap-branches": 0, "drop-minus": 0, "drop-not": 0,
              "compare": 1, "operator": 2, "literal": 3, "ref": 4, "add-minus": 9, "add-not": 9}

    def order(edit) -> float:
        kind, key = edit[0], edit[4]
        rank = _ORDER.get(kind, 5)
        if kind == "literal" and isinstance(key, tuple) and key[1] != "neg" and abs(key[1]) > 1:
            rank += 0.5                        # a constant from the examples' data: after the nudges
        return rank

    plans: List[List[Any]] = []
    for closure, body, scope_frame in targets:
        params = [closure.param] if isinstance(closure, Closure) else []
        nodes: List[Any] = []
        _walk(body, (), 0, nodes)
        nodes.sort(key=lambda c: (-c[2], c[0]))
        scopes = _scopes(body)
        items: List[Any] = []
        for path, node, depth, anchor in nodes:
            if anchor is None:
                continue
            for edit in _edits(node, scopes.get(id(node), []), params, name_of, text, literals):
                items.append((order(edit), closure, body, scope_frame, params, path, node, anchor, edit))
        items.sort(key=lambda it: it[0])       # stable: depth order kept within a kind
        plans.append(items)

    def rounds():
        for additions in (False, True):
            for items in plans:
                for it in items:
                    if (it[0] >= 9) == additions:
                        yield it[1:]

    deferred: List[Any] = []     # probes the step cap cut off: inconclusive, retried larger


    def roomy(cap: int) -> int:
        # A probe that passed the failing example is rare, so its other
        # examples may have the program's own ceiling.
        return ceiling if ceiling else cap * 16

    def probe(item, cap: int):
        """One edit tried: the `found` record when the example passes,
        None when it does not, or `StepTrap` when the cap cut it off."""
        nonlocal probes
        closure, body, scope_frame, params, path, node, anchor, edit = item
        kind, why, replacement, new, key = edit
        if _span(node) is None:
            # A node the parser synthesised inside a macro: the edit
            # is reported at the macro form, and its text is a lead,
            # not a replacement, unless the edit made one itself.
            if kind not in ("drop-minus", "drop-not", "ref", "literal"):
                replacement = None
        probes += 1
        fixed_others = 0
        edited_body = None
        if closure is not None:
            name = closure.name if isinstance(closure, Closure) else closure[1]
            if scope_frame is None or name not in scope_frame:
                return None
            edited_body = _replace(body, path, new)
            if kind == "ref" and _degenerate(edited_body, path):
                return None
            undo = install(closure, edited_body)
            try:
                try:
                    value = run(expr, cap)
                except StepTrap:
                    return StepTrap
                except Exception:      # noqa: BLE001 -- a probe that faults is not a fix
                    return None
                if not passes(value):
                    return None
                # The others run with room: an example that trapped
                # early says nothing of what its fixed run costs.
                for other_expr, other_passes in others:
                    try:
                        if other_passes(run(other_expr, roomy(cap))):
                            fixed_others += 1
                    except Exception:  # noqa: BLE001
                        pass
            finally:
                undo()
        else:
            edited = _replace(body, path, new)
            try:
                value = run(edited, cap)
            except StepTrap:
                return StepTrap
            except Exception:          # noqa: BLE001
                return None
            if not passes(value):
                return None
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
                    if other_passes(run(_replace(other_expr, path, again[0][3]), roomy(cap))):
                        fixed_others += 1
                except Exception:      # noqa: BLE001
                    pass
        # The enclosing expression (Exp 29, L4 and L6: "ten characters of
        # context around the span would turn a confident guess into a
        # check"): the nearest ancestor with a span whose text is short.
        context = None
        for up in range(1, len(path) + 1):
            parent = _at(body, path[:-up])
            if parent is None:
                break
            ptext = text(parent)
            if ptext is not None:
                if len(ptext) <= 100:
                    context = ptext
                break
        return {
            "kind": kind, "edit": why, "replacement": replacement, "context": context,
            "def": (name_of(closure.name) if isinstance(closure, Closure)
                    else name_of(closure[1]) if closure is not None else None),
            "constant": closure is not None and not isinstance(closure, Closure),
            "span": list(_span(anchor)),
            "excerpt": text(anchor),
            "within": _span(node) is None,
            "others_passing": fixed_others, "others": len(others), "probes": probes,
            "_closure": closure, "_body": edited_body,
        }

    def out_of_time() -> bool:
        now = time.perf_counter()
        if first_full is not None and now - first_full > budget_s / 4:
            return True
        return now - started > budget_s

    stopped = False
    for item in rounds():
        if out_of_time():
            if best is not None:
                best["budget"] = not full
                if full:
                    stopped = True
                    break
                return best
            return {"kind": "budget", "probes": probes}
        found = probe(item, max_steps)
        if found is StepTrap:
            deferred.append(item)
            continue
        if found is not None and consider(found):
            stopped = True
            break
    # The probes the cap cut off, again with more room: a fix for an
    # example that trapped early may run far longer than the trap did
    # (Exp 29, ttt-b: the trap at 5 000 steps, the fixed run at 790 000).
    cap = max_steps
    while deferred and not stopped and ceiling and cap < ceiling:
        cap = min(cap * 16, ceiling)
        again, deferred = deferred, []
        for item in again:
            if out_of_time():
                if best is not None:
                    best["budget"] = not full
                    if full:
                        stopped = True
                        break
                    return best
                return {"kind": "budget", "probes": probes}
            found = probe(item, cap)
            if found is StepTrap:
                deferred.append(item)
                continue
            if found is not None and consider(found):
                stopped = True
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
            undo = install(closure, edited)
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
                undo()
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
                         "kind": f["kind"], "excerpt": f.get("excerpt"), "def": f.get("def"),
                         "span": f.get("span"), "context": f.get("context")}
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


def user_closures(rt: Runtime, source_len: int, library: Any, *, called: bool = True) -> List[Closure]:
    """The named closures of a run that were defined in the user's source
    and were called (or, with `called=False`, merely defined), most-called
    first."""
    out = []
    for c in rt.named:
        s = _span(c.body)
        if (called and c.calls <= 0) or s is None or s[0] is None or s[1] is None or s[1] > source_len:
            continue
        out.append(c)
    out.sort(key=lambda c: -c.calls)
    return out


def deepest_frame(closures: List[Closure]) -> Any:
    """The frame the example's expression must be evaluated in: the one
    every other def's frame is an ancestor of.  A chain of defs shares one
    frame until a def takes a name the prelude already binds -- ttt.lova's
    `lines` (Exp 29) -- where the letrec opens a child frame, and the defs
    after it, `main` among them, live there.  Probing from the first
    closure's frame then finds no `main` and every edit fails."""
    frames = []
    for c in closures:
        if all(f is not c.env for f in frames):
            frames.append(c.env)
    if not frames:
        return None

    def ancestors(env: Any) -> List[Any]:
        out = []
        while env is not None:
            out.append(env)
            env = getattr(env, "parent", None)
        return out

    best, best_depth = frames[0], -1
    for f in frames:
        chain = ancestors(f)
        if all(any(g is x for x in chain) for g in frames) and len(chain) > best_depth:
            best, best_depth = f, len(chain)
    return best


def example_expression(compiled: Node) -> Node:
    """The innermost body of the program's let chain: the expression."""
    node = compiled
    while node.op == LET and len(node.args) == 3 and isinstance(node.args[2], Node):
        node = node.args[2]
    return node
