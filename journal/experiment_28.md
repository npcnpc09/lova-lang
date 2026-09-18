# Experiment 28 -- The located fault in the repair loop (Q96)

**Date:** 2026-09-18
**Script:** `experiments/experiment_21_repair.py` (the examples arm: a session named `e*`, and the `fault` command)
**Status:** Done, two runs. Run 1: three fresh Opus sessions, e1-e3, against Exp 21's r1-r3 in both languages -- **PARTIAL: WIN on attempts, NULL on reading.** Run 2, the same afternoon, e4-e6 with what run 1's sessions asked for (M29) -- **WIN: 24/24 first-try, and the program read falls below Python's.**

## Hypothesis

Exp 21 measured the fourth number's repair half as NULL: at twenty to
forty lines a one-token fault is found by reading, so repair cost is
reading, reading scales with length, and LOVA's programs are 2.35x
longer. The structured anomaly never spoke, because an example that
missed said `offender: apply at depth 0`.

M28 makes it speak: when an example misses, `check` probes every
single-node edit of the defs the example ran through and reports the
one that makes it pass, scored against the other examples, with
replacement text. On Exp 21's eight planted faults, five are located
with a fix that passes every test, one partially, two not at all.

The hypothesis: a session given the program *with its examples* and
the `fault:` line repairs in fewer attempts and with less context
read than Exp 21's sessions given the program alone -- and, where the
line is a lead rather than a repair, no worse. If reading falls below
Exp 21's Python figure (12 069 characters over three sessions), the
repair half of the fourth number is won at this size despite the
length; if it does not, the located fault is worth what it saves and
no more.

## Method

Exp 21's eight tasks and eight planted programs, unchanged, with each
task's tests written beside the defs as `(example ...)` forms (the
examples arm of the harness builds them from the tests: the body with
the inputs filled, and the expected value). A session gets the card,
the task prompts, and a `fault` command that runs `lova check` on the
current program and prints the report -- the failing examples with
expected and got, and the `fault:` line -- logged as context read.
`given` (the whole program), `patch` and `submit` are Exp 21's. Three
fresh Opus sessions, e1-e3. The comparison is Exp 21's r1-r3, LOVA
and Python, same tasks, same faults, same harness.

What the locator says about each task before any session runs (the
eight faults, `journal/README.md` M28): h01 exact, h02 and h03 a
different fix that passes every test, h04 partial and cut by the
budget, h05 and h07 nothing (the fix is an expression, or a second
call), h06 and h08 exact.

## Results

### The numbers

| arm | sessions | tasks green | first-try | attempts | written (chars) | read (chars) | fault reports | `given` reads |
|---|---|---|---|---|---|---|---|---|
| Exp 28, LOVA with examples and `fault` | e1, e2, e3 | 24/24 | 23/24 | 28 | 3 333 / 279 / 3 333 | 25 138 / 27 851 / 25 138 = 78 127 | 25 | 18 (6 a session, the same six) |
| Exp 21, LOVA, program alone | r1, r2, r3 | 24/24 | 18/24 | 30 | 672 | 27 108 | -- | 24 |
| Exp 21, Python, program alone | r1, r2, r3 | 24/24 | 20/24 | 28 | 391 | 12 069 | -- | 25 |

e2's twelve attempts are eight repairs, one span miscounted by one (a
parse error, fixed at once) and three patches after green to repair
the example copies of h03's comparator, which the session did so that
`lova check` would be clean; attempts to green were 9. e1 and e3
wrote 3 333 characters because h03's fault was copied into four
places and each submitted a whole file for it; e2 patched four spans.

What the sessions read, split: fault reports 11 214 / 13 278 / 11 214
characters; `given` 13 924 each (the program with its examples is
13 924 characters against 8 465-10 154 for the program alone).

### What the fault line did, task by task, identically in all three sessions

| task | the line said | was it the fault | what the session did |
|---|---|---|---|
| h01 | `(get f v)` -- this should be negated, fixes every example | yes, exactly | read `given` anyway: the excerpt occurs four times and `patch --find` needs one; the read bought the address, not the diagnosis |
| h02 | `(eq c 58)` -> `(lt c 58)`, fixes every example | no: a different edit that passes three examples and strips digits from words | read, found `39` for `46` |
| h03 | `ra` -> `rb` inside the example's own comparator, fixes every example | no: edits the test's copy of the code, makes the comparison constant | read, found `lt` for `gt`, in four copies |
| h04 | `(neg b)`, fixes 3 of 4 others, the fault may be elsewhere, budget | no, and said so | read, found the diagonal written twice |
| h05 | nothing | -- | read; "got eng 2, expected eng 150" was the diagnosis already |
| h06 | `lt` -> `le`, fixes every example | yes, exactly | patched blind; the prompt's "overlapping or touching" settled it |
| h07 | nothing | -- | read; the failing example's edges written backwards was the diagnosis |
| h08 | `gt` -> `ge`, fixes every example | yes, exactly | patched blind; the prompt's "if the balance covers it" settled it |

Three sessions, the same six `given` reads, the same two blind
patches, the same verdicts.

### What the sessions said

