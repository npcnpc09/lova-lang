# Experiment 10 — Historical pass-rate telemetry (Q22)

**Date:** 2026-04-24
**Script:** `experiments/experiment_10_telemetry.py`
**Status:** Done (20 refs + N=300 random bootstrap; Demo B N=50). **WIN.**

## Hypothesis

`valid_next_with_stats` returned static per-token metadata (arity,
depth_delta, effects, budget_cost) but no empirical signal. An AI
consumer sampling from it had to decide between valid tokens using
priors and type info alone. Most failure modes of random programs —
`(conserve N <body>)` where `<body>` accidentally violates N,
oversized number-theory inputs, `VIOLATE` anywhere a pure program is
expected — are not visible to a static schema but *are* visible in
run outcomes.

Q22 hypothesis:

- **H1** A per-token and per-(token, parent_op) pass/miss counter,
  bootstrapped from a small mix of known-good programs
  (LOVABench refs) and uncurated samples (constrained_random), yields
  a useful historical signal.
- **H2** `TokenChoice` can carry two views of this signal without
  breaking back-compat: `prior_pass_rate / prior_sample_count` (global,
  all contexts) and `prior_pass_rate_ctx / prior_sample_count_ctx`
  (specific to the slot's parent_op).
- **H3** A greedy sampler that scores by these rates produces
  materially more "passes-without-trap" programs than a uniform
  sampler on the same valid-next set.

## Method

Three substrate changes + one new module:

1. `Slot.parent_op: Optional[int]` added to the generator (default
   `None`, set by `GenState.step()` when pushing child slots for an
   operator's arguments). Non-breaking — prior tests still pass.

2. `core/telemetry.py` (new, ~180 LOC). `TelemetryDB` dataclass with
   two counters: `per_token[token] = {hits, misses}` and
   `per_context[(token, parent_op)] = {hits, misses}`. `record(tree,
   passed)` walks pre-order, bumps both. JSON serialisation via
   `save / load / to_dict / from_dict`. `lookup(token, parent_op=None)`
   falls back from context to global when the pair has no samples;
   `lookup_global` and `lookup_context` are strict views.

3. `TokenChoice` extended with four optional fields
   (`prior_pass_rate / prior_sample_count /
   prior_pass_rate_ctx / prior_sample_count_ctx`), all defaulting
   to `None / 0`. `valid_next_with_stats(state, telemetry=None)`
   reads `state.stack[-1].parent_op` and populates via
   `TelemetryDB.lookup_global` + `TelemetryDB.lookup_context` when
   a DB is passed.

4. `core.runtime.MAX_NT_INPUT = 2000` — DoS guard on number-theory
   primitives (p, tau, sigma, mobius raise `ValueError` if input >
   cap). LOVABench max input is n=100, so production code unaffected;
   random programs composing `(p (p N))` -style bombs are trapped
   cleanly rather than burning CPU.

The bootstrap experiment:

- **Seed phase**: record all 20 LOVABench v1 reference solutions with
  `passed=True`. Each ref is a known-good program so it seeds the
  counters with clean positive samples.
- **Fuzz phase**: generate 300 `constrained_random(max_depth=4)`
  programs, evaluate each with `_safe_evaluate` (budget-capped runtime,
  catches BudgetTrap / DeltaTrap / unbound-ref / oversized NT input),
  record outcome.
- **Persist**: write `corpus/token_telemetry.json` (~19 KB).
- **Three demos**:
  - *A. Global vs context divergence.* Probe six `(token, parent)`
    pairs to see where context-conditioning sharpens the pass rate.
  - *B. Weighted vs uniform sampling.* 50 fresh `max_depth=3` programs
    per sampler, same seeds. Weighted sampler scores each `TokenChoice`
    by `prior_pass_rate_ctx` (if n≥3) else `prior_pass_rate` (if n≥3)
    else 0.5; picks the top score, breaking ties uniformly at random.
    Depth-limit termination prefers END over LIT_INT to guarantee that
    variadic slots close.
  - *C. TokenChoice surface check.* Show `.summary()` of a telemetry-
    populated choice list — confirms the new fields render.

## Results

### Bootstrap

| | value |
|---|---:|
| LOVABench refs recorded | 20 / 20 (all pass) |
| random programs: pass / fail / skip | 185 / 115 / 0 |
| total programs | 320 |
| distinct tokens tracked | 18 |
| distinct `(token, parent)` pairs | 277 |
| on-disk JSON size | 19 240 bytes |

### Demo A — global vs context pass rates

| probe | global | context |
|---|---:|---:|
| `lit` as child of `merge` | 65% (n=1015) | 70% (n=88) |
| `lit` as child of `conserve` (contract slot) | 65% (n=1015) | **3% (n=66)** |
| `lit` as child of `violate` | 65% (n=1015) | 69% (n=13) |
| `violate` (any context) | 65% (n=66) | — |
| `sigma` (any context) | 71% (n=89) | — |
| `merge` as child of `conserve` (body slot) | 72% (n=80) | **0% (n=5)** |

Two contexts diverge sharply from the global rate: `lit-in-conserve`
and `merge-in-conserve`. Both point at the same structural truth —
contract-first `(conserve N body)` only passes when body *happens* to
equal N, which random bodies almost never do. Global pass rate
averages across many benign contexts and hides the conserve-specific
hazard.

### Demo B — weighted vs uniform sampling

| sampler | passes-without-trap |
|---|---:|
| uniform | 38 / 50 = 76.0% |
| telemetry-weighted | **48 / 50 = 96.0%** |
| Δ (weighted − uniform) | **+20 pp** |

Weighted sampler uses per-context rate when it has ≥3 samples there,
falls back to global rate (≥3 samples), falls back to 0.5 prior.
Greedy max; ties broken uniformly. Depth cap prefers END over LIT_INT
for termination (necessary — greedy pass-rate scoring let LIT_INT
edge out END in variadic seq slots, refilling forever).

### Demo C — TokenChoice surface

Sample render at the root slot (no parent_op, so ctx empty):

```
0x03 merge            arity=2  d-depth=+1  term=False  effects={}
    pass=72% (n=80)   ctx= - (n=0)
0x11 conserve         arity=2  d-depth=+1  term=False  effects={conservation-check}
    pass=3% (n=60)    ctx= - (n=0)
0x01 lit              arity=0  d-depth=-1  term=True   effects={}
    pass=65% (n=1015) ctx= - (n=0)
```

Notice `conserve` is at **3% pass rate** globally — almost every
random program that wrapped a conserve around a non-trivial body
tripped the Δ-trap. That's an AI-actionable signal: "avoid conserve
unless you can prove the body returns the contract value."

## Findings

### F1. Context-specific pass rates are load-bearing.

Global pass rate for LIT is 65%; context pass rate for LIT-as-child-
of-CONSERVE is 3%. A sampler relying on global rate alone treats LIT
as uniformly safe. Context-conditioning exposes a 20× difference and
flags the conserve-contract slot correctly as hostile to random
content. This is the minimum case for the `per_context` counter.

### F2. Weighted sampling produces +20 pp more passing programs.

At N=50, uniform 76% vs weighted 96%. The effect is large relative to
the sample size. Weighted drives the sampler away from CONSERVE (3%
rate globally in this telemetry) and toward MERGE / SEQ / SURPRISE
which have 70%+ rates; within each parent context it prefers the
tokens that historically co-occurred with passing programs.

### F3. Greedy-max sampling requires an explicit termination bias.

When pass-rate-scored greedy picks are tied or differ by fractional
points, a variadic continuation slot can loop forever picking the
highest-rate operand. Preferring END when depth exceeds the soft
limit restores termination without needing to renormalize the score
function. Documented in the sampler; journalled as Q27 (a
principled termination-weighting that doesn't need an if-branch).

### F4. DoS guard `MAX_NT_INPUT = 2000` is essential for random telemetry.

Composition `(p (p N))` takes p(42) = 53174 → p(53174) ≈ astronomical.
Without the cap, a single bad random sample can burn minutes in a
single Python call inside the runtime. The cap is invisible to all
LOVABench tasks (max input n=100) and to any sane generated program.

### F5. Telemetry file format is compact.

320 programs → 19 240 bytes of JSON. Scales linearly in distinct
(token, parent_op) pairs (277 here out of ~300 possible). A 10 000
program run would fit in ~500 KB — tractable to ship in the repo as
a seed file.

## Discussion

**What this enables.** An AI consumer of `valid_next_with_stats` now
has three layers of signal per token: static type/effect/arity,
plus global pass rate, plus context-specific pass rate. The fallback
chain (context → global → uninformed) works naturally — when context
data is sparse (first time a token appears under that parent), global
kicks in; when even global is sparse (rare token), the uniformed prior
0.5 reveals its rarity.

**Bootstrap bias.** The initial telemetry over-represents two kinds
of program:
- LOVABench refs, which are *handcrafted well-formed* and always pass.
- constrained_random samples, which are *uniformly generated* — not
  representative of what an AI sampler would actually produce.

The resulting telemetry is useful as a starting prior but will drift
as samplers that consume it generate more samples. Q28 is: incremental
update protocol — when a sampler run completes, merge its
outcomes back into the DB. Initial design sketch: `db.merge(other_db)`
takes a second TelemetryDB and adds counters; `record_trajectory(trees,
passed_flags)` ingests a batch.

**Sparsity.** With only 320 bootstrap programs, many (token, parent)
pairs have n < 10. For those the lookup falls back to global. As the
corpus grows this sparsity will recede, but the fallback is load-
bearing in the MVP; don't remove it without a much bigger bootstrap.

**Relation to language modelling.** This is a very shallow "n-gram of
one": condition the pass rate on the immediate parent only. Deeper
context (grandparent, sibling shape, slot-type combinations) is a
natural extension (Q29). Trade-off: sparsity grows multiplicatively,
so richer context needs much more data.

**Relation to RL / bandits.** The greedy-max weighted sampler is an
arg-max bandit with Laplace-smoothed rate + 0.5 uninformed prior.
Upper-confidence-bound (UCB1) would exploration-explore more
rigorously. For Q22 MVP, greedy was enough to demonstrate a +20 pp
gap; the richer algorithm belongs in a Day 4+ experiment.

## Next questions raised

→ **Q26**: Task-level pass signal. A program that evaluates without
trap but returns the wrong value for a LOVABench task should count as
a miss at the *task* level. Add a second record mode: `db.record(
tree, passed, level="task"|"runtime")`.

→ **Q27**: Principled termination-weighting in the greedy sampler —
score END as `1.0` (or rate-adjusted floor) when past depth cap, so no
if-branch is needed. Removes the special case.

→ **Q28**: Incremental merge. Once the sampler generates programs and
those programs are evaluated, fold the outcomes back into the DB so
telemetry improves online. Design spec: commutative `merge`, durable
`save`/`load`, content-hash identity for dedup.

→ **Q29**: Richer conditioning — grandparent, sibling-type, slot-
position. Requires a much bigger corpus to avoid sparsity collapse.

## Status

**WIN.** Bootstrap 20+300 → 19 KB DB; 6/6 probes render; weighted
sampler +20 pp over uniform on passes-without-trap. Q22 closed.
Three new questions (Q26–Q29) raised. `TokenChoice` surface is
backward-compatible (new fields default None/0); `valid_next_with_stats`
accepts optional `telemetry` param. M6 Day 1-3 complete; M6 Day 2's
body-offender + Day 3's telemetry together double the actionable
signal an AI consumer sees at generation time.
