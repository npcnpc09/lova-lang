# Experiment 22 -- The three-form experiment: which form does the model emit? (Q100)

**Date:** 2026-09-11
**Script:** `experiments/experiment_22_three_forms.py`
**Status:** Done, five sessions on Opus 4.8 (s1 x2, s2 x2, tok x1). **PARTIAL.**

## Hypothesis

The ruling of 2026-09-11 (`CLAUDE.md`, "The design method"): the
model's behaviour decides between representations by measured
experiment, and a decision made on the s-expression is a decision made
with human-language intuition in the room. LOVA has three forms of the
same program:

- **s1** -- the Stage-1 s-expression: parentheses, operator names.
- **s2** -- the Stage-2 surface: one symbol per byte, no parentheses,
  integer references (`core.surface2`).
- **tok** -- the raw token bytes, the substrate itself, written as
  space-separated decimal byte values (`core.tokens.encode`).

Axioms 1 and 2 assert the integer sequence is the program and the text
is a projection. Q47 has always asked whether a model can *emit* the
non-text forms at all. Q100 asks the design question on top of it:
across the AI's operations -- emit, and (a later leg) repair -- which
form does the model produce most reliably, at what token cost? If the
substrate forms cost more and are produced less reliably, "text is a
projection" is a true statement about the runtime and a false one about
convenience, and the case for Stage 2/3 rests only on density.

## Method

Ten **closed** programs (no inputs, one known integer answer each),
expressible in the core operators plus the list and text families and
nothing from the prelude -- because the prelude is a Stage-1 text
construct: its names are integers in the substrate, and s2/tok have no
include mechanism, so operator-only is the only footing on which the
identical program exists in all three forms. `dry-run` confirms every
task round-trips and evaluates to its answer in all three.

Two measurements:

- **Cost axis (no model).** One canonical solution per task, rendered
  three ways, measured in LLM tokens (tiktoken cl100k_base), surface
  characters, and bytes. Form-intrinsic; nothing to do with what a
  model has seen.
- **Generation axis (Q47).** A fresh session is given one form's card
  -- the three cards differ only in how a call is written, the operator
  set is identical -- and writes the ten programs in that form.
  `submit` assembles the form back into a tree, compiles, runs, checks
  the answer. Pass@1 and the LLM-token cost of what was emitted are
  logged. Sessions run on Opus 4.8, the model the earlier legs used.

The confound is named, not hidden: a frontier model has read millions
of lines of Lisp-like text and zero of Stage-2 or raw LOVA bytes. The
cost axis is immune to it; the generation axis measures reliability
*given that exposure*, which is the situation any real use starts from.

## Results

### Cost axis (deterministic)

LLM tokens to write the ten programs:

| form | LLM tokens | surface chars | bytes |
|---|---|---|---|
| s1 (s-expression) | 192 | 448 | -- |
| s2 (Stage-2 surface) | 141 | 146 | -- |
| tok (decimal bytes) | 520 | -- | 265 |

- **s2 is 1.36x cheaper than s1** in LLM tokens on this dense
  operator-only code -- consistent with Exp 14's 1.13x on algorithmic
  tasks, and far below the 5.38x the number-theory built-ins gave,
  because here neither form has a built-in shortcut. The density win of
  the substrate projection is real but modest where the program is
  already dense.
- **tok is 2.71x more expensive than s1.** The substrate written as
  bytes for a model to emit is the costliest form, not the cheapest:
  cl100k tokenises `1 1 48` and two-digit byte values into many tokens,
  and the length-prefix arithmetic adds bytes. "The integer is the
  program" is a statement about identity and storage, not about what is
  cheap for a model to produce.
- One thing the build surfaced: the Stage-2 symbols for the list and
  text families are Greek capitals (Α, Β, …), non-ASCII single
  characters. They render as mojibake on a Windows console and can be
  mangled by any text pipeline that is not UTF-8 clean -- a hazard the
  ASCII s-expression does not have, and a cost of the dense projection
  that the token count does not show.

### Generation axis (Q47)

Ten task-instances per session; up to five attempts each.

| form | sessions | green | first-try | attempts | attempts/task |
|---|---|---|---|---|---|
| s1 (s-expression) | 2 | 20/20 | 20/20 | 20 | 1.00 |
| s2 (Stage-2 surface) | 2 | 20/20 | 17/20 | 25 | 1.25 |
| tok (raw bytes) | 1 | 10/10 | 6/10 | 20 | 2.00 |

Reliability degrades monotonically toward the substrate, and the green
column overstates it: both non-text forms passed only by working around
what the card did not carry.

- **s1 was frictionless.** Two sessions, twenty programs, every one
  correct on the first submission. Both named the same load-bearing
  thing: the worked `fold` example that fixed the curried
  two-argument shape and the (f acc x) order.
- **s2 was written, but around a hole.** One session synthesised the
  missing comparisons from integer division (less-than as b div (a+1),
  membership-of-7 as ((x+1) div 8) times (8 div (x+1))) and passed
  honestly at 1.1 attempts a task; the other hard-coded the three
  ordering tasks (max, min, membership) as literals because it found
  no comparison symbol, and those greens are hollow. One retry was a
  Windows-console artifact (a backslash eaten by the shell), not the
  language.
