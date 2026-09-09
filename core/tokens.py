"""64-token core of LOVA (Stage 1 MVP).

Each token is a single byte in [0x00, 0x3F]. Tokens are grouped into 8
families of 8. The full table is declared here; most are placeholders
in Milestone 1 — only the operators needed for the first end-to-end
experiment are implemented in ``core.runtime``. Touching any operator
unimplemented in the runtime raises ``NotImplementedError`` with a
pointer to the relevant family; this is intentional (Axiom 8 —
small core, every byte semantic).

See ``../spec/tokens.md`` for the human reference (DRAFT).
See ``../spec/axioms.md`` for the ten design invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple, Union

# --- token table -------------------------------------------------------------

# Family 0x00-0x07  Structural
END             = 0x00   # list terminator for variadic ops
LIT_INT         = 0x01   # integer literal (length-prefixed big-endian follows)
PARTITION       = 0x02   # n → (a, b) with a+b=n, heat-directed split
MERGE           = 0x03   # a, b → a+b
HEAT_INC        = 0x04
HEAT_GET        = 0x05
INHERIT         = 0x06
IDENTITY        = 0x07

# Family 0x08-0x0F  Number theory
P               = 0x08   # partition number p(n)
TAU             = 0x09   # divisor count τ(n)
SIGMA           = 0x0A   # divisor sum σ(n)
PHI3            = 0x0B   # mock theta φ₃ (placeholder)
PSI7            = 0x0C   # mock theta ψ₇ (placeholder)
ETA             = 0x0D   # Dedekind η (placeholder)
GCD             = 0x0E
MOBIUS          = 0x0F

# Family 0x10-0x17  Conservation
BUDGET          = 0x10   # (budget k body) — body may consume ≤ k units
CONSERVE        = 0x11   # (conserve invariant body) — verify invariant holds
DELTA_CHECK     = 0x12
RESPAWN         = 0x13
BUDGET_REMAINING = 0x14
SUM_INVARIANT   = 0x15
PRESERVE        = 0x16
VIOLATE         = 0x17   # (violate)  — synthetic "break conservation" op, testing only

# Family 0x18-0x1F  Surprise / watch
SURPRISE        = 0x18   # (surprise predicted actual) — returns |p-a|, emits trace
WATCH           = 0x19
WHEN_ANOMALY    = 0x1A
THRESHOLD       = 0x1B
PREDICT         = 0x1C
TRACE_SURPRISE  = 0x1D
NORMAL_RANGE    = 0x1E
DEVIATION       = 0x1F

# Family 0x20-0x27  Evolution
DEFPOP          = 0x20
VARIANT         = 0x21
EVOLVE          = 0x22
SELECT          = 0x23
MUTATE          = 0x24
CLONE           = 0x25
FITNESS         = 0x26
RETIRE          = 0x27

# Family 0x28-0x2F  Composition
SEQ             = 0x28   # variadic sequential composition (terminated by END)
PAR             = 0x29
IF_SURPRISE     = 0x2A
LOOP_UNTIL      = 0x2B
LAMBDA          = 0x2C   # (lambda (params...) body) — params is a LIT_INT symbol list
APPLY           = 0x2D
LET             = 0x2E   # (let name value body)
REF             = 0x2F   # (ref name) — dereference bound name

# Family 0x30-0x37  Effects / IO (all placeholders in MVP)
EXTERNAL_BOUNDARY = 0x30
NET_SEND        = 0x31
NET_RECV        = 0x32
FS_READ         = 0x33
FS_WRITE        = 0x34
STDOUT          = 0x35
STDIN           = 0x36
CLOCK           = 0x37

# Family 0x38-0x3F  Meta / lineage
LINEAGE_QUERY   = 0x38
WHY             = 0x39
TRACE           = 0x3A
EXPLAIN         = 0x3B
HASH            = 0x3C
UID             = 0x3D
ANCESTOR_OF     = 0x3E
GENERATION      = 0x3F


# --- signatures (arity + semantic family for the decoder) -------------------

# arity: an int (fixed arity) or the string "variadic" (terminated by END).
# LIT_INT has arity 0 but a special length-prefixed payload.
SIGNATURES = {
    # Structural
    END:          {"name": "end",           "arity": 0, "family": "struct"},
    LIT_INT:      {"name": "lit",           "arity": 0, "family": "struct",
                   "payload": "varint"},
    PARTITION:    {"name": "partition",     "arity": 1, "family": "struct"},
    MERGE:        {"name": "merge",         "arity": 2, "family": "struct"},
    HEAT_INC:     {"name": "heat-inc",      "arity": 1, "family": "struct"},
    HEAT_GET:     {"name": "heat-get",      "arity": 1, "family": "struct"},
    INHERIT:      {"name": "inherit",       "arity": 2, "family": "struct"},
    IDENTITY:     {"name": "identity",      "arity": 1, "family": "struct"},
    # Number theory
    P:            {"name": "p",             "arity": 1, "family": "nt"},
    TAU:          {"name": "tau",           "arity": 1, "family": "nt"},
    SIGMA:        {"name": "sigma",         "arity": 1, "family": "nt"},
    PHI3:         {"name": "phi3",          "arity": 2, "family": "nt"},
    PSI7:         {"name": "psi7",          "arity": 2, "family": "nt"},
    ETA:          {"name": "eta",           "arity": 1, "family": "nt"},
    GCD:          {"name": "gcd",           "arity": 2, "family": "nt"},
    MOBIUS:       {"name": "mobius",        "arity": 1, "family": "nt"},
    # Conservation
    BUDGET:       {"name": "budget",        "arity": 2, "family": "cons"},
    CONSERVE:     {"name": "conserve",      "arity": 2, "family": "cons"},
    DELTA_CHECK:  {"name": "delta-check",   "arity": 1, "family": "cons"},
    RESPAWN:      {"name": "respawn",       "arity": 1, "family": "cons"},
    BUDGET_REMAINING: {"name": "budget-remaining", "arity": 0, "family": "cons"},
    SUM_INVARIANT: {"name": "sum-invariant", "arity": 0, "family": "cons"},
    PRESERVE:     {"name": "preserve",      "arity": 2, "family": "cons"},
    VIOLATE:      {"name": "violate",       "arity": 1, "family": "cons"},
    # Surprise
    SURPRISE:     {"name": "surprise",      "arity": 2, "family": "surp"},
    WATCH:        {"name": "watch",         "arity": 1, "family": "surp"},
    WHEN_ANOMALY: {"name": "when-anomaly",  "arity": 2, "family": "surp"},
    THRESHOLD:    {"name": "threshold",     "arity": 1, "family": "surp"},
    PREDICT:      {"name": "predict",       "arity": 1, "family": "surp"},
    TRACE_SURPRISE: {"name": "trace-surprise", "arity": 1, "family": "surp"},
    NORMAL_RANGE: {"name": "normal-range",  "arity": 2, "family": "surp"},
    DEVIATION:    {"name": "deviation",     "arity": 2, "family": "surp"},
    # Evolution
    DEFPOP:       {"name": "defpop",        "arity": "variadic", "family": "evo"},
    VARIANT:      {"name": "variant",       "arity": 2, "family": "evo"},
    EVOLVE:       {"name": "evolve",        "arity": 1, "family": "evo"},
    SELECT:       {"name": "select",        "arity": 2, "family": "evo"},
    MUTATE:       {"name": "mutate",        "arity": 2, "family": "evo"},
    CLONE:        {"name": "clone",         "arity": 1, "family": "evo"},
    FITNESS:      {"name": "fitness",       "arity": 1, "family": "evo"},
    RETIRE:       {"name": "retire",        "arity": 1, "family": "evo"},
    # Composition
    SEQ:          {"name": "seq",           "arity": "variadic", "family": "comp"},
    PAR:          {"name": "par",           "arity": "variadic", "family": "comp"},
    IF_SURPRISE:  {"name": "if-surprise",   "arity": 3, "family": "comp"},
    LOOP_UNTIL:   {"name": "loop-until",    "arity": 2, "family": "comp"},
    LAMBDA:       {"name": "lambda",        "arity": 2, "family": "comp"},
    APPLY:        {"name": "apply",         "arity": "variadic", "family": "comp"},
    LET:          {"name": "let",           "arity": 3, "family": "comp"},
    REF:          {"name": "ref",           "arity": 1, "family": "comp"},
    # IO (placeholders)
    EXTERNAL_BOUNDARY: {"name": "external-boundary", "arity": 2, "family": "io"},
    NET_SEND:     {"name": "net-send",      "arity": 1, "family": "io"},
    NET_RECV:     {"name": "net-recv",      "arity": 0, "family": "io"},
    FS_READ:      {"name": "fs-read",       "arity": 1, "family": "io"},
    FS_WRITE:     {"name": "fs-write",      "arity": 2, "family": "io"},
    STDOUT:       {"name": "stdout",        "arity": 1, "family": "io"},
    STDIN:        {"name": "stdin",         "arity": 0, "family": "io"},
    CLOCK:        {"name": "clock",         "arity": 0, "family": "io"},
    # Meta
    LINEAGE_QUERY: {"name": "lineage-query", "arity": 1, "family": "meta"},
    WHY:          {"name": "why",           "arity": 1, "family": "meta"},
    TRACE:        {"name": "trace",         "arity": 1, "family": "meta"},
    EXPLAIN:      {"name": "explain",       "arity": 1, "family": "meta"},
    HASH:         {"name": "hash",          "arity": 1, "family": "meta"},
    UID:          {"name": "uid",           "arity": 0, "family": "meta"},
    ANCESTOR_OF:  {"name": "ancestor-of",   "arity": 2, "family": "meta"},
    GENERATION:   {"name": "generation",    "arity": 1, "family": "meta"},
}

assert len(SIGNATURES) == 64, f"Token table must have exactly 64 entries, found {len(SIGNATURES)}"


# --- typed-slot extensions (Milestone 2) ------------------------------------
#
# Only operators implemented by the Milestone 1 runtime receive type
# annotations.  Reserved operators have no ``out_type``; the generator
# treats them as unreachable and never emits them.  As milestones land,
# operators get type info here and become generation-reachable.

from core.types import INT, LITERAL_INT  # noqa: E402

_TYPE_INFO = {
    # Literals
    LIT_INT:        {"in_types": [], "out_type": LITERAL_INT},
    # Structural (M1 subset)
    PARTITION:      {"in_types": [INT], "out_type": INT},
    MERGE:          {"in_types": [INT, INT], "out_type": INT},
    IDENTITY:       {"in_types": [INT], "out_type": INT},
    # Number theory (M1 subset)
    P:              {"in_types": [INT], "out_type": INT},
    TAU:            {"in_types": [INT], "out_type": INT},
    SIGMA:          {"in_types": [INT], "out_type": INT},
    GCD:            {"in_types": [INT, INT], "out_type": INT},
    MOBIUS:         {"in_types": [INT], "out_type": INT},
    # Conservation (M1 subset)
    BUDGET:         {"in_types": [LITERAL_INT, INT], "out_type": INT},
    CONSERVE:       {"in_types": [INT, INT], "out_type": INT},
    VIOLATE:        {"in_types": [INT], "out_type": INT},
    # Surprise (M1 subset)
    SURPRISE:       {"in_types": [INT, INT], "out_type": INT},
    TRACE_SURPRISE: {"in_types": [INT], "out_type": INT},
    # Composition (M1 subset)
    SEQ:            {"in_types": None, "variadic_type": INT, "out_type": INT},
    LET:            {"in_types": [LITERAL_INT, INT, INT], "out_type": INT},
    REF:            {"in_types": [LITERAL_INT], "out_type": INT},
    IF_SURPRISE:    {"in_types": [INT, INT, INT], "out_type": INT},
    # END is a structural sentinel — no out_type; the generator
    # handles it specially as a variadic terminator.
}

for _tok, _extra in _TYPE_INFO.items():
    SIGNATURES[_tok].update(_extra)

# Tokens currently reachable by type-directed generation.
TYPED_TOKENS = frozenset(_TYPE_INFO.keys())

# Symbol (interned name) → token byte.  Used by the surface parser.
NAME_TO_TOKEN = {sig["name"]: tok for tok, sig in SIGNATURES.items()}

# Unicode / ASCII aliases for Stage-1 readability.  These are surface-only;
# the substrate only knows NAME_TO_TOKEN.
ALIASES = {
    "⊕": "merge",
    "⊖": "partition",
    "τ": "tau",
    "σ": "sigma",
    "φ₃": "phi3",
    "ψ₇": "psi7",
    "η": "eta",
    "μ": "mobius",
    "λ": "lambda",
    "?":  "surprise",
}


# --- AST ---------------------------------------------------------------------

@dataclass
class Node:
    """Decoded program node — token + children (or an integer payload for LIT_INT)."""
    op: int
    args: List[Union["Node", int]]

    def __repr__(self) -> str:
        if self.op == LIT_INT:
            return f"Lit({self.args[0]})"
        name = SIGNATURES[self.op]["name"]
        return f"({name} {' '.join(repr(a) for a in self.args)})"


# --- encoding ----------------------------------------------------------------

def encode(node: Node) -> bytes:
    """Serialise a Node tree to a byte stream.

    LIT_INT uses a 1-byte length prefix (little surprise — Milestone 1
    picks a simple, obviously-lossless encoding over a space-optimal
    varint).  Max literal size is 255 bytes.  Values are signed, big-endian,
    two's complement (via Python ``int.to_bytes(..., signed=True)``).
    """
    buf = bytearray()
    _encode_into(node, buf)
    return bytes(buf)


def _encode_into(node: Node, buf: bytearray) -> None:
    buf.append(node.op)
    if node.op == LIT_INT:
        val: int = node.args[0]
        # How many bytes needed?  ``bit_length`` + sign bit.
        bits = val.bit_length() + 1
        n_bytes = max(1, (bits + 7) // 8)
        if n_bytes > 255:
            raise ValueError(f"LIT_INT too large: {val}")
        buf.append(n_bytes)
        buf.extend(val.to_bytes(n_bytes, "big", signed=True))
        return
    sig = SIGNATURES[node.op]
    if sig["arity"] == "variadic":
        for child in node.args:
            _encode_into(child, buf)
        buf.append(END)
    else:
        expected = sig["arity"]
        if len(node.args) != expected:
            raise ValueError(
                f"token {sig['name']} expects {expected} args, got {len(node.args)}"
            )
        for child in node.args:
            _encode_into(child, buf)


# --- decoding ----------------------------------------------------------------

def decode(data: bytes) -> Node:
    """Decode a byte stream into a Node.  The stream is expected to contain
    exactly one top-level expression."""
    node, pos = _decode_one(data, 0)
    if pos != len(data):
        trailing = data[pos:].hex()
        raise ValueError(f"trailing bytes after decode: {trailing}")
    return node


def _decode_one(data: bytes, pos: int) -> Tuple[Node, int]:
    if pos >= len(data):
        raise ValueError("unexpected end of stream")
    op = data[pos]
    if op not in SIGNATURES:
        raise ValueError(f"unknown token 0x{op:02X} at position {pos}")
    if op == LIT_INT:
        if pos + 1 >= len(data):
            raise ValueError("LIT_INT: missing length byte")
        length = data[pos + 1]
        if pos + 2 + length > len(data):
            raise ValueError("LIT_INT: truncated payload")
        val = int.from_bytes(data[pos + 2 : pos + 2 + length], "big", signed=True)
        return Node(op=LIT_INT, args=[val]), pos + 2 + length
    sig = SIGNATURES[op]
    pos += 1
    children: List[Any] = []
    if sig["arity"] == "variadic":
        while pos < len(data) and data[pos] != END:
            child, pos = _decode_one(data, pos)
            children.append(child)
        if pos >= len(data):
            raise ValueError(f"{sig['name']}: missing END terminator")
        pos += 1  # consume END
    else:
        for _ in range(sig["arity"]):
            child, pos = _decode_one(data, pos)
            children.append(child)
    return Node(op=op, args=children), pos


# --- convenience constructors ------------------------------------------------

def Lit(value: int) -> Node:
    return Node(op=LIT_INT, args=[value])


def Call(op_name: str, *args: Union[Node, int]) -> Node:
    """Build a Node by operator name (resolves aliases)."""
    actual_name = ALIASES.get(op_name, op_name)
    tok = NAME_TO_TOKEN[actual_name]
    children = [Lit(a) if isinstance(a, int) else a for a in args]
    return Node(op=tok, args=children)


# --- self-test ---------------------------------------------------------------

def _self_test() -> None:
    """Basic round-trip check.  Run via ``python -m core.tokens``."""
    tree = Call("p", 12)
    data = encode(tree)
    back = decode(data)
    assert back == tree, f"round-trip mismatch:\n  in:  {tree}\n  out: {back}"
    # nested
    tree2 = Call("merge", Call("p", 3), Call("tau", 12))
    data2 = encode(tree2)
    back2 = decode(data2)
    assert back2 == tree2
    # variadic SEQ
    tree3 = Call("seq", Call("p", 3), Call("p", 4), Call("p", 5))
    data3 = encode(tree3)
    back3 = decode(data3)
    assert back3 == tree3
    print("core.tokens self-test OK")
    print(f"  (p 12)                        -> {data.hex(' ')}  ({len(data)} bytes)")
    print(f"  (merge (p 3) (tau 12))        -> {data2.hex(' ')}  ({len(data2)} bytes)")
    print(f"  (seq (p 3) (p 4) (p 5))       -> {data3.hex(' ')}  ({len(data3)} bytes)")


if __name__ == "__main__":
    _self_test()
