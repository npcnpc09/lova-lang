"""Stage-1 surface syntax: s-expression ↔ token sequence.

The text surface is a Lisp-like s-expression.  It is a **projection**
over the integer-sequence substrate, not the canonical representation
(Axiom 1).  Milestone 1 verifies round-trip losslessness: any program
authored at the surface can be encoded, decoded, and pretty-printed
back to a semantically-equivalent s-expression.

Example:

    >>> tree = parse("(merge (p 3) (tau 12))")
    >>> from core.tokens import encode, decode
    >>> data = encode(tree); tree2 = decode(data)
    >>> pretty(tree2)
    '(merge (p 3) (tau 12))'
"""

from __future__ import annotations

from typing import List, Tuple, Union

from core.tokens import (
    ALIASES, LIT_INT, Node, SIGNATURES, NAME_TO_TOKEN, Lit,
)


# --- tokenizer ---------------------------------------------------------------

def _tokenize(src: str) -> List[str]:
    """Split source into atomic text tokens.  Comments are ``;...`` to end of line."""
    out: List[str] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1; continue
        if c == ";":  # comment
            while i < len(src) and src[i] != "\n":
                i += 1
            continue
        if c in "()":
            out.append(c); i += 1; continue
        # atom (identifier or integer literal)
        j = i
        while j < len(src) and not src[j].isspace() and src[j] not in "();":
            j += 1
        out.append(src[i:j])
        i = j
    return out


# --- parser ------------------------------------------------------------------

def parse(src: str) -> Node:
    """Parse a single s-expression to a Node."""
    tokens = _tokenize(src)
    if not tokens:
        raise ValueError("empty source")
    tree, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        trailing = " ".join(tokens[pos:])
        raise ValueError(f"trailing input after expression: {trailing!r}")
    return tree


def _parse_expr(tokens: List[str], pos: int) -> Tuple[Node, int]:
    if pos >= len(tokens):
        raise ValueError("unexpected end of input")
    t = tokens[pos]
    if t == "(":
        # (operator arg1 arg2 ...)
        if pos + 1 >= len(tokens):
            raise ValueError("unexpected EOF after '('")
        op_sym = tokens[pos + 1]
        if op_sym == "(":
            raise ValueError("operator must be an identifier, not a sub-expression")
        op_name = ALIASES.get(op_sym, op_sym)
        if op_name not in NAME_TO_TOKEN:
            raise ValueError(f"unknown operator: {op_sym!r}")
        op_tok = NAME_TO_TOKEN[op_name]
        args: List[Node] = []
        cursor = pos + 2
        while cursor < len(tokens) and tokens[cursor] != ")":
            child, cursor = _parse_expr(tokens, cursor)
            args.append(child)
        if cursor >= len(tokens):
            raise ValueError(f"unclosed list starting at token {pos}")
        # arity check
        sig = SIGNATURES[op_tok]
        if sig["arity"] != "variadic" and len(args) != sig["arity"]:
            raise ValueError(
                f"{op_name}: expects {sig['arity']} args, got {len(args)}"
            )
        return Node(op=op_tok, args=args), cursor + 1  # consume ')'
    if t == ")":
        raise ValueError(f"unexpected ')' at token {pos}")
    # bare atom at top level: must be an integer literal
    try:
        n = int(t, 0)  # accepts decimal, 0x hex, 0b bin
    except ValueError as e:
        raise ValueError(f"bare atom must be an integer literal: {t!r}") from e
    return Lit(n), pos + 1


# --- pretty-printer ----------------------------------------------------------

def pretty(node: Node, unicode: bool = False) -> str:
    """Project a Node tree back to s-expression text.

    If ``unicode`` is True, uses Unicode aliases where available
    (``merge`` → ``⊕``, ``tau`` → ``τ`` etc.).  Default is ASCII for
    scripting compatibility on Windows shells.
    """
    return _pretty(node, unicode)


# Reverse mapping from canonical name to any Unicode alias.
_UNICODE_REVERSE = {v: k for k, v in ALIASES.items()}


def _pretty(node: Node, unicode: bool) -> str:
    if node.op == LIT_INT:
        return str(node.args[0])
    name = SIGNATURES[node.op]["name"]
    if unicode and name in _UNICODE_REVERSE:
        name = _UNICODE_REVERSE[name]
    if not node.args:
        return f"({name})"
    children = " ".join(_pretty(c, unicode) for c in node.args)
    return f"({name} {children})"


# --- round-trip helper -------------------------------------------------------

def round_trip(src: str) -> Tuple[bytes, str]:
    """Parse → encode → decode → pretty.  Returns (bytes, pretty-printed)."""
    from core.tokens import encode, decode
    tree = parse(src)
    data = encode(tree)
    back = decode(data)
    out_src = pretty(back)
    return data, out_src


# --- self-test ---------------------------------------------------------------

def _self_test() -> None:
    cases = [
        "(p 12)",
        "(tau 12)",
        "(merge (p 3) (tau 12))",
        "(seq (p 3) (p 4) (p 5))",
        "(budget 100 (p 12))",
        "(surprise 10 (p 12))",
        "(let 1 12 (p (ref 1)))",     # integer-as-name placeholder in MVP
    ]
    for src in cases:
        data, back = round_trip(src)
        # Compare normalised forms (parse the re-emitted text, compare trees)
        tree_in = parse(src)
        tree_back = parse(back)
        assert tree_in == tree_back, (
            f"round-trip semantic mismatch:\n  in:  {src}\n  out: {back}"
        )
        print(f"  {src:<40s} -> {len(data):3d} bytes  -> {back}")
    print("core.surface self-test OK")


if __name__ == "__main__":
    _self_test()
