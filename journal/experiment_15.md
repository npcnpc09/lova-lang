# Experiment 15 — Axiom 6 in the language: Exp 05, re-run from inside LOVA

**Date:** 2026-09-09
**Script:** `experiments/experiment_15_populations.py`
**Status:** Done (10 seeds × 30 generations). **WIN.** Closes Q58 and Axiom 6.

## Hypothesis

Experiment 05 showed self-healing — five wrong variants evolving toward
a target under fitness pressure — with `core/populations.py` driving
LOVA programs from Python. Axiom 6 says a function *is* a population.
M15 put the six remaining Evolution operators into the language; the
hypothesis is that Exp 05 can be written **as a LOVA program** and
reproduce its shape, with Python doing nothing but seeding and printing.

## Method

One LOVA program:

```lova
(def score [p] (surprise 42 (eval p)))
(def gen [pop k] (if k (gen (evolve pop) (sub k 1)) pop))
(let 0 (defpop score (quote (p 5)) (quote (sigma 12)) (quote (merge 10 20))
                     (quote (tau 100)) (quote (gcd 24 36)))
  (let 1 (select (gen (ref 0) 30) 0)
    (seq (line (explain (ref 1))) (line (score (ref 1)))
         (line (generation (ref 1))) (line (why (ref 1)))
         (score (ref 1)))))
```

Same five variants and target as Exp 05; the scorer is `surprise`
itself, since lower is fitter. `evolve` applies `core/populations.py`'s
default rule — retire the bottom 20%, refill from survivors with
sharpness-3 fitness weighting, 30% clone / 70% mutate at strength 0.30.
Ten seeds via the lineage store's seed; 30 generations each.

## Results

| | Exp 05 (Python, 0.45, 12×10 dispatches) | Exp 15 (LOVA, 0.30, 30 generations) |
|---|---|---|
| improved on initial best (12) | all 10 | **9/10** |
| converged (≤ 2 from target) | 3/10 | **3/10** |
| best seed | 35 → 1 (97% from worst) | **35 → 1 (97%)** |
| mean gap closed, from worst (35) | 80% | **85%** |
| mean gap closed, from best (12) | — | 56% |
| variants that trapped under scoring | — | 0 |

Every winner is a `merge` of two bumped literals — the shape Exp 05
found too. Winners' provenance, written by the program about itself:
`gen 6 mutate strength=0.3 [lit:12->15]`, `gen 5 mutate strength=0.3
[lit:20->25]`, …

## Findings

**F1. Axiom 6 is in the language.** The Evolution family is 8/8. A LOVA
program builds a pool, scores it with its own function, evolves it,
selects the winner and asks the winner where it came from. Python's
role is a seed and a `print`.

**F2. It reproduces Exp 05's shape, not its run.** 3/10 converged in
both; best seed 97% in both; mean-from-worst 85% vs 80%. But `evolve`
runs the library default strength (0.30) and one refill per generation
where Exp 05 ran 0.45 and ten dispatches per round. Same rule,
different setting. The numbers agree because the rule is the same; the
agreement is not a replication.

**F3. Elitism holds by construction.** `evolve` keeps the fittest
survivors, so best-so-far never worsens — tested across seeds. Seed 9
never improved in 30 generations (0%): the rule admits a run that
draws only clones and unlucky bumps. That is the same 30% convergence
ceiling Exp 05 recorded, seen from the other side.

**F4. Unfit is a score, not a crash.** A variant whose scorer traps —
a mutation into `(div 1 0)` — scores `UNFIT` and is recorded in
`rt.caught`. Zero occurred here because the M1 swap groups cannot
produce `div`; see Q60.

**F5. Axioms 5 and 6 compose.** `generation` and `why` on the selected
winner answer from the same lineage store `evolve` wrote to. That is
the provenance-of-an-evolved-function property Axiom 5 promised and
could not deliver while populations were Python objects.

## Discussion

A population is a value with its own type, not a list of programs.
That sidestepped Q42 (`List<T>`) for this milestone, at the cost of a
fifth value kind and six operators that only make sense on it. The
alternative — parameterised lists — would have made `defpop` a
`fold` over a list of programs and `select` a `sort`. It is still the
better long-term shape, and now there is a working operator set to
measure it against.

`evolve`'s strength is fixed. `mutate` exists for custom strength on a
single program; a custom *evolution* rule has to be written by hand
from `fitness`, `retire`, `select`, `clone` and `mutate` — which is
possible, and is what makes the six operators a basis rather than a
black box.

## Next questions raised

- **Q61.** `evolve` at 0.30 needs ~30 generations for what Exp 05 did
  in 12 rounds at 0.45. Should the strength be a `defpop` parameter, or
  should the prelude ship an `evolve-with` written from the primitives?
- **Q62.** The scorer runs every variant on every `select`, `retire`
  and `evolve`. Exp 05 had rolling fitness windows and dispatch counts;
  this has neither. Is memoised fitness a population concern or a
  scorer concern?
- **Q63.** With a `Population` type in hand, would `List<T>` (Q42)
  have made it unnecessary? Measure: rewrite `evolve` from list
  primitives once they exist, compare token cost and clarity.

## Status

Exp 05, written as a LOVA program: 9/10 seeds improve, 3/10 converge,
85% of the worst-case gap closed on average, best seed 35 → 1 — the
same shape Python produced in April — with Python now doing nothing
but seeding and printing; the Evolution family is 8/8 and Axiom 6 is
true inside the language.
