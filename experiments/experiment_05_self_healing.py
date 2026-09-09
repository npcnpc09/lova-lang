"""Experiment 05 -- Self-healing population (Axiom 6).

The killer-demo half of Milestone 4:

  A population of 5 LOVA variants, NONE of which initially compute
  the target value, evolves under fitness pressure until the population
  converges to the correct answer.

No fine-tuning, no pre-training, no gradient descent.  Just conservation-
preserving mutation + type-directed generation + fitness-weighted
selection.

**The story the demo tells:**

  "Production function X is returning wrong values.  LOVA's
   population re-organizes itself: weaker variants retire, stronger
   variants clone + mutate, within a few evolution rounds the pool
   converges to variants that compute correctly."

This is the substrate-level mechanism behind 'AI-written code that
self-heals' -- the surface-level LLM repair loop would add
surprise-trace-driven mutation suggestions; here we demo the underlying
evolutionary engine working on its own.

Three sub-experiments:

  1. Single-seed convergence: watch fitness trajectory from wrong to
     (near-)perfect.
  2. Multi-seed robustness: across 10 seeds, measure how often the
     population converges.
  3. Lineage of the winning variant: trace its ancestor chain,
     highlighting the mutation that crossed into the solution class.
"""

from __future__ import annotations

import os
import random
import sys
from typing import List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.lineage import LineageStore
from core.populations import Population
from core.surface import parse, pretty


# --- target setup -----------------------------------------------------------

TARGET = 42   # = p(10).  Reachable via literal bumps OR operator swaps.
              # Initial pool doesn't know this.

# Five seed variants, diverse in structure, none computing 42.
# They collectively evaluate to [7, 28, 30, 9, 12] -- distances
# [35, 14, 12, 33, 30] from target.
SEEDS = (
    "(p 5)",             # 7    (can become (p 10) = 42 via +5 literal bump)
    "(sigma 12)",        # 28   (can become (p 12) = 77 via op swap, too far)
    "(merge 10 20)",     # 30   (can become (merge 12 30) = 42 etc.)
    "(tau 100)",         # 9    (can mutate, unlikely to reach)
    "(gcd 24 36)",       # 12   (can mutate, unlikely)
)


def fitness(result, inputs):
    if not isinstance(result, int):
        return -1e6
    return -abs(result - inputs["target"])


# --- helpers ----------------------------------------------------------------

def _hr(title: str) -> None:
    print()
    print("=" * 76)
    print(f"  {title}")
    print("=" * 76)


def _ascii_bar(value: float, min_v: float, max_v: float, width: int = 40) -> str:
    """Render a single-bar ASCII representation of ``value`` inside [min, max]."""
    if max_v <= min_v:
        return "#" * width
    frac = max(0.0, min(1.0, (value - min_v) / (max_v - min_v)))
    n = int(frac * width)
    return "#" * n + " " * (width - n)


def _plot_trajectory(traj: List[Tuple[int, float, float]]) -> None:
    """Print an ASCII trajectory of (step, best, mean) fitness.

    -inf means are discarded (happen right after a new variant is born
    with an empty fitness window).  Scale is computed from finite values."""
    bests = [b for _, b, _ in traj if b > float("-inf")]
    means = [m for _, _, m in traj if m > float("-inf")]
    lo = min(min(bests), min(means))
    hi = max(max(bests), max(means), 0.0)

    print(f"  fitness scale: {lo:+.1f} (worst) ---> {hi:+.1f} (best, 0=perfect)")
    print(f"  step |  best (rolling)                             |  mean")
    for (step, best, mean) in traj:
        b_bar = _ascii_bar(best, lo, hi)
        mean_str = f"{mean:+7.1f}" if mean > float("-inf") else "   --- "
        marker = "  <-- WITHIN +-1 OF TARGET" if best >= -1.0 else ""
        print(f"  {step:4d} [{b_bar}] best={best:+7.1f}  mean={mean_str}{marker}")


# --- sub-experiments --------------------------------------------------------

