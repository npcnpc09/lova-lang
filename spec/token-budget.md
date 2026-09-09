# LOVA — Token Budget: re-derivation and proposed allocation

> **Status: partly implemented (M10); the rest still awaiting a
> decision.** Six of the ten proposed slots are spent — see
> **As implemented** at the end, which also records one revision the
> proposal made to itself. `quote` / `eval` and the Axiom 8 revision are
> untouched and still need the owner's approval. The measurements are from
> `experiments/experiment_13_token_budget.py`
> (log: `experiments/results_13/run.log`); the reasoning is in
> `journal/experiment_13.md`. The Axiom 8 revision at the end
> **requires the project owner's approval** before any edit to
> `spec/axioms.md` (CLAUDE.md, "Still requires confirmation").

## Why this document exists

The 64-slot table was allocated in April 2026, before a single LOVA
program existed. Eight slots went to number theory; none went to
division, comparison, or any data type. M9 then spent nine milestones'
worth of goodwill discovering that the language could not express a
loop, and Exp 12 found that the density claim reverses on programs that
have to be written out rather than looked up.

So the table needs re-deriving. Two facts force the timing:

1. **The budget is nearly spent.** Of 39 reserved operators, 24 belong
   to the Evolution, Effects/IO and Meta families, each of which
   carries an axiom. That leaves **14 genuinely free slots**.
2. **Anything worth adding costs several of them.** A minimal list type
   is five. Division is one. Programs-as-data is two.

Spend them wrongly and the next milestone is blocked by a table nobody
wants to renumber.

## What the evidence says

### 1. The benchmark cannot be used as evidence about the table

Operator use across three corpora — LOVABench v2 (60 tasks), Exp 12's
algorithmic set (10 tasks), `apps/` (4 programs at the time of
measurement; `palindrome.lova` joined afterwards and the census is live,
so a re-run reports five):

| | LOVABench v2 | algorithmic | apps/ |
|---|---|---|---|
| `p` | 37 | 0 | 0 |
| `tau` | 32 | 0 | 0 |
| `sigma` | 28 | 0 | 1 |
| `gcd` | 20 | 0 | 1 |
| `mobius` | 7 | 0 | 0 |
| **number-theory family, all 8 slots** | **124 uses (33%)** | **9 (3%)** | **6 (5%)** |
| `ref` | 27 | 73 | 25 |
| `apply` | 0 | 24 | 6 |
| `lambda` | 0 | 19 | 6 |
| `if-surprise` | 4 | 14 | 7 |

The number-theory family is a third of all operator use in the
benchmark and 3–5% everywhere else. `p`, `tau` and `mobius` are used
**zero** times outside it.

This is not evidence that number theory is worthless. It is evidence
that **the benchmark cannot testify about the table**: its 60 tasks
were authored in the language, so they exercise the operators the
language had, and `corpus/tasks.py` says so in its own docstring —
HumanEval was rejected because LOVA "cannot express" string and list
manipulation. A corpus selected for what the language can do cannot
then be asked what the language should do.

Also worth recording: five implemented operators appear in none of the
three program corpora — `identity`, `budget`, `violate`,
`trace-surprise`, `loop-until`. (`budget` and `violate` do appear in
tests and experiment fixtures; `loop-until` was implemented in M9 and
no program has yet needed it, because iteration over a single value is
rarer than iteration with an accumulator, and an accumulator needs
recursion.)

### 2. Density is a surface problem, not a table problem

Where the Stage-1 LLM tokens go on the algorithmic corpus: **51%
operator names and identifiers, 25% parentheses, 10% literals**. A new
operator can only reclaim tokens from the names share, and only where
it removes nesting.

Three levers, measured separately on the same ten tasks (Python = 312
tokens):

| Lever | Slots | Tokens | vs Python | Gap closed |
|---|---|---|---|---|
| as shipped | 0 | 471 | 0.66× | — |
| \+ one-token operator spellings | **0** | 424 | 0.74× | **30%** |
| \+ `lt` and `sub` primitives | 2 | 409 | 0.76× | 9% |
| residual (parens + identifiers) | n/a | — | — | 61% |

The free lexical lever is worth **three times** the two slots. The
alias rewrite was verified by execution — all ten programs re-parsed
and re-evaluated to identical results — so this is a measurement, not
a projection.

