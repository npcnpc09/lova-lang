"""Experiment 15 -- Axiom 6 in the language: Exp 05, re-run from inside LOVA.

Experiment 05 (April) showed self-healing: five variants none of which
computes 42, evolved under fitness pressure, close most of the gap.  It
was run by ``core/populations.py`` -- Python driving LOVA programs from
outside.  Axiom 6 says a function *is* a population; M15 put the six
remaining Evolution operators into the language, so the same experiment
can now be written *as a LOVA program*:

    (def score [p] (surprise 42 (eval p)))
    (def gen [pop k] (if k (gen (evolve pop) (sub k 1)) pop))
    (select (gen (defpop score (quote (p 5)) ...) 30) 0)

The scorer is a LOVA function; the fitness signal is `surprise`; the
lineage of the winner is queryable by `generation` and `why`.  Nothing
about the experiment lives in Python except the seed loop and the
printing.

Three parts:

  1. Ten seeds, thirty generations each, from Exp 05's five variants
     toward Exp 05's target.  Reported against both baselines Exp 05
     used -- the initial *best* (distance 12) and the initial *worst*
     (35) -- because Exp 05's "gap closed" was measured from the worst.
  2. Provenance of each winner, answered from inside the language.
  3. What differs from Exp 05, stated plainly: `evolve` uses the library
     default mutation strength (30%); Exp 05 ran at 45% with ten
     dispatches per round.  This is the same rule at a different
     setting, not the same run.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.compiler import compile as lova_compile
from core.lineage import LineageStore
from core.runtime import Runtime, evaluate, list_to_python
from core.surface import parse

TARGET = 42
GENERATIONS = 30
SEEDS = 10

VARIANTS = ("(quote (p 5))", "(quote (sigma 12))", "(quote (merge 10 20))",
            "(quote (tau 100))", "(quote (gcd 24 36))")

# The whole experiment, as one LOVA program.  It evolves the pool for
# GENERATIONS steps and writes: the winner's text, its score, its
# generation, and why it exists -- one per line -- then returns the
# score of the winner.
PROGRAM = f"""
(def score [p] (surprise {TARGET} (eval p)))
(def gen [pop k] (if k (gen (evolve pop) (sub k 1)) pop))
(def line [v] (seq (stdout v) (stdout "\\n")))
(let 0 (defpop score {' '.join(VARIANTS)})
  (let 1 (select (gen (ref 0) {GENERATIONS}) 0)
    (seq (line (explain (ref 1)))
         (line (score (ref 1)))
         (line (generation (ref 1)))
         (line (why (ref 1)))
         (score (ref 1)))))
"""


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def run_seed(seed: int) -> dict:
    node, _ = lova_compile(parse(PROGRAM))
    rt = Runtime(lineage=LineageStore(seed=seed))
    score = evaluate(node, rt)
    winner, _score, generation, why = rt.written().rstrip("\n").split("\n")
    return {"seed": seed, "score": score, "winner": winner,
            "generation": int(generation), "why": why,
            "steps": rt.steps, "caught": len(rt.caught)}


def run() -> None:
    print("LOVA Experiment 15 -- Axiom 6 in the language (Exp 05 from inside)")

    _hr("1. Ten seeds, thirty generations, written as a LOVA program")
    initial = list_to_python(evaluate(lova_compile(parse(
        f"(fitness (defpop (lambda 9 (surprise {TARGET} (eval (ref 9)))) "
        f"{' '.join(VARIANTS)}))"))[0], Runtime()))
    best0, worst0 = min(initial), max(initial)
    print(f"  initial distances to {TARGET}: {initial}   "
          f"(best {best0}, worst {worst0}) -- Exp 05's numbers, from inside")
    print()
    print(f"  {'seed':>4s} {'final':>6s} {'from best':>10s} {'from worst':>11s}"
          f" {'gen':>4s} {'trapped':>8s}  winner")
    print("  " + "-" * 74)
    results = []
    for seed in range(SEEDS):
        r = run_seed(seed)
        results.append(r)
        from_best = (best0 - r["score"]) / best0
        from_worst = (worst0 - r["score"]) / worst0
        print(f"  {seed:>4d} {r['score']:>6d} {from_best:>9.0%} {from_worst:>10.0%}"
              f" {r['generation']:>4d} {r['caught']:>8d}  {r['winner']}")

    finals = [r["score"] for r in results]
    improved = sum(1 for f in finals if f < best0)
    converged = sum(1 for f in finals if f <= 2)
    perfect = sum(1 for f in finals if f == 0)
    mean_from_best = sum((best0 - f) / best0 for f in finals) / len(finals)
    mean_from_worst = sum((worst0 - f) / worst0 for f in finals) / len(finals)
    print("  " + "-" * 74)
    print(f"  improved on the initial best:  {improved}/{SEEDS}")
    print(f"  converged (distance <= 2):     {converged}/{SEEDS}")
    print(f"  perfect (distance 0):          {perfect}/{SEEDS}")
    print(f"  mean gap closed, from best:    {mean_from_best:.0%}")
    print(f"  mean gap closed, from worst:   {mean_from_worst:.0%}   "
          "(the baseline Exp 05 reported against)")

    _hr("2. Provenance of the winners, from inside the language")
    print("  `why` and `generation` are LOVA operators now; each line below")
    print("  was written by the program about its own winner.")
    for r in results[:4]:
        print(f"  seed {r['seed']}: gen {r['generation']:>2d}  {r['why']}")
    trapped = sum(r["caught"] for r in results)
    print(f"  variants that trapped under the scorer across all runs: {trapped}"
          "  (scored UNFIT, recorded in rt.caught, never crashed a pool)")

    _hr("3. What differs from Exp 05")
    print("  Exp 05: strength 0.45, 12 rounds x 10 dispatches, Python-driven,")
    print("          best seed 35 -> 1 (97% from worst), 3/10 within +-2,")
    print("          mean 80% closed from worst.")
    print(f"  Here:   strength 0.30 (the library default `evolve` encodes),")
    print(f"          {GENERATIONS} generations x 1 refill, LOVA-driven,")
    print(f"          mean {mean_from_worst:.0%} closed from worst, "
          f"{converged}/{SEEDS} within +-2.")
    print("  Same rule, different setting -- not the same run.  The point")
    print("  of this experiment is not the number; it is that the number")
    print("  was produced by a LOVA program calling `evolve`, `select`,")
    print("  `generation` and `why`, with Python doing nothing but seeding")
    print("  and printing.  Axiom 6 is in the language.")

    _hr("Experiment 15 -- summary")
    print(f"  {improved}/{SEEDS} seeds improve, {converged}/{SEEDS} converge, "
          f"mean {mean_from_worst:.0%} of the worst-case gap closed, all from")
    print("  inside LOVA; the Evolution family is 8/8 implemented.")


if __name__ == "__main__":
    run()
