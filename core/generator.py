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
from dataclasses import dataclass, field, replace
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from core.tokens import (
    APPLY, END, IF_SURPRISE, LAMBDA, LET, LIT_INT, REF,
    RESULT_FOLLOWS_OPERANDS, RESULT_NOT_STATIC, SIGNATURES, TYPED_TOKENS,
    WHEN_ANOMALY, CAPABILITY_OF, EXTERNAL_BOUNDARY, LIT_TEXT, TEXT_FAMILY,
)
from core.types import INT, LITERAL_INT, Type


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
    # M16 -- what a literal in this slot *means*.  "binder": the name a
    # LET or LAMBDA introduces.  "ref-name": the name a REF resolves.
    # "binding-value": the value slot of a LET, whose first token tells
    # the frame its type.  None for an ordinary literal or expression.
    role: Optional[str] = None
    frame: Optional[int] = None
    ref_type: Optional[Type] = None
    # M19 -- the capabilities the innermost `external-boundary` declared
    # for this position.  An effect operator is offered only where its
    # bit is set, so a generated program cannot use the world without
    # declaring it: Axiom 3 at the effect level, and the same rule the
    # compiler's capability pass enforces on hand-written trees.  The
    # role "caps" marks the boundary's own literal slot; ``enclosed``
    # says some boundary is already around this position, in which case
    # a nested one may only narrow (Q70).
    caps: int = 0
    enclosed: bool = False


@dataclass
class Frame:
    """One name in scope during generation (M16).

    ``name`` is None until the binder's literal is stepped with a
    payload; ``type`` is None -- unknown, fits anywhere -- until the
    binding's value shows its first token.  ``base`` is the stack depth
    the binding form was opened at; the frame is live while the stack
    is deeper than that, and is discarded the moment the form's subtree
    completes.
    """
    name: Optional[int]
    type: Optional[Type]
    base: int
    # M23 (Q79).  ``pending``: a LET's name while its value is still
    # being generated -- the runtime installs the binding only after
    # the value exists, so a reference evaluated inside the value is
    # unbound unless it sits under a lambda, which runs later.
    # ``lam``: the frame is a lambda's, which is what shields a
    # pending name.
    pending: bool = False
    lam: bool = False


