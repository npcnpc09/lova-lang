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
CONS            = 0x04   # (cons x xs)  (M10: was the heat-inc placeholder)
HEAD            = 0x05   # (head xs)    (M10: was the heat-get placeholder)
TAIL            = 0x06   # (tail xs)    (M10: was the inherit placeholder)
IDENTITY        = 0x07

# Family 0x08-0x0F  Number theory
P               = 0x08   # partition number p(n)
TAU             = 0x09   # divisor count τ(n)
SIGMA           = 0x0A   # divisor sum σ(n)
MUL             = 0x0B   # a × b        (M9: was the mock-theta φ₃ placeholder)
MOD             = 0x0C   # a mod b       (M9: was the mock-theta ψ₇ placeholder)
DIV             = 0x0D   # a // b       (M10: was the Dedekind-η placeholder)
GCD             = 0x0E
MOBIUS          = 0x0F

# Family 0x10-0x17  Conservation
BUDGET          = 0x10   # (budget k body) — body may consume ≤ k units
CONSERVE        = 0x11   # (conserve invariant body) — verify invariant holds
DELTA_CHECK     = 0x12
RESPAWN         = 0x13
BUDGET_REMAINING = 0x14
NIL             = 0x15   # the empty list (M10: was sum-invariant)
PRESERVE        = 0x16
VIOLATE         = 0x17   # (violate)  — synthetic "break conservation" op, testing only

# Family 0x18-0x1F  Surprise / watch
SURPRISE        = 0x18   # (surprise predicted actual) — returns |p-a|, emits trace
IS_NIL          = 0x19   # (nil? xs)    (M10: was the watch placeholder)
WHEN_ANOMALY    = 0x1A   # (when-anomaly body handler) -- M13
THRESHOLD       = 0x1B
EVAL            = 0x1C   # (eval program)   -- M14; was the predict placeholder
TRACE_SURPRISE  = 0x1D
READ            = 0x1E   # (read text) -- M18; was the normal-range placeholder
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
QUOTE           = 0x29   # (quote expr)     -- M14; was the par placeholder
IF_SURPRISE     = 0x2A
LOOP_UNTIL      = 0x2B
LAMBDA          = 0x2C   # (lambda (params...) body) — params is a LIT_INT symbol list
APPLY           = 0x2D
LET             = 0x2E   # (let name value body)
REF             = 0x2F   # (ref name) — dereference bound name

# Family 0x30-0x37  Effects / IO (stdout/stdin M11; boundary, fs, clock M19; net M21)
EXTERNAL_BOUNDARY = 0x30
NET_SEND        = 0x31
NET_RECV        = 0x32
FS_READ         = 0x33
FS_WRITE        = 0x34
STDOUT          = 0x35   # (stdout v)  -- write; M11
STDIN           = 0x36   # (stdin)     -- read a line; M11
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
    CONS:         {"name": "cons",          "arity": 2, "family": "struct"},
    HEAD:         {"name": "head",          "arity": 1, "family": "struct"},
    TAIL:         {"name": "tail",          "arity": 1, "family": "struct"},
    IDENTITY:     {"name": "identity",      "arity": 1, "family": "struct"},
    # Number theory
    P:            {"name": "p",             "arity": 1, "family": "nt"},
    TAU:          {"name": "tau",           "arity": 1, "family": "nt"},
    SIGMA:        {"name": "sigma",         "arity": 1, "family": "nt"},
    MUL:          {"name": "mul",           "arity": 2, "family": "nt"},
    MOD:          {"name": "mod",           "arity": 2, "family": "nt"},
    DIV:          {"name": "div",           "arity": 2, "family": "nt"},
    GCD:          {"name": "gcd",           "arity": 2, "family": "nt"},
    MOBIUS:       {"name": "mobius",        "arity": 1, "family": "nt"},
    # Conservation
    BUDGET:       {"name": "budget",        "arity": 2, "family": "cons"},
    CONSERVE:     {"name": "conserve",      "arity": 2, "family": "cons"},
    DELTA_CHECK:  {"name": "delta-check",   "arity": 1, "family": "cons"},
    RESPAWN:      {"name": "respawn",       "arity": 1, "family": "cons"},
    BUDGET_REMAINING: {"name": "budget-remaining", "arity": 0, "family": "cons"},
    NIL:          {"name": "nil",           "arity": 0, "family": "cons"},
    PRESERVE:     {"name": "preserve",      "arity": 2, "family": "cons"},
    VIOLATE:      {"name": "violate",       "arity": 1, "family": "cons"},
    # Surprise
    SURPRISE:     {"name": "surprise",      "arity": 2, "family": "surp"},
    IS_NIL:       {"name": "nil?",          "arity": 1, "family": "surp"},
    WHEN_ANOMALY: {"name": "when-anomaly",  "arity": 2, "family": "surp"},
    THRESHOLD:    {"name": "threshold",     "arity": 1, "family": "surp"},
    EVAL:         {"name": "eval",          "arity": 1, "family": "surp"},
    TRACE_SURPRISE: {"name": "trace-surprise", "arity": 1, "family": "surp"},
    READ:         {"name": "read",          "arity": 1, "family": "surp"},
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
    QUOTE:        {"name": "quote",         "arity": 1, "family": "comp"},
    IF_SURPRISE:  {"name": "if-surprise",   "arity": 3, "family": "comp"},
    LOOP_UNTIL:   {"name": "loop-until",    "arity": 2, "family": "comp"},
    LAMBDA:       {"name": "lambda",        "arity": 2, "family": "comp"},
    APPLY:        {"name": "apply",         "arity": "variadic", "family": "comp"},
    LET:          {"name": "let",           "arity": 3, "family": "comp"},
    REF:          {"name": "ref",           "arity": 1, "family": "comp"},
    # IO (placeholders)
    EXTERNAL_BOUNDARY: {"name": "external-boundary", "arity": 2, "family": "io"},
    NET_SEND:     {"name": "net-send",      "arity": 2, "family": "io"},
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
    UID:          {"name": "uid",           "arity": 1, "family": "meta"},
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

