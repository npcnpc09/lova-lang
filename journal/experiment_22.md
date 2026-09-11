# Experiment 22 -- The three-form experiment: which form does the model emit? (Q100)

**Date:** 2026-09-11
**Script:** `experiments/experiment_22_three_forms.py`
**Status:** Done. Exp-22 run (five sessions) + Q101 re-run (three sessions), Opus 4.8. **PARTIAL.**

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

### Generation axis, re-run with a substrate-native card (Q101)

The two substrate cards were rebuilt from the substrate's own
operators: comparison and branch given their real spelling --
deviation (signed compare), threshold (positive-test), if-surprise
(branch) -- with the recipe for lt/gt/eq/sub/neg from them; every
operator's arity stated; the Stage-2 reference scheme corrected
(declare a parameter as backslash-N, refer to it by a letter
A/L/r/...). The s-expression card was left alone. Three fresh Opus
sessions, same ten tasks, told to solve honestly (no literals):

| form | card | first-try | attempts | emitted LLM tokens/session |
|---|---|---|---|---|
| s2 | Exp-22 (projected) | 17/20 | 25 | -- (contaminated) |
| s2 | Q101 (substrate) | 20/20 | 20 | ~145 |
| tok | Exp-22 (projected) | 6/10 | 20 | -- |
| tok | Q101 (substrate) | 10/10 | 10 | 528 |

The whole Exp-22 degradation was the card. With a substrate-native
card, both s2 sessions and the tok session wrote all ten tasks
first-try, every one an honest computation -- max and min as a fold of
if-surprise(threshold(deviation ...)) ..., equality and membership from
deviation, evenness from mod -- no hard-coded literals. The raw byte
form, which in Exp 22 needed twenty submissions and a running probe of
the decode error, was first-try once the card stated the arities and
the compare/branch recipe; a multi-byte length prefix (100000 =
1 3 1 134 160) was laid down correctly by hand.

Emitted cost tracked the deterministic cost axis: s2 ~145 tokens a
session (against the canonical 141), tok 528 (against 520), s1 ~190. So
at this size, given a fair card, the three forms do NOT separate on
reliability -- they separate on cost, and Stage-2 dominates the
s-expression (same first-try success, a quarter fewer tokens) while the
raw byte form is reliable but 2.7x the s-expression.

What the sessions still flagged, none of it blocking here but all of it
scaling with program size:
- Global lambda numbering. A reference is by the parameter's number
  across the whole program, not per lambda, so in c01 the map lambda
  was number 2 because the fold already used 0 and 1. Correct, and
  inferred from one nested example; on a program with many lambdas the
  writer must track a global counter, and a wrong number is a silent
  value error, not a parse error.
- Digit-run spacing. range 0 20 must have the space; without it the two
  digits parse as one different literal and fail silently. The rule is
  load-bearing and appears in many places.
- No text-literal byte in the tok card. The token form lists the text
  operators but gives no way to write "foo" as bytes, so c07 was done
  by building the string with int-text. A real gap in the tok card
  (the tok form does have a text literal; the card just did not teach
  its byte layout).
- The Stage-2 & (ref) operator in the table reads as if references need
  a & prefix; they do not (a bare letter is the reference). And the
  non-ASCII Greek symbols must be copied exactly, which a non-UTF-8
  console mangles.

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
- **F5 (Q101: with a substrate-native card the forms tie on
  reliability and separate on cost).** Rebuilt cards -- compare/branch
  in their real spelling, arities stated -- took s2 from 17/20 to 20/20
  first-try and tok from 6/10 to 10/10 first-try, all honest. At this
  size the three forms are equally writable; what separates them is the
  emitted token count (s2 ~145, s1 ~190, tok 528), so Stage-2 dominates
  the s-expression. The Exp-22 reliability gap (F2) was the card, not
  the form.

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

The Exp-22 run tested the card as much as the form; Q101 fixed the
card and the picture changed. With a substrate-native card the two
substrate forms were written first-try, honestly, as reliably as the
s-expression -- so at this size reliability does not favour the text,
and the case for the text layer as the AUTHORING surface is only
zero-shot familiarity, which a fine-tune or a fair card removes.
Stage-2 is then strictly better than the s-expression here: same
first-try success, a quarter fewer tokens. The raw byte form is
writable too but costs 2.7x, so nothing recommends it as an authoring
surface even though a model can produce it by hand.

What Q101 did NOT settle is scale. Both s2 sessions named two
silent-corruption risks -- a reference is by a global lambda number
(track a counter across the whole program) and adjacent literals need a
separating space -- that did not bite on ten tiny closed programs but
grow with size and fail as a wrong value, not a parse error. Whether
s2 stays as reliable as the s-expression on a tictactoe-sized program
is Q104. So: for small programs the text layer is not required for
authoring; for large ones it is untested, and the substrate's
silent-corruption failure modes are the thing to watch.

The deeper thing the run exposed: the gap between the text and the
substrate is not only density (Stage-2 is a modest 1.36x on dense
code) but vocabulary -- the substrate has no subtraction, comparison,
equality or if, only their macro expansions. That is a design choice
worth revisiting on its own terms (Q102): if the substrate is what an
AI is meant to author one day, the operators an author needs every
line -- compare and branch -- arguably belong in the 64, not in a text
macro layer that cannot be projected.

## Next questions raised

- ~~**Q101**~~ -- *answered, 2026-09-11.* A substrate-native card took
  s2 to 20/20 and tok to 10/10 first-try, all honest: the Exp-22 gap
  was the card. At this size the forms tie on reliability; Stage-2
  dominates the s-expression on cost.
- **Q104** -- does Stage-2 stay as reliable as the s-expression on a
  program the size of `tictactoe.lova`, where the global lambda
  numbering and the digit-run spacing (both silent-corruption risks)
  actually bite? The scaling test the ten closed tasks could not run.
- **Q102** -- should comparison and if be operators rather than text
  macros? They are the vocabulary an author needs every line, and the
  one thing that did not project to the substrate. Costed against the
  slot budget.
- **Q103** -- the repair axis of the three forms: a planted fault in
  each, the cost to locate and fix, now that the emit axis is measured.

## Status

**PARTIAL.** Cost axis: Stage-2 saves a third of the LLM tokens on
dense code, the raw-byte form costs 2.71x. Exp-22 generation axis put
first-try at 100% / 85% / 60% for s1 / s2 / tok -- but Q101 showed that
gap was the card: rebuilt from the substrate's own operators (real
compare/branch, arities, corrected references), the substrate forms
went 20/20 (s2) and 10/10 (tok) first-try, all honest. So at this size
the three forms tie on reliability and separate on cost, with Stage-2
dominating the s-expression. The text layer is not required to AUTHOR
small closed programs; its remaining case is zero-shot familiarity and
the untested scaling risks (global lambda numbering, silent spacing) --
Q104. Whether compare and branch should be operators, not text macros,
is Q102; the repair axis is Q103.