The residual is larger than both levers combined and is a property of
s-expressions. Closing it means a different **surface** (Stage 2), not
different **operators**.

### 3. `div` is a complexity argument, not a density argument

| | today | with one slot |
|---|---|---|
| tokens | 48 | 6 |
| nodes | 33 | 3 |
| runtime | O(a/b) recursion | O(1) |

One task's density, but every future program that divides — and every
one of them currently burns call depth against `MAX_CALL_DEPTH` to do
arithmetic.

## Proposed allocation

**10 of the 14 free slots. 4 left unspent.**

| Slots | Operators | Basis | Rationale |
|---|---|---|---|
| 5 | `nil`, `cons`, `head`, `tail`, `nil?` | census | One cons cell buys pairs, lists **and** strings in one purchase. Without it there is no two-value return — `partition` currently returns `n // 2` instead of a pair because a pair is not representable — and no collection of any kind. |
| 1 | `div` | complexity | See above. |
| 2 | `quote`, `eval` | axiom | A program as a value. Axiom 1 says programs are integers; Stage 3's only human interface is `(explain program)`. Neither is reachable from inside the language today, and neither becomes reachable without this. |
| 2 | `lt`, `sub` | density | 9% of the measured gap, 5 and 7 sites in ten tasks. The cheapest defensible density purchase available, and the only one the data supports at all. |

Suggested placement, keeping families semantically coherent:

| Byte | Currently | Proposed |
|---|---|---|
| 0x04 | `heat-inc` | `nil` |
| 0x05 | `heat-get` | `cons` |
| 0x06 | `inherit` | `head` |
| 0x29 | `par` | `tail` |
| 0x19 | `watch` | `nil?` |
| 0x0D | `eta` | `div` |
| 0x1E | `normal-range` | `lt` |
| 0x12 | `delta-check` | `sub` |
| 0x1C | `predict` | `quote` |
| 0x1A | `when-anomaly` | `eval` |

Placement is negotiable and the family boundaries make some of these
awkward (`nil?` in the Surprise family is ugly). The alternative is to
admit that "8 families of 8" is an aesthetic constraint rather than a
semantic one — see the Axiom 8 discussion.

**The bytes actually used differ from this table** — `cons` / `head` /
`tail` ended up contiguous at 0x04-0x06 and `nil` at 0x15, which keeps
the cons trio together. See **As implemented** below; this table is kept
as the proposal that was reviewed.

Left unspent: 0x13 `respawn`, 0x14 `budget-remaining`, 0x15
`sum-invariant`, 0x16 `preserve` — all in the Conservation family,
which is the one family with a plausible near-term use for its own
reserved slots.

## Explicitly not proposed

**Reallocating the number-theory family (8 slots).** The census looks
damning until you notice the demand above fits in 14 slots without
touching it. Reallocation is the reserve position: spend those slots
only if strings-as-lists proves too slow to be usable, or if a real
string type becomes necessary.

**A dedicated string type (5–6 slots).** Unnecessary. Once `cons`
exists, a string is a list of codepoints, and `"abc"` is surface sugar
expanding to `(cons 97 (cons 98 (cons 99 nil)))` — zero slots. This is
how C and early Lisps did it. It is slow; LOVA is a research
substrate.

**Shorter operator names (0 slots).** Not a table decision at all.
This is the largest measured density lever and it is free, which is
exactly why it must not be filed under "budget".

## Proposed revision to Axiom 8

Axiom 8 currently reads:

> **Small core, dense tokens.** Core operator set ≤ 64 (1 byte each).
> Every byte carries semantic weight. Sugar is a Stage-1 bootstrap
> concession, not a language feature.

Three problems, all surfaced by measurement rather than argument.

**(a) The 64 is not derived from the byte.** A byte holds 256 values.
"64" comes from "8 families of 8", which is an aesthetic choice, and
the choice is now costing something real: the placement table above has
to put `nil?` in the Surprise family because the families are full in
the places the operators belong. The load-bearing invariant is *one
byte per operator*; 64 is a self-imposed quarter of it.