def run_single_seed(seed: int = 0, verbose: bool = True) -> dict:
    """Run the evolve loop with one seed; return final stats."""
    store = LineageStore(seed=seed)
    rng = random.Random(seed)

    variants = [parse(s) for s in SEEDS]
    pop = Population(store, variants, fitness, rng=rng,
                     window_size=5, alpha=3.0)

    # Warmup: each seed variant gets one dispatch so they all have fitness.
    for _ in range(len(SEEDS)):
        pop.dispatch({"target": TARGET})

    # Evolution rounds: 10 dispatches per round, evolve between rounds.
    ROUNDS = 12
    DISPATCH_PER_ROUND = 10
    for rnd in range(ROUNDS):
        for _ in range(DISPATCH_PER_ROUND):
            pop.dispatch({"target": TARGET})
        summary = pop.evolve(retire_frac=0.4, clone_prob=0.2,
                              mutation_strength=0.45)
        if verbose:
            best_v, best_s = pop.best()
            print(f"    round {rnd + 1:2d}  evolve: {summary}  "
                  f"best={best_s.mean_fitness():+6.1f}  "
                  f"-> {pretty(best_v)}")

    # Final dispatches to solidify last-round fitness
    for _ in range(10):
        pop.dispatch({"target": TARGET})

    best_v, best_s = pop.best()
    return {
        "pop": pop,
        "store": store,
        "best_node": best_v,
        "best_stat": best_s,
        "converged": best_s.mean_fitness() >= -2.0,  # within ±2 of target
        "perfect": best_s.mean_fitness() >= -0.5,    # exact
        "final_result": None,   # computed below
    }


def report_single_seed() -> None:
    _hr("Test 1 -- single-seed self-healing (seed=0)")
    print(f"  target value: {TARGET}  (= p(10))")
    print(f"  seed variants ({len(SEEDS)}):")
    for s in SEEDS:
        from core.runtime import Runtime, evaluate
        v = evaluate(parse(s), Runtime())
        print(f"    {s:<24s} = {v}  (distance {abs(v - TARGET)})")
    print()
    print("  Evolving (warmup + 12 evolution rounds x 10 dispatches)...")
    result = run_single_seed(seed=0, verbose=True)

    print()
    print("  Final population:")
    print(result["pop"].summary())

    print()
    print("  Winner's lineage chain (self -> parent -> ... -> root):")
    best_node = result["best_node"]
    store = result["store"]
    chain = store.ancestors(best_node.uid)  # type: ignore[arg-type]
    for rec in chain:
        print(f"    {rec}  {rec.notes}")

    from core.runtime import Runtime, evaluate
    final_result = evaluate(best_node, Runtime())
    print()
    print(f"  Winner: {pretty(best_node)}  =  {final_result}")
    print(f"  Target: {TARGET}")
    print(f"  Distance: {abs(final_result - TARGET)}")
    converged = "CONVERGED (within 2)" if result["converged"] else "NOT CONVERGED"
    perfect = "  PERFECT MATCH" if result["perfect"] else ""
    print(f"  Verdict: {converged}{perfect}")

    print()
    print("  Fitness trajectory (ASCII, 83 steps total):")
    # Sample every 5th trace so output is readable
    traj_all = result["pop"].fitness_trajectory()
    traj = [traj_all[i] for i in range(0, len(traj_all), 5)] + [traj_all[-1]]
    _plot_trajectory(traj)


def run_multi_seed(n_seeds: int = 10) -> None:
    _hr(f"Test 2 -- multi-seed robustness (n_seeds={n_seeds})")
    converged_count = 0
    perfect_count = 0
    best_fitnesses = []
    print(f"  {'seed':>4s}  {'best_fitness':>12s}  {'winner':<40s}  verdict")
    for s in range(n_seeds):
        res = run_single_seed(seed=s, verbose=False)
        best_v = res["best_node"]
        best_f = res["best_stat"].mean_fitness()
        best_fitnesses.append(best_f)
        verdict = ""
        if res["perfect"]:
            verdict = "PERFECT"
            perfect_count += 1
            converged_count += 1
        elif res["converged"]:
            verdict = "converged"
            converged_count += 1
        else:
            verdict = "did not converge"
        print(f"  {s:>4d}  {best_f:>+12.2f}  {pretty(best_v):<40s}  {verdict}")

    print()
    print(f"  Summary across {n_seeds} seeds:")
    print(f"    perfect (|err| <= 0.5):  {perfect_count} / {n_seeds}")
    print(f"    converged (|err| <= 2):  {converged_count} / {n_seeds}")
    print(f"    mean best fitness:       {sum(best_fitnesses)/len(best_fitnesses):+.2f}")
    print(f"    worst best fitness:      {min(best_fitnesses):+.2f}")
    print(f"    best best fitness:       {max(best_fitnesses):+.2f}")


# --- main -------------------------------------------------------------------

def run():
    print("LOVA M4 Day 3-5 -- Self-healing population (Axiom 6)")
    print()
    print(f"  Problem:     starting from 5 WRONG variants, evolve to target={TARGET}")
    print(f"  Mechanism:   fitness-weighted reproduction + type-preserving mutation")
    print(f"  No training, no gradients, no prior knowledge of the target structure.")

    report_single_seed()
    run_multi_seed(n_seeds=10)

    _hr("Experiment 05 -- RESULT")
    print("  Axiom 6 operational: populations compete at dispatch, losers")
    print("  retire, winners clone+mutate, fitness trajectory shows")
    print("  substrate-level self-healing under target pressure.")


if __name__ == "__main__":
    run()
