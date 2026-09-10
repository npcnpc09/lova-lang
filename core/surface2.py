"""Stage-2 surface: the text projection of the byte encoding.

Stage 1 is a Lisp.  It was always a bootstrap, and Experiment 13 put a
number on what it costs: on algorithmic programs, **25% of the LLM
tokens are parentheses** and another 51% are operator names, so the
best any change to the token table could reach was 0.76x against
Python — still below parity — with 61% of the gap sitting in
s-expression syntax that no allocation of 64 slots can touch.

This module is the instrument for that residual.

**The parentheses were never necessary.**  The integer encoding has no
delimiters: `core.tokens.decode` recovers the tree from the byte
stream alone, because every operator's arity is known from its
signature.  Stage 1 spends parentheses re-stating something the
substrate already knows.  So the Stage-2 surface is the *same*
structure the encoder emits, one printable symbol per byte:

    Stage 1   (merge (p 3) (tau 12))          9 bytes
    Stage 2   +p3t12                          9 bytes, 4 LLM tokens
    bytes     03 08 01 01 03 09 01 01 0c

That is what makes it stage-coherent (Axiom 10) rather than a second
syntax to maintain: Stage 2 is not a different language, it is the
byte sequence written in characters instead of hex.  Anything
expressible in one is expressible in the other by construction, and
``parse(render(node)) == node`` is a property test rather than an
aspiration.

**Lexing without delimiters.**  A literal is a run of digits with an
optional leading `-`; every operator symbol is a non-digit, non-`-`
character.  So the lexer reads one character and knows which it has.
The single ambiguity is two adjacent literals — `+ 3 12` would pack to
`+312` and read back as one number — so a space is emitted between a
digit and a following digit, and only there.

**One compression rule, and only one.**  A projection is not obliged
to be one character per byte — it is obliged to be lossless.  Measured
on the algorithmic corpus, ``(ref k)`` is 22% of all AST nodes and 36%
of the Stage-2 LLM-token cost, because `&` and its index tokenize
separately.  So the three bytes ``REF LIT_INT k`` get a single symbol
for ``k`` in 0..9, which is where essentially every reference lives:
parameters and let-bindings are numbered from zero upward.

That rule is declared here rather than discovered per corpus, and it
is deliberately the only one.  ``$&0`` (a call of the first binding)
and ``\\1`` (a one-parameter lambda) are the next two candidates, and
adding them would fit the surface to the ten programs that motivated
it rather than to the language.  See journal Q46.

Human readability is a non-goal of the substrate (Axiom 2); this is
the first place in the project where that is cashed in rather than
merely asserted.  ``core.surface.pretty`` remains for auditing.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from core.tokens import END, LIT_INT, LIT_TEXT, Node, REF, SIGNATURES


# --- the symbol table --------------------------------------------------------
#
# One printable, single-LLM-token character per byte, mnemonic where a
# mnemonic exists and arbitrary where none does.  Digits and `-` are
# reserved for literals.  The table is total over all 64 bytes, including
# reserved operators, so a program using a future operator still projects.

SYMBOLS: Dict[int, str] = {
    # Structural 0x00-0x07
    0x00: ";",   # end            -- closes a variadic
    0x01: "#",   # lit            -- never printed; digits stand for it
    0x02: "h",   # partition      -- halve
    0x03: "+",   # merge
    0x04: ":",   # cons
    0x05: "^",   # head
    0x06: "_",   # tail
    0x07: "=",   # identity
    # Number theory 0x08-0x0F
    0x08: "p",   # p
    0x09: "t",   # tau
    0x0A: "s",   # sigma
    0x0B: "*",   # mul
    0x0C: "%",   # mod
    0x0D: "/",   # div
    0x0E: "g",   # gcd
    0x0F: "u",   # mobius
    # Conservation 0x10-0x17
    0x10: "B",   # budget
    0x11: "C",   # conserve
    0x12: "D",   # delta-check    (reserved)
    0x13: "E",   # respawn        (reserved)
    0x14: "F",   # budget-remaining (reserved)
    0x15: "~",   # nil
    0x16: "G",   # preserve       (reserved)
    0x17: "V",   # violate
    # Surprise 0x18-0x1F
    0x18: "?",   # surprise
    0x19: "z",   # nil?           -- zero-length
    0x1A: "H",   # when-anomaly   (reserved)
    0x1B: ">",   # threshold
    0x1C: "I",   # predict        (reserved)
    0x1D: "T",   # trace-surprise
    0x1E: "J",   # normal-range   (reserved)
    0x1F: "d",   # deviation
    # Evolution 0x20-0x27 (all reserved)
    0x20: "K", 0x21: "M", 0x22: "N", 0x23: "O",
    0x24: "P", 0x25: "Q", 0x26: "R", 0x27: "S",
    # Composition 0x28-0x2F
    0x28: ",",   # seq
    0x29: "U",   # par            (reserved)
    0x2A: "!",   # if-surprise
    0x2B: "@",   # loop-until
    0x2C: "\\",  # lambda
    0x2D: "$",   # apply
    0x2E: "W",   # let
    0x2F: "&",   # ref
    # Effects / IO 0x30-0x37 (all reserved)
    0x30: "X", 0x31: "Y", 0x32: "Z", 0x33: "a",
    0x34: "b", 0x35: "c", 0x36: "e", 0x37: "f",
    # Meta / lineage 0x38-0x3F (all reserved)
    0x38: "i", 0x39: "j", 0x3A: "k", 0x3B: "l",
    0x3C: "m", 0x3D: "n", 0x3E: "o", 0x3F: "q",
    # Text 0x40-0x4D (M25).  0x40 is the text literal, printed as a
    # quoted string and never by its symbol.
    0x40: "'", 0x41: "[", 0x42: "]", 0x43: "{", 0x44: "}", 0x45: "`",
    0x46: "~", 0x47: "(", 0x48: ")", 0x49: "|", 0x4A: "<", 0x4B: ">",
    0x4C: "?", 0x4D: "!",
}

# The text family (M25) takes one Greek capital per byte: printable ASCII
# has eight characters left after the core table, the reference digram
# and the literal characters, and the family needs fourteen.
for _tok, _sym in zip(sorted(t for t in SYMBOLS if t >= 0x40), "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞ"):
    SYMBOLS[_tok] = _sym
assert len(SYMBOLS) == len(SIGNATURES), f"symbol table must cover every token, has {len(SYMBOLS)}"
assert len(set(SYMBOLS.values())) == len(SYMBOLS), "symbols must be distinct"
assert not (set(SYMBOLS.values()) & set("0123456789-")), \
    "digits and '-' are reserved for literals"

TOKEN_FOR_SYMBOL: Dict[str, int] = {sym: tok for tok, sym in SYMBOLS.items()}


# --- the reference digram ----------------------------------------------------
#
# ``(ref 0)`` .. ``(ref 9)`` -- three bytes each, one character each.  Ten
# is not arbitrary: name ids are handed out from zero by both the surface
# symbol table and every hand-written program, so a reference outside
# 0..9 is rare enough to fall back to the general form ``&12``.

REF_SYMBOLS: str = "ALrvwxy<|."

assert len(REF_SYMBOLS) == 10, "one symbol per single-digit reference"
assert len(set(REF_SYMBOLS)) == 10, "reference symbols must be distinct"
assert not (set(REF_SYMBOLS) & set(SYMBOLS.values())), \
    "reference symbols must not collide with operator symbols"
assert not (set(REF_SYMBOLS) & set("0123456789-")), \
    "digits and '-' are reserved for literals"

REF_INDEX_FOR_SYMBOL: Dict[str, int] = {
    sym: index for index, sym in enumerate(REF_SYMBOLS)
}


def _packed_ref_index(node: Node):
    """The index if ``node`` is a single-digit ``(ref k)``, else None."""
    if node.op != REF or not node.args:
        return None
    target = node.args[0]
    if target.op != LIT_INT:
        return None
    index = int(target.args[0])
    return index if 0 <= index <= 9 else None


# --- rendering ---------------------------------------------------------------

def render(node: Node, pack_refs: bool = True) -> str:
    """Project a tree to the Stage-2 surface.

    Emits the sequence ``core.tokens.encode`` emits, one character per
    byte, with a separating space only where two literals would
    otherwise run together.  ``pack_refs=False`` disables the reference
    digram, which is what the measurement in Experiment 14 compares
    against; it is not a second dialect.
    """
    parts: List[str] = []
    _render_into(node, parts, pack_refs)
    return "".join(parts)


def _render_into(node: Node, parts: List[str], pack_refs: bool = True) -> None:
    if pack_refs:
        index = _packed_ref_index(node)
        if index is not None:
            parts.append(REF_SYMBOLS[index])
            return
    if node.op == LIT_INT:
        text = str(int(node.args[0]))
        # A space only where it is load-bearing: between this literal and
        # a previous one.  `-` starts a literal unambiguously, so a
        # negative number needs no separator.
        if parts and parts[-1][-1].isdigit() and text[0].isdigit():
            parts.append(" ")
        parts.append(text)
        return
    if node.op == LIT_TEXT:
        from core.surface import quote_text
        parts.append(quote_text(node.args[0]))     # self-delimiting
        return
    parts.append(SYMBOLS[node.op])
    sig = SIGNATURES[node.op]
    for child in node.args:
        _render_into(child, parts, pack_refs)
    if sig["arity"] == "variadic":
        parts.append(SYMBOLS[END])


# --- parsing -----------------------------------------------------------------

def parse(text: str) -> Node:
    """Read a Stage-2 surface string back into a tree."""
    node, pos = _parse_one(text, _skip(text, 0))
    pos = _skip(text, pos)
    if pos != len(text):
        raise ValueError(f"trailing input at {pos}: {text[pos:]!r}")
    return node


def _skip(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _parse_one(text: str, pos: int) -> Tuple[Node, int]:
    if pos >= len(text):
        raise ValueError("unexpected end of input")
    char = text[pos]

    if char == "-" or char.isdigit():
        end = pos + 1
        while end < len(text) and text[end].isdigit():
            end += 1
        if end == pos + 1 and char == "-":
            raise ValueError(f"bare '-' at {pos}")
        return Node(op=LIT_INT, args=[int(text[pos:end])]), end

    if char == '"':
        end = pos + 1
        buf: List[str] = []
        while end < len(text) and text[end] != '"':
            if text[end] == chr(92) and end + 1 < len(text):
                esc = text[end + 1]
                buf.append({"n": chr(10), "t": chr(9), "r": chr(13)}.get(esc, esc))
                end += 2
                continue
            buf.append(text[end])
            end += 1
        if end >= len(text):
            raise ValueError(f"unterminated text literal at {pos}")
        return Node(op=LIT_TEXT, args=["".join(buf)]), end + 1

    if char in REF_INDEX_FOR_SYMBOL:
        index = REF_INDEX_FOR_SYMBOL[char]
        return Node(op=REF, args=[Node(op=LIT_INT, args=[index])]), pos + 1

    if char not in TOKEN_FOR_SYMBOL:
        raise ValueError(f"unknown symbol {char!r} at {pos}")
    token = TOKEN_FOR_SYMBOL[char]
    if token == END:
        raise ValueError(f"unexpected end-of-variadic marker at {pos}")
    if token == LIT_INT:
        raise ValueError(
            f"the literal symbol {char!r} is never emitted; write the digits"
        )

    sig = SIGNATURES[token]
    pos += 1
    children: List[Node] = []
    if sig["arity"] == "variadic":
        while True:
            pos = _skip(text, pos)
            if pos >= len(text):
                raise ValueError(f"{sig['name']}: missing end marker")
            if text[pos] == SYMBOLS[END]:
                pos += 1
                break
            child, pos = _parse_one(text, pos)
            children.append(child)
    else:
        for _ in range(sig["arity"]):
            pos = _skip(text, pos)
            child, pos = _parse_one(text, pos)
            children.append(child)
    return Node(op=token, args=children), pos


# --- round-trip helper -------------------------------------------------------

def round_trip(node: Node, pack_refs: bool = True) -> str:
    """Render, re-parse, and confirm the tree survived."""
    text = render(node, pack_refs=pack_refs)
    back = parse(text)
    if back != node:
        raise AssertionError(
            f"stage-2 round-trip lost information:\n  in:  {node}\n  out: {back}"
        )
    return text


# --- self-test ---------------------------------------------------------------

def _self_test() -> None:
    from core.surface import parse as parse1, pretty

    cases = [
        "(merge (p 3) (tau 12))",
        "(seq (p 3) (p 4) (p 5))",
        "(let 1 12 (p (ref 1)))",
        "(merge 3 12)",              # adjacent literals need the separator
        "(merge 3 -12)",             # a negative literal does not
        "(defn square [n] (mul n n))(square 7)",
        '"abc"',
        "(def sum [xs] (if (nil? xs) 0 (merge (head xs) (sum (tail xs)))))"
        "(sum (list 1 2 3))",
    ]
    print(f"  {'Stage 1':<52s} {'Stage 2':<24s} {'B':>3s}")
    for src in cases:
        tree = parse1(src)
        text = round_trip(tree)
        from core.tokens import encode
        shown = src if len(src) <= 50 else src[:47] + "..."
        print(f"  {shown:<52s} {text:<24s} {len(encode(tree)):>3d}")

    # Both renderings round-trip; the packed one is what render() emits.
    for src in cases:
        tree = parse1(src)
        round_trip(tree, pack_refs=False)
        round_trip(tree, pack_refs=True)

    # The projection is total over the table, including reserved slots.
    assert len(SYMBOLS) == len(SIGNATURES) and len(TOKEN_FOR_SYMBOL) == len(SIGNATURES)

    example = parse1("(defn square [n] (mul n n))(square 7)")
    print()
    print(f"  reference digram: {render(example, pack_refs=False)}"
          f"  ->  {render(example)}")
    print("core.surface2 self-test OK")


if __name__ == "__main__":
    _self_test()