**(b) "Every byte carries semantic weight" is not what a small core
buys.** Exp 13 measures the density contribution of operator count as
9% against 30% for spelling and 61% for syntax. What a small core
actually buys is a narrow `valid_next` set — fewer candidates per
generation position, i.e. a sharper constraint on the model — plus a
small runtime. Those are good things and they are the real
justification. Density is not.

**(c) "Sugar is a bootstrap concession, not a language feature"
actively discourages the highest-value change available.** The axiom as
written tells a designer to deprioritise the one lever measured at 30%.
If AI is the first-class reader, then how an operator *tokenizes in the
generating model's vocabulary* is a substrate-level concern, not a
human convenience.

Proposed replacement:

> **8. Small core, one byte per operator.** Every core operator is a
> single byte. The core stays as small as the language's expressive
> obligations allow, with 64 as a soft target and 256 as the hard
> ceiling; families are an organising convenience, not an invariant,
> and an operator belongs where its semantics belong. A small core is
> justified by the two things it actually buys — a narrow `valid_next`
> set at each generation position, and a runtime small enough to
> verify — not by density, which Exp 13 shows is dominated by surface
> spelling and syntax.
>
> Surface spelling is a substrate-level concern, not a human
> convenience: if AI is the first-class reader, the tokenizer of the
> generating model is part of the interface. Sugar must desugar
> losslessly into the core (Constraint 6 unchanged), and *should* be
> chosen to minimise the generating model's token count.

This is a revision to a load-bearing axiom, so per `CLAUDE.md` it
needs the owner's explicit approval. Axioms 1–7, 9 and 10 are
unaffected.

## As implemented (M10, 2026-09-09)

**Six slots spent of the fourteen; eight remain.**

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x04 | `heat-inc` | `cons` | `Int, List -> List` |
| 0x05 | `heat-get` | `head` | `List -> Int` |
| 0x06 | `inherit` | `tail` | `List -> List` |
| 0x0D | `eta` | `div` | `Int, Int -> Int` |
| 0x15 | `sum-invariant` | `nil` | `-> List` |
| 0x19 | `watch` | `nil?` | `List -> Int` |

Implemented operators: 25 → **31 of 64**. The number-theory family was
**not** reallocated, as proposed.

### One revision the proposal made to itself

`lt` and `sub` were costed at one slot each. They shipped as **surface
macros instead, costing zero slots**, because this document's own
measurement said so: they are worth 9% of the density gap, and a macro
expansion captures the same *surface* saving — the token count is
identical whether `(lt a b)` is an operator or expands to
`(threshold (deviation b a))`. What a macro gives up is the node-count
saving, which Exp 13 measured at 2% (5 nodes in 330). Two slots for 2%
is a bad trade, and noticing that is what the measurement was for.

`gt` and `list` shipped as macros on the same reasoning, and string
literals with them:

| Written | Expands to | Slots |
|---|---|---|
| `(sub a b)` | `(merge a (mul -1 b))`, or `(merge a -k)` for a literal | 0 |
| `(lt a b)` / `(gt a b)` | `(threshold (deviation b a))` | 0 |
| `(list a b c)` | `(cons a (cons b (cons c (nil))))` | 0 |
| `"abc"` | `(cons 97 (cons 98 (cons 99 (nil))))` | 0 |

So **strings cost the table nothing**, as predicted: a string is a list
of codepoints. `apps/palindrome.lova` is the first program to use them.

### The zero-slot lever, shipped

Eight one-token operator spellings are now accepted:
`if`, `dev`, `tr`, `loop`, `keep`, `dist`, `mu`, `def`. Canonical names
stay canonical — `pretty` still prints `if-surprise`, and these are
additional spellings rather than renames. Measured: 471 → 424 LLM tokens
on the ten algorithmic tasks, **30% of the gap to Python for zero
slots**, verified by re-executing all ten.

### M11 activated the IO family's own slots

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x35 | `stdout` (reserved) | `stdout` | `Value -> Int` |
| 0x36 | `stdin` (reserved) | `stdin` | `-> List` |

These are **activations, not reallocations**: the original table named
them, the Effects/IO family was reserved for exactly this, and no free
slot was consumed. Implemented operators 31 → 33 of 64; the eight free
slots below are untouched.

Everything else M11 needed cost nothing: `not` / `and` / `or` / `eq` /
`min` / `cond` and the rest are macros, and the standard library is
written in LOVA.

