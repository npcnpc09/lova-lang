# Experiment 24 -- Linear authoring: emitting the substrate left to right (Q105)

**Date:** 2026-09-11
**Script:** `experiments/experiment_24_linear.py`
**Status:** Done, four sessions on Opus (frontier x2, blind x2); **run 2, 2026-09-18, four more on the pending stack (Q108).** **WIN for the measurement, NULL for the claim, twice.**

## Hypothesis

Experiment 23 found the three forms of a LOVA program equally reliable
at size, and then found out why: **neither Stage-2 session composed in
Stage-2.** Both built a parenthesised tree and flattened it, keeping an
external name-to-letter table. "The stream was a serialisation step,
not an authoring step ... the form gives you no place to stand: there
is no closing bracket to tell you an argument list is done." So the
substrate was demonstrated as a storage and transport form and left
untested as an authoring one.

Q105 tests it as an authoring one. If a model can compose a program
directly in the substrate -- deciding each token as it emits it -- then
Stage 3's picture of an AI thinking in integers is reachable. If it
cannot, the substrate is a serialisation format and the tree is the
medium of thought, whatever the artifact looks like.

## Method

A session emits the program **left to right into LOVA's own generation
state machine** (`core.generator.GenState`, Axiom 3). Every token is
checked against the well-typed successors as it arrives; an ill-typed
or out-of-scope token is refused and nothing after it is applied; the
stream finishes only when no argument slot is open. There is no program
text to revise -- what is accepted stays, and the only escape from a
corner is to restart the task.

Tokens are written by NAME (`merge`, `fold`, `if-surprise`) rather than
by the Stage-2 symbol, deliberately: Exp 22 already priced the dense
symbols, and this experiment is about the substrate's *structure* --
prefix order, positional arguments, no delimiters -- not about
recalling Greek letters.

Four graded tasks: `c01` (a fold over a range), `c04` (a fold with a
comparison), `b04` (recursion, one binding), `b01` (Collatz: recursion,
two bindings, a nested conditional inside a call). Canonical solutions
are 22 to 39 tokens.

Two arms price the machine's help:

- **frontier** -- after every emission the harness reports how many
  slots are open and what may come next.
- **blind** -- the harness accepts or refuses and says nothing else.

Every session was told plainly that a candid "I built the tree in my
head" was the finding, not a failure.

## Results

### The numbers

| arm | sessions | tasks | pass | refusals | restarts | tokens (c01/c04/b04/b01) |
|---|---|---|---|---|---|---|
| frontier | 2 | 8 | 8/8 | 0 | 0 | 17 / 28 / 26 / 36 |
| blind | 2 | 8 | 8/8 | 0 | 0 | 17 / 28 / 26 / 36 |

**16 of 16 passed, with not one refused token and not one restart.**
Every session wrote exactly as many tokens as it emitted -- no waste.
All four sessions, in both arms, produced programs of *identical*
length on every task, and all four were shorter than the canonical
solutions (17 against 22 on c01). The frontier made no measurable
difference to anything.

### What the sessions said, unanimously

**All four held the tree.** Asked directly, every session answered that
it composed the complete nested expression first and then read it out
in prefix order. In their own words: "the linearisation was a
mechanical transcription step, not an act of composition"; "the
emission was a *traversal* of a finished structure"; "my chunk
boundaries are subtree boundaries, not 'as far as I had thought'".

One named the giveaway: "**The tell is the refusal count.** Zero
refusals across 107 tokens is not what genuine left-to-right authorship
looks like; it is what reading out a finished plan looks like. I never
once discovered at token k that I wanted something different at token
k-3, because I had already resolved all of that before token 1."
Another called its own chunking "theatre in retrospect".

**None of them wanted to write the tree down in order to find the
program -- they wanted to in order to check it.** Two sessions asked
for paper at exactly the same two moments: choosing between two whole
designs for `b04`, and verifying that the `;` and the nested
conditionals in `b01` closed every slot exactly once. One drew the
distinction sharply: "The desire was for *verification*, not for
authorship ... the tree was cheap to form, and expensive to audit
without a written form."