@dataclass
class GenState:
    """Incremental generation state — what we expect to see next.

    Each step consumes one token and updates the expected-slot stack.
    When the stack is empty, the program is complete.
    """
    stack: List[Slot] = field(default_factory=list)
    # M16 -- the names in scope at this point of the program.  Until
    # M16 the state machine saw only operator bytes: a name id lives in
    # a LIT_INT payload it never inspected, so it could not know which
    # names were bound, and `ref` was offered everywhere on the chance
    # that one was.  Axiom 3 therefore held at the operator level and
    # not the name level (Exp 12, F4).  With payloads passed to `step`,
    # the machine keeps scope, `ref` is offered only where a compatible
    # bound name exists, and an unbound reference is unrepresentable
    # rather than a compile error.
    scopes: List[Frame] = field(default_factory=list)
    track_scope: bool = True

    @classmethod
    def fresh(cls, top_type: Type = INT, track_scope: bool = True) -> "GenState":
        """Start a fresh state expecting a single expression of ``top_type``.

        ``track_scope=False`` restores the pre-M16 machine -- every
        `ref` offered, no names kept -- which is what Experiment 16
        measures against.
        """
        return cls(stack=[Slot(expected_type=top_type)], track_scope=track_scope)

    def is_complete(self) -> bool:
        return not self.stack

    # ---- scope (M16) ------------------------------------------------------

    def bound_names(self) -> List[Frame]:
        """Frames whose binder has been named, innermost last."""
        return [f for f in self.scopes if f.name is not None]

    def valid_names(self) -> List[int]:
        """Name ids a `ref` may use in the current slot.

        Empty unless the top slot is a ref-name slot.  A name fits when
        its binding's type is unknown or a subtype of what the `ref` has
        to produce.  Innermost binding of a name wins, as at run time.
        """
        if not self.stack or self.stack[-1].role != "ref-name":
            return []
        from core.types import is_subtype
        wanted = self.stack[-1].ref_type
        seen: Dict[int, Frame] = {}
        for frame in self.bound_names():
            if frame.pending and not any(
                    f.lam and f.base > frame.base for f in self.scopes):
                continue                          # Q79: strict self-reference
            seen[frame.name] = frame              # later shadows earlier
        out = []
        for name, frame in seen.items():
            if frame.type is None or wanted is None or is_subtype(frame.type, wanted):
                out.append(name)
        return sorted(out)

    def fresh_name(self) -> int:
        """A name id not bound in the current scope."""
        taken = {f.name for f in self.bound_names()}
        candidate = 0
        while candidate in taken:
            candidate += 1
        return candidate

    def literal_for(self, rng, small_lit_range: int = 20) -> int:
        """The payload a sampler should emit for the top literal slot."""
        if self.stack:
            role = self.stack[-1].role
            if role == "binder":
                return self.fresh_name()
            if role == "ref-name":
                names = self.valid_names()
                if names:
                    return rng.choice(names)
            if role == "caps":
                top = self.stack[-1]
                if top.enclosed:
                    return rng.randint(0, 15) & top.caps  # narrow only (Q70)
                return rng.randint(0, 15)         # any mix of fs-read/fs-write/clock/net
        return rng.randint(0, small_lit_range - 1)

    # ---- valid next ------------------------------------------------------

    def valid_next(self, generate: bool = True) -> FrozenSet[int]:
        """The set of token bytes that can validly follow the current prefix.

        At any point this is the intersection of:
        - tokens whose ``out_type`` is a subtype of the top slot's
          expected type, AND
        - whose out_type is defined (i.e. Milestone-1-runtime-supported).

        If the top slot is a variadic continuation, ``END`` is also valid.

        ``generate=False`` is the *validation* view (M25): it admits the
        text family and the text literal as well, so a program that
        uses them validates, while the samplers -- which call this with
        the default -- do not yet emit them (their distributions, and
        Exp 16's figures, stay put until text generation is designed).
        """
        if not self.stack:
            return frozenset()  # program complete
        slot = self.stack[-1]
        valid: Set[int] = set()
        from core.types import LITERAL_INT, TEXT, is_subtype
        if not generate and slot.role not in ("binder", "ref-name", "caps")                 and is_subtype(TEXT, slot.expected_type):
            valid.add(LIT_TEXT)
        for tok in TYPED_TOKENS if generate else (TYPED_TOKENS | TEXT_FAMILY):
            sig = SIGNATURES[tok]
            out_type = sig.get("out_type")
            if out_type is None:
                continue
            if tok in CAPABILITY_OF and not slot.caps & CAPABILITY_OF[tok]:
                continue          # the world is not declared here (M19)
            if tok in RESULT_NOT_STATIC:
                # Either the result type follows the slot (if / let /
                # apply / eval) or it follows a binding.  A binding the
                # machine can see (M16) is checked: `ref` is offered only
                # where some bound name fits.  Nothing fits a slot that
                # demands a literal, which demands a *literal*, not a type.
                if slot.expected_type == LITERAL_INT:
                    continue
                if tok == REF and self.track_scope:
                    probe = Slot(expected_type=LITERAL_INT, role="ref-name",
                                 ref_type=slot.expected_type)
                    if not GenState(stack=self.stack + [probe],
                                    scopes=self.scopes).valid_names():
                        continue
                valid.add(tok)
                continue
            # subtype check: does this token produce something that
            # fits the expected slot?
            if is_subtype(out_type, slot.expected_type):
                valid.add(tok)
        if slot.variadic_continuation:
            valid.add(END)
        return frozenset(valid)

    # ---- step -----------------------------------------------------------

    def step(self, token: int, payload: Optional[int] = None) -> "GenState":
        """Consume a token, return a new state reflecting the advance.

        ``payload`` is the value of a LIT_INT.  It matters in exactly
        three places -- the name slot of LET, of LAMBDA, and of REF --
        where it is what the machine needs to keep scope.  Elsewhere it
        is ignored.  Without it a binder binds an anonymous name and a
        ref is unchecked, which is the pre-M16 behaviour.

        Raises ``ValueError`` if ``token`` is not in ``self.valid_next()``,
        or if a ref names something not in scope.
        """
        valid = self.valid_next(generate=False)
        if token not in valid:
            raise ValueError(
                f"token 0x{token:02X} not in valid_next {sorted(valid)}"
            )

        scopes = [Frame(f.name, f.type, f.base, f.pending, f.lam)
                  for f in self.scopes]

        # Closing a variadic?
        if token == END:
            new_stack = list(self.stack)
            closed = new_stack.pop()
            assert closed.variadic_continuation
            return self._advance(new_stack, scopes)

        sig = SIGNATURES[token]
        new_stack = list(self.stack)
        top = new_stack[-1]

        if self.track_scope:
            if token == LIT_INT and top.role == "binder" and top.frame is not None:
                scopes[top.frame].name = payload
            elif token == LIT_INT and top.role == "ref-name" and payload is not None:
                if payload not in self.valid_names():
                    raise ValueError(
                        f"ref {payload} names nothing in scope that fits "
                        f"{top.ref_type}; in scope: {self.valid_names()}"
                    )
            if top.role == "binding-value" and top.frame is not None:
                declared = sig.get("out_type")
                if token == LIT_INT:
                    scopes[top.frame].type = INT
                elif token in RESULT_NOT_STATIC or declared is None:
                    scopes[top.frame].type = None
                else:
                    scopes[top.frame].type = declared

        # If the top slot is a variadic continuation, we do NOT pop it —
        # it stays on the stack, ready to accept another element or END.
        # If it's a single slot, pop it (we're about to fill it).
        if not top.variadic_continuation:
            new_stack.pop()

        if token == LIT_INT and top.role == "caps" and new_stack:
            # The boundary's literal names what its body may do; the
            # body slot is the next one down.  Nested, it may only narrow.
            declared = int(payload or 0)
            if top.enclosed and declared & ~top.caps:
                raise ValueError(
                    f"nested boundary declares {declared:#x} beyond the "
                    f"enclosing {top.caps:#x}"
                )
            new_stack[-1] = replace(new_stack[-1], caps=declared, enclosed=True)

        base = len(new_stack)

        # Push the operator's children.  Variadic operators push a
        # single "variadic continuation" slot.  Fixed-arity operators
        # push their ``in_types`` in reverse, so the first arg is at
        # the top of the stack.
        if sig.get("in_types") is None:
            # Variadic.  The continuation slot goes on FIRST so that it
            # ends up *below* any typed head slots — the head arguments
            # are consumed before the variadic tail opens.  APPLY is the
            # only head-typed variadic today: ``(apply f a b ...)`` wants
            # an Fn first and Values thereafter.
            new_stack.append(
                Slot(
                    expected_type=sig["variadic_type"],
                    variadic_continuation=True,
                    parent_op=token,
                    caps=top.caps,
                    enclosed=top.enclosed,
                )
            )
            for t in reversed(sig.get("head_types", ())):
                new_stack.append(Slot(expected_type=t, parent_op=token,
                                      caps=top.caps, enclosed=top.enclosed))
        else:
            children = [Slot(expected_type=t, parent_op=token,
                             caps=top.caps, enclosed=top.enclosed)
                        for t in _child_types(token, top.expected_type)]
            if token == EXTERNAL_BOUNDARY:
                children[0].role = "caps"
            if self.track_scope and token in (LET, LAMBDA):
                scopes.append(Frame(name=None, type=None, base=base,
                                    pending=token == LET, lam=token == LAMBDA))
                index = len(scopes) - 1
                children[0].role, children[0].frame = "binder", index
                if token == LET:
                    children[1].role, children[1].frame = "binding-value", index
            elif self.track_scope and token == REF:
                children[0].role = "ref-name"
                children[0].ref_type = top.expected_type
            for child in reversed(children):
                new_stack.append(child)

        return self._advance(new_stack, scopes)

    def _advance(self, new_stack: List[Slot], scopes: List[Frame]) -> "GenState":
        # A frame lives while the stack is deeper than where its binding
        # form was opened; when the form's subtree completes, the stack
        # is back at that depth and the name goes out of scope.
        live = [f for f in scopes if f.base < len(new_stack)]
        for f in live:
            # A LET's children are [body, value, binder] above ``base``;
            # once only the body slot is left, the value is complete
            # and the binding is installed.
            if f.pending and len(new_stack) <= f.base + 1:
                f.pending = False
        return GenState(stack=new_stack, scopes=live, track_scope=self.track_scope)


