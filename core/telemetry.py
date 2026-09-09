"""Telemetry — per-token pass-rate accumulator (Q22, M6 Day 3).

Two-level counter keyed by:

- ``per_token``     — each token byte, aggregated across all contexts.
- ``per_context``   — each ``(token, parent_op)`` pair, where ``parent_op``
                      is the operator whose child-slot this token occupied
                      (``None`` for the root slot; not stored in per_context
                      — the global counter IS the no-parent view).

An AI generator pulling ``valid_next_with_stats`` then sees, for each
candidate token, historical pass-rates conditioned on where it's about to
be placed.  Example:

    LIT_INT globally: 99% pass (nearly every well-formed program contains
    literals and most well-formed programs pass).

    LIT_INT as child of VIOLATE: 2% pass (VIOLATE breaks conservation,
    so any program wrapping a literal in VIOLATE is likely to trap).

"Pass" here means **evaluated without raising a trap** (BudgetTrap /
DeltaTrap / any other runtime error).  Task-level pass (produces the
expected value for a benchmark task) is a strictly stronger signal
but requires task context; that variant is planned (Q26) but not in
this module.

JSON format on disk (v1):

    {
      "version": 1,
      "total_programs": N,
      "per_token":   { "0x01": {"hits": int, "misses": int}, ... },
      "per_context": { "0x01|0x09": {"hits": int, "misses": int}, ... }
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from core.tokens import Node


# --- value type ------------------------------------------------------------

@dataclass(frozen=True)
class TokenStats:
    """Read-only view over a (hits, misses) counter pair."""
    hits: int
    misses: int

    @property
    def sample_count(self) -> int:
        return self.hits + self.misses

    @property
    def pass_rate(self) -> Optional[float]:
        n = self.sample_count
        return (self.hits / n) if n > 0 else None

    @classmethod
    def empty(cls) -> "TokenStats":
        return cls(hits=0, misses=0)


# --- storage ---------------------------------------------------------------

_VERSION = 1


@dataclass
class TelemetryDB:
    """Pass-rate counters for tokens and (token, parent_op) pairs.

    Mutable: ``record(tree, passed)`` bumps counters; ``save(path)`` writes
    a deterministic JSON snapshot.  Thread-unsafe by design — telemetry is
    built offline from experiment runs, not at live generation time.
    """
    per_token: Dict[int, Dict[str, int]] = field(default_factory=dict)
    per_context: Dict[Tuple[int, int], Dict[str, int]] = field(default_factory=dict)
    total_programs: int = 0

    @classmethod
    def empty(cls) -> "TelemetryDB":
        return cls()

    # ---- ingestion ------------------------------------------------------

    def record(self, tree: Node, passed: bool) -> None:
        """Walk ``tree`` in pre-order; bump counters for every (token,
        parent_op) pair it contains.  Increments ``total_programs``."""

        def walk(node: Node, parent_op: Optional[int]) -> None:
            self._bump(node.op, parent_op, passed)
            for arg in node.args:
                if isinstance(arg, Node):
                    walk(arg, node.op)

        walk(tree, None)
        self.total_programs += 1

    def _bump(self, token: int, parent_op: Optional[int], passed: bool) -> None:
        counter = self.per_token.setdefault(token, {"hits": 0, "misses": 0})
        counter["hits" if passed else "misses"] += 1
        if parent_op is not None:
            key = (token, parent_op)
            ctx = self.per_context.setdefault(key, {"hits": 0, "misses": 0})
            ctx["hits" if passed else "misses"] += 1

    # ---- queries --------------------------------------------------------

    def lookup(
        self, token: int, parent_op: Optional[int] = None
    ) -> TokenStats:
        """Return stats for ``token``, optionally conditioned on the op
        whose child-slot it fills.  Falls back to global stats if no
        context-specific samples exist."""
        if parent_op is not None:
            ctx = self.per_context.get((token, parent_op))
            if ctx is not None and (ctx["hits"] + ctx["misses"]) > 0:
                return TokenStats(hits=ctx["hits"], misses=ctx["misses"])
        glob = self.per_token.get(token)
        if glob is None:
            return TokenStats.empty()
        return TokenStats(hits=glob["hits"], misses=glob["misses"])

    def lookup_global(self, token: int) -> TokenStats:
        """Unconditioned stats for ``token`` across all prior contexts."""
        glob = self.per_token.get(token)
        if glob is None:
            return TokenStats.empty()
        return TokenStats(hits=glob["hits"], misses=glob["misses"])

    def lookup_context(
        self, token: int, parent_op: int
    ) -> TokenStats:
        """Stats for ``token`` specifically as a child-slot of ``parent_op``.
        Returns empty if no context samples — does NOT fall back to global.
        """
        ctx = self.per_context.get((token, parent_op))
        if ctx is None:
            return TokenStats.empty()
        return TokenStats(hits=ctx["hits"], misses=ctx["misses"])

    # ---- serialisation --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        per_tok_out = {
            f"0x{tok:02X}": {"hits": v["hits"], "misses": v["misses"]}
            for tok, v in sorted(self.per_token.items())
        }
        per_ctx_out = {
            f"0x{tok:02X}|0x{par:02X}": {"hits": v["hits"], "misses": v["misses"]}
            for (tok, par), v in sorted(
                self.per_context.items(), key=lambda kv: kv[0]
            )
        }
        return {
            "version": _VERSION,
            "total_programs": self.total_programs,
            "per_token": per_tok_out,
            "per_context": per_ctx_out,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryDB":
        if data.get("version") != _VERSION:
            raise ValueError(
                f"unsupported telemetry version: {data.get('version')!r}"
            )
        db = cls.empty()
        db.total_programs = int(data.get("total_programs", 0))
        for k, v in data.get("per_token", {}).items():
            tok = int(k, 16)
            db.per_token[tok] = {"hits": int(v["hits"]), "misses": int(v["misses"])}
        for k, v in data.get("per_context", {}).items():
            tok_str, par_str = k.split("|")
            tok, par = int(tok_str, 16), int(par_str, 16)
            db.per_context[(tok, par)] = {
                "hits": int(v["hits"]),
                "misses": int(v["misses"]),
            }
        return db

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")

    @classmethod
    def load(cls, path: str) -> "TelemetryDB":
        if not os.path.exists(path):
            return cls.empty()
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