**The honest reading of a perfect score**, from the session that
volunteered it: "these programs are small enough to hold entirely in
working memory, and when you can do that, linear emission is a lossless
serialisation of something you already finished."

**And the reason they all did it**, which one session traced to the
rule itself: "Knowing that a wrong token is permanent made me want more
certainty before the first token, not less. A language that lets you
revise invites you to start emitting and fix it; this harness punishes
that, so the rational response is to finish thinking first. **Linear
emission did not produce linear composition -- it produced *more*
up-front composition.**" The irreversibility meant to force incremental
authoring forced its opposite.

### What the frontier actually bought

Nothing measurable, and the sessions agree on why. At a `Value` slot 79
of 86 tokens qualify, and the harness says so; the aided sessions
reported those lines as "honest of it, and useless". It narrowed
exactly once per program, at a **function-typed** slot, where it fell
to twelve tokens -- and there it was genuinely valuable: it confirmed
`lambda` was the move and, by the absence of the arithmetic operators
from the list, enforced the card's "an operator is not a value" rule
without the session having to trust its memory.

Both aided sessions ranked the **open-slot count** above the token
list: it is the running arity debt, used "as a checksum after every
chunk". The blind sessions rebuilt the same quantity by re-scanning the
echoed stream, and one noted that this only works at this size: "at 300
tokens it would be the dominant cost."

### Where the linear form actually hurt

Three costs, named independently by at least two sessions each, and
**none of them is a thing the type checker checks**:

1. **`apply`'s `;` is bracket-matching with the brackets removed.**
   Every other operator self-terminates by arity; the one variadic does
   not, so the writer alone decides when a call is finished. Both blind
   sessions called it the sharpest edge, and one aided session said it
   was the single thing it wanted written down.
2. **Irreversibility buys worse programs.** One session seeded a
   maximum-fold with `0` -- correct for the data, wrong in general --
   and said why: doing it properly means naming the list, which means a
   `let`, which means restructuring a layer already emitted, and "once
   you are emitting left-to-right, 'restructure the outer layer' is not
   available". It paid the cost as correctness debt rather than a
   failure. That is the medium shaping the program, not the programmer.
3. **The protection is orthogonal to the risk.** "Type-constrained
   generation protects you from ill-typed tokens; it does nothing about
   a semantic guess." A wrong-but-well-typed choice -- the wrong one of
   two in-scope `Int` bindings, a mis-guessed exclusive bound -- is
   accepted silently and surfaces only at `finish`, where the sole
   remedy is a full restart. Linear emission makes that failure
   maximally expensive.
4. **Token order runs backwards from reasoning order.** A fold's seed
   is decided while designing the lambda that consumes it, and emitted
   sixteen tokens after it. One session called carrying "the seed is 4"
   across the whole lambda body "the single fiddliest moment of the
   session" -- in `c04` the seed and the first list element are the same
   number for different reasons. The same happens to an `if-surprise`
   else-branch, emitted eighteen tokens after its condition "with no
   local cue".

Binding numbers were comfortable here and every session said the same
thing about why: no task had more than three live bindings, introduced
in strictly nested order, so `ref 0 / 1 / 2` coincided with
outermost/middle/innermost. All four flagged it as the next thing to
break: "a program with two sibling lambdas that both reach for an
enclosing binding would have broken this heuristic immediately, and I
would have had no way to notice except a refusal -- and only if the
shadowed reference happened to be ill-typed; if both were `Int` the
machine would have accepted my mistake silently." And one drew the
conclusion the substrate has been avoiding: at five or six live bindings it would need a scratch note,
"and the thing I'd write in it would be a binding table, which is
exactly the information a name carries for free."

## Findings

- **F1. The substrate is emittable and nobody authored in it.** 16/16,
  zero refusals, zero restarts, in both arms -- and all four sessions
  independently reported composing the tree first and transcribing it.
  Q105's question is answered in the negative for a current model: the
  tree is the medium of thought, the stream is the artifact.
- **F2. A perfect score is evidence of the task size, not the form.**
  Zero refusals over 107 tokens is the signature of transcription. The
  sessions said so before being asked to interpret their own results.