from core.types import FN, INT, LIST, LITERAL_INT, POPULATION, PROGRAM, VALUE  # noqa: E402

_TYPE_INFO = {
    # Literals
    LIT_INT:        {"in_types": [], "out_type": LITERAL_INT},
    # Structural (M1 subset)
    PARTITION:      {"in_types": [INT], "out_type": INT},
    MERGE:          {"in_types": [INT, INT], "out_type": INT},
    IDENTITY:       {"in_types": [INT], "out_type": INT},
    # Lists (M10; elements widened in M17).  A cons cell holds any value
    # -- an integer, a program, a list -- so trees and lists of programs
    # are representable.  The price is that `head`'s result type is no
    # longer written on the operator: it follows the list, which the
    # checker and the generator cannot see, so `head` joins the
    # result-follows-operands set and a misuse fails at run time with a
    # structured error.  The same trade `apply` and `ref` made (Q42).
    NIL:            {"in_types": [], "out_type": LIST},
    CONS:           {"in_types": [VALUE, LIST], "out_type": LIST},
    HEAD:           {"in_types": [LIST], "out_type": INT},
    TAIL:           {"in_types": [LIST], "out_type": LIST},
    IS_NIL:         {"in_types": [LIST], "out_type": INT},
    # Number theory (M1 subset)
    P:              {"in_types": [INT], "out_type": INT},
    TAU:            {"in_types": [INT], "out_type": INT},
    SIGMA:          {"in_types": [INT], "out_type": INT},
    GCD:            {"in_types": [INT, INT], "out_type": INT},
    MOBIUS:         {"in_types": [INT], "out_type": INT},
    MUL:            {"in_types": [INT, INT], "out_type": INT},
    MOD:            {"in_types": [INT, INT], "out_type": INT},
    DIV:            {"in_types": [INT, INT], "out_type": INT},
    # Conservation (M1 subset)
    BUDGET:         {"in_types": [LITERAL_INT, INT], "out_type": INT},
    CONSERVE:       {"in_types": [INT, INT], "out_type": INT},
    VIOLATE:        {"in_types": [INT], "out_type": INT},
    # Surprise (M1 subset + M9 comparison pair)
    SURPRISE:       {"in_types": [INT, INT], "out_type": INT},
    TRACE_SURPRISE: {"in_types": [INT], "out_type": INT},
    # DEVIATION is the signed sibling of SURPRISE (which returns |a-b|);
    # THRESHOLD is the sign test.  Together they give ordering:
    #   (a < b)  ==  (threshold (deviation b a))
    DEVIATION:      {"in_types": [INT, INT], "out_type": INT},
    THRESHOLD:      {"in_types": [INT], "out_type": INT},
    # Composition (M1 subset)
    SEQ:            {"in_types": None, "variadic_type": INT, "out_type": INT},
    # LET's value slot is the language's only ``Value`` slot: a binding
    # may hold an integer or a function, and this is what lets
    # ``(let f (lambda ...) ...)`` — and therefore recursion — type.
    LET:            {"in_types": [LITERAL_INT, VALUE, INT], "out_type": INT},
    REF:            {"in_types": [LITERAL_INT], "out_type": INT},
    IF_SURPRISE:    {"in_types": [INT, INT, INT], "out_type": INT},
    # Programs as values (M14).  `quote` is the constructor: its operand
    # is a well-formed expression of any type that is *not evaluated*.
    # `eval` is the eliminator, and its result is whatever the program
    # produces, so it joins the result-follows-operands set.
    QUOTE:          {"in_types": [VALUE], "out_type": PROGRAM},
    EVAL:           {"in_types": [PROGRAM], "out_type": INT},
    # Meta / lineage (M14) -- Axiom 5, in the language rather than in
    # core/lineage.py.  Every operator here takes a program value; the
    # ones that answer in text answer with a codepoint list, which is
    # what a string is.
    EXPLAIN:        {"in_types": [PROGRAM], "out_type": LIST},
    HASH:           {"in_types": [PROGRAM], "out_type": INT},
    UID:            {"in_types": [PROGRAM], "out_type": INT},
    GENERATION:     {"in_types": [PROGRAM], "out_type": INT},
    ANCESTOR_OF:    {"in_types": [PROGRAM, PROGRAM], "out_type": INT},
    LINEAGE_QUERY:  {"in_types": [PROGRAM], "out_type": LIST},
    WHY:            {"in_types": [PROGRAM], "out_type": LIST},
    TRACE:          {"in_types": [PROGRAM], "out_type": LIST},
    # Evolution (M14, first two) -- Axiom 6 begins to move into the
    # language.  `mutate` takes its strength as a percentage, because
    # LOVA has no fractions.
    CLONE:          {"in_types": [PROGRAM], "out_type": PROGRAM},
    MUTATE:         {"in_types": [PROGRAM, INT], "out_type": PROGRAM},
    # read (M18): text -> Program, the inverse of `explain`.  With both,
    # a LOVA program can construct a program from text and run it --
    # which is what a module system, and an agent writing LOVA from
    # inside LOVA, need.  Placed in the Surprise family only because the
    # Meta family is full (Q39).
    READ:           {"in_types": [LIST], "out_type": PROGRAM},
    # Evolution, the rest (M15) -- Axiom 6 in the language.  A scorer is
    # an Fn from Program to Int, and **lower is fitter**: the natural
    # score is a surprise magnitude, and zero surprise is perfect.
    #   (defpop scorer p1 p2 ...)   build a pool
    #   (fitness pop)               every variant's score, in pool order
    #   (variant pop k)             the k-th variant in pool order
    #   (select pop k)              the k-th *fittest* (0 = best)
    #   (retire pop)                the pool without its least-fit member
    #   (evolve pop)                one generation: retire the bottom 20%,
    #                               refill from the survivors by sharp
    #                               fitness-weighted clone (30%) or
    #                               mutate (70%, strength 30%)
    # The tail takes programs, or lists of programs (M18): a pool has to
    # be rebuildable from `variants-of`, and a variadic cannot be spliced
    # any other way.  The runtime checks that each element is one or the
    # other.
    DEFPOP:         {"in_types": None, "head_types": [FN],
                     "variadic_type": VALUE, "out_type": POPULATION},
    VARIANT:        {"in_types": [POPULATION, INT], "out_type": PROGRAM},
    EVOLVE:         {"in_types": [POPULATION], "out_type": POPULATION},
    SELECT:         {"in_types": [POPULATION, INT], "out_type": PROGRAM},
    FITNESS:        {"in_types": [POPULATION], "out_type": LIST},
    RETIRE:         {"in_types": [POPULATION], "out_type": POPULATION},
    # Error handling (M13).  ``(when-anomaly body handler)``: evaluate
    # `body`; if it traps, call `handler` with the anomaly's integer code
    # and return that instead.  The handler is an ``Fn`` because a
    # handler that is told nothing can only guess -- and Axiom 7 says the
    # anomaly is the signal.  Codes live in ``core.conservation``.
    #
    # The result type follows the body, so a guarded expression can stand
    # wherever the unguarded one could.
    WHEN_ANOMALY:   {"in_types": [VALUE, FN], "out_type": INT},
    # Abstraction (M9).  Lambdas are unary; multi-argument functions are
    # curried, so ``(lambda a (lambda b body))`` has type Fn and returns
    # an Fn.  APPLY is variadic with a *typed head*: the first slot must
    # be an Fn, every following slot an Int, and the call is applied
    # left-associatively (one argument at a time).
    # A lambda body is a ``Value``, not an ``Int``: currying means the
    # body of the outer lambda in ``(lambda a (lambda b ...))`` is
    # itself a function.
    LAMBDA:         {"in_types": [LITERAL_INT, VALUE], "out_type": FN},
    # An argument is any value: an Int, a List, or another function.
    # Typing the tail slots Int instead would make every list-processing
    # function unrepresentable, which is most of the point of having
    # lists.
    APPLY:          {"in_types": None, "head_types": [FN],
                     "variadic_type": VALUE, "out_type": INT},
    # LOOP_UNTIL is a combinator, not a statement: it takes a predicate
    # Fn and a step Fn and returns the Fn that iterates step until pred
    # is non-zero.  Arity 2 as declared; the seed arrives via APPLY.
    LOOP_UNTIL:     {"in_types": [FN, FN], "out_type": FN},
    # Effects / IO (M11).  The first operators in the language with a
    # side effect on the world rather than on the runtime's own state.
    #
    # `stdout` takes a Value because it writes both shapes: an integer
    # goes out as its decimal digits, a list as the text of its
    # codepoints.  It returns the number of codepoints written, which is
    # an Int, so a write can sit anywhere an Int can.
    #
    # `stdin` is the only non-deterministic operator in the language;
    # `static_analyze` reports that, and every claim about
    # reproducibility elsewhere is conditioned on its absence.
    STDOUT:         {"in_types": [VALUE], "out_type": INT},
    STDIN:          {"in_types": [], "out_type": LIST},
    # M19 -- the world beyond the terminal, under a declared boundary.
    # `(external-boundary caps body)` declares, as a literal bitmask
    # (CAPABILITY_BITS), which effects `body` may use; it is Axiom 4's
    # "effect bounds in the signature" made concrete, the way `budget`
    # declares cost.  The compiler rejects a use outside a boundary that
    # declares it, and the runtime traps a boundary the host did not
    # grant.  Its result is the body's, so it fits any slot.
    #
    # `fs-read` takes a path and yields the file as a codepoint list;
    # `fs-write` takes a path and a value -- text, or an integer written
    # as its digits, the same two shapes `stdout` writes -- and yields
    # the codepoints written; `clock` is milliseconds since the epoch.
    # All three are activations of slots the original table named.
    EXTERNAL_BOUNDARY: {"in_types": [LITERAL_INT, VALUE], "out_type": VALUE},
    FS_READ:        {"in_types": [LIST], "out_type": LIST},
    FS_WRITE:       {"in_types": [LIST, VALUE], "out_type": INT},
    CLOCK:          {"in_types": [], "out_type": INT},
    # M21 -- the network, as datagrams.  `(net-send "host:port" value)`
    # sends one UDP datagram (the value as UTF-8 text, an integer as its
    # digits) and yields the bytes sent; `(net-recv)` yields the next
    # datagram on the granted listening port as a codepoint list, or
    # `nil` when none arrives within the runtime's timeout -- the
    # end-of-input shape `stdin` has, because a receive that can hang
    # is a receive that can hang the substrate.  The program declares
    # the *kind* (`net`); the host names the *places* (`--allow
    # net=host:port` to send there, `net=:port` to listen there).
    # Where lives in host policy, not in the byte sequence (Q69).
    NET_SEND:       {"in_types": [LIST, VALUE], "out_type": INT},
    NET_RECV:       {"in_types": [], "out_type": LIST},
    # END is a structural sentinel — no out_type; the generator
    # handles it specially as a variadic terminator.
}

