# Experiment 14 — The Stage-2 surface, built and measured

**Date:** 2026-09-09
**Script:** `experiments/experiment_14_stage2.py`
**Module:** `core/surface2.py`
**Status:** Done. **WIN (strong).** Closes Q37.

## Hypothesis

Exp 13 localised the algorithmic density gap: 30% operator spelling
(free), 9% new primitives (two slots), and **61% s-expression syntax,
unreachable by any change to the token table**. The best case under any
allocation was 0.76× against Python — still below parity.

H1. The residual is reachable by a different *surface*, and the surface
that reaches it is not a new design problem: the integer encoding
already has no delimiters, so a text projection of the byte sequence
removes 100% of the parenthesis cost by construction.

H2. Exp 11's Stage-2 numbers (3.2× vs sympy) are a projection from AST
node counts. Building the thing will show whether that projection was
any good.

## Method

`core/surface2.py`: one printable, single-LLM-token character per byte,
no delimiters. Arity determines structure, exactly as `decode` does it.
A literal is a run of digits with an optional leading `-`; every
operator symbol is a non-digit, so the lexer decides on one character.
A separating space is emitted only between a digit and a following
digit, which is the sole ambiguity.

One compression rule beyond one-char-per-byte: `(ref k)` for `k` in
0..9 — three bytes — gets a single symbol. Refs are 22% of AST nodes
and 36% of the Stage-2 token cost, because `&` and its index tokenize
separately. The rule is declared, not discovered, and deliberately the
only one.

Losslessness checked as a property: `parse(render(t)) == t` **and**
`encode(parse(render(t))) == encode(t)`, over LOVABench v2 (60), the
algorithmic set (10), `apps/` (5), and 1000 `constrained_random`
programs, each with and without the digram — 2150 round-trips — plus
evaluation compared before and after on the algorithmic set.

Density measured with `tiktoken cl100k_base`, the same tokenizer as
Exp 11/12/13, against the same Python baselines.

## Results

**Losslessness: 2150 / 2150 exact.** Evaluation identical 10/10.

### Algorithmic tasks (no built-in shortcut on either side)

| Surface | Tokens | vs Python |
|---|---|---|
| Stage 1 (s-expressions) | 471 | 0.66× |
| Stage 1 + best possible table change (Exp 13) | 409 | 0.76× |
| Stage 2, one char per byte | 379 | 0.82× |
| **Stage 2 + reference digram** | **277** | **1.13×** |
| Python | 312 | — |

### LOVABench v2, against Exp 11's projection

| Measure | Tokens | vs sympy | vs pure Python |
|---|---|---|---|
| Stage 1 (measured) | 866 | 2.00× | 8.51× |
| Stage 2 *estimate* (Exp 11) | 546 | 3.17× | 13.50× |
| **Stage 2 (measured)** | **322** | **5.38×** | **22.89×** |

### Where the tokens go now

| Class | Tokens | Share |
|---|---|---|
| operators | 132 | 48% |
| literals | 77 | 28% |
| references | 63 | 23% |
| separators | 5 | 2% |
| parentheses | 0 | **0%** |

```
Stage 1   (defn square [n] (mul n n))(square 7)
Stage 2   W0\1*LL$A7;
bytes     2e 01 01 00 2c 01 01 01 0b 2f 01 01 01 2f 01 01 01 2d 2f 01 01 00 01 01 07 00
```

## Findings

**F1. LOVA is denser than Python on algorithmic code, for the first
time.** 1.13×, from 0.66×. Exp 12's negative result — the one that said
the density claim reverses on real programs — is answered, and answered
by the instrument Exp 13 said was the only one that could: not the
token table, the surface.

**F2. The parentheses were never necessary, and had not been for nine
milestones.** `core.tokens.decode` has always recovered the tree from
the byte stream alone, because arity is in the signature. Stage 1
spent 25% of its LLM tokens re-stating something the substrate already
knew. Nothing had to be invented to fix this; it had to be noticed.

That also makes Stage 2 stage-coherent by construction (Axiom 10)
rather than by argument: it is not a second syntax to keep in sync, it
is the byte sequence written in characters instead of hex. Round-trip
is a property test, not an aspiration.

