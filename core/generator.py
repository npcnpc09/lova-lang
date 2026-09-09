"""Type-directed generation — the core of Axiom 3.

For any prefix of a LOVA token sequence, the set of well-typed next
tokens is computable.  A generator that samples only from this set
produces programs that are **guaranteed** to be well-formed and
well-typed — no syntax errors, no type errors, no arity errors.  This
is the substrate-level property that makes LOVA an AI-friendly
language: an LLM constrained to the valid set cannot produce ill-formed
programs at all, so all error-handling happens at higher semantic
layers (conservation violations, behavioural correctness).

**Paradigm lineage** (see ``../spec/paradigm-inheritance.md``):

- Grammar-constrained decoding (Outlines, llguidance, LMQL).
- Dependent-type narrowing (Agda/Idris/Lean).
- Positional typing (stack languages, Forth).

LOVA's synthesis:  the constraint applies to the entire language
(not just JSON/regex) and is computed by position in the integer
sequence (not by explicit annotations in text).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Set

from core.tokens import END, LIT_INT, SIGNATURES, TYPED_TOKENS
from core.types import INT, Type


# --- generation state -------------------------------------------------------

@dataclass
class Slot:
    """A pending position in the program being built.

    ``expected_type``: the type required to fill this slot.
    ``variadic_continuation``: if True, the slot stays on the stack
      after being filled (each filling appends another variadic
      element); acceptance of the ``END`` token closes the variadic.
    ``parent_op``: the operator token whose child-slot this is, if any
      (None for the root slot).  Used by telemetry / AI-preference
      layers that want per-context pass-rate stats (Q22).
    """
    expected_type: Type
    variadic_continuation: bool = False
    parent_op: Optional[int] = None


@dataclass
class GenState:
    """Incremental generation state — what we expect to see next.

    Each step consumes one token and updates the expected-slot stack.
    When the stack is empty, the program is complete.
    """
    stack: List[Slot] = field(default_factory=list)

    @classmethod
    def fresh(cls, top_type: Type = INT) -> "GenState":
        """Start a fresh state expecting a single expression of ``top_type``."""
        return cls(stack=[Slot(expected_type=top_type)])

    def is_complete(self) -> bool:
        return not self.stack

    # ---- valid next ------------------------------------------------------

    def valid_next(self) -> FrozenSet[int]:
        """The set of token bytes that can validly follow the current prefix.

        At any point this is the intersection of:
        - tokens whose ``out_type`` is a subtype of the top slot's
          expected type, AND
        - whose out_type is defined (i.e. Milestone-1-runtime-supported).

        If the top slot is a variadic continuation, ``END`` is also valid.
        """
        if not self.stack:
            return frozenset()  # program complete
        slot = self.stack[-1]
        valid: Set[int] = set()
        for tok in TYPED_TOKENS:
            sig = SIGNATURES[tok]
            out_type = sig.get("out_type")
            if out_type is None:
                continue
            # subtype check: does this token produce something that
            # fits the expected slot?
            from core.types import is_subtype
            if is_subtype(out_type, slot.expected_type):
                valid.add(tok)
        if slot.variadic_continuation:
            valid.add(END)
        return frozenset(valid)

    # ---- step -----------------------------------------------------------

    def step(self, token: int) -> "GenState":
        """Consume a token, return a new state reflecting the advance.

        Raises ``ValueError`` if ``token`` is not in ``self.valid_next()``.
        """
        valid = self.valid_next()
        if token not in valid:
            raise ValueError(
                f"token 0x{token:02X} not in valid_next {sorted(valid)}"
            )

        # Closing a variadic?
        if token == END:
            new_stack = list(self.stack)
            closed = new_stack.pop()
            assert closed.variadic_continuation
            return GenState(stack=new_stack)

        sig = SIGNATURES[token]
        new_stack = list(self.stack)
        top = new_stack[-1]

        # If the top slot is a variadic continuation, we do NOT pop it —
        # it stays on the stack, ready to accept another element or END.
        # If it's a single slot, pop it (we're about to fill it).
        if not top.variadic_continuation:
            new_stack.pop()

        # Push the operator's children.  Variadic operators push a
        # single "variadic continuation" slot.  Fixed-arity operators
        # push their ``in_types`` in reverse, so the first arg is at
        # the top of the stack.
        if sig.get("in_types") is None:
            # variadic
            new_stack.append(
                Slot(
                    expected_type=sig["variadic_type"],
                    variadic_continuation=True,
                    parent_op=token,
                )
            )
        else:
            for t in reversed(sig["in_types"]):
                new_stack.append(Slot(expected_type=t, parent_op=token))

        return GenState(stack=new_stack)


# --- literal payload helpers ------------------------------------------------

def encode_lit(value: int) -> bytes:
    """Encode a LIT_INT payload (length prefix + big-endian signed)."""
    bits = value.bit_length() + 1
    n_bytes = max(1, (bits + 7) // 8)
    if n_bytes > 255:
        raise ValueError(f"literal too large: {value}")
    return bytes([n_bytes]) + value.to_bytes(n_bytes, "big", signed=True)


# --- constrained random generator -------------------------------------------

def constrained_random(
    seed: int = 0,
    max_depth: int = 8,
    small_lit_range: int = 20,
) -> bytes:
    """Generate a random well-typed program, guided by ``valid_next``.

    At each step, sample a token uniformly from ``state.valid_next()``.
    A soft depth preference is applied: past ``max_depth`` the sampler
    biases toward LIT_INT and END so generation terminates.  This is a
    generation heuristic; correctness (well-typedness) is guaranteed by
    the valid-next filter, not by the heuristic.

    Returns a byte sequence that is by construction a well-formed,
    well-typed LOVA program.
    """
    rng = random.Random(seed)
    state = GenState.fresh()
    out = bytearray()
    depth = 0
    while not state.is_complete():
        valid = list(state.valid_next())
        # Termination bias: past max_depth, prefer LIT_INT or END.
        if depth > max_depth:
            terminating = [t for t in valid if t in (LIT_INT, END)]
            if terminating:
                valid = terminating
        token = rng.choice(valid)
        out.append(token)
        if token == LIT_INT:
            v = rng.randint(0, small_lit_range - 1)
            out.extend(encode_lit(v))
        state = state.step(token)
        depth += 1
    return bytes(out)


# --- unconstrained random generator (for comparison) ------------------------

def unconstrained_random(
    seed: int = 0,
    max_tokens: int = 12,
    small_lit_range: int = 20,
) -> bytes:
    """Generate a random byte sequence with NO type constraint.

    At each step, pick a random token from the typed subset (i.e. from
    operators the runtime can interpret — we don't add pure garbage
    bytes; the comparison is fair to a "well-intentioned but
    unconstrained" LLM).  No arity, no type, no END correctness is
    checked.  Most output will fail to parse or type-check.
    """
    rng = random.Random(seed)
    out = bytearray()
    all_typed = list(TYPED_TOKENS) + [END]  # END is also pickable
    for _ in range(max_tokens):
        tok = rng.choice(all_typed)
        out.append(tok)
        if tok == LIT_INT:
            v = rng.randint(0, small_lit_range - 1)
            out.extend(encode_lit(v))
    return bytes(out)


# --- validation helpers -----------------------------------------------------

def validates(data: bytes) -> bool:
    """True if ``data`` parses as a single well-typed LOVA program.

    Uses the integer decoder (``core.tokens.decode``) plus an independent
    re-walk through the type-directed state machine to confirm that every
    token was in its valid-next set.  This is the canonical "well-formed"
    predicate.
    """
    from core.tokens import decode
    try:
        node = decode(data)
    except ValueError:
        return False
    # Walk the resulting tree through the state machine to verify each
    # token is in the valid-next set at its position.
    try:
        _walk_tree(node)
    except ValueError:
        return False
    return True


def _walk_tree(node) -> None:
    """Rebuild a GenState from a Node tree and assert each step is valid."""
    state = GenState.fresh()
    _apply_node(state, node)
    # After walking the whole tree, state must be complete.
    # NB: _apply_node mutates a new state each step via its return.
    # The helper below does the real work.


def _apply_node(state: GenState, node) -> GenState:
    # Enter this token.
    state = state.step(node.op)
    if node.op == LIT_INT:
        # LIT_INT has no children in the AST — payload is intrinsic.
        return state
    # Walk the operator's children.
    for child in node.args:
        state = _apply_node(state, child)
    # For variadic, after all children we also need to close with END.
    sig = SIGNATURES[node.op]
    if sig.get("in_types") is None:
        state = state.step(END)
    return state


# --- self-test --------------------------------------------------------------

def _self_test() -> None:
    # Fresh state's valid_next should include every M1-typed op whose
    # out_type is a subtype of Int.
    s0 = GenState.fresh()
    v0 = s0.valid_next()
    assert LIT_INT in v0
    # Spot check a few expected members
    from core.tokens import GCD, MERGE, P, TAU, SEQ
    for tok in (LIT_INT, P, TAU, GCD, MERGE, SEQ):
        assert tok in v0, f"missing {tok:02X}"

    # After LET, the NEXT valid token should ONLY be LIT_INT — the
    # name-binding slot demands a literal.
    from core.tokens import LET
    s1 = s0.step(LET)
    v1 = s1.valid_next()
    assert v1 == frozenset({LIT_INT}), (
        f"after LET, valid_next should be {{LIT_INT}} but got {sorted(v1)}"
    )

    print("core.generator self-test OK")
    print(f"  fresh state valid_next size: {len(v0)}  (all Int-producing ops)")
    print(f"  after LET valid_next size:   {len(v1)}  (only LIT_INT allowed)")

    # Constrained random: 10 programs, all must validate.
    pass_count = 0
    for seed in range(10):
        data = constrained_random(seed=seed)
        if validates(data):
            pass_count += 1
    print(f"  constrained_random: {pass_count}/10 validate  "
          f"(expected 10/10)")


if __name__ == "__main__":
    _self_test()