for _tok, _extra in _TYPE_INFO.items():
    SIGNATURES[_tok].update(_extra)

# Tokens currently reachable by type-directed generation.
TYPED_TOKENS = frozenset(_TYPE_INFO.keys())

# Operators whose result type is their operands' rather than their own.
#
# ``(if c a b)`` is whatever its branches are, ``(let n v body)``
# whatever ``body`` is, ``(apply f ...)`` whatever ``f`` returns.  Their
# declared ``out_type`` above is a placeholder that both the compiler and
# the generation state machine must look past, or a conditional could
# never return a list -- which is to say `map`, `filter` and `reverse`
# would be neither writable nor generatable.
#
# ``SEQ`` is transparent in the compiler but deliberately *not* here: a
# variadic may be empty, and `(seq)` evaluates to 0, so its result type
# is not determined by the slot it sits in.  The compiler checks that
# case separately.
RESULT_FOLLOWS_OPERANDS = frozenset({IF_SURPRISE, LET, APPLY, WHEN_ANOMALY, EVAL, HEAD,
                                     EXTERNAL_BOUNDARY})

# ``REF`` is the other operator whose result type is not its declared
# one: it is whatever the binding holds.  The compiler resolves that
# from its scope-aware type environment; the generation state machine
# cannot, because name ids live in LIT_INT payloads it never inspects
# (Exp 12, F4).  So a reference is admitted wherever a value is wanted,
# which is what lets a generated program call a bound function --
# `(apply (ref f) x)` -- and therefore have the shape of `map`.
#
# The two sets are kept apart because the reasons differ: one is a
# typing rule, the other is a limit on what the state machine can see.
RESULT_NOT_STATIC = RESULT_FOLLOWS_OPERANDS | {REF}

