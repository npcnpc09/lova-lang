"""Populations over individuals — Axiom 6.

A LOVA function is not a single definition; it is a **population**
of variants that compete at dispatch time.  Each dispatch picks the
best-fit variant for the current workload; every so often the pool
evolves — losers retire, winners clone + mutate — so the function's
behavior improves over time.

This module builds on ``core.lineage`` (Axiom 5): each variant is a
Node registered in a LineageStore, so the evolutionary lifecycle
produces a queryable DAG of derivations.

**Paradigm lineage** (see ``../spec/paradigm-inheritance.md``):

- Koza's Genetic Programming (1992) — population-based program search.
- Haskell type classes — ad-hoc polymorphism via multiple instances.
- Rust traits — same.
- DNA OS v3 ``evolution_engine`` (Exp 28/52/72) — enforce_diversity +
  clone_prob=0.3 + mutation_strength=0.01 + sharp α=3 selection.

LOVA's synthesis: genetic programming as a **substrate primitive**,
not a framework embedded in a host language.  LOVA has `defpop` as
a core construct; DNA OS has it as library machinery.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.lineage import LineageStore
from core.runtime import Runtime, evaluate
from core.surface import parse, pretty
from core.tokens import Node


FitnessFn = Callable[[int, dict], float]
"""Fitness function signature: ``fn(result, inputs) -> fitness``.