# --- termination control -----------------------------------------------------
#
# A depth-limited sampler needs to know which choice gets it *finished*,
# and neither of the two obvious tests answers that.
#
# "Does this token shrink the slot stack" cannot: ``LOOP_UNTIL`` pushes
# two ``Fn`` slots and ``LAMBDA`` pushes none, yet both have a stack
# delta of +1.  Sampling uniformly between them is a *critical* branching
# process — mean one offspring — which terminates with probability 1 and
# infinite expected time.  In practice, a hang (Experiment 02, seed 808).
#
# "Does this token push another slot of the type I am filling" cannot
# either: in an ``Int`` slot ``APPLY`` pushes no ``Int``, so it looks
# safe, while actually opening an ``Fn`` slot *and* a variadic ``Value``
# tail that only closes on ``END``.  Sampling it repeatedly grows the
# stack without ever repeating a type (Experiment 02, seed 2: 358 slots
# still open after 4096 tokens).
#
# What does answer it is the **minimum number of tokens still needed to
# finish**.  Choosing a minimum-cost token strictly decreases that
# quantity, so generation terminates in at most `cost` further steps.

def _child_types(token: int, slot_type: Type) -> List[Type]:
    """The types of a fixed-arity operator's children, given its slot.

    For most operators this is just the declared ``in_types``.  For the
    result-follows-operands set it is the declared types with the
    *slot's* type substituted into the positions that determine the
    result -- both branches of an `if`, the body of a `let`.  Without
    this the generator can build `(if c 1 2)` but never
    `(if c (nil) xs)`, so no generated program can have the shape of
    `map` (journal Q52).
    """
    sig = SIGNATURES[token]
    declared = list(sig["in_types"])
    if token == IF_SURPRISE:
        return [declared[0], slot_type, slot_type]
    if token == LET:
        return [declared[0], declared[1], slot_type]
    if token == WHEN_ANOMALY:
        return [slot_type, declared[1]]
    if token == EXTERNAL_BOUNDARY:
        return [declared[0], slot_type]
    return declared


