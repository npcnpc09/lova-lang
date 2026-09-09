# Experiment 13 — Re-deriving the 64-slot token budget

**Date:** 2026-09-09
**Script:** `experiments/experiment_13_token_budget.py`
**Proposal:** `spec/token-budget.md`
**Status:** Done. **WIN on diagnosis — and it refuted this experiment's own starting hypothesis.**

## Hypothesis

Exp 12's F7 concluded that the density gap pointed "at the operator set
rather than at the tokenizer", because the Stage-2 estimate (one token
per AST node) was *worse* than Stage-1. The hypothesis carried into
this experiment was therefore:

H1. Adding the missing arithmetic and comparison primitives (`div`,
`lt`, `sub`) is the lever that closes the algorithmic density gap.

H2. The 8 slots spent on number theory are poor value and should be
reallocated.

H3. The 14 free slots are enough for a minimal list type, division and
comparison — just barely.

## Method

Three corpora, chosen so they disagree: LOVABench v2 (60 tasks,
authored in the language before M9), Exp 12's algorithmic set (10
tasks), `apps/` (4 programs). Operator use counted by walking the
parsed AST of each.

Token cost decomposed by classifying every `tiktoken cl100k_base` token
of each program as operator-name/identifier, parenthesis, literal,
bracket or whitespace.

Three levers measured **separately** on the ten algorithmic tasks:

1. **Surface aliases** — a one-tiktoken-token spelling for each
   multi-token operator name (`if-surprise`→`if`, `deviation`→`dev`,
   `loop-until`→`loop`, `trace-surprise`→`tr`, `conserve`→`keep`,
   `surprise`→`dist`, `mobius`→`mu`, `defn`→`def`). Zero slots.
   **Executed**: aliases registered, every program re-parsed and
   re-evaluated, results compared to the original.
2. **`lt` and `sub` primitives** — a paren-aware contraction of the
   idioms they would replace, applied to the *sugared* source text.
   Cannot be executed (the primitives do not exist), so measured as
   surface cost plus an analytic node-count delta.
3. **`div`** — measured separately, because it removes a whole
   user-defined function rather than contracting an idiom.

Two methodological corrections were needed before the numbers meant
anything, and both are worth recording because either would have
produced a confident wrong answer:

- The first implementation matched idioms with a regex whose argument
  groups were `[^()]+?`, which cannot match a nested argument. It found
  1 `lt` site instead of 5 and produced "`lt` buys nothing".
- The second implementation contracted the **AST** and re-rendered it,
  which measures the *desugared* form — 788 tokens against 471 for the
  same programs as written. Density has to be measured on what an LLM
  actually emits.

## Results

### Slot census

| | LOVABench v2 | algorithmic | apps/ |
|---|---|---|---|
| `p` / `tau` / `mobius` | 37 / 32 / 7 | 0 / 0 / 0 | 0 / 0 / 0 |
| number-theory family (8 slots) | **124 uses = 33%** | **9 = 3%** | **6 = 5%** |
| `lambda` + `apply` | 0 | 43 | 12 |

Free slots, after excluding the Evolution / IO / Meta families whose
reserved slots each carry an axiom: **14**.

Implemented but used in none of the three program corpora: `identity`,
`budget`, `violate`, `trace-surprise`, `loop-until`. (`budget` and
`violate` appear in tests and experiment fixtures; `loop-until` shipped
in M9 and nothing has needed it yet.)

### Where the tokens go (algorithmic corpus)

| names / identifiers | parens | literals | brackets | whitespace |
|---|---|---|---|---|
| 240 (51%) | 119 (25%) | 48 (10%) | 26 | 38 |

### Three levers

| Lever | Slots | Tokens | vs Python | Gap closed |
|---|---|---|---|---|
| as shipped | 0 | 471 | 0.66× | — |
| \+ one-token operator spellings | **0** | 424 | 0.74× | **30%** |
| \+ `lt`, `sub` | 2 | 409 | 0.76× | 9% |
| residual (parens + identifiers) | n/a | — | — | 61% |

Alias rewrite verified by execution on 10/10 tasks, identical results.
`lt` fired at 5 sites, `sub` at 7. Node count 330 → 325 (2%).

`div`: 48 tokens / 33 nodes / O(a/b) → 6 tokens / 3 nodes / O(1).

## Findings

**F1. H1 is refuted, and by a factor of three.** The free lexical
lever closes 30% of the algorithmic density gap; the two new primitives
close 9%. Exp 12's F7 read "Stage-2 estimate is worse than Stage-1"
as evidence that the operator set was the problem. It was evidence that
*node count* is not the binding constraint — which does not imply the
operator set is. Spelling was never measured, so it was never a
candidate. It turns out to be the biggest one.

**F2. The largest term is neither lever.** 61% of the gap is
parentheses and identifiers: irreducible s-expression syntax. No
allocation of the 64 slots reaches it. The instrument for that residual
is a different surface — the Stage-2 terse projection the roadmap
already names — and the honest conclusion is that **LOVA does not reach
Python's token density on algorithmic code under any table change**,
only under a surface change.

