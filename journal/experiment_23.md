# Experiment 23 -- Does the substrate form hold at program size? (Q104)

**Date:** 2026-09-11
**Script:** `experiments/experiment_23_scale.py` (Exp 22's cards and scoring)
**Status:** Done, five sessions on Opus (s1 x2, s2 x2, tok x1). **PARTIAL.**

## Hypothesis

Q101 found that once the substrate cards were rebuilt from the
substrate's own operators, the three forms of a LOVA program did not
separate on reliability: s1, s2 and tok were all written first-try on
ten closed one-line tasks, and they separated only on cost. Both
Stage-2 sessions then named what that size had hidden. A reference in
s2/tok is by the NAME's number, tracked across the whole program, and
adjacent literals need a separating space. Both failures are silent:
they yield a wrong VALUE, not a parse error. On a one-line program
there is nothing to track. Q104 asks what happens when there is.

## Method

Six tasks under Exp 22's rules -- closed, operator-only, no prelude,
one known answer -- but 2x to 5x the size, each needing recursion
through a `let`-bound self-referencing lambda, the last carrying eight
distinct names at once (`b01` Collatz from 27, `b02` naive Fibonacci,
`b03` primes below 50, `b04` a digit sum, `b05` primes composed with a
fold, `b06` the longest run of equal characters). The cards are Exp
22's, unchanged apart from the task list, so the only variable is
program size. Five fresh Opus sessions: two s1, two s2, one tok, each
told to solve honestly rather than hard-code, and asked directly
whether the bookkeeping bit and whether any mistake produced a wrong
value rather than an error.

## Results

### The numbers

| form | sessions | green | first-try | attempts | emitted LLM tokens / task |
|---|---|---|---|---|---|
| s1 | 2 | 12/12 | 12/12 | 12 | 66 |
| s2 | 2 | 12/12 | 12/12 | 12 | 33 |
| tok | 1 | 6/6 | 6/6 | 6 | 169 |

**Every session, every task, first attempt.** No parse, compile or run
failure anywhere, and no wrong value ever reached a submission. The
predicted silent-corruption failure did not occur.

Cost separated further with size. The deterministic cost axis over the
canonical solutions: s2 is 1.68x cheaper than s1 here against 1.36x on
the one-line tasks; what the sessions actually emitted makes it 2.0x
(33 against 66 tokens a task). The raw byte form is 2.6x s1. The
Stage-2 density advantage grows as programs grow.

### What the sessions actually did, which the numbers hide

**Neither Stage-2 session composed in Stage-2.** Both built the tree
first -- as a parenthesised s-expression or an explicit binding plan --
and then flattened it. In one session's words: "the stream was a
serialisation step, not an authoring step ... I would expect a much
worse number from anyone emitting the stream left-to-right without the
tree in hand -- the form gives you no place to stand: there is no
closing bracket to tell you an argument list is done." Both wrote the
name-to-letter table down before emitting a character, and both said
the `2->r, 3->v, 4->w` stretch is where they would expect a slip if
working linearly, because the letters carry no mnemonic relation to the
number they stand for.

**The characteristic error is silent, and all three substrate sessions
said so independently.** A swapped reference stays well-typed: in b06,
`$A_Lr+v1w;` and `$A_Lr+w1v;` both parse, compile and run, differing
only in the answer. Nothing in the form reports it. As one session put
it, the type-constrained substrate "does not cover the mistake the form
makes most likely". The same holds for name-id shadowing in the byte
form. No session actually made the mistake -- but none of them wrote
linearly either.

**The byte form's own verdict is the opposite of the expected one.**
The tok session found the encoding "the easy part": prefix notation
with a published arity table has no bracket matching, no whitespace and
no precedence, every node is locally decidable, and a missing END is a
parse error rather than a silent misparse, because fixed arities let
the parser re-synchronise structurally. It assembled a 165-byte program
in one pass with no backtracking, and put the cost at 1.5-2x the
authoring effort of equivalent Python -- all of it front-loaded into
currying every multi-parameter function by hand and expanding
subtraction and comparison, none of it into the bytes. Its estimate of
where cost lives: "proportional to the number of distinct binders,
because that is the only non-local state", not to byte count.

**A card defect distorted one program, again.** The Stage-2 card
printed only six reference letters, so one session believed names above
5 were unavailable, and rather than spend an attempt finding out it
inlined a six-character sub-expression three times in b06 -- which is
the whole reason its b06 cost 65 tokens against 25-30 for everything
else. The form has ten (`A L r v w x y < | .`); the card was the limit.
Fixed in this commit. This is the third time an Exp-22-family result
turned out to be the card rather than the form.

**Card gaps every session named.** `let` and `apply` are not in the
card's operator table at all -- all four s1/s2 sessions pointed this
out, and every task here needs recursion, so a session given only the
card could not have written b01, b02, b04 or b06. The recursion recipe
reached them through the harness prompt instead, given identically to
all five sessions, so the comparison is fair but the card is not
self-sufficient. The tok card still has no text-literal encoding, so
b06's input was built as a ten-cell cons list (41 of its 165 bytes).
The Greek symbols are invisible on a non-UTF-8 console.

## Findings

- **F1. All three forms are written first-try at 2x-5x the size.** The
  scaling failure Q101 predicted did not appear: 30 of 30 task
  instances green on the first submission, no wrong values.
- **F2. Stage-2's cost advantage grows with program size** -- 1.36x
  cheaper than the s-expression on one-liners, 1.68x on the canonical
  solutions here, 2.0x on what the sessions actually wrote.
- **F3. The substrate forms are output formats, not thinking formats.**
  Neither Stage-2 session authored in Stage-2; both built a tree and
  serialised it, with an external binding table. The s-expression (or
  an equivalent tree) remained the medium of composition even when the
  artifact was the stream. The first-try rate measures a two-phase
  process, and the sessions say a one-phase one would be worse.
- **F4. The error the form invites is the one the type system cannot
  catch.** A swapped or shadowed reference is well-typed and yields a
  wrong value silently. Axiom 3's guarantee is structural, and
  reference bookkeeping sits outside it.
- **F5. The byte encoding is not the hard part.** Prefix plus fixed
  arity re-synchronises structurally and is cheap to emit; the cost is
  the substrate's missing vocabulary (hand-currying, expanded
  comparison) and the number of live binders, not the bytes.