def _pushed_types(token: int, slot_type: Type = INT) -> Tuple[List[Type], bool]:
    """The slot types ``token`` opens, and whether it opens a variadic tail."""
    sig = SIGNATURES[token]
    if sig.get("in_types") is None:
        return list(sig.get("head_types", ())), True
    return _child_types(token, slot_type), False


def _compute_completion_costs() -> Dict[Type, int]:
    """Fixpoint: the fewest tokens that can close a slot of each type.

    ``Int`` and ``Value`` cost 1 (a literal), ``List`` 1 (``nil``),
    ``LiteralInt`` 1, ``Fn`` 3 (``lambda`` plus a name plus a body).
    A variadic tail costs 1, because ``END`` closes it.
    """
    from core.types import is_subtype

    types = {slot.expected_type for slot in ()}  # placeholder for clarity
    types = set()
    for tok in TYPED_TOKENS:
        pushed, _variadic = _pushed_types(tok)
        types.update(pushed)
        out = SIGNATURES[tok].get("out_type")
        if out is not None:
            types.add(out)

    costs: Dict[Type, int] = {t: _UNREACHABLE for t in types}
    for _ in range(len(types) + 2):
        changed = False
        for target in types:
            best = _UNREACHABLE
            for tok in TYPED_TOKENS:
                out = SIGNATURES[tok].get("out_type")
                if out is None:
                    continue
                # Only operators whose result type is written on them.
                # A transparent operator -- `head`, `apply`, `eval` --
                # can fill any slot and be wrong at run time; counting
                # `(head (nil))` as the cheapest way to close an Fn slot
                # (M17 made it so) would make the termination bias reach
                # for a guaranteed trap.  Certainty is the bias's job;
                # the free phase may still gamble.
                if tok in RESULT_NOT_STATIC or not is_subtype(out, target):
                    continue
                pushed, variadic = _pushed_types(tok, target)
                total = 1 + (1 if variadic else 0)
                for child in pushed:
                    total += costs.get(child, _UNREACHABLE)
                best = min(best, total)
            if best < costs[target]:
                costs[target] = best
                changed = True
        if not changed:
            break
    return costs