# Capabilities (M19).  A boundary's literal is a bitmask over these; an
# effect operator is usable only where the enclosing boundary's mask
# has its bit, and a boundary is enterable only if the host granted
# every bit it declares.  `net` is reserved with the two network slots.
CAPABILITY_BITS: Dict[str, int] = {
    "fs-read": 1,
    "fs-write": 2,
    "clock": 4,
    "net": 8,
}
CAPABILITY_OF: Dict[int, int] = {
    FS_READ: CAPABILITY_BITS["fs-read"],
    FS_WRITE: CAPABILITY_BITS["fs-write"],
    CLOCK: CAPABILITY_BITS["clock"],
    NET_SEND: CAPABILITY_BITS["net"],
    NET_RECV: CAPABILITY_BITS["net"],
}
ALL_CAPABILITIES = sum(CAPABILITY_OF[t] for t in (FS_READ, FS_WRITE, CLOCK))


def capability_names(mask: int) -> List[str]:
    """The capability names a bitmask carries, in bit order."""
    return [name for name, bit in CAPABILITY_BITS.items() if mask & bit]

# Symbol (interned name) → token byte.  Used by the surface parser.
NAME_TO_TOKEN = {sig["name"]: tok for tok, sig in SIGNATURES.items()}

# Unicode / ASCII aliases for Stage-1 readability.  These are surface-only;
# the substrate only knows NAME_TO_TOKEN.
ALIASES = {
    "⊕": "merge",
    "⊖": "partition",
    "τ": "tau",
    "σ": "sigma",
    "⊗": "mul",
    "μ": "mobius",
    "λ": "lambda",
    "?":  "surprise",
}