**F3. One compression rule beat the entire token-table question.** The
reference digram is worth 379 → 277 tokens, **27%**, against 9% for the
two new primitives Exp 13 costed at two slots. It costs zero slots,
because it is a fact about the projection rather than about the
language. Exp 13's conclusion — a table change is the wrong instrument
for density — holds even more strongly than when it was written.

**F4. Exp 11's Stage-2 projection understated density by 70%.** It
predicted 546 tokens on LOVABench where the built surface needs 322.
Combined with Exp 12, which found the same projection erring in the
*opposite* direction on algorithmic programs (480 estimated against 471
measured), the lesson is not "the projection was pessimistic" but
**node count is a poor proxy in both directions**. Two experiments now
quote it. Both should be read as bounded by this.

The README's Stage-2 row should be replaced with the measurement.

**F5. This is the first time Axiom 2 was cashed in rather than
asserted.** "Human readability is a non-goal of the substrate" has been
in the axioms since day one while every artifact stayed a readable
Lisp — Exp 12's F6 noted the axiom was paying costs and collecting no
benefit. `W0\1*LL$A7;` is the benefit: 1.13× against Python, and
unreadable without the table. `core.surface.pretty` remains for
auditing, which is exactly the role the axiom always assigned it.

**F6. What is left is the program itself.** 48% operators, 28%
literals, 23% references, 0% syntax. Further compression means naming
more frequent subtrees — `$&0` (a call of the first binding) and `\1`
(a one-parameter lambda) are the obvious next two — which would fit the
surface to the ten programs that motivated it. That is a real risk and
the reason only one rule was taken.

## Discussion

The density claim now has three measured regimes and a defensible
shape, where before it had one number and an objection:

| | Stage 1 | Stage 2 |
|---|---|---|
| number-theory tasks vs sympy-Python | 2.00× | **5.38×** |
| number-theory tasks vs pure Python | 8.51× | **22.89×** |
| algorithmic tasks vs Python | 0.66× | **1.13×** |

The honest summary is no longer "LOVA is 8.5× denser" but "**LOVA's
Stage-2 surface is 5.4× denser than sympy-Python where its built-ins
match the task and 1.1× denser where they do not**" — which is a
smaller claim, and one that survives the obvious attack.

Two caveats sit on it.

First, `cl100k_base` was not designed for this surface. A fine-tuned
vocabulary would do better — but that is a projection again, and F4 is
what projections are worth. The measurement stands on a tokenizer
nobody chose to favour LOVA.

Second and larger: **a surface only pays off if a model can write it.**
Nothing here shows that. `W0\1*LL$A7;` is exactly the kind of string a
model produces badly by free generation. The saving grace is that LOVA
does not need free generation — `valid_next` constrains decoding to
well-typed continuations, and the constraint is *sharper* in Stage 2
than in Stage 1 because there are no delimiter positions to get wrong.
That is testable today with a frontier model and no fine-tuning, and
until it is tested this experiment measures a page, not a workflow.
It is the single most load-bearing open question in the project (Q47).

## Next questions raised

- **Q46.** More digrams? `$&0` and `\1` are the next most frequent
  subtrees. Each is free in slots and each fits the surface a little
  harder to the corpus that motivated it. What is the principled
  stopping rule — frequency threshold, or a held-out corpus?
- **Q47.** **Can a model actually emit Stage 2?** Constrained decoding
  through `valid_next` should make it easier than Stage 1, not harder,
  since there are no delimiters to misplace. Measure pass@1 on
  LOVABench in Stage 2 against Stage 1, same model, constrained
  decoding, no fine-tuning. Everything in this experiment is contingent
  on the answer.
- **Q48.** Should Stage 1 be relegated to audit-only in the docs and
  `apps/`? Keeping two surfaces alive has a cost, and Axiom 2 says
  which one is the product.
- **Q49.** LOVABench's tasks were selected for what Stage-1 LOVA could
  express (Exp 13, F3). The 5.38× inherits that circularity. A v3
  corpus with an algorithmic category (Q33) would measure both regimes
  on one task set.

## Status

Stage 2 exists, round-trips losslessly 2150/2150, and takes LOVA from
0.66× to **1.13× against Python on algorithmic code** and from 2.00× to
**5.38× against sympy-Python on LOVABench** — closing the 61% residual
Exp 13 said no token-table change could reach, and refuting Exp 11's
projection by 70% in the process; whether a model can write it is
untested and is now the project's load-bearing question.