_UNREACHABLE = 10 ** 6
COMPLETION_COST: Dict[Type, int] = {}


def completion_cost(slot_type: Type) -> int:
    """Fewest tokens that can close a slot of ``slot_type``."""
    if not COMPLETION_COST:
        COMPLETION_COST.update(_compute_completion_costs())
    return COMPLETION_COST.get(slot_type, _UNREACHABLE)


def token_completion_cost(token: int, slot: Slot) -> int:
    """Fewest tokens to finish everything, if ``token`` fills ``slot``.

    ``END`` costs 1 and closes the slot.  Any other token in a variadic
    continuation leaves that continuation open, so its own ``END`` is
    still owed — which is what makes ``END`` the cheapest choice in a
    tail, and a literal the cheapest choice in a fixed slot.
    """
    if token == END:
        return 1
    pushed, variadic = _pushed_types(token, slot.expected_type)
    total = 1 + (1 if variadic else 0)
    for child in pushed:
        total += completion_cost(child)
    if slot.variadic_continuation:
        total += 1
    return total


def is_certain(state: "GenState", token: int) -> bool:
    """Does ``token``'s result type certainly fit the top slot?

    True for END, literals and any operator whose declared out_type is
    the slot's.  For ``ref`` it depends on scope: certain when a bound
    name of *known*, compatible type exists.  False for the transparent
    operators, whose result is whatever their operands turn out to be.
    """
    if token == END or token == LIT_INT or token == LIT_TEXT:
        return True
    if token == REF:
        if not state.stack or not state.track_scope:
            return False
        from core.types import is_subtype
        wanted = state.stack[-1].expected_type
        return any(f.type is not None and is_subtype(f.type, wanted)
                   for f in state.bound_names())
    return token not in RESULT_NOT_STATIC


def cheapest_to_finish(state: "GenState", tokens) -> List[int]:
    """Restrict ``tokens`` to those that finish the program soonest.

    Among *certain* closers (M17): a transparent operator is never the
    bias's choice, because "cheapest" would then mean "cheapest gamble".
    Every slot type has a certain closer -- a literal, `nil`, `lambda`,
    `quote`, `defpop` -- so the fallback to all tokens never fires for a
    well-formed slot.

    Exposed because every sampler needs it and the obvious hand-rolled
    version is wrong.  "Prefer END, else LIT_INT" reads like a
    termination rule and is not one: neither is valid in an ``Fn`` slot,
    so the filter silently does nothing exactly where it is needed, and
    the walk becomes a critical branching process.  Experiment 10 had
    that version copied into both of its samplers and hung the moment
    M13 made ``Fn`` slots common.
    """
    if not state.stack:
        return list(tokens)
    slot = state.stack[-1]
    certain = [t for t in tokens if is_certain(state, t)] or list(tokens)
    costs = {t: token_completion_cost(t, slot) for t in certain}
    if not costs:
        return list(tokens)
    cheapest = min(costs.values())
    return [t for t in costs if costs[t] == cheapest]


