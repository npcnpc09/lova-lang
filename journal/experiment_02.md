# Experiment 02 — Type-directed generation (Axiom 3)

**Date:** 2026-04-24
**Script:** `experiments/experiment_02_type_directed_generation.py`
**Status:** Done. **WIN (STRONG).**

## Hypothesis

Axiom 3: *For any prefix of a LOVA token sequence, the set of
well-typed next tokens is computable. An AI sampling only from this
set produces programs that are by construction well-formed and
well-typed.*

Operationalised as four sub-claims:

- **C1**. `GenState.valid_next()` at a fresh state admits exactly the
  M1 typed operators whose `out_type` is a subtype of `Int`.
- **C2**. After `LET`, the sharp constraint fires: `valid_next() ==
  {LIT_INT}` (the name slot demands `LiteralInt`).
- **C3**. Sampling 1000 programs under `constrained_random` produces
  100% well-formed, well-typed outputs.
- **C4**. Sampling 1000 programs under `unconstrained_random` (uniform
  over the M1 token set, no state check) produces ≪ 100% valid
  outputs. The delta is load-bearing.

## Method

Implement three modules:

| file | role | lines |
|---|---|---|
| `core/types.py` | `Type` class + `is_subtype` (INT, LITERAL_INT) | 80 |
| `core/tokens.py` (extended) | attach `in_types`/`out_type` to 18 M1 operators | +45 |
| `core/generator.py` | `GenState` state machine, `valid_next`, `constrained_random`, `unconstrained_random`, `validates` | 240 |

Experiment tests:

1. Walk through 7 concrete prefixes; for each, print the size and
   identity of `valid_next()`. Demonstrate the LET-sharp-constraint
   concretely.
2. Seed 0..999 through `constrained_random(max_depth=6)`; count how
   many `validates()`.
3. Seed 0..999 through `unconstrained_random(max_tokens=10)`; count
   how many `validates()`.
4. Report `(constrained_rate, unconstrained_rate, absolute_delta,
   ratio)`.

## Results

### Concrete prefix walk

```
empty (start)                            |valid| = 18  (all M1 Int producers)
GCD .                                    |valid| = 18
GCD LIT .                                |valid| = 18
LET .                                    |valid| =  1  (only LIT_INT allowed)
LET LIT LIT .                            |valid| = 18
SEQ .                                    |valid| = 19  (18 + END)
SEQ LIT .                                |valid| = 19
```

The LET slot **drops from 18 to 1** — from "any Int expression" to
"literal only". This is the sharp-constraint demonstration: the
generator is physically unable to place a non-literal where a name is
expected.

### Constrained vs unconstrained (N=1000 each)

| metric | constrained | unconstrained |
|---|---|---|
| validated | **1000 / 1000 (100.00%)** | 0 / 1000 (0.00%) |
| avg bytes per program | 17.1 | 10.0 (fixed max_tokens) |
| generation time | 610 ms | 27 ms |
| delta (absolute) | **+100.00 pp** | — |
| ratio | **∞×** | — |

Five sample constrained programs (first 5 seeds):

```
seed 0: (surprise (trace-surprise (partition (mobius (let 12 (budget 11 16) 9)))) 3)
seed 1: (p (merge (mobius (identity (if-surprise (seq (seq 6) 0 13) 8 18))) 10))
seed 2: (partition (merge (merge (violate (tau (budget 19 19))) 18) 13))
seed 3: (gcd (ref 11) (if-surprise (merge 15 (mobius 6)) 17 12))
seed 4: (gcd (budget 12 (if-surprise (p (merge (merge 12 1) 16)) 8 3)) 6)
```

