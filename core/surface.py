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

**Stage-1 sugar (M9).**  Three surface conveniences were added when
abstraction landed.  All three are *desugarings* — each expands to
operators that already exist in the 64-token core, so nothing here
introduces semantics the substrate cannot express (Constraint 6):

  ``(defn name [a b] body)``   →  ``(let name (lambda a (lambda b body)) …)``
  ``(name x y)``               →  ``(apply (ref name) x y)``
  bare ``x`` in an argument     →  ``(ref x)``

Names are the fourth piece.  The substrate binds by integer id, so an
identifier written at the surface is *interned* to an integer by the
parser.  Interning is one-way on purpose: ``pretty`` prints the
integer, because the integer is what the program is (Axiom 1).  The
identifier is a comment the parser understood, not part of the
program.  Round-tripping a symbolic source therefore yields the same
*tree*, not the same *text* — which is the correct direction for a
language whose canonical form is the integer sequence.
"""

from __future__ import annotations

import os
import re

from typing import Any, Dict, List, Optional, Tuple, Union

from core.tokens import (
    ALIASES, APPLY, CONS, DEVIATION, IF_SURPRISE, LAMBDA, LET, LIT_INT,
    MERGE, MUL, NIL, Node, REF, SIGNATURES, SURFACE_ALIASES, SURPRISE,
    THRESHOLD, WHEN_ANOMALY, NAME_TO_TOKEN, Lit,
    CAPABILITY_BITS, EXTERNAL_BOUNDARY, MAP_PUT, MAP_GET, SIGNAL, LIT_TEXT,
)


# --- tokenizer ---------------------------------------------------------------

class Tok(str):
    """A token that remembers its place in the source (M24).

    A ``str``, so every comparison and table lookup in the parser is
    unchanged; ``start`` and ``end`` are character offsets into the
    text that was tokenized.  Spans on nodes are built from them, and
    a fault reported with a span is what lets an AI patch the one
    expression at fault instead of re-emitting the program.
    """
    __slots__ = ("start", "end")

    @classmethod
    def at(cls, text: str, start: int, end: int) -> "Tok":
        tok = cls(text)
        tok.start = start
        tok.end = end
        return tok


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
        if c in "()[]":
            out.append(Tok.at(c, i, i + 1)); i += 1; continue
        if c == '"':
            # A string literal.  Kept quoted in the token stream so the
            # parser can tell `"1"` from `1`.
            j = i + 1
            buf = ['"']
            while j < len(src) and src[j] != '"':
                if src[j] == "\\" and j + 1 < len(src):
                    escape = src[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r",
                                '"': '"', "\\": "\\"}.get(escape, escape))
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            if j >= len(src):
                raise ValueError("unterminated string literal")
            buf.append('"')
            out.append(Tok.at("".join(buf), i, j + 1))
            i = j + 1
            continue
        # atom (identifier or integer literal)
        j = i
        while j < len(src) and not src[j].isspace() and src[j] not in "();[]":
            j += 1
        out.append(Tok.at(src[i:j], i, j))
        i = j
    return out


def _spanned(node: Node, tokens: List[str], pos: int, after: int) -> Node:
    """Give ``node`` the span from token ``pos`` to the token before ``after``."""
    first, last = tokens[pos], tokens[after - 1]
    start, end = getattr(first, "start", None), getattr(last, "end", None)
    if start is not None and end is not None:
        node.span = (start, end)
    return node


def span_of(node: Any) -> Optional[Tuple[int, int]]:
    """The (start, end) offsets a node came from, if it came from text."""
    return getattr(node, "span", None)


def line_col(source: str, offset: int) -> Tuple[int, int]:
    """1-based line and column of an offset in ``source``."""
    line = source.count(chr(10), 0, offset) + 1
    col = offset - (source.rfind(chr(10), 0, offset) + 1) + 1
    return line, col


# --- symbol interning --------------------------------------------------------

# Identifiers written at the surface are interned to integer name ids,
# because the substrate binds by integer (Axiom 2 -- the identifier is a
# convenience for whoever is typing, not part of the program).
#
# Ids are handed out sequentially from a base chosen so that they can
# never collide with an explicit numeric name id in the same source.
# Sequential small ids matter: a name id is a LIT_INT payload, and a
# one-byte payload is the difference between a dense program and a
# program full of five-byte hashes.

# Binder head-words: the atom right after one of these inside a list is
# a *name*, not a value.
_BINDER_HEADS = frozenset({"let", "lambda", "defn"})
_NAME_HEADS = _BINDER_HEADS | {"ref"}


class SymbolTable:
    """Surface identifier -> substrate name id, for one parse."""

    def __init__(self, base: int = 0):
        self.base = base
        self._ids: Dict[str, int] = {}
        self.examples: List[Dict[str, Any]] = []     # (example ...) forms met (M26)

    def intern(self, name: str) -> int:
        if name not in self._ids:
            self._ids[name] = self.base + len(self._ids)
        return self._ids[name]

    def known(self, name: str) -> bool:
        return name in self._ids

    def name_of(self, name_id: int) -> Optional[str]:
        """The surface spelling of a name id, if this parse interned it."""
        for name, ident in self._ids.items():
            if ident == name_id:
                return name
        return None

    def gensym(self) -> int:
        """A name id no source can collide with.

        Macros that must not evaluate an argument twice need somewhere to
        put it.  The name contains a space, and the tokenizer splits on
        whitespace, so nothing a user writes can reach it.
        """
        return self.intern(f" g{len(self._ids)}")

    def as_dict(self) -> Dict[str, int]:
        return dict(self._ids)


def _explicit_name_ids(tokens: List[str]) -> List[int]:
    """Numeric name ids the source binds or references directly.

    Programs written before symbols existed say ``(let 0 12 ...)``.  Such
    a source may be mixed with symbolic names, so interning has to start
    above whatever the source already uses.
    """
    found: List[int] = []
    for i, tok in enumerate(tokens):
        if tok != "(" or i + 2 >= len(tokens):
            continue
        head = SURFACE_ALIASES.get(tokens[i + 1], tokens[i + 1])
        if head not in _NAME_HEADS:
            continue
        candidate = tokens[i + 2]
        try:
            found.append(int(candidate, 0))
        except ValueError:
            continue
    return found


def _is_identifier(tok: str) -> bool:
    if tok in ("(", ")", "[", "]"):
        return False
    if tok.startswith('"'):
        return False
    try:
        int(tok, 0)
    except ValueError:
        return True
    return False


# --- parser ------------------------------------------------------------------

def parse(src: str) -> Node:
    """Parse LOVA source to a Node.

    The source is one expression, optionally preceded by ``defn``
    definitions.  Definitions desugar to nested ``let`` bindings
    wrapping the final expression, in source order, so a later
    definition sees every earlier one -- and, because ``let`` is a
    letrec, itself.
    """
    src = expand_uses(src)
    tokens = _tokenize(src)
    if not tokens:
        raise ValueError("empty source")
    explicit = _explicit_name_ids(tokens)
    syms = SymbolTable(base=max(explicit) + 1 if explicit else 0)
    definitions, body = _parse_program(tokens, syms)
    return _wrap(definitions, body, syms)


def _parse_program(tokens: List[str], syms: SymbolTable
                   ) -> Tuple[List[Tuple[int, Node]], Optional[Node]]:
    """The `defn` forms and the one expression of a token stream.

    ``(example expr expected)`` forms (M26) are read wherever a `defn`
    may stand and collected on the parser (`syms.examples`), not into
    the program: they are what the program says about itself, and
    `core.examples.check` runs them.
    """
    definitions: List[Tuple[int, Node]] = []
    body: Optional[Node] = None
    cursor = 0
    while cursor < len(tokens):
        if _peek_head(tokens, cursor) == "defn":
            name_id, fn_node, cursor = _parse_defn(tokens, cursor, syms)
            definitions.append((name_id, fn_node))
            continue
        if _peek_head(tokens, cursor) == "example":
            start = cursor
            args, cursor = _parse_args(tokens, cursor + 2, syms)
            if len(args) != 2:
                raise ValueError(f"example: expects (example expr expected), got {len(args)} parts")
            first, last = tokens[start], tokens[cursor - 1]
            span = (getattr(first, "start", None), getattr(last, "end", None))
            syms.examples.append({"expr": args[0], "expected": args[1],
                                  "span": span if None not in span else None})
            continue
        if body is not None:
            trailing = " ".join(tokens[cursor:])
            raise ParseError(
                "a program is a sequence of `defn` forms followed by one "
                f"expression; found a second top-level expression: {trailing!r}",
                _token_span(tokens, cursor),
            )
        body, cursor = _parse_expr(tokens, cursor, syms)
    return definitions, body


def _wrap(definitions: List[Tuple[int, Node]], body: Optional[Node],
          syms: SymbolTable) -> Node:
    if body is None:
        raise ValueError(
            f"program defines {len(definitions)} function(s) but has no "
            "expression to evaluate"
        )
    inner = body
    for name_id, fn_node in reversed(definitions):
        body = Node(op=LET, args=[Lit(name_id), fn_node, body])
        if span_of(fn_node) is not None:
            body.span = fn_node.span          # the def form
    # The names, for whoever reports an error about one (M23, Q79).
    # The integer is the program; the spelling is a courtesy.
    body.symbols = syms
    # What the program says about itself (M26): its examples, and
    # where its own expression sits, so `core.examples` can put a
    # contract in that place.
    body.examples = list(syms.examples)
    body.body_span = getattr(inner, "span", None)
    return body


def _peek_head(tokens: List[str], pos: int) -> Optional[str]:
    """The head word of the list starting at ``pos``, if it is a list."""
    if tokens[pos] != "(" or pos + 1 >= len(tokens):
        return None
    return SURFACE_ALIASES.get(tokens[pos + 1], tokens[pos + 1])


def _parse_defn(
    tokens: List[str], pos: int, syms: SymbolTable
) -> Tuple[int, Node, int]:
    """``(defn name [p ...] body)`` -> ``(name_id, curried-lambda, next_pos)``.

    Zero parameters is legal and yields the body itself -- a named
    constant rather than a function.
    """
    try:
        return _parse_defn_inner(tokens, pos, syms)
    except ParseError:
        raise
    except ValueError as exc:
        raise ParseError(str(exc), _token_span(tokens, pos)) from None


def _parse_defn_inner(
    tokens: List[str], pos: int, syms: SymbolTable
) -> Tuple[int, Node, int]:
    cursor = pos + 2  # past the open paren and `defn`
    if cursor >= len(tokens) or not _is_identifier(tokens[cursor]):
        raise ValueError("defn: expected a name after `defn`")
    label = tokens[cursor]
    name_id = syms.intern(label)
    cursor += 1
    if cursor >= len(tokens) or tokens[cursor] != "[":
        raise ValueError(f"defn {label!r}: expected a bracketed parameter list")
    cursor += 1
    params: List[int] = []
    while cursor < len(tokens) and tokens[cursor] != "]":
        if not _is_identifier(tokens[cursor]):
            raise ValueError(
                f"defn {label!r}: parameter names must be identifiers, got "
                f"{tokens[cursor]!r}"
            )
        params.append(syms.intern(tokens[cursor]))
        cursor += 1
    if cursor >= len(tokens):
        raise ValueError(f"defn {label!r}: unclosed parameter list")
    cursor += 1  # past the closing bracket
    body, cursor = _parse_expr(tokens, cursor, syms)
    if cursor >= len(tokens) or tokens[cursor] != ")":
        raise ParseError(
            f"defn {label!r}: expected a closing paren after the body, "
            f"got {tokens[cursor]!r}" if cursor < len(tokens) else
            f"defn {label!r}: expected a closing paren after the body, got the end of the source",
            _token_span(tokens, cursor),
        )
    cursor += 1
    # Curry: (defn f [a b] body) is (lambda a (lambda b body)).
    fn = body
    for param in reversed(params):
        fn = _spanned(Node(op=LAMBDA, args=[Lit(param), fn]), tokens, pos, cursor)
    return name_id, fn, cursor


# --- macros ------------------------------------------------------------------
#
# Two operators the core does not have, provided as surface macros
# because they *expand* into it (Constraint 6): nothing here reaches the
# substrate that the 64 tokens could not already express.
#
# Exp 13 costed both as candidates for real token slots and measured
# them at 9% of the algorithmic density gap between them.  As macros
# they capture that 9% of the *surface* saving for zero slots; what they
# give up is the node-count saving, which the same experiment measured
# at 2% (5 nodes in 330).  Two slots is a bad price for 2%.

def _macro_sub(args: List[Node], syms: "SymbolTable") -> Node:
    """``(sub a b)`` -> ``a - b``.

    Subtraction is merge-with-a-negated-operand.  When ``b`` is a
    literal the negation is folded into the literal, so ``(sub n 1)``
    is two nodes rather than four -- and one LLM token rather than two,
    because ``-1`` tokenizes as ``-`` plus ``1``.
    """
    left, right = args
    if right.op == LIT_INT:
        return Node(op=MERGE, args=[left, Lit(-int(right.args[0]))])
    return Node(op=MERGE, args=[left, Node(op=MUL, args=[Lit(-1), right])])


def _macro_lt(args: List[Node], syms: "SymbolTable") -> Node:
    """``(lt a b)`` -> 1 when a < b, else 0.

    ``(threshold (deviation b a))``: deviation is the signed sibling of
    surprise, threshold is the sign test.
    """
    left, right = args
    return Node(op=THRESHOLD, args=[Node(op=DEVIATION, args=[right, left])])


def _macro_gt(args: List[Node], syms: "SymbolTable") -> Node:
    """``(gt a b)`` -> 1 when a > b, else 0."""
    left, right = args
    return Node(op=THRESHOLD, args=[Node(op=DEVIATION, args=[left, right])])


def _cons_chain(elements: List[Node]) -> Node:
    """Build ``(cons e1 (cons e2 ... (nil)))`` from a list of elements."""
    out = Node(op=NIL, args=[])
    for element in reversed(elements):
        out = Node(op=CONS, args=[element, out])
    return out


def _macro_list(args: List[Node], syms: "SymbolTable") -> Node:
    """``(list a b c)`` -> ``(cons a (cons b (cons c (nil))))``."""
    return _cons_chain(args)


def text_literal(text: str) -> Node:
    """``"abc"`` -> a text literal (M25, Q85): one node, one value."""
    return Node(op=LIT_TEXT, args=[text])


def string_to_nodes(text: str) -> Node:
    """``"abc"`` -> the codepoint list ``(cons 97 (cons 98 (cons 99 (nil))))``.

    The form every string literal took from M10 to M24.  Kept for the
    programs and tests that build the list on purpose; the parser now
    reads a literal as `text_literal`.

    A string is not a type in LOVA; it is a list of integers.  That is
    why the token table spends no slots on strings: once a cons cell
    exists, string *literals* are surface sugar and cost nothing.  It is
    also why they are slow, which is the trade a research substrate can
    afford (see spec/token-budget.md).
    """
    return _cons_chain([Lit(ord(ch)) for ch in text])


def _bind_once(value: Node, syms: "SymbolTable", build) -> Node:
    """``(let g value (build (ref g)))`` -- evaluate ``value`` exactly once.

    Before M11 a macro could duplicate its argument freely: everything
    was pure, so ``(if a a b)`` merely cost time.  ``stdout`` ended that.
    Any macro that would mention an argument twice binds it here first.
    """
    name = syms.gensym()
    reference = Node(op=REF, args=[Lit(name)])
    return Node(op=LET, args=[Lit(name), value, build(reference)])


def _if(condition: Node, then: Node, otherwise: Node) -> Node:
    return Node(op=IF_SURPRISE, args=[condition, then, otherwise])


def _macro_not(args, syms):
    """``(not x)`` -- 1 when x is zero, else 0."""
    return _if(args[0], Lit(0), Lit(1))


def _macro_and(args, syms):
    """``(and a b)`` -- b when a is non-zero, else 0.  Short-circuits."""
    return _if(args[0], args[1], Lit(0))


def _macro_or(args, syms):
    """``(or a b)`` -- a when it is non-zero, else b.  Short-circuits.

    ``a`` is bound first: it appears twice in the expansion, and since
    M11 an argument may write to stdout.
    """
    left, right = args
    return _bind_once(left, syms, lambda ref: _if(ref, ref, right))


def _macro_eq(args, syms):
    """``(eq a b)`` -- 1 when equal, else 0.

    `deviation` is the comparator (M22; it was `surprise` from M11):
    the same test, without recording a surprise event.  A comparison
    in a loop is not a prediction, and a word count of a thousand lines
    was recording a hundred thousand events that meant nothing.  Write
    `surprise` when the observation is the point.
    """
    return _if(Node(op=DEVIATION, args=[args[0], args[1]]), Lit(0), Lit(1))


def _macro_ne(args, syms):
    return _if(Node(op=DEVIATION, args=[args[0], args[1]]), Lit(1), Lit(0))


def _macro_le(args, syms):
    """``(le a b)`` -- not (a > b)."""
    return _macro_not([_macro_gt(args, syms)], syms)


def _macro_ge(args, syms):
    return _macro_not([_macro_lt(args, syms)], syms)


def _macro_neg(args, syms):
    return Node(op=MUL, args=[Lit(-1), args[0]])


def _macro_abs(args, syms):
    """``(abs x)`` -- |0 - x|, which is what `surprise` computes."""
    return Node(op=SURPRISE, args=[Lit(0), args[0]])


def _macro_min(args, syms):
    left, right = args
    return _bind_once(
        left, syms,
        lambda a: _bind_once(
            right, syms, lambda b: _if(_macro_lt([a, b], syms), a, b)
        ),
    )


def _macro_max(args, syms):
    left, right = args
    return _bind_once(
        left, syms,
        lambda a: _bind_once(
            right, syms, lambda b: _if(_macro_gt([a, b], syms), a, b)
        ),
    )


def _macro_try(args, syms):
    """``(try body fallback)`` -- the common case of ``when-anomaly``.

    Expands to ``(when-anomaly body (lambda _ fallback))``: a handler
    that ignores which anomaly it caught.  When the code matters, write
    ``when-anomaly`` and take the parameter.
    """
    body, fallback = args
    ignored = syms.gensym()
    handler = Node(op=LAMBDA, args=[Lit(ignored), fallback])
    return Node(op=WHEN_ANOMALY, args=[body, handler])


def _macro_cond(args, syms):
    """``(cond c1 v1 c2 v2 ... default)`` -- a chain of ifs.

    An odd number of arguments: pairs, then the fallback.
    """
    if len(args) % 2 == 0:
        raise ValueError(
            "cond: expects condition/value pairs followed by one default, "
            f"so an odd number of arguments; got {len(args)}"
        )
    result = args[-1]
    for i in range(len(args) - 3, -1, -2):
        result = _if(args[i], args[i + 1], result)
    return result


def _field_name(node: Node, syms: "SymbolTable", macro: str) -> Node:
    """A field written as a bare identifier, as the text of its name.

    ``(get r memo)`` names the field ``memo``; the parser has already
    read ``memo`` as a reference, so the name is recovered from the
    symbol table and becomes the string key ``"memo"``.  A string
    literal is accepted as it is, so a computed field name can be
    written ``(get r "memo")`` too.
    """
    if node.op == REF and node.args and node.args[0].op == LIT_INT:
        name = syms.name_of(int(node.args[0].args[0]))
        if name is not None:
            return text_literal(name)
    if node.op in (CONS, NIL, LIT_TEXT):
        return node                       # already text
    raise ValueError(f"{macro}: a field is a bare name or a string, not {node!r}")


def _macro_rec(args, syms):
    """``(rec x 1 y 2)`` -- a record: a map from field names to values.

    Named fields where a list would be taken apart by position (Q84):
    a fold that threads three things carries ``(rec best 0 move -1
    memo m)`` and reads ``(get st memo)`` instead of ``(nth st 2)``.
    A record is a map, so `map-pairs`, `map-size` and `map-put` work
    on it, and a program that already had maps has records.
    """
    if len(args) % 2:
        raise ValueError(f"rec: expects field/value pairs, got {len(args)} arguments")
    out: Node = Node(op=NIL, args=[])
    for i in range(0, len(args), 2):
        out = Node(op=MAP_PUT, args=[out, _field_name(args[i], syms, "rec"), args[i + 1]])
    return out


def _macro_get(args, syms):
    """``(get r x)`` -- the field, or a `missing-field` signal (code 17)."""
    record, field = args
    missing = Node(op=SIGNAL, args=[Lit(17)])
    return Node(op=MAP_GET, args=[record, _field_name(field, syms, "get"), missing])


def _macro_put(args, syms):
    """``(put r x v)`` -- the record with field ``x`` set to ``v``."""
    record, field, value = args
    return Node(op=MAP_PUT, args=[record, _field_name(field, syms, "put"), value])


# name -> (arity, expander).  Arity ``None`` means variadic.  Arity is
# checked before expansion so the error message names the macro rather
# than the operator it expands to.
#
# Every macro here expands into the core 64 tokens (Constraint 6).  They
# exist because Exp 13 measured what a token slot is worth against what a
# surface expansion is worth, and expansions won: identical token count,
# zero slots.
def _text_of_chain(node: Node) -> Optional[str]:
    """The text a cons chain of codepoint literals spells, else None."""
    if node.op == LIT_TEXT:
        return node.args[0]              # a text literal (M25)
    out = []
    while node.op == CONS and len(node.args) == 2:
        head, node = node.args
        if head.op != LIT_INT:
            return None
        out.append(chr(int(head.args[0])))
    return "".join(out) if node.op == NIL else None


def _macro_boundary(args, syms):
    """``(boundary "fs-read clock" body)`` -> ``(external-boundary 5 body)``.

    The capability mask is a literal in the core -- one byte, no names
    -- and the names are surface only.  A literal integer is accepted
    as well, which is how `explain` prints it and `read` reads it back.
    """
    spec, body = args
    if spec.op == LIT_INT:
        return Node(op=EXTERNAL_BOUNDARY, args=[Lit(int(spec.args[0])), body])
    text = _text_of_chain(spec)
    if text is None:
        raise ValueError(
            'boundary: expects a string naming capabilities, e.g. '
            '"fs-read clock", or a literal mask'
        )
    mask = 0
    for name in text.replace(",", " ").split():
        if name not in CAPABILITY_BITS:
            raise ValueError(
                f"boundary: unknown capability {name!r}; known: "
                + ", ".join(CAPABILITY_BITS)
            )
        mask |= CAPABILITY_BITS[name]
    return Node(op=EXTERNAL_BOUNDARY, args=[Lit(mask), body])


MACROS = {
    "sub": (2, _macro_sub),
    "lt": (2, _macro_lt),
    "gt": (2, _macro_gt),
    "le": (2, _macro_le),
    "ge": (2, _macro_ge),
    "eq": (2, _macro_eq),
    "ne": (2, _macro_ne),
    "not": (1, _macro_not),
    "and": (2, _macro_and),
    "or": (2, _macro_or),
    "neg": (1, _macro_neg),
    "abs": (1, _macro_abs),
    "min": (2, _macro_min),
    "max": (2, _macro_max),
    "cond": (None, _macro_cond),
    "try": (2, _macro_try),
    "list": (None, _macro_list),
    "rec": (None, _macro_rec),
    "get": (2, _macro_get),
    "put": (3, _macro_put),
    "boundary": (2, _macro_boundary),
}


class ParseError(ValueError):
    """A parse fault that says where (Exp 19).

    Three sessions in a row read "unexpected closing paren at token
    330" and "expects 2 args, got 7" with no line to go to.  A
    ``ValueError`` still, so every handler keeps working; ``anomaly``
    carries the span of the token or form at fault, which the CLI and
    the MCP server turn into a line, a column and an excerpt.
    """

    def __init__(self, message: str, span: Optional[Tuple[int, int]] = None):
        super().__init__(message)
        self.anomaly: Dict[str, Any] = {
            "kind": "parse-error",
            "detail": {"message": message},
            "position_path": (),
            "offending_op": None,
            "offending_op_name": "",
            "valid_alternatives": (),
            "repair_hint": message,
        }
        if span is not None:
            self.anomaly["span"] = span


def _token_span(tokens: List[str], start: int, end: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """The source span from token ``start`` to token ``end`` (exclusive)."""
    if not tokens:
        return None
    first = tokens[min(start, len(tokens) - 1)]
    last = tokens[min((end if end is not None else start + 1) - 1, len(tokens) - 1)]
    if isinstance(first, Tok) and isinstance(last, Tok):
        return (first.start, max(last.end, first.end))
    return None


def _parse_expr(
    tokens: List[str], pos: int, syms: Optional[SymbolTable] = None
) -> Tuple[Node, int]:
    try:
        return _parse_expr_inner(tokens, pos, syms)
    except ParseError:
        raise
    except ValueError as exc:
        # The innermost frame converts, so the span is the token in hand.
        raise ParseError(str(exc), _token_span(tokens, pos)) from None


def _parse_expr_inner(
    tokens: List[str], pos: int, syms: Optional[SymbolTable] = None
) -> Tuple[Node, int]:
    if syms is None:
        syms = SymbolTable()
    if pos >= len(tokens):
        raise ValueError("unexpected end of input")
    t = tokens[pos]
    if t == "(":
        # (operator arg1 arg2 ...)
        if pos + 1 >= len(tokens):
            raise ValueError("unexpected EOF after an open paren")
        op_sym = tokens[pos + 1]
        if op_sym == "(":
            raise ValueError("operator must be an identifier, not a sub-expression")
        op_name = SURFACE_ALIASES.get(op_sym, op_sym)
        if op_name == "defn":
            raise ValueError(
                "defn is a top-level form: it introduces a binding for the "
                "rest of the program and cannot appear as a subexpression"
            )
        if op_name == "boundary":
            # A boundary is a region (M26, Q86): after the capability
            # spec, `def` forms may precede the body.  They are bound
            # inside the boundary, so a helper defined there carries the
            # declared effect -- lexically, which is what the compiler
            # checks -- and the region ends where the boundary does.
            spec, cursor = _parse_expr(tokens, pos + 2, syms)
            definitions: List[Tuple[int, Node]] = []
            while cursor < len(tokens) and _peek_head(tokens, cursor) == "defn":
                name_id, fn_node, cursor = _parse_defn(tokens, cursor, syms)
                definitions.append((name_id, fn_node))
            body, cursor = _parse_expr(tokens, cursor, syms)
            if cursor >= len(tokens) or tokens[cursor] != ")":
                raise ValueError("boundary: expects a capability spec, optional `def` forms, and one body")
            cursor += 1
            for name_id, fn_node in reversed(definitions):
                body = Node(op=LET, args=[Lit(name_id), fn_node, body])
                if span_of(fn_node) is not None:
                    body.span = fn_node.span
            return _spanned(_macro_boundary([spec, body], syms), tokens, pos, cursor), cursor
        if op_name in MACROS:
            arity, expand = MACROS[op_name]
            macro_args, cursor = _parse_args(tokens, pos + 2, syms)
            if arity is not None and len(macro_args) != arity:
                raise ParseError(
                    f"{op_name}: expects {arity} args, got {len(macro_args)}",
                    _token_span(tokens, pos, cursor),
                )
            return _spanned(expand(macro_args, syms), tokens, pos, cursor), cursor
        if op_name not in NAME_TO_TOKEN:
            # Call sugar: an unknown head is a call of a bound name.
            #   (square 5)  ->  (apply (ref square) 5)
            # A typo lands here too, and the compiler scope pass reports
            # it as `unbound-ref` -- a better error than "unknown
            # operator", because it comes with the names that ARE bound.
            if not _is_identifier(op_sym):
                raise ValueError(f"unknown operator: {op_sym!r}")
            name_id = syms.intern(op_sym)
            call_args, cursor = _parse_args(tokens, pos + 2, syms)
            head = _spanned(Node(op=REF, args=[Lit(name_id)]), tokens, pos + 1, pos + 2)
            return _spanned(Node(op=APPLY, args=[head] + call_args), tokens, pos, cursor), cursor
        op_tok = NAME_TO_TOKEN[op_name]
        cursor = pos + 2
        args: List[Node] = []
        # A binder's first slot names a variable rather than computing one.
        if (op_name in _NAME_HEADS and cursor < len(tokens)
                and _is_identifier(tokens[cursor])):
            args.append(Lit(syms.intern(tokens[cursor])))
            cursor += 1
        rest, cursor = _parse_args(tokens, cursor, syms)
        args.extend(rest)
        # arity check
        sig = SIGNATURES[op_tok]
        if sig["arity"] != "variadic" and len(args) != sig["arity"]:
            raise ParseError(
                f"{op_name}: expects {sig['arity']} args, got {len(args)}",
                _token_span(tokens, pos, cursor),
            )
        return _spanned(Node(op=op_tok, args=args), tokens, pos, cursor), cursor
    if t == ")":
        raise ValueError(f"unexpected closing paren at token {pos}")
    if t in ("[", "]"):
        raise ValueError(
            f"unexpected {t!r} -- brackets appear only in a defn parameter list"
        )
    if t.startswith('"'):
        return _spanned(text_literal(t[1:-1]), tokens, pos, pos + 1), pos + 1
    # bare atom: an integer literal, or a reference to a bound name.
    try:
        n = int(t, 0)  # accepts decimal, 0x hex, 0b bin
    except ValueError:
        if _is_identifier(t):
            return _spanned(Node(op=REF, args=[Lit(syms.intern(t))]), tokens, pos, pos + 1), pos + 1
        raise ValueError(f"bare atom must be an integer literal: {t!r}")
    return _spanned(Lit(n), tokens, pos, pos + 1), pos + 1


def _parse_args(
    tokens: List[str], cursor: int, syms: SymbolTable
) -> Tuple[List[Node], int]:
    """Parse expressions up to the closing paren; returns (args, pos-after)."""
    args: List[Node] = []
    while cursor < len(tokens) and tokens[cursor] != ")":
        child, cursor = _parse_expr(tokens, cursor, syms)
        args.append(child)
    if cursor >= len(tokens):
        raise ValueError("unclosed list")
    return args, cursor + 1  # consume the closing paren


# --- the prelude -------------------------------------------------------------

PRELUDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lib", "prelude.lova",
)


LIB_DIR = os.path.dirname(PRELUDE_PATH)


def load_prelude() -> str:
    """The text of ``lib/prelude.lova``."""
    with open(PRELUDE_PATH, encoding="utf-8") as handle:
        return handle.read()


def resolve_library(name: str) -> str:
    """Where ``(use "name")`` looks: ``lib/name.lova``, then a plain path."""
    candidates = [os.path.join(LIB_DIR, name + ".lova"),
                  os.path.join(LIB_DIR, name), name]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise ValueError(
        f"use: no library named {name!r} (looked in {LIB_DIR} and the "
        "working directory)"
    )


_USE_FORM = re.compile(r'\(\s*use\s+"([^"]*)"\s*\)')


def expand_uses(src: str, _seen: Optional[set] = None) -> str:
    """Replace every ``(use "name")`` with the text of that library (M18).

    Textual inclusion, the same mechanism the prelude has used since
    M11, made addressable: a library is a `.lova` file of `def`s, and a
    program that uses it sees those definitions as if written above.
    Included once per program however many times it is named, and a
    cycle is an error rather than a loop.  `drop-unused` keeps it free.
    """
    seen = _seen if _seen is not None else set()

    def include(match: "re.Match[str]") -> str:
        path = resolve_library(match.group(1))
        if path in seen:
            return ""                       # already included
        seen.add(path)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        return expand_uses(text, seen) + "\n"

    return _USE_FORM.sub(include, src)


def parse_with_prelude(src: str) -> Node:
    """Parse ``src`` with the standard library in scope.

    The prelude is prepended textually, which is the whole mechanism --
    LOVA has no module system, and does not need one for this: `def`
    binds sequentially, so the user's program simply sees every earlier
    definition, and a user definition of the same name shadows the
    prelude's.

    Including it is free.  The compiler's ``drop-unused`` pass removes
    every binding the program never mentions, so a program that calls
    none of the prelude compiles to exactly what it would have without
    it.

    M23: the prelude's parse is cached (per name base, since a source
    that says `(let 0 ...)` pushes the prelude's names above 0) and
    its definitions copied in, so this costs what parsing the program
    costs.  The tree is identical to the one parsing the concatenated
    text gives; `tests/test_surface.py` checks that.
    """
    prelude = load_prelude()
    src = expand_uses(src)
    body_tokens = _tokenize(src)
    if not body_tokens:
        raise ValueError("empty source")
    prelude_tokens = _prelude_tokens(prelude)
    explicit = _explicit_name_ids(prelude_tokens + body_tokens)
    base = max(explicit) + 1 if explicit else 0
    definitions, snapshot = _prelude_parsed(prelude, prelude_tokens, base)
    syms = SymbolTable(base=base)
    syms._ids = dict(snapshot)
    own, body = _parse_program(body_tokens, syms)
    copied = [(name_id, _copy_tree(node)) for name_id, node in definitions]
    return _wrap(copied + own, body, syms)


_PRELUDE_TOKENS: Dict[str, List[str]] = {}
_PRELUDE_PARSED: Dict[Tuple[str, int], Tuple[List[Tuple[int, Node]], Dict[str, int]]] = {}


def _prelude_tokens(prelude: str) -> List[str]:
    tokens = _PRELUDE_TOKENS.get(prelude)
    if tokens is None:
        tokens = _PRELUDE_TOKENS[prelude] = _tokenize(expand_uses(prelude))
    return tokens


def _prelude_parsed(prelude: str, tokens: List[str], base: int):
    key = (prelude, base)
    entry = _PRELUDE_PARSED.get(key)
    if entry is None:
        syms = SymbolTable(base=base)
        definitions, body = _parse_program(tokens, syms)
        if body is not None:
            raise ValueError("the prelude must be definitions only")
        entry = _PRELUDE_PARSED[key] = (definitions, syms.as_dict())
    return entry


def _copy_tree(node: Node) -> Node:
    """A fresh copy of a definition, so no two programs share a node."""
    if node.op == LIT_INT:
        return Node(op=LIT_INT, args=[node.args[0]])
    return Node(op=node.op, args=[_copy_tree(c) if isinstance(c, Node) else c
                                  for c in node.args])


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
    if node.op == LIT_TEXT:
        return quote_text(node.args[0])
    name = SIGNATURES[node.op]["name"]
    if unicode and name in _UNICODE_REVERSE:
        name = _UNICODE_REVERSE[name]
    if not node.args:
        return f"({name})"
    children = " ".join(_pretty(c, unicode) for c in node.args)
    return f"({name} {children})"


def quote_text(text: str) -> str:
    """A text as the literal the parser reads back: quoted, escaped."""
    out = text.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')
    out = out.replace(chr(10), chr(92) + "n").replace(chr(9), chr(92) + "t").replace(chr(13), chr(92) + "r")
    return '"' + out + '"'


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

def encode_check(tree: Node) -> bytes:
    """Encode a tree and confirm it decodes back to itself."""
    from core.tokens import decode, encode
    data = encode(tree)
    assert decode(data) == tree, "encode/decode round-trip failed"
    return data


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
    # Sugar (M9): defn, calls and bare-name references all desugar into
    # core tokens, and it is the desugared form that runs.
    from core.runtime import evaluate
    from core.tokens import APPLY as _A, LAMBDA as _L, LET as _E, REF as _R

    sugared = (
        "(defn square [n] (mul n n))\n"
        "(defn sum-of-squares [a b] (merge (square a) (square b)))\n"
        "(sum-of-squares 3 4)"
    )
    tree = parse(sugared)
    data = encode_check(tree)
    result = evaluate(tree)
    assert result == 25, result
    print(f"  defn/call sugar  -> {len(data):3d} bytes, evaluates to {result}"
          "  (expected 25)")

    # No new semantics reached the substrate (Constraint 6): the sugar
    # expands to LET + LAMBDA + APPLY + REF and nothing else.
    ops = set()

    def _collect(n: Node) -> None:
        ops.add(n.op)
        if n.op != LIT_INT:
            for c in n.args:
                _collect(c)

    _collect(tree)
    assert {_E, _L, _A, _R} <= ops, sorted(hex(o) for o in ops)

    # Short spellings and macros (Exp 13): accepted spellings and pure
    # expansions, both verified against the long form.
    from core.tokens import SHORT_ALIASES
    pairs = [
        ("(if 1 10 20)", "(if-surprise 1 10 20)"),
        ("(dev 3 10)", "(deviation 3 10)"),
        ("(sub 10 3)", "(merge 10 -3)"),
        ("(sub 10 (p 3))", "(merge 10 (mul -1 (p 3)))"),
        ("(lt 3 5)", "(threshold (deviation 5 3))"),
        ("(gt 3 5)", "(threshold (deviation 3 5))"),
        ("(def f [x] (mul x 2))(f 21)", "(defn f [x] (mul x 2))(f 21)"),
    ]
    for short, long in pairs:
        assert parse(short) == parse(long), f"{short} != {long}"
    print(f"  short spellings + macros: {len(pairs)} forms expand to the "
          f"long form exactly ({len(SHORT_ALIASES)} aliases, {len(MACROS)} macros)")

    # Lists and strings (M10): both are sugar over cons/nil.
    from core.runtime import list_to_python
    assert parse("(list 1 2 3)") == parse("(cons 1 (cons 2 (cons 3 (nil))))")
    assert parse('"abc"') == parse("(list 97 98 99)")
    codes = list_to_python(evaluate(parse('"LOVA"')))
    assert codes == [76, 79, 86, 65], codes
    print(f"  (list ...) and \"strings\" desugar to cons/nil: "
          f"\"LOVA\" -> {codes}")

    print("core.surface self-test OK")


if __name__ == "__main__":
    _self_test()