# A sampler that cannot terminate is a bug, not a slow path, so the loop
# carries a hard ceiling and reports rather than spins.
MAX_GENERATED_TOKENS = 4096


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
    track_scope: bool = True,
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
    state = GenState.fresh(track_scope=track_scope)
    out = bytearray()
    depth = 0
    emitted = 0
    while not state.is_complete():
        valid = sorted(state.valid_next())
        # Termination bias: past max_depth, restrict the candidates to
        # those with the smallest completion cost.  That is a strict
        # decrease in the work remaining, so the program closes in at
        # most `cost` further tokens — unlike the two weaker tests this
        # replaced, both of which admitted non-terminating walks.
        if depth > max_depth:
            valid = cheapest_to_finish(state, valid)
        token = rng.choice(valid)
        out.append(token)
        payload = None
        if token == LIT_INT:
            # A fresh name for a binder, a bound one for a ref, a small
            # integer anywhere else (M16).
            payload = state.literal_for(rng, small_lit_range)
            out.extend(encode_lit(payload))
        state = state.step(token, payload)
        depth += 1
        emitted += 1
        if emitted > MAX_GENERATED_TOKENS:
            raise ValueError(
                f"constrained_random(seed={seed}) exceeded "
                f"MAX_GENERATED_TOKENS={MAX_GENERATED_TOKENS} with "
                f"{len(state.stack)} slots still open; the termination bias "
                "failed to close the program"
            )
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

def validates(data: bytes, top_type: Type = None, track_scope: bool = True) -> bool:
    """True if ``data`` parses as a single well-typed LOVA program.

    Uses the integer decoder (``core.tokens.decode``) plus an independent
    re-walk through the type-directed state machine to confirm that every
    token was in its valid-next set.  This is the canonical "well-formed"
    predicate.

    The top slot is ``Value``: a program is an expression, not an integer
    expression, which is the same choice the compiler makes.  Pass
    ``top_type=INT`` to ask the narrower question.
    """
    from core.tokens import decode
    try:
        node = decode(data)
    except ValueError:
        return False
    # Walk the resulting tree through the state machine to verify each
    # token is in the valid-next set at its position.
    if top_type is None:
        from core.types import VALUE
        top_type = VALUE
    try:
        _walk_tree(node, top_type, track_scope)
    except ValueError:
        return False
    return True


def _walk_tree(node, top_type: Type = INT, track_scope: bool = True) -> None:
    """Rebuild a GenState from a Node tree and assert each step is valid."""
    state = GenState.fresh(top_type, track_scope=track_scope)
    _apply_node(state, node)
    # After walking the whole tree, state must be complete.
    # NB: _apply_node mutates a new state each step via its return.
    # The helper below does the real work.