# Short spellings, chosen so that each is a **single LLM token** under
# GPT-4-class vocabularies (measured with tiktoken cl100k_base).
#
# This is not cosmetic.  Exp 13 decomposed the Stage-1 token cost of the
# algorithmic corpus and found 51% of it goes to operator names, against
# 25% for parentheses: `if-surprise` costs three LLM tokens, `deviation`
# two.  Rewriting ten programs to these spellings closed **30% of the
# density gap against Python for zero token-table slots** — three times
# what the two candidate new primitives were worth.  If AI is the
# first-class reader (Axiom 2), the generating model's tokenizer is part
# of the interface, and operator spelling is a substrate concern rather
# than a human convenience.
#
# The canonical names stay canonical: ``pretty`` still prints them, and
# ``spec/tokens.md`` still names them.  These are additional accepted
# spellings, not renames.
SHORT_ALIASES = {
    "if":   "if-surprise",       # 3 LLM tokens -> 1
    "dev":  "deviation",         # 2 -> 1
    "tr":   "trace-surprise",    # 3 -> 1
    "loop": "loop-until",        # 3 -> 1
    "keep": "conserve",          # 2 -> 1
    "dist": "surprise",          # 2 -> 1
    "mu":   "mobius",            # 2 -> 1
    "def":  "defn",              # 2 -> 1  (surface form, not an operator)
}

# What the surface parser accepts.  ``ALIASES`` alone drives the
# Unicode pretty-printer, so the two are kept separate: adding a short
# ASCII spelling must not change what ``pretty(unicode=True)`` emits.
SURFACE_ALIASES = {**ALIASES, **SHORT_ALIASES}


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