- **F3. Axiom 3 as an authoring interface is inert where authoring is
  hard.** The frontier changed no outcome, no token count and no
  refusal rate between arms. It narrowed usefully at exactly one slot
  kind per program (function-typed), and was honest noise elsewhere.
  What it checks -- types and scope -- is disjoint from what cost the
  sessions effort: variadic termination, arity debt, and semantic
  choice.
- **F4. The open-slot count is the field that carries the value.**
  Both aided sessions preferred it to the valid-token list, both blind
  sessions reconstructed it by hand, and one predicted that
  reconstruction becomes the dominant cost at scale. A rendering of the
  *pending stack* -- how many slots, and which operator each belongs to
  -- is what all four asked for and none had.
- **F5. Irreversible emission degrades the program, measurably.** A
  session knowingly shipped a fold seeded with a wrong-in-general
  constant because the correct version required restructuring an
  already-emitted layer. Left-to-right authoring has no edit, so it
  trades correctness for order.
- **F6. The one error the form invites is the one nothing catches**
  -- a well-typed wrong reference or a wrong semantic guess -- and
  linear emission makes its remedy a full restart. This is Q106 from
  the other side, confirmed by three sessions independently.
- **F7. Irreversibility causes the tree-holding it was meant to
  prevent.** Because a wrong token is permanent and the only remedy is
  a restart, the rational strategy is to finish composing before
  emitting anything. The no-revision rule produced *more* up-front
  tree-building, not less -- so an interface that forbids editing
  cannot, by construction, elicit incremental authoring.

## Discussion

Four sessions wrote sixteen programs into the substrate without a
single refused token, and every one of them says the result does not
mean what the number suggests. That agreement is the experiment's
value. The substrate is a perfectly good thing to *emit*: prefix order
with published arities is mechanical, the state machine never had to
refuse anyone, and the programs came out shorter than the references.
What did not happen, in any session, in either arm, is composition.

This settles the Stage-3 question as far as a current model can settle
it. "An AI thinks in integers" is not what these sessions did; they
thought in trees and spoke in integers. The architecture that follows
is the one the project already half has -- a tree the model composes
in, projected to the substrate for storage, transport and identity --
and the honest name for Stage 2 and Stage 3 is *serialisation*, not
*authoring*. Nothing here forbids a model trained on the byte stream
from behaving differently; nothing here is evidence that one would.

The more useful finding is about Axiom 3. Type-constrained generation
is the project's oldest and most-validated claim (Exp 02: 100% vs 0%
well-formed), and this is the first time a *model* rather than a
sampler has been put behind it. For a sampler the constraint is
everything, because a sampler picks uniformly. For a model the
constraint is nearly always slack -- it already knows `merge` takes
two integers -- and it binds only where the model's own priors are
weakest, which turned out to be the function-typed slot where an
operator might be mistaken for a value. That is a real and narrow win,
and it is worth keeping for exactly that reason. But the guarantee does
not touch the three things that actually cost these sessions effort,
and one session put the asymmetry better than I can: the checker guards
types and scope; the cost was variadic termination and the unaided
naming of bindings.

There is also a trap in the experiment's own design worth recording,
because it generalises to any "AI writes the substrate directly"
interface. Forbidding revision was meant to force incremental
authoring; it did the opposite, because when a mistake is permanent the
rational move is to finish thinking first. An interface that wants
incremental composition has to make small corrections cheap, not
impossible -- which argues for an editable tree with a projection, and
against a write-once stream, on exactly the grounds the project cares
about.

So the design consequence is not "drop Axiom 3". It is that a
type-constrained interface should stop reporting the alphabet and start
reporting the **stack**: slots open, which operator owns each, and
whether the variadic in front of you may be closed here. Every session
asked for that, in those words, and it is cheap -- the state machine
already holds it.

## Next questions raised