- **F6. The card, not the form, has been the confound three times
  running** (Exp 22's dropped macros, its missing arities, and now the
  six-letter reference table). A measurement of a representation is a
  measurement of its documentation until proven otherwise.

## Discussion

Q104 asked whether Stage-2 survives program size and the answer is yes,
with a qualification that matters more than the result. It survives
because the model does not actually write it: it writes a tree and
serialises. That reframes the Stage-2/Stage-3 thesis. As a *storage and
transport* form the substrate is vindicated here -- cheaper than the
text, growing cheaper with size, and reliably producible. As an
*authoring* form it is untested, because no session in this experiment
authored in it, and both said linear authoring is where the silent
failure would land.

That suggests the honest architecture is the one the project already
half has: a tree the model composes in, projected to the substrate for
storage, transport and identity. What it does not support is the Stage-3
picture of a model thinking directly in integers. Nothing here shows a
model doing that, and the two sessions closest to trying said the form
gives them "no place to stand".

The silent-error finding is the one to carry forward. LOVA's pitch is
that a fault is structured data rather than a stack trace, and Axiom 3
says ill-typed programs are unrepresentable. Both hold. But the mistake
the substrate form most invites -- a reference to the wrong binder -- is
well-typed by construction, so it lands as a wrong answer with no
diagnostic at all. That is a gap in the error model exactly where the
substrate is supposed to be strongest, and it grows with the number of
live names.

## Next questions raised

- **Q105** -- linear authoring: can a model emit Stage-2 left-to-right
  without composing a tree first, and what does that cost? Both
  sessions here declined to, and their reliability number is the
  two-phase process's. This is the experiment that would actually test
  the substrate as an authoring surface.
- **Q106** -- a diagnostic for the silent reference error: can the
  compiler warn when a reference's binder is plausibly wrong (a shadow,
  an out-of-scope number, a name bound but never used) so the one
  mistake the form invites stops being invisible?
- **Q107** -- the card is not self-sufficient: `let` and `apply` are
  absent from the operator table, the tok card has no text literal.
  Regenerate all three cards from the token table itself so nothing an
  operator needs is missing, and re-run.

## Status

**PARTIAL.** At 2x-5x the size, all three forms were written first-try
by every session (30/30), with no wrong values, and Stage-2's cost
advantage grew to 2.0x the s-expression on what was actually emitted.
But neither Stage-2 session authored in Stage-2 -- both composed a tree
and serialised it with an external binding table -- so the substrate is
demonstrated as a storage and transport form, not as an authoring one
(Q105). The error the form invites, a reference to the wrong binder, is
well-typed and therefore silent (Q106). A card defect distorted one
program for the third time in this family (Q107).
