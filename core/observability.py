"""Observability — make LOVA's internal state readable to AI.

Three APIs:

- ``valid_next_with_stats``: per-token metadata at a generation
  position (depth delta, termination bias, declared effects, budget
  cost, type info).  AI sampling from ``valid_next()`` alone has to
  guess which choice is best; with stats it has structured input to
  weight the decision.

- ``StaticAnalysis`` / ``static_analyze``: pre-execution reasoning
  over a Node tree.  Returns effects, budget upper bound, determinism
  flag, whether the program uses conservation / surprise / lineage
  machinery.  AI can ask "what will this program DO" before committing
  to generate + execute.

- Richer ``AnomalyReport`` shape (living in ``core.conservation``):
  position hint + valid alternatives + repair hint, rather than just
  a string.

This module doesn't add new LOVA operators.  It exposes information
the runtime already has in a form AI can consume directly.  Design
intent: AI-preference lever (see ``docs/ai-preference.md`` once
written).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Tuple

from core.generator import GenState
from core.tokens import (
    END, IF_SURPRISE, LIT_INT, SEQ, SIGMA, SIGNATURES, SURPRISE, TAU,
    TYPED_TOKENS, TRACE_SURPRISE, VIOLATE, CONSERVE, BUDGET, MERGE, GCD,
    PARTITION, IDENTITY, P, MOBIUS, LET, REF, Node,
)
from core.types import INT, LITERAL_INT, Type, is_subtype


# --- theoretical per-operator metadata --------------------------------------
#
# Each M1-runtime-supported operator has a known (arity, depth_delta,
# effect_set, cost).  These are computed once at import time from
# SIGNATURES.  They do not depend on runtime history.

# Declared effects per operator (M5 minimum: all pure-integer computations
# have no effects; conservation / surprise / lineage ops have their own
# structural effects).  As IO ops land in M6+ this table grows.
_EFFECTS: dict = {
    # pure arithmetic / nt
    P: frozenset(),
    TAU: frozenset(),
    SIGMA: frozenset(),
    MOBIUS: frozenset(),
    GCD: frozenset(),
    MERGE: frozenset(),
    PARTITION: frozenset(),
    IDENTITY: frozenset(),
    LIT_INT: frozenset(),
    # composition — effects inherited from children
    SEQ: frozenset(),
    LET: frozenset(),
    REF: frozenset(),
    IF_SURPRISE: frozenset({"read-surprise"}),
    # conservation
    BUDGET: frozenset({"budget-scope"}),
    CONSERVE: frozenset({"conservation-check"}),
    VIOLATE: frozenset({"synthetic-violation"}),
    # surprise
    SURPRISE: frozenset({"write-surprise-trace"}),
    TRACE_SURPRISE: frozenset({"write-surprise-trace"}),
}


def _depth_delta(token: int) -> int:
    """How many net new slots this token pushes onto the gen-state stack.

    Terminals (LIT_INT, END) reduce the stack by 1.  Operators with
    N args push N slots and pop 1 (the slot they fill), so net = N - 1.
    Variadic ops produce a single continuation slot (net 0).
    """
    if token == END:
        return -1
    sig = SIGNATURES.get(token, {})
    if token == LIT_INT:
        return -1
    in_types = sig.get("in_types")
    if in_types is None:
        # variadic — pushes a continuation slot, pops none of its own
        return 0
    return len(in_types) - 1


def _is_terminating(token: int) -> bool:
    """True iff this token reduces slot count (brings generation closer to done)."""
    return _depth_delta(token) <= 0


# --- TokenChoice ------------------------------------------------------------

@dataclass(frozen=True)
class TokenChoice:
    """Structured per-token info at a generation position.

    An AI sampling from ``valid_next_with_stats`` gets, for each valid
    next token:

    - token: the byte
    - name: human-readable name (for debug / logging)
    - arity: operator's declared arity (int or "variadic")
    - depth_delta: net change to generation-state stack size
    - terminating: whether choosing this shrinks the stack
    - in_types / out_type: type signature
    - effects: declared effect set
    - budget_cost: unit cost in the current cost model (MVP: 1)

    Historical pass-rate telemetry (Q22) — populated when ``valid_next_
    with_stats`` is called with a ``TelemetryDB``; otherwise ``None`` /
    ``0``.  Two views:

    - ``prior_pass_rate`` / ``prior_sample_count``: global (unconditioned)
    - ``prior_pass_rate_ctx`` / ``prior_sample_count_ctx``: specific to
      the current slot's parent_op; None / 0 if no context data.
    """
    token: int
    name: str
    arity: object                    # int or "variadic"
    depth_delta: int
    terminating: bool
    in_types: Tuple[str, ...]
    out_type: str
    effects: FrozenSet[str]
    budget_cost: int
    prior_pass_rate: Optional[float] = None
    prior_sample_count: int = 0
    prior_pass_rate_ctx: Optional[float] = None
    prior_sample_count_ctx: int = 0

    def summary(self) -> str:
        eff = "{" + ",".join(sorted(self.effects)) + "}" if self.effects else "{}"
        parts = [
            f"0x{self.token:02X} {self.name:<16s} ",
            f"arity={str(self.arity):>3s}  ",
            f"d-depth={self.depth_delta:+d}  ",
            f"term={self.terminating!s:<5s}  ",
            f"effects={eff}",
        ]
        if self.prior_sample_count > 0 or self.prior_sample_count_ctx > 0:
            pr_g = (
                f"{self.prior_pass_rate:.0%}"
                if self.prior_pass_rate is not None else "  -"
            )
            pr_c = (
                f"{self.prior_pass_rate_ctx:.0%}"
                if self.prior_pass_rate_ctx is not None else "  -"
            )
            parts.append(
                f"  pass={pr_g} (n={self.prior_sample_count})  "
                f"ctx={pr_c} (n={self.prior_sample_count_ctx})"
            )
        return "".join(parts)


def _tokenchoice(
    token: int,
    parent_op: Optional[int] = None,
    telemetry: Optional["TelemetryDB"] = None,
) -> TokenChoice:
    sig = SIGNATURES[token]
    # END is a structural terminator — no operator signature.
    if token == END:
        base_kwargs = dict(
            token=END,
            name=sig["name"],
            arity=0,
            depth_delta=-1,
            terminating=True,
            in_types=(),
            out_type="-",
            effects=frozenset(),
            budget_cost=0,
        )
    else:
        if "variadic_type" in sig:
            arity: object = "variadic"
            in_type_names: Tuple[str, ...] = (f"{sig['variadic_type']!s}*",)
        elif "in_types" in sig and sig["in_types"] is not None:
            arity = len(sig["in_types"])
            in_type_names = tuple(str(t) for t in sig["in_types"])
        else:
            arity = 0
            in_type_names = ()
        out_type = sig.get("out_type")
        out_name = str(out_type) if out_type is not None else "-"
        base_kwargs = dict(
            token=token,
            name=sig["name"],
            arity=arity,
            depth_delta=_depth_delta(token),
            terminating=_is_terminating(token),
            in_types=in_type_names,
            out_type=out_name,
            effects=_EFFECTS.get(token, frozenset()),
            budget_cost=1,
        )
    if telemetry is not None:
        g = telemetry.lookup_global(token)
        base_kwargs["prior_pass_rate"] = g.pass_rate
        base_kwargs["prior_sample_count"] = g.sample_count
        if parent_op is not None:
            c = telemetry.lookup_context(token, parent_op)
            base_kwargs["prior_pass_rate_ctx"] = c.pass_rate
            base_kwargs["prior_sample_count_ctx"] = c.sample_count
    return TokenChoice(**base_kwargs)


# --- valid_next_with_stats -------------------------------------------------

def valid_next_with_stats(
    state: GenState,
    telemetry: Optional["TelemetryDB"] = None,
) -> List[TokenChoice]:
    """Return the valid-next set enriched with per-token metadata.

    Ordered by (terminating first if stack is deep, then by token byte).
    When ``telemetry`` is provided each choice also carries historical
    pass-rate stats — global and conditioned on the slot's parent_op.
    Downstream samplers (AI or heuristic) can re-rank on any field.
    """
    raw = state.valid_next()
    parent_op = state.stack[-1].parent_op if state.stack else None
    out: List[TokenChoice] = [
        _tokenchoice(tok, parent_op=parent_op, telemetry=telemetry)
        for tok in sorted(raw)
    ]
    stack_depth = len(state.stack)
    if stack_depth >= 6:
        out.sort(key=lambda c: (not c.terminating, c.token))
    else:
        out.sort(key=lambda c: (c.terminating, c.token))
    return out


# --- static analysis --------------------------------------------------------

@dataclass(frozen=True)
class StaticAnalysis:
    """Summary of what a LOVA program will do, computed without
    executing it.

    All bounds are upper bounds (conservative).  ``is_deterministic``
    is True iff no non-deterministic operators appear in the tree.
    ``lineage_root`` is filled only if the root Node has a uid.
    """
    node_count: int
    max_depth: int
    effects: FrozenSet[str]
    budget_upper_bound: int
    is_deterministic: bool
    uses_conservation: bool
    uses_surprise: bool
    uses_lineage: bool
    lineage_root: Optional[int]

    def summary(self) -> str:
        eff = "{" + ", ".join(sorted(self.effects)) + "}" if self.effects else "{}"
        lines = [
            f"  nodes:           {self.node_count}",
            f"  max depth:       {self.max_depth}",
            f"  effects:         {eff}",
            f"  budget bound:    <= {self.budget_upper_bound} units",
            f"  deterministic:   {self.is_deterministic}",
            f"  uses conserve:   {self.uses_conservation}",
            f"  uses surprise:   {self.uses_surprise}",
            f"  uses lineage:    {self.uses_lineage}",
        ]
        if self.lineage_root is not None:
            lines.append(f"  lineage root:    uid={self.lineage_root}")
        return "\n".join(lines)


# --- repair suggestions -----------------------------------------------------
#
# Given an offending operator, which tokens would be a "small edit"
# replacement?  Used by the conservation layer to attach
# ``valid_alternatives`` to anomaly reports (L2).

_SWAP_GROUPS_FOR_REPAIR = [
    frozenset({P, TAU, SIGMA, MOBIUS}),
    frozenset({MERGE, GCD}),
    frozenset({IDENTITY, PARTITION}),
]


def suggest_alternatives(op: int) -> Tuple[int, ...]:
    """Return a small set of tokens AI could use to replace ``op``.

    Currently derives from same-family swap groups.  Future versions may
    query ``valid_next()`` in context for a more precise set.
    """
    # For VIOLATE: suggest IDENTITY (preserves the value) to fix a
    # conservation break.
    if op == VIOLATE:
        return (IDENTITY,)
    for group in _SWAP_GROUPS_FOR_REPAIR:
        if op in group:
            return tuple(sorted(group - {op}))
    return ()


def static_analyze(node: Node) -> StaticAnalysis:
    """Walk a Node tree, summarise what it does, without running it."""
    effects_accum: set = set()
    counts = {"nodes": 0, "max_depth": 0,
              "conserve": 0, "surprise": 0, "lineage": 0}

    def walk(n: Node, depth: int) -> None:
        counts["nodes"] += 1
        counts["max_depth"] = max(counts["max_depth"], depth)
        effects_accum.update(_EFFECTS.get(n.op, frozenset()))
        if n.op in (BUDGET, CONSERVE, VIOLATE):
            counts["conserve"] += 1
        if n.op in (SURPRISE, IF_SURPRISE, TRACE_SURPRISE):
            counts["surprise"] += 1
        if getattr(n, "uid", None) is not None:
            counts["lineage"] += 1
        if n.op == LIT_INT:
            return
        for child in n.args:
            if isinstance(child, Node):
                walk(child, depth + 1)

    walk(node, 1)

    # LOVA M5 runtime is deterministic by construction (no random,
    # no IO, no clock).  This will change when we add effect tokens.
    is_deterministic = True
    for bad_effect in ("read-clock", "net-recv", "random"):
        if bad_effect in effects_accum:
            is_deterministic = False
            break

    return StaticAnalysis(
        node_count=counts["nodes"],
        max_depth=counts["max_depth"],
        effects=frozenset(effects_accum),
        budget_upper_bound=counts["nodes"],  # each node costs 1 in MVP
        is_deterministic=is_deterministic,
        uses_conservation=counts["conserve"] > 0,
        uses_surprise=counts["surprise"] > 0,
        uses_lineage=counts["lineage"] > 0,
        lineage_root=getattr(node, "uid", None),
    )