- **Q108** -- render the pending stack, not the alphabet: replace the
  frontier line with "slots open, and which operator owns each, and
  whether `;` is legal here", and re-run this experiment. It is the
  one thing all four sessions asked for, and the state machine already
  has it.

  **Half done, 2026-09-15.** The rendering exists: `open_forms`,
  `pending` and `render_pending` in `core/generator.py`, returned by
  `lova_valid_next` and available to this harness as a third arm,
  `--frontier stack`. Building it turned up one thing worth recording:
  the slots of two forms of the *same* operator sit next to each other
  on the stack and cannot be told apart by `parent_op` alone, so a slot
  now carries the depth its form was opened at -- without which
  `(merge (merge ...) ...)` would have been reported as one form owing
  three. `tests/test_pending.py` (19) holds that case and the variadic
  ones. What is *not* done is the half that matters: the re-run needs
  four fresh sessions, as the first run had.
- **Q111** -- allow one retraction: let a session un-emit the last
  token (or the last subtree) and see whether incremental composition
  appears when a mistake stops being fatal. F7 says the write-once rule
  is what forced the tree-holding, so this is the control that would
  test it.
- **Q109** -- the size where transcription breaks: these programs fit
  in working memory, which is why nobody needed to compose forward. At
  what token count does a session start discovering at token k that it
  wanted something else at token k-3? That is where linear authoring
  is really tested, and `b06` (169 bytes) is the obvious next rung.
- **Q110** -- a model trained on the stream: every finding here is
  about a model that has read millions of trees and no LOVA bytes.
  The fine-tune corpus exists (`corpus/finetune`); does a model taught
  the substrate compose in it, or transcribe faster?

## Run 2 (2026-09-18) -- Q108, the pending stack in place of the alphabet

Four fresh sessions (S1-S4, Opus, the same four tasks in the same
order, the same card), with the third arm: after every emission the
harness prints the pending stack -- which forms are open, which
operator owns each, what each still owes, and whether `;` may close
the variadic in front of you -- and never the alphabet. Each session
was asked the same four questions afterwards, with the same
assurance that "I composed the tree first" is a finding.

### The numbers

| arm | sessions | tasks | pass | refusals | restarts | tokens (c01/c04/b04/b01) |
|---|---|---|---|---|---|---|
| stack | 4 | 16 | 16/16 | 0 | 0 | 17 / 28 / 26-28 / 36-42 |

Sixteen of sixteen, not one refused token, not one restart, every
token written a token kept (107 written and 107 kept in three
sessions, 115 and 115 in the fourth). Three of the four sessions
produced programs identical to each other on every task; the fourth
took the text route on b04 (28 tokens against 26) and carried a
counter as a second parameter on b01 (42 against 36). Nothing in the
table differs from run 1 except that the b04 and b01 programs are
shorter than run 1's 26 / 36 in three sessions, which is the card's
`let`-recursion recipe being reused.

### What the sessions said, again unanimously

**All four held the tree.** "Up front, completely, on all four";
"what I composed up front was a *tree*, not a *stream* ... the prefix
stream is not how I think about the program; it is an output format I
convert to"; "emitting was transcription of a pre-order walk of that
tree, and my chunks were exactly the subtrees I had already named to
myself". One session had composed all four programs before emitting
the first token of the first. Three of the four volunteered the same
tell as run 1: "zero refusals across 107 tokens is not what
exploration looks like, it is what reading out a finished plan looks
like".

**The stack changed nothing.** All four read it after every emission
and all four say it altered zero tokens. What it was: "a checksum",
"a receipt, not input", "accurate, legible, and not load-bearing for
a program I had already finished composing". The one figure they
would keep is `debt`, the count of open slots, "the only cheap check
that the tree I am transcribing is the size I think it is"; the one
line that ever confirmed a belief rather than echoed it was
`` `;` closes it here `` on b01. One session's estimate of when it
would matter: "a memory aid for a writer who has run out of memory,
and on 17-42 token programs I had not".

**The no-revision rule did what it did in run 1, and one thing more.**
All four: more composition up front, earlier, none of it in the
stream. Two of the four add that it made them compose *smaller and
duller* -- the arithmetic b04 over the text b04, the integer seed over
a head/tail seed -- "to avoid a restart on an unknown", so the
irreversible interface selects against the program the session
thought was better.

**What they wanted, in the same three words each.** Not one asked for
the valid-token set and not one asked for more of the stack. All four
asked for:

1. *The tree back.* The accepted prefix re-printed as the s-expression
   it already determines, with a hole at the frontier: "the machine has
   that tree; it is showing me the serialisation instead". The stream
   line "becomes unreadable by ~25 tokens".
2. *The binding table.* What `ref 0` and `ref 1` denote at the open
   form, and by which construct they were bound. Every session carried
   this in its head as an external table and named it as the one
   mistake it feared: a swapped reference is well-typed and silently
   wrong, "two of my four programs are one token away from that
   failure and the machine would have applauded either". This is Q106
   again, and Q89 (a scope the runtime can list) from the other side.
3. *A dry run on a subtree.* "Evaluate this partial subtree on this
   input" before committing; the only oracle for a semantic bet
   (`text-slice` half-open or not, the operand order of `deviation`)
   was `finish`.

And, from every session, the same account of where the cost went: not
the missing parentheses ("easy to *write*, genuinely hard to *read
back*"), but the missing vocabulary -- a comparison is three or four
tokens, subtraction is `merge a (mul -1 b)`, a five-element list is
eleven tokens of `cons` -- and every such encoding "is a place where a
mistake is well-typed and therefore silent".

### Findings of run 2

**F8. Q108 is answered: no.** The pending stack, offered to four fresh
sessions in place of the alphabet, changed no token, no chunk and no
account. The frontier was not the problem; the interface's premise
was.

**F9. The finding of run 1 is now eight sessions wide.** Eight of
eight, across three arms, composed a tree and transcribed it, and
eight of eight say so unprompted in the same terms. For a current
model the substrate is a serialisation format. Nothing short of Q110
(a model trained on the stream) can reopen this, and Q109 (the size at
which transcription breaks) would measure a failure of memory, not the
appearance of linear composition.

**F10. The three things every session asked for are the tree, its
scope and its value** -- the s-expression with a hole, the binding
table, and a scratch evaluation. Those are the working surface of the
*text* loop: `explain`, the scope listing of Q89, and `lova_execute`
on a fragment. The substrate-authoring line of experiments has, in
answering its own question, pointed back at the surface the project
already authors in.

**F11. The irreversible interface selects against the better program.**
New in run 2: two sessions chose the duller design on b04 because a
wrong bet on an operator's semantics would cost a restart. An
authoring interface that punishes probing gets conservative programs,
not incremental ones.

### Next questions raised by run 2

- ~~**Q108**~~: answered, no. Closed.
- **Q112**: the tree echo -- render the accepted prefix as an
  s-expression with a hole, plus the binders in scope at the hole, in
  `render_pending`. Cheap, asked for by 4 of 4, and the measurement
  that would justify it is a run at Q109's size, where the sessions say
  they would run out of memory. Not built until that run is wanted.
- **Q113**: the semantic bet -- a session's only oracle for an
  operator's exact semantics (`text-slice` half-open, `mod` on a
  negative, `sort-by` strict) is running the program. One worked
  example per operator on the card, and a scratch evaluation of a
  fragment in the loop harness, would remove the one uncertainty every
  session named. This is the card's number-1 lever from Exp 18 again,
  and it applies to the text loop as much as to the substrate.

## Status

**WIN for the measurement, NULL for the claim.** Sixteen of sixteen
programs emitted into the substrate with zero refused tokens and zero
restarts, in both arms -- and all four sessions independently reported
that they composed a tree first and transcribed it, one identifying the
zero-refusal count as the proof. The substrate is emittable, not
authorable, by a current model; Stage 2 and Stage 3 are serialisation,
not thinking. Axiom 3's constraint was inert except at function-typed
slots, and disjoint from the three real costs (variadic `;`, arity
debt, semantic guesses). What every session wanted instead of the valid
-token list was a rendering of the pending stack, which the state
machine already holds: Q108. **Run 2 (2026-09-18) offered it to four
fresh sessions: 16/16, zero refusals, zero restarts, and all four
composed the tree first and say the stack changed no token. Eight of
eight sessions over three arms; the substrate is a serialisation
format for a current model, and what every session asked for is the
tree, its scope and its value -- the working surface of the text
loop.**