def _apply_node(state: GenState, node) -> GenState:
    # Enter this token.  A literal carries its value, which the machine
    # uses only where the literal is a name (M16).
    if node.op == LIT_INT:
        return state.step(node.op, int(node.args[0]))
    if node.op == LIT_TEXT:
        return state.step(node.op)
    state = state.step(node.op)
    # Walk the operator's children.
    for child in node.args:
        state = _apply_node(state, child)
    # For variadic, after all children we also need to close with END.
    # Head-typed variadics (APPLY) are no different here: the head is
    # simply the first child, and END closes the tail.
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

    # An Int slot must never offer LAMBDA / LOOP_UNTIL (they produce Fn),
    # and the APPLY head slot must offer only Fn-producing operators.
    from core.tokens import APPLY, LAMBDA, LOOP_UNTIL
    assert LAMBDA not in v0 and LOOP_UNTIL not in v0, (
        "Fn-producing operators leaked into an Int slot"
    )
    s_apply = s0.step(APPLY)
    v_apply = s_apply.valid_next()
    # Fn producers, plus the operators whose result type follows their
    # slot -- `(apply (if c f g) x)` chooses between two functions, and
    # that is a legitimate program.
    assert {LAMBDA, LOOP_UNTIL} <= v_apply, sorted(v_apply)
    assert v_apply <= {LAMBDA, LOOP_UNTIL} | RESULT_NOT_STATIC, (
        f"APPLY head slot admits a non-Fn producer: {sorted(v_apply)}"
    )

    # Every slot type must be closable, and the cheapest closer must be
    # the one the sampler is supposed to reach for.
    from core.tokens import APPLY as _AP, LOOP_UNTIL as _LU, NIL
    from core.types import FN as _FN, LIST as _LIST, VALUE as _VALUE
    # A literal closes Int, Value and LiteralInt in one token; `nil`
    # closes List in one.  Fn takes two, because the cheapest way to
    # produce a function is to name one -- `(ref k)` is an operator plus
    # its literal, against `lambda`'s three.
    # Certain closers only: Fn is three tokens (a lambda), not two (a ref
    # that might exist).  A ref is the cheapest closer once a *typed*
    # function is bound -- checked below.
    expected = {INT: 1, LITERAL_INT: 1, _VALUE: 1, _LIST: 1, _FN: 3}
    for slot_type, want in expected.items():
        got = completion_cost(slot_type)
        assert got == want, f"completion_cost({slot_type}) = {got}, want {want}"
    # The cost table counts `ref` as the cheapest way to close an Fn slot,
    # but since M16 `ref` is offered only where a bound function exists.
    # In a fresh state nothing is bound, so the cheapest *available*
    # closer is `lambda`; once a function is in scope it is `ref`.
    for slot_type, escape in ((INT, LIT_INT), (_VALUE, LIT_INT),
                              (_LIST, NIL), (_FN, LAMBDA)):
        fresh = GenState.fresh(slot_type)
        chosen = cheapest_to_finish(fresh, fresh.valid_next())
        # Ties are legitimate -- a Value slot closes in one token by a
        # literal, `nil` or `stdin` alike.  What must hold is that the
        # certain closer is among the choices and no gamble is.
        assert escape in chosen, (
            f"{slot_type}: bias picks {[SIGNATURES[t]['name'] for t in chosen]}, "
            f"not {SIGNATURES[escape]['name']}"
        )
        assert not any(t in RESULT_NOT_STATIC for t in chosen), (
            f"{slot_type}: the bias chose a transparent operator"
        )
    from core.tokens import REF as _REF
    with_fn = (GenState.fresh(INT).step(LET).step(LIT_INT, 0)
               .step(LAMBDA).step(LIT_INT, 1).step(LIT_INT, 5))   # (let 0 (lambda 1 5) _)
    fn_slot_state = with_fn.step(_AP)                              # apply's Fn head
    assert _REF in fn_slot_state.valid_next(), "a bound function should make ref available"
    assert is_certain(fn_slot_state, _REF), "a typed bound function makes ref certain"
    assert cheapest_to_finish(fn_slot_state, fn_slot_state.valid_next()) == [_REF]
    # The two shapes that defeated the earlier tests.
    fn_slot = Slot(expected_type=_FN)
    assert token_completion_cost(_LU, fn_slot) > token_completion_cost(LAMBDA, fn_slot)
    assert token_completion_cost(LAMBDA, fn_slot) > token_completion_cost(_REF, fn_slot)
    int_slot = Slot(expected_type=INT)
    assert token_completion_cost(_AP, int_slot) > token_completion_cost(LIT_INT, int_slot)

    print("core.generator self-test OK")
    print(f"  fresh state valid_next size: {len(v0)}  (all Int-producing ops)")
    print(f"  after LET valid_next size:   {len(v1)}  (only LIT_INT allowed)")
    print(f"  after APPLY valid_next:      {sorted(hex(t) for t in v_apply)}  (Fn slot)")
    print(f"  completion costs: "
          + ", ".join(f"{t}={completion_cost(t)}"
                      for t in sorted(COMPLETION_COST, key=str)))

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
