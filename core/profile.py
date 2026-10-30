"""The step profiler's driver: where a call's steps went, by function.

The native runtime does the counting (`native/lova-rt/src/callprof.rs`):
a session ``call`` with ``"profile": true`` comes back with a calling-
context tree, one row per node --

    [parent, body ordinal, name id, owner name id, calls, inclusive]

-- whose root (row 0) is the call itself.  A node's self steps are its
inclusive less its children's; the root's self is what was spent outside
every closure.  This module names the nodes (the name id through the
tree's symbols, the body through its preorder place to a source span),
sums them over a range of calls, and prints

  * the functions, costliest self first, with inclusive (outermost
    activation only, so recursion is not counted twice) and calls;
  * the dearest call alone, the same table;
  * optionally the folded stacks (``a;b;c 123`` per line), the input of
    every flame-graph tool (flamegraph.pl, inferno, speedscope).

A function is a closure's body: a `def` of several parameters is one
lambda per parameter, the outer named and the inner ones attributed to
it (``f/2`` for the second), and an anonymous lambda inside a def is
``f/lambda`` at its line.  `lova profile` (core/cli.py) is the command; a
game's own driver can call `Profile.add(session.profile, steps)` after
each ``session.call(..., profile=True)``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.runtime import Node
from core.tokens import LAMBDA

Row = Sequence[Any]


# --- naming the nodes --------------------------------------------------------

class Namer:
    """Body ordinal -> (label, where) for one built program."""

    def __init__(self, tree: Node, source: Optional[str] = None) -> None:
        from core.native import _index
        self.tree = tree
        self.source = source
        self.order, self.parent = _index(tree)
        self.symbols = getattr(tree, "symbols", None)
        self._cache: Dict[Tuple[Any, Any, Any], Tuple[str, str]] = {}
        self._exp: Any = None

    def name(self, ident: Optional[int]) -> Optional[str]:
        if ident is None:
            return None
        if self.symbols is not None:
            got = self.symbols.name_of(ident)
            if got:
                return got
        return f"#{ident}"

    def _span(self, ordinal: Optional[int]):
        if not isinstance(ordinal, int) or not 0 <= ordinal < len(self.order):
            return None
        node: Optional[Node] = self.order[ordinal]
        while node is not None:
            span = getattr(node, "span", None)
            if span is not None:
                return span
            node = self.parent.get(id(node))
        return None

    def where(self, ordinal: Optional[int]) -> str:
        span = self._span(ordinal)
        if span is None or self.source is None:
            return "" if span is None else f"@{span[0]}"
        try:
            if self._exp is None:
                from core.surface import expansion
                self._exp = expansion(self.source)
            o, line, col = self._exp.where(span[0])
            return f"{o}:{line}" if o is not None else f"line {line}"
        except Exception:                                   # noqa: BLE001
            return f"@{span[0]}"

    def _depth(self, ordinal: Optional[int]) -> int:
        """How many lambdas this body is directly inside (a curried def's
        second parameter is 2): bodies that are themselves lambdas."""
        if not isinstance(ordinal, int) or not 0 <= ordinal < len(self.order):
            return 1
        depth = 1
        node = self.parent.get(id(self.order[ordinal]))     # the lambda
        while node is not None:
            above = self.parent.get(id(node))
            if above is None or above.op != LAMBDA or above.args[-1] is not node:
                break
            depth += 1
            node = above
        return depth

    def label(self, row: Row) -> Tuple[str, str]:
        """(label, where) for one row of a profile."""
        _, body, name, owner, _, _ = row
        key = (body, name, owner)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if body is None:
            out = ("(outside every closure)", "")
        else:
            where = self.where(body)
            own = self.name(name)
            if own is not None:
                out = (own, where)
            else:
                d = self._depth(body)
                base = self.name(owner) or "(top)"
                out = (f"{base}/{d}" if d > 1 else f"{base}/lambda", where)
        self._cache[key] = out
        return out


# --- summing -----------------------------------------------------------------

class Profile:
    """Profiles of many calls, summed; the dearest one kept apart."""

    def __init__(self, namer: Namer) -> None:
        self.namer = namer
        self.calls = 0
        self.steps = 0
        self.self_: Dict[Tuple[str, str], int] = defaultdict(int)
        self.incl: Dict[Tuple[str, str], int] = defaultdict(int)
        self.count: Dict[Tuple[str, str], int] = defaultdict(int)
        self.folded: Dict[str, int] = defaultdict(int)
        self.dearest: Optional[Tuple[int, Any, List[Row]]] = None

    def add(self, rows: Optional[List[Row]], steps: int, tag: Any = None) -> None:
        if not rows:
            return
        self.calls += 1
        self.steps += steps
        if self.dearest is None or steps > self.dearest[0]:
            self.dearest = (steps, tag, rows)
        for key, s, i, c in flat(rows, self.namer):
            self.self_[key] += s
            self.incl[key] += i
            self.count[key] += c
        for stack, s in folded(rows, self.namer).items():
            self.folded[stack] += s

    def table(self, top: int = 25) -> str:
        return render(self.self_, self.incl, self.count, self.steps, top,
                      per=max(self.calls, 1))

    def dearest_table(self, top: int = 15) -> str:
        if self.dearest is None:
            return "(no call profiled)"
        steps, _, rows = self.dearest
        s, i, c = defaultdict(int), defaultdict(int), defaultdict(int)
        for key, a, b, n in flat(rows, self.namer):
            s[key] += a
            i[key] += b
            c[key] += n
        return render(s, i, c, steps, top)

    def folded_text(self) -> str:
        return "".join(f"{k} {v}\n" for k, v in sorted(self.folded.items()) if v > 0)


def _selfs(rows: List[Row]) -> List[int]:
    child = [0] * len(rows)
    for r in rows[1:]:
        child[r[0]] += r[5]
    return [max(0, r[5] - child[i]) for i, r in enumerate(rows)]


def flat(rows: List[Row], namer: Namer):
    """(key, self, inclusive, calls) per node; a node's inclusive counts
    only when no node above it is the same function (recursion)."""
    selfs = _selfs(rows)
    keys = [namer.label(r) for r in rows]
    out = []
    for i, r in enumerate(rows):
        outer = True
        p = r[0]
        while p is not None:
            if keys[p] == keys[i]:
                outer = False
                break
            p = rows[p][0]
        out.append((keys[i], selfs[i], r[5] if outer else 0, r[4]))
    return out


_SEMI = re.compile(r"[; ]")


def folded(rows: List[Row], namer: Namer) -> Dict[str, int]:
    selfs = _selfs(rows)
    names: List[str] = []
    out: Dict[str, int] = defaultdict(int)
    for i, r in enumerate(rows):
        label, where = namer.label(r)
        me = _SEMI.sub("_", f"{label}" if i else "(call)")
        names.append(me if r[0] is None else f"{names[r[0]]};{me}")
        if selfs[i]:
            out[names[i]] += selfs[i]
    return out


def render(self_, incl, count, total: int, top: int, per: int = 1) -> str:
    keys = sorted(self_, key=lambda k: -self_[k])
    head = (f"{'self':>10} {'self%':>6} {'incl':>10} {'calls':>8}  function  (where)")
    if per > 1:
        head = (f"{'self/call':>10} {'self%':>6} {'incl/call':>10} {'calls/c':>8}  function  (where)")
    lines = [head]
    for k in keys[:top]:
        if self_[k] <= 0:
            continue
        label, where = k
        lines.append(f"{self_[k] / per:>10.0f} {100.0 * self_[k] / max(total, 1):>5.1f}% "
                     f"{incl[k] / per:>10.0f} {count[k] / per:>8.1f}  {label}"
                     + (f"  ({where})" if where else ""))
    return "\n".join(lines)


# --- the command -------------------------------------------------------------

def strip_last_form(source: str) -> Tuple[str, str]:
    """The program without its last top-level form, and that form."""
    depth, i, n = 0, 0, len(source)
    start = None
    last = (n, n)
    while i < n:
        ch = source[i]
        if ch == ";":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == '"':
            i += 1
            while i < n and source[i] != '"':
                i += 2 if source[i] == "\\" else 1
            i += 1
            continue
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                last = (start, i + 1)
        i += 1
    return source[:last[0]] + source[last[1]:], source[last[0]:last[1]]


def parse_range(text: str) -> Tuple[int, int]:
    lo, sep, hi = text.partition("..")
    if not sep:
        return int(lo), int(lo)
    return int(lo or 0), int(hi)


DRIVER = """
(def lova-profile-init [_] {init})
(def lova-profile-step [w k] {step})
(rec init lova-profile-init step lova-profile-step)
"""


def run(source: str, init: str, step: str, ticks: Tuple[int, int], *,
        max_steps: int = 400_000_000, build=None) -> Tuple[Profile, List[int]]:
    """Build ``source`` with its last form replaced by a driver, call
    ``init`` once and ``step`` (``w`` the world, ``k`` the tick) up to
    tick ``ticks[1]``, profiling ticks ``ticks[0]..ticks[1]``."""
    from core.native import open_session
    if build is None:
        from core.cli import build
    head, _ = strip_last_form(source)
    program = head.rstrip() + "\n" + DRIVER.format(init=init, step=step)
    tree, _ = build(program)
    s = open_session(tree, "on", max_steps=max_steps)
    prof = Profile(Namer(tree, program))
    costs: List[int] = []
    try:
        w = s.call(s.get("init"), 0)
        stepf = s.get("step")
        lo, hi = ticks
        for k in range(hi + 1):
            on = k >= lo
            nxt = s.call(stepf, w, k, profile=on)
            if on:
                costs.append(s.steps)
                prof.add(s.profile, s.steps, k)
            s.release(w)
            w = nxt
    finally:
        s.close()
    return prof, costs