- **tok was feasible but slow and card-independent.** The one session
  reached 10/10 in twenty submissions (two of them deliberate probes),
  reverse-engineering the arities of fold, lambda, sort-by and any
  from the decoder's "trailing bytes" error, because the card gave
  byte values but not signatures. A misplaced END (byte 0) closed a
  node early and the stream still decoded into something plausible --
  a silent corruption. The integer length-prefixes, the part expected
  to be hardest, were error-free.

The cause of the degradation, both forms: the card was projected from
the s-expression's vocabulary, and the substrate does not share it.
sub, neg, eq, ne, lt, gt, le, ge and if are Stage-1 macros with no
byte; the card's operator list named them and the symbol/byte table
silently dropped all nine, so the model was promised comparison and
branching it had no way to spell. And the parentheses that make every
operator's arity self-evident in s1 are gone in s2/tok, so the arities
had to be recovered from error messages. Both are the ruling's point
made concrete: a card designed on the s-expression smuggles in exactly
what the substrate lacks.

## Findings

- **F1 (cost).** On dense operator-only code the Stage-2 surface saves
  a third of the LLM tokens against the s-expression, and the raw-byte
  form costs nearly three times as much. The density argument for the
  substrate is Stage-2's alone, and it is modest here; the pure-token
  form is the most expensive thing to emit, which is the opposite of
  what "programs are integers, not text" suggests about convenience.
- **F2 (reliability degrades toward the substrate).** First-try rate
  s1 100%, s2 85%, tok 60%; attempts a task 1.00, 1.25, 2.00. The
  s-expression is the surface a current model writes without friction;
  the byte stream costs it twice the attempts and a running probe of
  the error channel.
- **F3 (a card projected from the text does not carry to the
  substrate).** Nine comparison/branch macros have no byte and vanished
  from the substrate card while its prose still promised them; operator
  arities that parentheses give for free had to be reverse-engineered.
  The reason s2/tok are hard here is not depth of the notation but a
  card built on the s-expression -- rule 1 and rule 2 of the
  2026-09-11 ruling, demonstrated the first time they were tested.
- **F4 (the substrate is poorer than the text, not just denser).**
  There is no subtraction, comparison, equality or if as an operator;
  they are text macros. A program in s2/tok must desugar them by hand
  into arithmetic (comparison as integer division), which two of three
  non-text sessions did and one faked. Density is not the whole gap
  between the surfaces; vocabulary is.

## Discussion

For a model as it exists now the answer is one-sided: the s-expression
is the surface it authors reliably, the Stage-2 surface it can write
around a card gap for a third fewer tokens, and the raw byte stream is
both the most expensive form to emit (2.71x s1) and the least reliable
(twice the attempts, dependent on the error channel to learn the
grammar). Nothing measured supports authoring in raw tokens. Axiom 1's
"programs are integers, not text" is a claim about identity and storage
that holds; it is not a claim about the authoring surface, and this run
is the first evidence that the authoring surface a current model wants
is the text.

But the run cannot settle whether the text layer is removable, because
the s2/tok cards were defective in the exact way the ruling predicts:
projected from the s-expression, they carried its macros (which the
substrate lacks) and omitted its arities (which its parentheses supply
for free). The honest reading is that this experiment tested the card
as much as the form, and found that a card made on the text does not
transfer. A fair test of the substrate forms needs a card built from
the substrate's own operators -- comparison and branch given their real
byte spelling, every operator's arity stated -- which is Q101. Until
that runs, "the text layer stays" is supported for a current model and
"the text layer is removable" is untested.

The deeper thing the run exposed: the gap between the text and the
substrate is not only density (Stage-2 is a modest 1.36x on dense
code) but vocabulary -- the substrate has no subtraction, comparison,
equality or if, only their macro expansions. That is a design choice
worth revisiting on its own terms (Q102): if the substrate is what an
AI is meant to author one day, the operators an author needs every
line -- compare and branch -- arguably belong in the 64, not in a text
macro layer that cannot be projected.

## Next questions raised

- **Q101** -- the substrate-native card: rebuild the s2 and tok cards
  from the 86 operators (comparison and if in their real byte spelling,
  every arity stated), and re-run the generation axis, so the s2/tok
  reliability number is the form's and not the card's.
- **Q102** -- should comparison and if be operators rather than text
  macros? They are the vocabulary an author needs every line, and the
  one thing that did not project to the substrate. Costed against the
  slot budget.
- **Q103** -- the repair axis of the three forms: a planted fault in
  each, the cost to locate and fix, now that the emit axis is measured.

## Status

**PARTIAL.** Cost axis: Stage-2 saves a third of the LLM tokens on
dense code, the raw-byte form costs 2.71x, the Stage-2 symbols are
non-ASCII. Generation axis (Opus 4.8): first-try 100% / 85% / 60% for
s1 / s2 / tok, attempts a task 1.00 / 1.25 / 2.00 -- reliability
degrades toward the substrate. The cause is the ruling's own point:
the s2/tok cards were projected from the s-expression, carried its
comparison/if macros (which the substrate cannot spell) and omitted
its arities (which parentheses supply). For a current model the
s-expression is the authoring surface; whether the substrate forms are
writable from a substrate-native card is Q101; whether compare and
branch should be operators is Q102.
