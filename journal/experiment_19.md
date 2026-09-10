# Experiment 19 — The agent loop at a size where first attempts fail

**Date:** 2026-09-10 / 2026-09-11
**Script:** `experiments/experiment_19_agent_loop_apps.py` (on Exp 18's harness)
**Status:** Done, two runs of three sessions per language. **PARTIAL.**

## Hypothesis

Exp 18's ten tasks went green at the first attempt in both languages,
so the yardstick's second number -- what an agent reads to understand
a failure -- had one side. Q87: at a size where first attempts fail
in both languages, does the loop separate them, and on which of the
four numbers?

## Method

Eight tasks with edge cases a first attempt tends to miss: an
expression calculator with precedence and unary minus, a word-frequency
report, a log summary, the best tic-tac-toe move under perfect play, a
department ledger, interval merging, shortest paths, a bank ledger with
rejected lines. Answers are integers or texts; three to five hidden
tests each from Python oracles. The harness is Exp 18's: `submit`
prints `PASS` or the first failure with the structured anomaly (LOVA)
or the traceback (Python); `patch` on the LOVA side; every submission
logged with what was emitted and what was read back. Sessions are
fresh Claude sessions with no repository access; the LOVA sessions have
the generated card and nothing else.

Two runs, because the first found defects in the instrument:

- **Run 1** (sessions s1-s3, Claude Fable): a LOVA answer ran under a
  200 000-step budget, a Python answer under a ten-second wall clock.
  The LOVA sessions were cut short by an account limit after seven or
  eight tasks each; the Python sessions finished.
- **Run 2** (sessions o1-o3, Claude Opus, the only model available
  after the limit): the budget at parity with the wall clock
  (7 000 000 steps, the ~700 000 a second CPython runs), the step
  trap's hint rewritten, parse errors with a position, the card's
  zero-parameter `def` still undocumented at its call site (found in
  this run).

The two runs used different models, so they are compared within a run,
not across.

## Results

Per session, on eight tasks (run 1 LOVA sessions were interrupted at
seven or eight):

| run | lang | session | tasks | green | first-try | attempts | emitted chars | feedback chars | failures |
|---|---|---|---|---|---|---|---|---|---|
| 1 | LOVA | s1 | 8 | 7 | 7 | 13 | 17 294 | 2 463 | 6 |
| 1 | LOVA | s2 | 7 | 6 | 6 | 14 | 21 521 | 3 182 | 8 |
| 1 | LOVA | s3 | 7 | 7 | 6 | 14 | 20 216 | 2 725 | 7 |
| 1 | Python | s1-s3 | 24 | 24 | 24 | 24 | 16 121 | 0 | 0 |
| 2 | LOVA | o1 | 8 | 8 | 7 | 13 | 16 781 | 2 364 | 5 |
| 2 | LOVA | o2 | 8 | 8 | 7 | 10 | 12 376 | 1 051 | 2 |
| 2 | LOVA | o3 | 8 | 8 | 6 | 12 | 16 215 | 3 123 | 4 |
| 2 | Python | o1-o3 | 24 | 24 | 22 | 26 | 18 013 | 142 | 2 |

Run 2 totals: LOVA 24/24 green, 20 first-try, 35 attempts, 6 538 chars
of feedback over 11 failures (594 per failure); Python 24/24 green, 22
first-try, 26 attempts, 142 chars over 2 failures (71 per failure).

**Where the failures were.** Every LOVA failure but one was on h04,
the tic-tac-toe search; the one other was a leftover draft `def`
naming a renamed symbol (unbound-ref, fixed in one try). Both Python
failures were h06, the sessions reading "touching" intervals as
integer-adjacent; fixed in one try from the expected value.

**Run 1's step traps, replayed.** Fourteen of run 1's twenty-one LOVA
failures were step traps at 200 000. Replayed under the CLI's own
ceiling of 20 000 000, eleven of the fourteen pass: correct programs,
trapped by a budget thirty times smaller than the Python clock. The
trap's hint said "the program does not terminate"; the sessions
rewrote correct programs. With the budget at parity, run 1's attempt
counts on h04 would have been 2, 3 and 2 instead of 6, 8 and 8.

**Run 2's step traps, replayed.** Five step traps at 7 000 000.
Replayed under 40 000 000: three pass, in 25 s, 25 s and 70 s; two
still trap after 74 s and 102 s. At parity these programs were
genuinely too costly, not wrong: a minimax over a nine-element list
board costs tens of millions of steps in LOVA where Python's takes
under a second.

**What the sessions said** (run 2, LOVA, in substance):

- "The compile-time diagnostics were excellent -- `unbound-ref` with a
  scope listing and `type-mismatch` naming the produced and expected
  type were both one-glance fixes." All five compile faults across the
  three sessions were fixed at the next submission.
- "The step-limit trap is the one place the language gives an outcome
  but no diagnosis ... the only recovery was to rewrite the whole
  algorithm blind." Each session needed one or two rewrites of h04
  after a step trap, guessing at which operations were expensive
  (`nth`, `take`/`drop`/`append`, a text key in the memo).
- "The card is unusually well-calibrated ... the two explicit gotchas
  it calls out (operators are not values; `fold` calls `(f acc x)`) are
  exactly the two things I would otherwise have got wrong." Three of
  three sessions hit the one gap it still had: `(def k [] v)` is a
  value, referenced bare, and the card showed no call site.

Python sessions: "the task statements were precise on the ambiguous
points, so each task could be written once"; "Python's standard
library carried most of the weight -- `sorted` with a key tuple covers
three of the eight tasks outright, and `heapq` covers h07."

## Findings

- **F1. On seven of eight tasks the languages do not separate.** Run
  2, tasks other than h04: LOVA 20 of 21 first-try, Python 22 of 24.
  What Exp 18 found on small tasks holds at this size.
- **F2. Where they separate is cost, not correctness.** h04 took LOVA
  6, 3 and 4 attempts against Python's 1, 1, 1, and every extra attempt
  after the card gap was a rewrite for speed. The interpreter runs
  ~700 000 steps a second; the natural program for a game-tree search
  costs 40 million. Q76's speed floor is now an attempts number.
- **F3. Compile faults cost one attempt; step traps cost two.** Five of
  five compile faults were fixed at the next submission. Seven step
  traps took one or two rewrites each, because the trap said where it
  stopped and not where the budget went.
- **F4. The instrument had four defects, all found by the sessions.**
  A text that looks like a number arrived as an integer; the budget was
  thirty times tighter than the Python clock; the step trap asserted
  non-termination; parse errors had no position. Each was closed before
  run 2, and each is a language-interface change, not only a harness
  one (`s="7"` on any command line; `ParseError` with a span; an honest
  hint).
- **F5. Feedback per failure: LOVA 594 chars, Python 71.** Python's
  two failures were wrong values, which cost a line; LOVA's were
  anomalies with detail. The number is one-sided in a new way: the
  languages failed on different things, so what was read is not the
  same kind of feedback.
- **F6. Emission: LOVA 2.5× Python's characters** over run 2 (45 372
  against 18 013), of which the h04 rewrites are about a third.