**F3. H2 is refuted too, but for an interesting reason.** The
number-theory family really is 33% of benchmark use and 3–5% of
everything else, and `p` / `tau` / `mobius` are used zero times outside
the benchmark. That reads as a slam-dunk for reallocation until you
count the demand: it fits in 14 slots without touching number theory.
Reallocation is the reserve position, not the plan.

The deeper point is that **the benchmark cannot testify about the
table.** `corpus/tasks.py` explains in its own docstring that HumanEval
was rejected because LOVA "cannot express" strings and lists, and that
tasks were chosen to be "natively expressible in LOVA's *present*
expressive power". A corpus selected for what the language can do
cannot then be asked what the language should do. Every operator-use
statistic drawn from LOVABench inherits that circularity — including
Exp 10's telemetry priors.

**F4. H3 holds, and one purchase does more work than expected.** A
single cons cell buys pairs, lists **and** strings: a string is a list
of codepoints, and `"abc"` is surface sugar for
`(cons 97 (cons 98 (cons 99 nil)))`. So the string type I had costed at
5–6 slots costs zero, and the proposal fits in 10 of 14 with four left
over. Pairs matter more than they look: `partition` (0x02) returns
`n // 2` today with a comment promising a real pair "when we have Pair
types", because a two-value return is not representable.

**F5. Two slots are needed for something no measurement asked for.**
`quote` / `eval` — a program as a value. Axiom 1 says programs are
integers; Stage 3's only human interface is `(explain program)`. Neither
is reachable from inside the language, and no amount of list or
arithmetic work makes them reachable. This is the one line in the
proposal justified by an axiom rather than a number, and it is flagged
as such.

**F6. Axiom 8's stated justification does not survive its own
measurement.** "Every byte carries semantic weight" is a density
argument, and operator count is the 9% term. What a small core actually
buys is a narrow `valid_next` set — fewer candidates per generation
position, i.e. a sharper constraint on the model — and a runtime small
enough to verify. Those are good justifications. Density is not one.

Worse, "sugar is a Stage-1 bootstrap concession, not a language
feature" instructs a designer to deprioritise the 30% lever. If AI is
the first-class reader, the generating model's tokenizer is part of the
interface, and operator spelling is a substrate concern. A revision is
proposed in `spec/token-budget.md`; per `CLAUDE.md` it needs the
owner's approval and has not been applied.

**F7. The 64 is not derived from the byte.** A byte holds 256 values.
"64" comes from "8 families of 8", which is aesthetic, and the cost is
visible in the proposed placement table: `nil?` has to go in the
Surprise family because Structural is full where it belongs. The
load-bearing invariant is one byte per operator.

## Discussion

The two methodological bugs in this experiment are the most transferable
part of it. Both were the kind that yield a confident number: a regex
that silently matched a fifth of the sites, and an AST re-render that
measured a form nobody writes. The first would have justified *not*
spending slots on `lt`; the second would have inflated LOVA's cost by
67% and made Python look better than it is. Neither would have looked
like a bug in the output.

Which bears on how Exp 12's F7 came to be wrong. F7 was a correct
observation ("the Stage-2 estimate is worse") with an inference attached
("so the lever is the operator set") that no measurement supported. The
journal convention says observation goes in Results and interpretation
in Discussion; F7 put an interpretation in a finding. Worth watching for.

On the substance: the project's density pitch now has three measured
regimes rather than one number.

- **Number-theory tasks: 8.5×.** Real, and it measures a domain-shaped
  standard library rendered as opcodes.
- **Algorithmic tasks, as shipped: 0.66×.** Real, and it measures the
  language.
- **Algorithmic tasks, best case under any table change: 0.76×.** Still
  below parity. The remaining 61% needs Stage 2.

That last number is the one to plan against, because it says the
Stage-2 terse surface is not a nice-to-have on the roadmap — it is
load-bearing for the central claim, and it has never been built or
measured. Exp 11's Stage-2 figures are a projection from node counts,
and Exp 12 showed that projection is *pessimistic in the wrong
direction* (it went up, not down) on exactly the programs that matter.

## Next questions raised

- **Q37.** Build the Stage-2 surface and measure it. It carries 61% of
  the density gap and currently exists only as a node-count projection.
  Until it is real, the density pitch rests on the number-theory regime
  alone.
- **Q38.** Ship the one-token aliases? Zero slots, verified on ten
  programs, 30% of the gap. The only argument against is that it makes
  the surface uglier for humans — which Axiom 2 says is not a
  consideration, so the axiom and the reluctance cannot both stand.
- **Q39.** Does the 8×8 family structure earn its keep? It forces
  operators into semantically wrong families and it is not what makes a
  token one byte.
- **Q40.** Every statistic drawn from LOVABench inherits the corpus's
  self-selection (F3), including Exp 10's telemetry priors, which are
  used to *weight generation*. What does the weighted sampler's +20 pp
  become on a corpus that was not authored in the language?
- **Q41.** `loop-until` has zero uses in any corpus. Is a single-value
  loop combinator the right iteration primitive, or should it thread an
  accumulator — which is what every program that iterates actually
  needs?

## Status

The table can hold what the language needs (10 of 14 free slots, four
spare, strings free once `cons` exists) — and the same experiment
refuted its own premise: the density gap is 30% spelling, 9% operators
and 61% s-expression syntax, so a table change was never the right
instrument for it, and no allocation reaches parity with Python on
algorithmic code.