These are **structurally non-trivial** — nested 5-7 levels deep, using
most of the M1 operator family including `let/ref`, `if-surprise`,
`budget`, `violate`, `seq`. They are well-formed LOVA programs that
a future runtime can evaluate (some will trip Δ-trap if `violate` is
wrapped in `conserve`; that's semantic behavior, not a form error).

## Findings

### F1. Type-directed generation is 100% correct by construction
**Zero ill-formed outputs** across 1000 seeded generations. This is
not an empirical observation — it is a **theorem** of the state
machine: `valid_next()` is defined so that no ill-typed token can be
sampled, and `step()` correctly updates the stack.

### F2. Unguided generation over the same token set is 0% correct
**Zero valid outputs** across 1000 unguided seeds. The valid-program
subspace of the byte-stream space is vanishingly small; random picks
from even the typed token subset (18 ops + END) land in it
essentially never. This quantifies why the constraint is load-bearing
rather than cosmetic.

### F3. The constraint sharpens dramatically at semantic choke-points
At `LET`'s name slot, valid_next drops from 18 to 1 — an 18× narrowing
in a single position. This is the kind of sharp constraint that a
natural-language LLM cannot easily learn but that a state-machine
constraint enforces for free. **Sharp constraints are where the
AI-friendly property pays off most.**

### F4. Generated programs are non-trivial
The `constrained_random` output includes deeply nested programs with
full operator diversity. This isn't toy output — an LLM's
`logits[valid_next_mask]` sampling in a fine-tuned LOVA model
would produce programs of this shape and complexity.

## Discussion

Three honest caveats:

1. **No LLM yet.** The generator is a random sampler on top of the
   constraint. A real LLM would weight tokens by learned semantic
   priors; the valid-next filter only ensures well-formedness. The
   claim "LLM-constrained LOVA generation is 100% well-formed"
   follows from "constrained_random is 100% well-formed" + "the LLM
   logit mask respects the valid-next set". The second part is a
   standard technique (llguidance / Outlines) with no novel work
   required.

2. **Well-formed ≠ correct.** Axiom 3 only buys well-formedness. The
   generated programs may still fail conservation contracts, produce
   surprising values, or be semantically wrong. That is exactly the
   design intent — Axiom 3 removes the lowest-layer noise so that
   higher-layer reasoning (conservation, surprise, behavior) gets
   useful signal.

3. **Only 18 of 64 operators are typed in M1.** The remaining 46
   reserved operators (effect layer, evolution beyond `defpop`, meta,
   I/O) need type annotations as they come online in M3-M5.

What this experiment establishes is the **foundational property** of
Axiom 3, in code, empirically: there is a state machine; it is
computable; sampling from it produces well-formed programs. This is
what makes LOVA different from "Python with constrained JSON
output" — the constraint is at the language level, not at the message
level.

### Paradigm-inheritance note

The `valid_next` function is a direct descendant of:

- **Grammar-constrained decoding** (Outlines, llguidance, 2023-24):
  runtime enforcement of a regular/context-free grammar during LLM
  generation. LOVA's state machine is the same idea lifted from
  JSON/regex to a full-language type system.
- **Positional typing** (stack languages, Forth, APL, 1960s-present):
  the expected type at each position is a function of what came
  before, not of explicit annotation tokens. LOVA inherits this:
  our `in_types` declarations are on operators, not on positions in
  the source text.
- **Dependent-type narrowing** (Agda/Idris/Lean, 2000s-present): as
  you fill in a program, the remaining type context sharpens. The
  LET-from-18-to-1 is a miniature version of the narrowing that
  Coq/Agda do for dependent pattern matches.

None of these is novel. LOVA's synthesis — running all three
patterns at the same time on the same substrate — is the contribution.

## Next questions raised

→ **Q05**: What's the right tie-in between `valid_next()` and an LLM
  logits mask? Spec the interface so fine-tuning experiments can
  reuse the state machine unmodified.

→ **Q06**: Does `constrained_random`'s structural distribution match
  what a fine-tuned LLM would produce? Probably not — unguided random
  over-represents rare ops (all 18 weighted equally). Worth building
  a frequency-calibrated sampler for corpus bootstrapping.

→ **Q07**: How do the other 46 reserved operators phase in? Proposal:
  M3 adds effect/IO types, M4 adds evolution/population types, M5
  adds meta/lineage types. Each milestone reduces the "reserved"
  count by ~8-12 tokens.

→ **Q08**: Can we measure the "information-theoretic compression" of
  type-directed generation? I.e., how many bits per token does
  constrained generation save over unconstrained? This is the
  quantitative cousin of the 100% vs 0% comparison.

## Status

**WIN (STRONG).** All four sub-claims pass. Axiom 3 is operational in
~370 LOC across two new modules and one extension. The 100% vs 0%
comparison is the sharpest result LOVA has produced so far, and it
is a **structural** result (valid_next is computable, so the outcome
is not a measurement but a proof by construction). Ready for M3
planning.