## Discussion

Q87 asked for failures on both sides and got them, and the answer is
sharper than expected: for an agent that writes both languages from a
page, LOVA's correctness is Python's, its diagnostics for compile
faults are better than a traceback (one attempt each, the sessions'
own words), and its one deficit is that a search-shaped program is
slow enough to hit a budget, at which point the language said nothing
useful. That deficit was known as Q76 (speed) and is now measured as
attempts: two or three per search task.

Two changes follow from the run and are in this commit. The step trap
and the depth trap now carry `hot`, the most-called functions by name
with their counts ("Most called: minimax (412 000), winner (398 000)"),
so a rewrite for speed starts from a reading rather than a guess;
`PASS` reports the largest run's steps against the budget, so an agent
sees cost before the wall. The card documents the zero-parameter
`def`'s call site. Whether attribution turns two blind rewrites into
one is Q91.

The thing to be honest about: the instrument's four defects were mine
and cost run 1 its LOVA side. The finding stands on run 2, which is
three sessions on one model; the journal's rule asks for ten.

## Next questions raised

- **Q90** -- the interpreter's speed as an attempts number: what does
  h04 cost at 5 million steps a second (PyPy), and is a native
  evaluator the next design change the numbers call for?
- **Q91** -- does cost attribution in the step trap turn the two blind
  rewrites into one? Same tasks, three more sessions, the `hot` list
  in the feedback.
- **Q92** -- ten sessions per language on one model, both runs' tasks,
  so the per-task attempt distribution is load-bearing.

## Status

**PARTIAL.** Twelve sessions, two runs. On seven of eight tasks LOVA
and Python are at parity in attempts; on the game-tree search LOVA
took two to five more attempts, all of them rewrites for cost after a
step trap that said nothing about where the cost was. Compile faults
were fixed in one attempt every time. The instrument's own defects are
fixed; the step trap now attributes cost by function; Q90-Q92 raised.
