"""Questions about a program, answered from its tree (2026-09-18).

Exp 28's sessions read the whole program on six of eight tasks, and on
one of them only to find a string that occurs once, because the fault
line named an excerpt that occurs four times.  The card's second cost
is the table a model keeps in its head -- which def is which, what it
takes, what is in scope here, who calls it -- and the eight sessions
of Exp 24 all said they kept one.  The machine holds all of it.  This
module answers, so that a model reads the def it asked about and not
the file:

    defs(source)              every def of the program: name, span, parameters
    def_text(source, name)    one def's text and span
    scope_at(source, offset)  the names bound at a point, and what bound them
    callers(source, name)     the defs whose bodies mention a name
    callees(source, name)     the names a def's body mentions
    find_in_def(source, name, text)   the span of a text that occurs once in a def

Everything is on the parsed tree, before the compiler drops what the
expression does not use, so a def no one calls is still a def.  The
prelude's own defs carry no span and are not listed; the card lists
them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.surface import line_col, parse_with_prelude
from core.tokens import LAMBDA, LET, LIT_INT, REF, Node


def _span(node: Any) -> Optional[Tuple[int, int]]:
    s = getattr(node, "span", None)
    if s is None or s[0] is None or s[1] is None:
        return None
    return s


def _tree(source: str):
    tree = parse_with_prelude(source)
    return tree, tree.symbols


def defs(source: str) -> List[Dict[str, Any]]:
    """The program's own defs, in order, with their spans and parameter names."""
    tree, symbols = _tree(source)
    out = []
    node = tree
    while node.op == LET and len(node.args) == 3:
        name_id = int(node.args[0].args[0])
        value = node.args[1]
        span = _span(value)
        if span is not None and span[1] <= len(source):
            params = []
            inner = value
            while inner.op == LAMBDA and len(inner.args) == 2 and _span(inner) == span:
                params.append(symbols.name_of(int(inner.args[0].args[0])) or "?")
                inner = inner.args[1]
            line, col = line_col(source, span[0])
            out.append({"name": symbols.name_of(name_id) or f"#{name_id}", "span": list(span),
                        "line": line, "col": col, "params": params,
                        "chars": span[1] - span[0]})
        node = node.args[2]
    return out


def def_text(source: str, name: str) -> Optional[Dict[str, Any]]:
    for d in defs(source):
        if d["name"] == name:
            a, b = d["span"]
            return {**d, "text": source[a:b]}
    return None


def _walk_refs(node: Node, out: List[int]) -> None:
    if node.op == REF and node.args and node.args[0].op == LIT_INT:
        out.append(int(node.args[0].args[0]))
    for arg in node.args:
        if isinstance(arg, Node):
            _walk_refs(arg, out)


def _def_nodes(source: str) -> Dict[str, Node]:
    tree, symbols = _tree(source)
    out: Dict[str, Node] = {}
    node = tree
    while node.op == LET and len(node.args) == 3:
        value = node.args[1]
        span = _span(value)
        if span is not None and span[1] <= len(source):
            out[symbols.name_of(int(node.args[0].args[0])) or "?"] = value
        node = node.args[2]
    return out


def callees(source: str, name: str) -> List[str]:
    """The program's defs a def's body mentions (not its own parameters)."""
    tree, symbols = _tree(source)
    nodes = _def_nodes(source)
    if name not in nodes:
        return []
    ids: List[int] = []
    _walk_refs(nodes[name], ids)
    names = {symbols.name_of(i) for i in ids}
    return [d for d in nodes if d in names and d != name]


def callers(source: str, name: str) -> List[str]:
    """The program's defs whose bodies mention `name`."""
    return [d for d in _def_nodes(source) if name in callees(source, d)]


def scope_at(source: str, offset: int) -> Dict[str, Any]:
    """The names bound at a character offset: the program's defs, and
    the parameters and lets of every form enclosing the offset,
    innermost last."""
    tree, symbols = _tree(source)
    top = [d["name"] for d in defs(source)]
    local: List[Dict[str, Any]] = []
    where: Optional[Dict[str, Any]] = None

    def go(node: Node, bound: List[Dict[str, Any]]) -> None:
        nonlocal where
        span = _span(node)
        inside = span is not None and span[0] <= offset < span[1] and span[1] <= len(source)
        if inside:
            where = {"span": list(span), "excerpt": source[span[0]:span[1]]} if where is None or (span[1] - span[0]) < (where["span"][1] - where["span"][0]) else where
        if node.op == LAMBDA and len(node.args) == 2 and node.args[0].op == LIT_INT:
            pname = symbols.name_of(int(node.args[0].args[0]))
            body = node.args[1]
            b = bound + ([{"name": pname, "by": "parameter"}] if pname and inside else [])
            if inside:
                local[:] = b
            go(body, b)
            return
        if node.op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
            lname = symbols.name_of(int(node.args[0].args[0]))
            value, body = node.args[1], node.args[2]
            vs = _span(value)
            is_def = vs is not None and vs[1] <= len(source) and lname in top
            b = bound + ([{"name": lname, "by": "let"}] if lname and not is_def and inside else [])
            if inside and not is_def:
                local[:] = b
            go(value, b)
            go(body, b)
            return
        for arg in node.args:
            if isinstance(arg, Node):
                go(arg, bound)

    go(tree, [])
    return {"offset": offset, "at": where, "defs": top, "local": local}


def find_in_def(source: str, name: str, text: str) -> Dict[str, Any]:
    """The span of `text` inside the def named `name`, which must occur
    exactly once there (it may occur elsewhere in the program)."""
    d = def_text(source, name)
    if d is None:
        return {"ok": False, "message": f"no def named {name!r}; the defs are " +
                ", ".join(x["name"] for x in defs(source))}
    n = d["text"].count(text)
    if n != 1:
        return {"ok": False, "message": f"{text!r} occurs {n} times in def {name}; it must occur once"}
    start = d["span"][0] + d["text"].index(text)
    return {"ok": True, "span": [start, start + len(text)], "def": name}
