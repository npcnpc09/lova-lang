"""Conservation layer — budget tracking + Δ-trap (AI-observable).

Axiom 4: conservation is a type, not a runtime afterthought.

Trap classes:

- ``BudgetTrap`` — a ``(budget k body)`` scope overran its declared
  cost budget.
- ``DepthTrap`` (⊂ ``BudgetTrap``) — recursion nested past
  ``runtime.MAX_CALL_DEPTH``.
- ``StepTrap`` (⊂ ``BudgetTrap``) — the run exceeded
  ``runtime.MAX_STEPS`` evaluation steps.  This is the substrate-level
  non-termination backstop: it applies even when the program declares
  no budget of its own.
- ``DeltaTrap`` — a ``(conserve k body)`` invariant was violated at
  exit (body produced a value inconsistent with the declared contract).
- ``DomainTrap`` (⊂ ``ValueError``) — division by zero, the head of an
  empty list, a reference to nothing, a value used at the wrong type.
  These carry the same anomaly schema as the rest, so the uniform
  handler really is uniform.

Every one of them is catchable *inside* LOVA with ``when-anomaly``,
with one deliberate exception: ``StepTrap``.  The step ceiling is the
substrate's guarantee that a program terminates, and a guarantee a
program can mask is not one.

**M5 observability layer (AI-friendly errors).** Each trap carries a
rich ``anomaly`` dict (and the older string ``__str__`` for human
readability):

  anomaly = {
    "kind": "budget-exceeded" | "conservation-violated",
    "position_path": (int, ...),     # tree path from root, if known
    "offending_op": int,             # token byte of the operator at fault
    "offending_op_name": str,
    "valid_alternatives": (int, ...),# tokens that could replace it
    "repair_hint": str,              # one-line actionable suggestion
    "detail": { ... kind-specific ... },
  }

AI code generators consuming this output can ``state.step(alt)`` with
one of ``valid_alternatives`` to patch the program without re-parsing
a stack trace.  This is the load-bearing difference between LOVA
error model and conventional Python traceback: machine-actionable,
not human-readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Budget:
    """Mutable budget counter.  Decremented by the runtime on each op."""

    limit: int
    spent: int = 0

    def charge(self, cost: int = 1) -> None:
        self.spent += cost
        if self.spent > self.limit:
            raise BudgetTrap(
                anomaly={
                    "kind": "budget-exceeded",
                    "detail": {
                        "limit": self.limit,
                        "spent": self.spent,
                        "overrun": self.spent - self.limit,
                    },
                    # Position / repair info is enriched by the runtime
                    # when the trap propagates out of ``_eval`` — we
                    # stash placeholders here so AI consumers can rely
                    # on the field shape.
                    "position_path": (),
                    "offending_op": None,
                    "offending_op_name": "",
                    "valid_alternatives": (),
                    "repair_hint": (
                        "reduce body size (fewer operators) or raise "
                        f"budget to >= {self.spent}"
                    ),
                }
            )

    def remaining(self) -> int:
        return max(0, self.limit - self.spent)


class BudgetTrap(Exception):
    """Raised when a ``BUDGET`` scope overruns its declared unit budget."""

    def __init__(self, anomaly: Dict[str, Any]):
        super().__init__(
            "BUDGET trap: spent {spent} > limit {limit} (overrun {overrun})"
            .format(**anomaly["detail"])
        )
        self.anomaly = anomaly


class DepthTrap(BudgetTrap):
    """Raised when recursion nests deeper than ``MAX_CALL_DEPTH`` (M9).

    Subclasses ``BudgetTrap`` deliberately: call depth *is* a budget,
    and every existing ``except BudgetTrap`` handler — including the
    runtime's trap-enrichment path — keeps working unchanged.  The
    anomaly ``kind`` distinguishes it for consumers that care.
    """

    def __init__(self, depth: int, limit: int, call_chain: Tuple[int, ...] = ()):
        Exception.__init__(
            self, f"Depth trap: call depth {depth} > limit {limit}"
        )
        self.anomaly: Dict[str, Any] = {
            "kind": "recursion-depth-exceeded",
            "detail": {
                "limit": limit,
                "spent": depth,
                "overrun": depth - limit,
                "call_chain": tuple(call_chain),
            },
            "position_path": (),
            "offending_op": None,
            "offending_op_name": "",
            "valid_alternatives": (),
            "repair_hint": (
                "the recursion has no reachable base case, or needs more "
                f"than {limit} frames; add / fix the `if-surprise` guard "
                "that terminates it, or shrink the input"
            ),
        }


class StepTrap(BudgetTrap):
    """Raised when a run exceeds ``MAX_STEPS`` evaluation steps (M9).

    This is the always-on ceiling that makes non-terminating programs
    *observable* rather than hanging.  ``BUDGET`` scopes are the
    program-declared, fine-grained version of the same idea; this is
    the substrate-level backstop that applies even to programs which
    declare no budget at all.
    """

    def __init__(self, steps: int, limit: int):
        Exception.__init__(
            self, f"Step trap: {steps} evaluation steps > limit {limit}"
        )
        self.anomaly: Dict[str, Any] = {
            "kind": "step-limit-exceeded",
            "detail": {
                "limit": limit,
                "spent": steps,
                "overrun": steps - limit,
            },
            "position_path": (),
            "offending_op": None,
            "offending_op_name": "",
            "valid_alternatives": (),
            "repair_hint": (
                "the program does not terminate within the substrate step "
                f"ceiling ({limit}); check the loop-until predicate or the "
                "recursive base case"
            ),
        }


class DomainTrap(ValueError):
    """A runtime fault that is neither a budget nor a contract violation.

    Division by zero, the head of an empty list, a reference to nothing,
    applying something that is not a function -- until M13 each of these
    raised a bare ``ValueError`` with a sentence in it and no ``kind``,
    which meant the "one error handler for everything" property the
    project claims (Exp 08) held for two of its four fault classes.

    Subclasses ``ValueError`` deliberately: every existing handler and
    test that catches ``ValueError`` keeps working, and gains structure
    it can use if it wants it.
    """

    def __init__(self, kind: str, message: str,
                 detail: Optional[Dict[str, Any]] = None,
                 repair_hint: str = ""):
        super().__init__(message)
        self.anomaly: Dict[str, Any] = {
            "kind": kind,
            "detail": detail or {},
            "position_path": (),
            "offending_op": None,
            "offending_op_name": "",
            "valid_alternatives": (),
            "repair_hint": repair_hint,
        }


# Anomaly kinds as integers, because a LOVA program that handles one can
# only branch on a number.  Kept small and stable: a program written
# against these is written against the substrate's error model.
ANOMALY_CODES: Dict[str, int] = {
    "budget-exceeded": 1,
    "recursion-depth-exceeded": 2,
    "conservation-violated": 3,
    "domain-error": 4,
    "type-violation": 5,
    "unbound-ref": 6,
    "malformed": 7,
    "step-limit-exceeded": 8,   # not catchable; see the WHEN_ANOMALY handler
    "capability-denied": 9,     # M19: an effect outside a boundary that declares it
}

ANOMALY_KINDS: Dict[int, str] = {v: k for k, v in ANOMALY_CODES.items()}


def anomaly_code(anomaly: Dict[str, Any]) -> int:
    """The integer a handler receives for this anomaly.  0 if unknown."""
    return ANOMALY_CODES.get(anomaly.get("kind", ""), 0)


class DeltaTrap(Exception):
    """Raised when a ``CONSERVE`` invariant is violated at exit."""

    def __init__(self, anomaly: Dict[str, Any]):
        d = anomaly["detail"]
        super().__init__(
            f"Delta trap: {d['invariant']} violated -- "
            f"entry {d['entry']} vs exit {d['exit']}"
        )
        self.anomaly = anomaly


# ---------------------------------------------------------------------------
# Enrichment helpers — the runtime calls these on trap-catch to fill in the
# position / repair fields.
# ---------------------------------------------------------------------------

def enrich_anomaly(
    anomaly: Dict[str, Any],
    position_path: Tuple[int, ...],
    offending_op: Optional[int],
    valid_alternatives: Tuple[int, ...],
    op_name_for: Optional[callable] = None,
) -> Dict[str, Any]:
    """Attach positional + repair info to an in-flight anomaly dict.

    ``op_name_for`` is an optional token-byte -> name resolver (typically
    ``lambda t: SIGNATURES[t]['name']``).  Kept as a parameter to avoid
    a circular import from ``core.tokens``.
    """
    anomaly["position_path"] = tuple(position_path)
    anomaly["offending_op"] = offending_op
    anomaly["offending_op_name"] = (
        op_name_for(offending_op) if (op_name_for and offending_op is not None)
        else ""
    )
    anomaly["valid_alternatives"] = tuple(valid_alternatives)
    return anomaly


@dataclass
class SurpriseTrace:
    """Ordered log of surprise events emitted during a run."""

    events: List[Dict[str, Any]] = field(default_factory=list)

    def emit(self, predicted: int, actual: int, ctx: Optional[str] = None) -> int:
        dev = abs(predicted - actual)
        self.events.append(
            {
                "predicted": predicted,
                "actual": actual,
                "deviation": dev,
                "ctx": ctx or "",
            }
        )
        return dev

    def summary(self) -> str:
        if not self.events:
            return "(no surprise events)"
        lines = [f"surprise events ({len(self.events)}):"]
        for i, e in enumerate(self.events):
            lines.append(
                f"  [{i:02d}] predicted={e['predicted']}  actual={e['actual']}  "
                f"deviation={e['deviation']}  ctx={e['ctx']!r}"
            )
        return "\n".join(lines)