All three, unprompted, the same rule: "the fault line is an *address*,
not a diagnosis". Five reports named a location, and "zero false
neighbourhoods in five" -- 2:73 was in `punct?`, 43:31 in the
comparator, 2:42 one line above the win table -- "but it proposed the
correct token change only twice out of five". They trusted it blind
exactly when "the suggested edit was a comparison-operator swap inside
a `def`, the report said fixes every example, and the prompt contained
a sentence I could check the proposed semantics against"; "the fault
line gave me a hypothesis, and the task text, not the code, confirmed
it".

On the confident misleads: "the line was never *false* about what it
claimed -- it always did fix the examples -- but 'fixes every example'
is a much weaker statement than it reads like"; "any edit that
collapses a comparison to a constant can satisfy three examples while
being nonsense against hidden inputs"; and on h03, "the search is
allowed to edit the test, and the test is a copy of the code, so the
cheapest edit is the one that breaks the copy rather than repairing
the original" -- "close to misleading by construction".

What they asked for, all three: the span in the line ("h01 would have
been a zero-read repair; one of eight tasks whose entire read cost is
an interface mismatch"); a word when nothing was found ("silence is
indistinguishable from no search was run"); no edits inside an
`(example ...)` form, or a flag on them; a confidence that reflects
how much the examples constrain the edit; and, from one, "a reason"
-- why the example fails -- rather than a replacement.

On the instrument: "the examples duplicate the whole main expression
verbatim, so one planted fault appears in four places, the single-node
repair model cannot express the fix, and `--find`'s uniqueness rule
becomes the binding constraint rather than the language"; the
programs read "three times longer than their logic warrants".


## Run 2 (2026-09-18, later) -- with what run 1's sessions asked for

Three more fresh Opus sessions, e4-e6, the same eight tasks and
faults, after M29 and the report changes: the body is a def the
examples call; the fault line carries the span and how many examples
reach the def; a miss says "no single edit of a def"; no edit is
offered inside an example; `show --defs` (free), `show --def name`
(logged as the def's size) and `patch --def name --find text`.

### The numbers

| arm | sessions | first-try | attempts | written | read, total | of which fault reports | of which program | whole-program reads |
|---|---|---|---|---|---|---|---|---|
| run 2 (M29) | e4, e5, e6 | 24/24 | 24 | 269 / 274 / 274 | 5 529 / 6 858 / 5 738 = 18 125 | 4 093 each | 1 436 / 2 765 / 1 645 | 0 / 1 / 0 |
| run 1 | e1, e2, e3 | 23/24 | 28 | 3 333 / 279 / 3 333 | 78 127 | 11 214-13 278 | 13 924 each | 6 a session |
| Exp 21 LOVA | r1-r3 | 18/24 | 30 | 672 | 27 108 | -- | 27 108 | 8 a session |
| Exp 21 Python | r1-r3 | 20/24 | 28 | 391 | 12 069 | -- | 12 069 | 8 a session |

Every session repaired every task at the first submission. The same
four tasks were patched blind in all three sessions -- h01, h03, h06,
h08 -- from the span in the fault line; the other four were read as
one to three defs (57 to 634 characters each) chosen from the free
def list, and one session opened the whole program once (h04). The
program read per session, 1 436-2 765 characters, is below Python's
4 023 a session in Exp 21; the total read, with the reports, is 6 042
a session against Python's 4 023 and run 1's 26 042.

### What the sessions said

The rule, stated by all three: trust the line when its edit "can be
restated as a clause of the prompt" -- `le` for "touching", `ge` for
"covers it", `gt` for "descending", a `neg` under a unary minus --
and read when it cannot. "The prompt plus the line was a complete
argument"; "half these repairs were done blind".

On the free def list: "the single most valuable command in the
loop"; "the quiet hero"; "the def list plus the parameter names told
me the architecture before I read a single body, and let me pick the
right two or three bodies out of seven"; on h04 "I could see `w3` was
57 chars and spend that before spending the 634 of `best2`". On the
honest miss: "a cheap, honest negative that saved me from probing by
hand"; "the honest 'no single edit' message is worth more than a
confident wrong one, and h02 is the case that proves it".

h02 was again the confident mislead in all three, and again caught by
reading the replacement against the prompt: "`(lt c 58)` is not a
description of punctuation; it is a description of the test suite".

What they asked for, this time: on a miss, which defs the failing
example reaches (built: the miss now names them); the step-limit
failure diagnosed beside the wrong value on h04, with `hot` (built:
a trap in an example prints its hint); a runner-up edit; a
counterexample search rather than an example-fitting one (Q115); a
way to evaluate an expression of their own without submitting.

### Findings of run 2

**F7. The repair half of the fourth number is won at this size, on
reading as well as attempts.** 24 of 24 first-try; the program read
below Python's; the total read above it only by the report, which has
since been cut to the failures.

**F8. The address was the product, and the def list its index.**
Nothing about the locator changed between the runs; what changed is
that the address could be acted on (a span, a def-scoped patch) and
that the program could be read a def at a time. Reading fell from
13 924 to 558-1 645 characters a session.

**F9. The confident mislead is unchanged and was caught three of
three times** by the same rule, which is the model's, not the
machine's. Q115 is what would make it the machine's.

## Findings

**F1. Attempts: WIN, small.** First-try repairs 23 of 24 against Exp
21's 18 (LOVA) and 20 (Python); attempts to green 27 against 30 and
28. The one miss was a span miscounted by hand.

**F2. Reading: NULL, and worse.** 78 127 characters read against
27 108 and 12 069. Two thirds of the difference is the instrument: the
program with its examples is 40-60% longer than the program alone
because each example carried a verbatim copy of the body, and the
fault report reprinted every example's multi-line expression, eleven
to thirteen thousand characters a session. The remaining third is
the finding: the sessions read `given` on six of eight tasks anyway,
because the line was trusted only where the prompt could adjudicate
it (h06, h08), needed a unique anchor it did not give (h01), or was
absent or wrong (h02-h05, h07).

**F3. The line is right where it is exact and wrong where the
examples are weak.** Three of five lines named the planted token
(h01, h06, h08). Two named an edit that passes every example and is
not the fault (h02, h03), and both are the same failure: three
examples do not constrain a single edit, so an edit that collapses a
test to a constant scores as well as the repair. h03's was inside the
example's own copy of the code, which repairs the statement, not the
program.

**F4. The address is worth more than the edit.** Five of five lines
pointed at the right neighbourhood. The sessions' own rule -- "an
address, not a diagnosis" -- is the honest description of what a
located fault is at this evidence: it says where to read, and the
task text says what to write.

**F5. Expected and got did the work where the line was silent.** On
h05 and h07 the values ("eng 2" for "eng 150", -1 for 7 on edges
written backwards) were the diagnosis; the sessions read the program
to find the address, not the fault.

**F6. What all three asked for is buildable, and built the same
afternoon:** the span in the line; a word when no edit is found; no
edits offered inside an example's expression; the number of examples
the score rests on, in the score; an exchanged reference that makes a
comparison compare a thing with itself no longer offered; the report
printing an example as its first line; and the harness writing the
body as a def the examples call. On the same eight faults after the
changes, the reports are shorter and h03's line is in the def.


## Discussion

The located fault moved the first number and not the second, and the
sessions explain why in one sentence: at twenty to sixty lines,
reading a program costs less than deciding whether a proposed edit is
safe. The line saved a read only when the task statement could
confirm it without the code. That is a real and narrow win, of the
same shape as Axiom 3's: the machine's signal is decisive exactly
where the model's own judgement is cheapest to apply, and inert
elsewhere.

Q95 is therefore still the open question and this run sharpens it:
the located fault should pay at the size where reading fails, and
only there. At Exp 21's size it competes with something very cheap.
The right next measurement is `apps/`-sized programs -- 150-500 lines,
faults with run-time symptoms -- where a session cannot read in one
pass, and the comparison is the `fault:` line against a Python
traceback that names a line.

The confident mislead is the design lesson. "Fixes every example" was
true and misleading twice out of five, because the oracle is the
examples and the examples are few; the score now names their number,
which is honest, and stops short of what one session asked for -- a
reason. A reason would be a second oracle: the prompt's sentence, or
a property the examples do not state. Whether a located edit can be
checked against a *declared* property rather than a handful of cases
is what the conservation contract was always for (Axiom 4), and this
is the first experiment to say concretely what it would buy: the
difference between an address and a diagnosis.

The instrument finding is also a language finding. Examples that
copy the body are what a harness writes; examples that call a def are
what an author writes, and the second reads and repairs at a third of
the cost. A program that carries its examples wants its body to be a
def.


## Next questions raised

- **Q95** *(sharpened)*: the located fault against a traceback at the
  size where reading fails -- `apps/`-sized programs, faults with
  run-time symptoms, the `fault:` line and the span against a Python
  traceback naming a line. This run says the line pays only there.
- **Q115**: a second oracle for a located edit -- can the edit be
  checked against a declared contract (a `conserve`, a property the
  examples do not state) so that "fixes all 3 examples" becomes a
  reason? Axiom 4's machinery, pointed at the repair.
- **Q116**: the confident mislead as a number -- over more planted
  faults, how often does a "fixes all N examples" edit that is not
  the fault appear, as a function of N? The count that would let the
  score be a probability.
- **Q117**: examples that call a def against examples that copy the
  body, for the same faults: the read and write cost of the program's
  own shape, measured.

## Status

**Run 1, PARTIAL; run 2, WIN.** The located fault takes first-try
repairs from 18 of 24 to 23 of 24 (run 1) and 24 of 24 (run 2), and
attempts to green from 30 to 27 and then 24. Reading tripled in run 1
-- two thirds instrument, a third the sessions reading anyway -- and
in run 2, with the span in the line, a free def list and a def-scoped
read and patch, fell to 1 436-2 765 characters of program a session,
below Python's 4 023. Four of eight repairs blind in every session;
the same rule in all six: trust the line when its edit is a clause of
the prompt. The confident mislead (h02) is unchanged and caught every
time by that rule, which is the model's; Q115 would make it the
machine's. Q95 remains the size where the claim is untested.
