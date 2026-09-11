# Experiment 20 — Does cost attribution turn a blind rewrite into a read one?

**Date:** 2026-09-11
**Script:** `experiments/experiment_19_agent_loop_apps.py` (sessions o4-o6; Exp 18's harness)
**Status:** Done, three sessions, one model (Opus, as run 2). **PARTIAL.**

## Hypothesis

Q91. Exp 19's run 2 put three sessions through a step trap on the
game-tree search and each rewrote blind: 6, 3 and 4 attempts on h04,
the sessions' own words "the only recovery was to rewrite the whole
algorithm blind". The trap was then given `hot`, the most-called
functions by name with counts. Does that turn the two blind rewrites
into one?

## Method

Exp 19's eight tasks, harness and rules, unchanged: a fresh session
with the generated card and `submit` / `patch`, hidden tests, a 7 000
000-step budget, up to eight attempts a task. Three LOVA sessions on
the model of run 2 (Opus), named o4-o6, so the comparison is within a
model; the Python side is run 2's. The instrument's only differences
from run 2 are the three changes Exp 19 shipped: `hot` in the step
trap, the cost on `PASS`, the zero-parameter `def`'s call site on the
card.

After the sessions, every step-trapped h04 program from runs 2 and 3
was replayed under a 40 000 000-step ceiling, before and after the
changes this experiment made to the prelude.

## Results

Per session (run 2 for comparison):

| run | session | green | first-try | attempts | h04 attempts | h04 sequence | feedback chars | failures |
|---|---|---|---|---|---|---|---|---|
| 2 | o1 | 8 | 7 | 13 | 6 | type, type, step, parse, step, PASS | 2 364 | 5 |
| 2 | o2 | 8 | 7 | 10 | 3 | type, step, PASS | 1 051 | 2 |
| 2 | o3 | 8 | 6 | 12 | 4 | type, step, step, PASS | 3 123 | 4 |
| 3 | o4 | 8 | 6 | 11 | 3 | step, parse, PASS | 1 626 | 3 |
| 3 | o5 | 8 | 7 | 9 | 2 | step, PASS | 910 | 1 |
| 3 | o6 | 8 | 7 | 11 | 4 | step, step, step, PASS | 3 057 | 3 |

Run 3 totals: 24/24 green, 20 first-try, 31 attempts (run 2: 35),
h04 9 attempts (run 2: 13), 7 failures (run 2: 11), 5 593 feedback
chars (run 2: 6 538). The four `type-mismatch` faults of run 2 were
the card gap Exp 19 closed; they did not recur. Step traps: five in
each run. Rewrites after a step trap before green: run 2 -- 2, 1, 2;
run 3 -- 1, 1, 3.

**What the sessions did after the trap** (their reports, in
substance). o5: "`iterate 56842, nth 49702, code 37107` against
`bestloop 13052` said the search had reached ~13 000 nodes and the
budget went into list indexing and a key recomputed per node; guessing
I would have added alpha-beta pruning, which attacks the node count";
board to a base-3 integer, key threaded; 7M+ → 3.03M, one rewrite.
o4: "`mval` at 2 059 told me the search had expanded ~2 000 nodes;
`nth` (55 907) and `line-win` named the cost; pruning would have been
the wrong fix"; nine scalar parameters; one rewrite (plus one paren).
o6: three traps. After the first (`iterate`, `nth`) it removed `nth`;
after the second, whose list led with `three (97625), setat (87750),
nm (61887), inc (53485)`, it inlined `three`, `inc` and `other` -- "a
one-line helper for i+1 was costing ~1.2M steps"; after the third
(`setat (99705)`, `pick (9)`) it packed the board into an integer and
passed at 89% of budget.

**What a call to `inc` costs.** Measured after the run: a loop of
5 000 iterations costs 65 014 steps bare, 75 014 with `(merge acc 1)`
in it and 90 016 with `(inc acc)` -- a `def` call is about three steps
over its body. `(nth nine 8)` cost 210 a call. o6's second rewrite
attacked a cost of 3 steps a call because the list ranked it by calls.

**Cost by steps, the same programs.** With the attribution changed to
steps spent in each function's own body (this experiment), the run-2
program o1-3 reads: `nth 3 943 421 steps in 56 879 calls, iterate
770 488, rev-onto 425 454, winline 345 230, take 308 638, drop
239 877` -- list access is three quarters of the budget; `winline`,
the user's own function, five percent.

**The natural first attempt, replayed at 40M steps:**

| program | old prelude | native `nth` / `take` / `drop` / `append` | wall, old → new |
|---|---|---|---|
| o4-1 | 30 721 481 | 9 932 479 | 45 s → 25 s |
| o5-1 | 23 762 225 | 13 009 425 | 35 s → 28 s |
| o6-1 | > 40 000 000 | 28 820 651 | -- → 69 s |
| o1-3 | > 40 000 000 | 36 623 714 | -- → 72 s |
| o2-2 | 31 981 820 | 11 177 122 | 46 s → 21 s |
| o3-2 | > 40 000 000 | 31 242 185 | -- → 65 s |

The six programs the sessions finally passed with are unchanged by the
prelude (2.59M to 6.46M steps before and after): every one had already
engineered the list away.

**The interpreter after this experiment** (in-process, min of seven,
CPU seconds): the search 2.6-2.9 → 2.2-2.3, the word count 0.33-0.36 →
0.28-0.38, `fib 24` 1.6-1.7 → 1.2-1.5 -- faster with the attribution
than without it, because `Closure` and `Runtime` got `__slots__` on
the way (the dict-based attribution cost 15-19% on call-heavy
programs; the slotted classes gave that back and more).

## Findings

- **F1. Attribution moved h04 from 13 attempts to 9, and the sessions
  say it changed what they rewrote.** Three of three would have
  attacked the node count (pruning, memoisation); the list said the
  cost was per node, in list access. Two sessions rewrote once and
  passed. Not a ten-session result.
- **F2. Call counts are not costs, and the list said so once in three.**
  o6's second rewrite inlined `inc`, `three` and `other` because they
  led the list by calls; a call costs three steps. Its third trap
  followed. Steps spent in a function's own body is the honest
  ranking, and every session asked for it unprompted.
- **F3. `nth` was half the budget, and a slot was never needed.**
  `text-slice` and `text-cat` now keep a list's shape, so `nth`,
  `take`, `drop`, `last` and `append` are one native operator each: 13
  to 19 steps where the walk cost 80 to 400. The natural first attempt
  costs 1.3-3.1× fewer steps; three programs that did not finish in
  40M now do.
- **F4. The natural program still does not fit the budget.** 9.9M to
  36.6M against 7M. What remains is the other walkers (`map`, `filter`,
  `fold`, `any`, `range`: 20-40 steps an element) and a wall clock of
  ~400 000 steps a second. A game-tree search over a nine-element list
  is a two-attempt task in LOVA until one of those moves. Q90 stands.
- **F5. The card's silence on cost was the gap this time.** All three
  sessions: nothing on the card says what is cheap and what walks; one
  distrusted maps in a search for no reason, one inlined helpers. The
  card has a cost section now, with the measured numbers.
- **F6. Six card facts the sessions guessed right and should not have
  had to:** mutual recursion between `def`s, the empty map `(nil)`,
  `words` yielding texts, negative literals, `\n` in a text literal,
  field names as bare symbols. All on the card now; none cost an
  attempt in this run.
- **F7. Two of seven failures were a paren.** Each cost a submission.
  The harness now has `check` -- compile with the prelude, run the
  program's `example` forms, placeholders filled with typed dummies;
  `py_compile` on the Python side -- logged and reported in its own
  column, not as an attempt. `tasks` states the budget; `patch --out`
  writes the patched source back.

## Discussion

Q91's answer is a qualified yes. The rewrites were read, not blind,
and two of three sessions needed one; the third was misled by the
instrument itself, which ranked a three-step helper above a
two-hundred-step walk because it counted calls. That defect is the
finding of the experiment: what the trap must say is where the *steps*
went, and it does now, at no cost to the interpreter.

The step ranking also showed something the call ranking had hidden:
the user's own functions were a small share. Three quarters of the
budget was the prelude's `nth`, called by name from a card that
presented it as an accessor. So the cheapest change was not in the
program or the algorithm but in the library, at zero slots -- the
text operators already existed and `text-len` already accepted a list.
That halved to quartered the natural program and did not make it fit.

What the four numbers now say about h04: the first attempt is written
correctly (six of six replayed programs return the right move), and it
costs the budget. Under the goal that is a cost of the language, and
it is the interpreter's: ~400 000 steps a second, with a 25-step walk
per element in every library function that is not native. The choice
Q90 names -- native evaluator, or a native walker family -- is the
next design decision the numbers call for, and it is not this
experiment's to make.

## Next questions raised

- **Q93** -- with steps in the ranking, native list access and a cost
  section on the card, does the natural h04 pass in one rewrite, or in
  none? Three sessions, the same tasks.
- **Q94** -- `map` / `filter` / `fold` / `reverse` / `range` at 20-40
  steps an element are the cost that remains. Native, at what slot or
  family cost, against the ~25× a native `nth` gave?
- **Q90** -- stands, sharpened: the natural search costs 10-37M steps
  at ~400 000 a second; a native evaluator is the alternative to Q94.
- **Q92** -- ten sessions, still.

## Status

**PARTIAL.** Attribution by call count took h04 from 13 to 9 attempts
over three sessions and misled one of them; attribution by steps
replaces it, at no interpreter cost. `nth` was half the budget and is
native now at zero slots, with `take`, `drop`, `last` and `append`;
the natural first attempt costs a third as much and still does not
fit. Card: a cost section and six facts. Harness: `check`. Q93, Q94
raised; Q90 sharpened. Tests 781 → 783.