### M13 activated `when-anomaly`

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x1A | `when-anomaly` (reserved) | `when-anomaly` | `Value, Fn -> Value` |

Another activation rather than a reallocation — the slot carried that
name from the first table. It does come out of the eight free slots,
because the Surprise family is not one of the three whose reserved
range was already committed to an axiom. **Seven free slots remain**:
0x12 `delta-check`, 0x13 `respawn`, 0x14 `budget-remaining`, 0x16
`preserve`, 0x1C `predict`, 0x1E `normal-range`, 0x29 `par`.

`(try body fallback)` is a macro over it, and `DomainTrap` — which gave
the other twenty-two runtime faults the same anomaly schema — cost no
slot at all, being a Python-level class rather than an operator.

### M14 spent two free slots and activated the Meta family

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x29 | `par` (free) | `quote` | `Value -> Program` |
| 0x1C | `predict` (free) | `eval` | `Program -> (follows)` |
| 0x38-0x3F | Meta, reserved | `lineage-query` `why` `trace` `explain` `hash` `uid` `ancestor-of` `generation` | activated as named |
| 0x24, 0x25 | `mutate`, `clone` (Evolution, reserved) | activated as named | `Program -> Program` |

`quote` / `eval` were the two lines this document flagged as "the one
thing justified by an axiom rather than a number", and they were the
prerequisite for the whole Meta family: no program value, nothing to
explain. **Five free slots remain**: 0x12 `delta-check`, 0x13 `respawn`,
0x14 `budget-remaining`, 0x16 `preserve`, 0x1E `normal-range`.

### M15 activated the rest of the Evolution family

| Byte | Name | Type |
|---|---|---|
| 0x20 | `defpop` | `Fn, Program* -> Population` |
| 0x21 | `variant` | `Population, Int -> Program` |
| 0x22 | `evolve` | `Population -> Population` |
| 0x23 | `select` | `Population, Int -> Program` |
| 0x26 | `fitness` | `Population -> List` |
| 0x27 | `retire` | `Population -> Population` |

Activated as named; no free slot consumed. **52 of 64 implemented.**
The five free slots are unchanged: 0x12 `delta-check`, 0x13 `respawn`,
0x14 `budget-remaining`, 0x16 `preserve`, 0x1E `normal-range`. The
twelve reserved are those five plus the seven Effects/IO slots that
are not `stdout` / `stdin`.

### Still unspent, still needing a decision

| Candidate | Slots | Status |
|---|---|---|
| `quote`, `eval` | 2 | Not implemented. Programs-as-data is a real design commitment (evaluator re-entrancy, what `eval` may touch), and it is the one line here justified by an axiom rather than a number. |
| Axiom 8 revision | — | Not applied. `CLAUDE.md` requires the owner's approval for any axiom change. |
| number-theory reallocation | 8 | Reserve position, not taken. |

Eight free slots remain: 0x12 `delta-check`, 0x13 `respawn`, 0x14
`budget-remaining`, 0x16 `preserve`, 0x1A `when-anomaly`, 0x1C
`predict`, 0x1E `normal-range`, 0x29 `par`.

### What the placement cost in coherence

`cons` / `head` / `tail` sit together in the Structural family, which is
right. `div` sits in the number-theory family, which is right. But
`nil` had to go to a Conservation slot and `nil?` to a Surprise slot,
because Structural was full where those operators belong. That is the
8×8 family constraint charging rent, and it is the concrete case for
Q39.

## Decision checklist

- [x] ~~Approve or amend the 10-slot allocation~~ — 6 spent (lists +
      `div`); `lt` / `sub` became macros, `quote` / `eval` held
- [x] ~~Confirm strings-as-lists rather than a string type~~ — done, 0 slots
- [x] ~~Decide whether to ship the one-token operator aliases~~ — shipped
- [ ] **Approve or revise the placement**, in particular `nil` in a
      Conservation slot and `nil?` in a Surprise slot — or drop the 8×8
      family constraint (Q39) and place them properly
- [ ] **Approve, amend or reject the Axiom 8 revision** (not applied)
- [ ] **Decide on `quote` / `eval`** — 2 slots, and the only route to
      Axiom 1's programs-as-data and Stage 3's `(explain program)`
