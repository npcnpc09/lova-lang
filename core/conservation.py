"""Conservation layer — budget tracking + Δ-trap (AI-observable).

Axiom 4: conservation is a type, not a runtime afterthought.

Two trap classes:

- ``BudgetTrap`` — a ``(budget k body)`` scope overran its declared
  cost budget.
- ``DeltaTrap`` — a ``(conserve k body)`` invariant was violated at
  exit (body produced a value inconsistent with the declared contract).

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