Higher fitness = better.  A typical implementation:
``lambda result, inputs: -abs(result - inputs['target'])``.
"""


@dataclass
class VariantStat:
    """Per-variant tracking — rolling fitness history, dispatch count."""

    uid: int
    dispatches: int = 0
    fitness_sum: float = 0.0
    fitness_window: List[float] = field(default_factory=list)
    last_error: Optional[str] = None
    retired_at: Optional[int] = None  # dispatch index when retired, if any

    def record(self, fitness: float, window_size: int) -> None:
        self.dispatches += 1
        self.fitness_sum += fitness
        self.fitness_window.append(fitness)
        if len(self.fitness_window) > window_size:
            self.fitness_window.pop(0)

    def mean_fitness(self) -> float:
        if not self.fitness_window:
            return float("-inf")
        return sum(self.fitness_window) / len(self.fitness_window)

    def is_retired(self) -> bool:
        return self.retired_at is not None


@dataclass
class DispatchTrace:
    """One dispatch event for telemetry / visualisation."""

    step: int
    inputs: dict
    chosen_uid: int
    result: object
    fitness: float
    pool_best_fitness: float
    pool_mean_fitness: float


class Population:
    """A pool of LOVA variants with fitness-weighted dispatch.

    The population is maintained at roughly constant size.  Each
    ``dispatch(inputs)`` call picks the best-fit variant (within the
    current fitness window) and records how it performed.  Periodic
    ``evolve()`` calls retire the worst variants and create mutated
    offspring from the best.
    """

    def __init__(
        self,
        store: LineageStore,
        variants: List[Node],
        fitness_fn: FitnessFn,
        rng: Optional[random.Random] = None,
        window_size: int = 10,
        alpha: float = 3.0,           # selection sharpness for reproduce
    ):
        self.store = store
        self.variants: List[Node] = []   # alive variants
        self.stats: Dict[int, VariantStat] = {}
        self.fitness_fn = fitness_fn
        self.rng = rng or random.Random(0)
        self.window_size = window_size
        self.alpha = alpha
        self.traces: List[DispatchTrace] = []

        for v in variants:
            if v.uid is None:
                store.register_root(v)
            self.variants.append(v)
            self.stats[v.uid] = VariantStat(uid=v.uid)

    # ---- dispatch --------------------------------------------------------

    def dispatch(self, inputs: dict) -> DispatchTrace:
        """Evaluate the best-fit variant on ``inputs``.  Returns trace."""
        # Pick the variant with highest rolling mean fitness.  Ties are
        # broken by uid (deterministic).  Unseen variants (no fitness
        # yet) get -inf and are always outranked, but since we
        # always-try-all-variants in the warmup phase below, they get
        # evaluated first.
        chosen = self._pick_best_or_warmup()
        result, fitness = self._evaluate_variant(chosen, inputs)
        stat = self.stats[chosen.uid]
        stat.record(fitness, self.window_size)

        best = max((s.mean_fitness() for s in self._alive_stats()), default=fitness)
        alive = list(self._alive_stats())
        mean = sum(s.mean_fitness() for s in alive) / len(alive) if alive else fitness

        trace = DispatchTrace(
            step=len(self.traces),
            inputs=inputs,
            chosen_uid=chosen.uid,
            result=result,
            fitness=fitness,
            pool_best_fitness=best,
            pool_mean_fitness=mean,
        )
        self.traces.append(trace)
        return trace

    def _pick_best_or_warmup(self) -> Node:
        # Warmup: if any alive variant hasn't been dispatched yet, pick
        # it (so every variant gets at least one fitness reading before
        # argmax kicks in).
        for v in self.variants:
            if self.stats[v.uid].dispatches == 0:
                return v
        # Otherwise argmax by rolling mean fitness.
        return max(
            self.variants,
            key=lambda v: (self.stats[v.uid].mean_fitness(), v.uid),
        )

    def _evaluate_variant(self, variant: Node, inputs: dict) -> Tuple[object, float]:
        """Fill template placeholders (if any), evaluate, score."""
        # Variants don't have placeholders in this design — they are
        # concrete programs.  The ``inputs`` dict is passed to the
        # fitness function for context (e.g., target value).
        try:
            rt = Runtime()
            result = evaluate(variant, rt)
            fitness = self.fitness_fn(result, inputs)
        except Exception as e:
            # Trap / evaluation failure → very low fitness (but not -inf
            # so that comparisons still work).
            self.stats[variant.uid].last_error = f"{type(e).__name__}: {e}"
            result = None
            fitness = -1e9
        return result, fitness

    # ---- evolution --------------------------------------------------------

    def evolve(
        self,
        retire_frac: float = 0.2,
        clone_prob: float = 0.3,
        mutation_strength: float = 0.3,
    ) -> Dict[str, int]:
        """One evolution step.

        Retires the bottom ``retire_frac`` of variants by fitness.  For
        each retired slot, sample a parent from the survivors with
        probability ``fitness**alpha`` (sharp selection), and create a
        child.  With probability ``clone_prob`` the child is an exact
        clone; otherwise it's a mutation.

        Returns summary of how many retired / cloned / mutated.
        """
        alive = [s for s in self.stats.values() if not s.is_retired()
                 and s.dispatches > 0]
        if len(alive) < 2:
            return {"retired": 0, "cloned": 0, "mutated": 0, "reason": "too few alive"}

        # Sort by mean fitness (ascending)
        alive.sort(key=lambda s: s.mean_fitness())
        n_retire = max(1, int(len(alive) * retire_frac))
        to_retire = alive[:n_retire]
        survivors = alive[n_retire:]

        # Retire
        step_idx = len(self.traces)
        for s in to_retire:
            s.retired_at = step_idx
        self.variants = [v for v in self.variants
                         if not self.stats[v.uid].is_retired()]

        # Reproduce — sharp fitness-weighted pick
        min_fit = min(s.mean_fitness() for s in survivors)
        shifted = [max(1e-6, s.mean_fitness() - min_fit + 1.0) for s in survivors]
        weights = [w ** self.alpha for w in shifted]
        summary = {"retired": n_retire, "cloned": 0, "mutated": 0}
        for _ in range(n_retire):
            idx = self._weighted_pick(weights)
            parent_stat = survivors[idx]
            parent_node = next(v for v in self.variants
                               if v.uid == parent_stat.uid)
            if self.rng.random() < clone_prob:
                child = self.store.clone(parent_node)
                summary["cloned"] += 1
            else:
                child = self.store.mutate(parent_node, strength=mutation_strength)
                summary["mutated"] += 1
            self.variants.append(child)
            self.stats[child.uid] = VariantStat(uid=child.uid)
        return summary

    def _weighted_pick(self, weights: List[float]) -> int:
        total = sum(weights)
        r = self.rng.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                return i
        return len(weights) - 1

    # ---- queries / summary ------------------------------------------------

    def _alive_stats(self) -> List[VariantStat]:
        return [self.stats[v.uid] for v in self.variants]

    def best(self) -> Tuple[Node, VariantStat]:
        """Current best variant by rolling mean fitness."""
        v = max(self.variants, key=lambda v: self.stats[v.uid].mean_fitness())
        return v, self.stats[v.uid]

    def fitness_trajectory(self) -> List[Tuple[int, float, float]]:
        """Return list of (step, pool_best, pool_mean) from traces."""
        return [(t.step, t.pool_best_fitness, t.pool_mean_fitness)
                for t in self.traces]

    def summary(self) -> str:
        lines = [
            f"Population: {len(self.variants)} alive, "
            f"{sum(1 for s in self.stats.values() if s.is_retired())} retired, "
            f"{len(self.traces)} dispatches"
        ]
        alive_sorted = sorted(
            self._alive_stats(),
            key=lambda s: -s.mean_fitness(),
        )
        for s in alive_sorted:
            v = next(v for v in self.variants if v.uid == s.uid)
            lines.append(
                f"  uid={s.uid:<3d}  fitness(mean)={s.mean_fitness():+9.3f}  "
                f"dispatches={s.dispatches:<3d}  {pretty(v)}"
            )
        return "\n".join(lines)
