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

### M18 spent one free slot on `read`

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x1E | `normal-range` | `read` | `List -> Program` |

The inverse of `explain`. Not a macro: a program has to be able to
construct a program from text at run time, which no expansion can do.
Placed in the Surprise family because Meta is full. `use` cost
nothing — it is textual inclusion in the surface, the prelude's own
mechanism made addressable — and neither did `defpop` taking lists.
**53 of 64 implemented. Four free slots remain**: 0x12 `delta-check`,
0x13 `respawn`, 0x14 `budget-remaining`, 0x16 `preserve`. The eleven
reserved are those four plus the seven Effects/IO slots that are not
`stdout` / `stdin`.

### M19 activated the IO family, all but the network

| Byte | Name | Type |
|---|---|---|
| 0x30 | `external-boundary` | `LiteralInt, Value -> Value` (result follows the body) |
| 0x33 | `fs-read` | `List -> List` |
| 0x34 | `fs-write` | `List, Value -> Int` |
| 0x37 | `clock` | `-> Int` |

Activations as named; no free slot consumed. The boundary's literal is
a capability mask — one byte, `fs-read` 1, `fs-write` 2, `clock` 4,
`net` 8 reserved — and `(boundary "fs-read clock" ...)` is surface
sugar over it, so the capability *names* cost nothing. **57 of 64
implemented.** The four free slots are unchanged: 0x12 `delta-check`,
0x13 `respawn`, 0x14 `budget-remaining`, 0x16 `preserve`. Reserved
beyond those: 0x31 `net-send`, 0x32 `net-recv`.

### M21 activated the network

| Byte | Name | Type |
|---|---|---|
| 0x31 | `net-send` | `List, Value -> Int` |
| 0x32 | `net-recv` | `-> List` |

Activations as named; `net-send` grew from arity 1 to 2 because a
datagram needs a destination. The destination is an operand and the
grant is the host's (`--allow net=host:port`), so no address ever
enters the byte sequence. **59 of 64 implemented.** The IO family is
8/8. Nothing is reserved any more except the four free slots below,
which have been waiting on a decision since M10.

### M22 spent the last four: `signal`, and the map

| Byte | Was | Now | Type |
|---|---|---|---|
| 0x12 | `delta-check` | `signal` | `Int -> Value` (never returns; fits any slot) |
| 0x13 | `respawn` | `map-put` | `Value, Value, Value -> Map` |
| 0x14 | `budget-remaining` | `map-get` | `Map, Value, Value -> Value` (result follows the stored value) |
| 0x16 | `preserve` | `map-pairs` | `Map -> List` |

`signal` because a language that can catch (M13) but not raise leaves
its libraries guessing at bad input. The map because of a number: an
association list written from the list operators could not count the
words of a thousand lines in twenty million steps, and a native map
does it in 3.4 million (journal M22). The owner said yes to the last
three slots on that number.

**63 of 64 implemented; the table is full.** What remains to decide:

| Candidate | Slots | Status |
|---|---|---|
| Axiom 8 revision | — | Not applied. `CLAUDE.md` requires the owner's approval for any axiom change. |
| number-theory reallocation | up to 4 | The reserve position (Q74): `p`, `tau`, `sigma`, `mobius` underpin LOVABench and nothing else. The next operator that earns a slot takes one of these. |

### The decisions M10 left open, as they stood

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

## As implemented (M27, 2026-09-11): a list family

The second family past 0x3F, after the text family (M25). The
numbers that called for it: Exp 19 and Exp 20 measured the game-tree
search at two to four extra attempts, every one a rewrite for cost,
and Exp 20's step attribution read the cost as the prelude's list
walkers -- `nth` first (made native at zero slots through a
shape-keeping `text-slice`), then `map` / `filter` / `fold` / `any` /
`range` at 20-40 steps an element, the price of `loop-until` with a
cons-cell state. Eight operators at 0x50-0x57, one step an element:

| Byte | Name | Was (prelude, steps/element) | Now |
|---|---|---|---|
| 0x50 | `map` | 39 | 5 |
| 0x51 | `filter` | 35 | 5 |
| 0x52 | `fold` | 22 | 5 |
| 0x53 | `reverse` | 17 | 2 |
| 0x54 | `range` | 20 | 2 |
| 0x55 | `any` | ~25 (no early exit cost saving) | 1 + the call, stops at the first hit |
| 0x56 | `sort-by` | 213 (merge sort over `iterate`) | 8 (one comparison a step) |
| 0x57 | `zip` | ~30 | 1 |

Zero slots were spent in the core 64; 0x4E-0x4F stay free for the text
family. `sum`, `product`, `contains`, `all` remain prelude idioms over
the operators at one lambda call an element. The validator admits the
family and the samplers do not emit it (the text family's rule, M25).

## Q102 (2026-09-11): should compare and branch be operators?

Experiment 22 found that nine spellings an author uses constantly --
`sub`, `neg`, `eq`, `ne`, `lt`, `gt`, `le`, `ge`, `if` -- are Stage-1
**macros with no byte**, so they do not exist in the substrate and a
card projected from the text promised operators the byte stream cannot
spell.  That raised the design question: if the substrate is what an AI
is meant to author, do the operators an author needs every line belong
in the table rather than in a text layer that cannot be projected?

Costed, not argued.  `if` is not at issue: it maps 1:1 onto
`if-surprise`, which is already an operator.  The rest expand like
this, and the extra bytes are what a dedicated operator would save:

| macro | expansion | extra bytes |
|---|---|---|
| `lt` / `gt` | `(threshold (deviation b a))` | 1 |
| `neg` | `(mul -1 a)` | 3 |
| `sub` a b, b a **literal** | folds to `(merge a -b)` | **0** |
| `sub` a b, b a variable | `(merge a (mul -1 b))` | 4 |
| `eq` / `ne` | `(if-surprise (deviation a b) 0 1)` | 7 |
| `le` / `ge` | `(if-surprise (threshold (deviation a b)) 0 1)` | 9 |

Measured over the sixteen reference programs of Experiments 22 and 23
(one-line and larger, operator-only):

| task set | bytes now | bytes saved if all were operators |
|---|---|---|
| c, one-line (10) | 265 | 16 (6%) |
| b, larger (6) | 587 | 27 (5%) |

**Verdict: not worth the slots on current evidence.** Three reasons,
all measured:

1. **The cheap cases are common and the dear cases are rare.** The
   recursion idiom `(sub n 1)` -- by far the most frequent use -- costs
   nothing, because the constant-folder turns it into one `merge` with
   a negative literal.  `lt`/`gt` cost a single byte.  Only `eq`, `ne`,
   `le`, `ge` are expensive, and across sixteen programs they appear
   five times.
2. **The total is 5-6% of program bytes**, against six to eight slots.
   The 64-slot ceiling is a preference since 2026-09-10, but a family
   is added when the four numbers call for it, and a 5% byte saving on
   the substrate form does not.
3. **A model does not need them as primitives.** Q101 gave three
   sessions a card stating `a>b` is `(threshold (deviation a b))` and
   `a==b` is `(if-surprise (deviation a b) 0 1)`, and all three wrote
   every task first-try in the substrate forms, building comparison and
   branching from the recipe without error.  The gap Exp 22 measured
   was the card's silence, not the table's shape.

What would reopen it: evidence that the expansions cause *errors* at
program scale rather than merely costing bytes -- a writer mis-nesting
`if-surprise (threshold (deviation ...)) 0 1` where a single `le` would
have been unmistakable.  That is what Experiment 23 (Q104) watches for.

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
