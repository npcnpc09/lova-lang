# Experiment 29 -- The repair leg at the size where reading fails (Q95)

**Date:** 2026-09-18
**Script:** `experiments/experiment_29_repair_size.py`; the pairs, tests and session briefs in `experiments/exp29/`; the logs and every session's own report in `experiments/results_29/`
**Status:** Done, two runs. Run 1: three fresh Opus sessions a language, L1-L3 and P1-P3, four tasks each. **WIN on reading and writing at parity on attempts: 12/12 first-try on both sides; LOVA read 14 244 characters against Python's 27 259, of which program text 3 882 against 27 259; nine of twelve LOVA repairs applied without reading a line of the program.** Run 2, the same night: Q118 (P4-P6, Python with a test run that is not an attempt) and Q120 (L4-L6, split pairs and two helper-constant faults) -- **the free test run is most of the total-read difference (Python 10 922, below LOVA's 14 244, the fault report's own size the cost); program text stays 7 679 against 3 882 and Python read a def before every patch where LOVA read none on nine of twelve and five of six; the cold LOVA repairs match the warm ones.**

## Hypothesis

Exp 21 measured repair at twenty to forty lines and found it was
reading: a one-token fault is found by reading the program before any
feedback, so the cost is program length and LOVA's programs are 2.35x
longer. Exp 28 gave the fault an address and a def-scoped read and won
at that size: 24/24 first-try, the program read below Python's. Both
runs' sessions gave the same rule: reading a program of that size
costs less than deciding whether a hint is safe.

Q95 asks what happens where reading is not cheap. Two programs of
108-146 lines in LOVA (146 and 108; 184 and 145 in Python), each with
a Python transliteration of the same structure, checked to agree on
hundreds of random inputs; two faults planted in each at the analogous
place in both languages, with run-time symptoms -- a wrong value on
some inputs, a trap or an exception on others. If the `fault:` line
carries the repair at this size, the LOVA session reads the report and
patches; if it does not, the LOVA session reads the program, and the
program is longer.

The hypothesis: at 110-160 lines the LOVA session repairs in no more
attempts than the Python session and reads less, because the located
fault replaces the reading that the Python session must do.

## Method

**The programs.** `g2048` -- the 2048 engine: sixteen cells and a text
of moves, the original game's merge rules (a tile merged this move
cannot merge again; traversal order decides which pair merges), the
score and the moved count returned. `ttt` -- noughts and crosses: the
memoised negamax's chosen square and score, or the winner when the
board is decided. Each pair was built together and checked to agree on
random inputs (`*_check.py`). A third pair, taken from the SSH fleet
manager's policy layer, was removed before the run at the owner's
standing rule against that subject.

**The faults**, the same in both languages:

| task | what was planted | symptom |
|---|---|---|
| g2048-a | the merged-this-move flag is never written (`(map-put (get st m) k 1)` -> `(get st m)`) | a wrong value on 1 of 8 examples: `2 2 4` moved left gives one `8` and score 12 where `4 4` and score 4 are due |
| g2048-b | the letter for left maps to direction 4, which does not exist (`3` -> `4`) | a domain trap in the direction table on 4 of 8 |
| ttt-a | among equally good squares the last is chosen (`gt` -> `ge`) | a wrong square on 3 of 8: `8` where `1` or `2` is due |
| ttt-b | the empty squares are counted one past the board (`(range 0 9)` -> `(range 0 10)`) | a domain trap in `(nth powers k)` on 7 of 8 |

Three are a node changed; g2048-a is a node *dropped* -- an argument
replaced by a sub-expression of itself -- which the locator's
single-node edits do not reach.

**The harness.** A LOVA session has the program with its eight tests
as `(example ...)` forms and the tools of Exp 28 run 2: `fault` (runs
the examples; prints each failing one with expected/got or the trap,
and the located edit with replacement text and its score), `show
--defs` (free), `show --def NAME` (counted), `given` (the whole
program, counted), `patch --def NAME --find TEXT`, `submit`. A Python
session has `show --defs` (free), `show --def NAME`, `given`, `patch
--find` (unique in the program) and `submit`, and sees a failure only
on an attempt: inputs, expected, got or the traceback. Neither side
has a test run that is not an attempt. The briefs are
`experiments/exp29/BRIEF_lova.md` and `BRIEF_python.md`, verbatim;
tasks in the order g2048-a, g2048-b, ttt-a, ttt-b; give up after six
failed attempts; a report at the end, in the session's own words.

**Before any session ran**, the locator was put to the four faults
and found none of them: a def that takes a prelude name (`lines`)
split the letrec frame and the example was evaluated in the wrong
one; runaway probes ran at ten times the combined run; defs were
probed most-called first and edits deepest first, so a second a probe
went on `cell` before `choose`; trapped examples were never located.
Those four are Milestone 31 (`journal/README.md`); after them, three
of the four faults are located exactly with "fixes all 8 examples"
(ttt-a 77 s, ttt-b 22 s, g2048-b 6 s) and g2048-a reports a partial
lead in the wrong def with "the fault may be elsewhere" and "search
cut short by the time budget" (93 s). The `fault` budget for the
experiment is 90 s. The harness's `tasks` had been appending what was
planted to each prompt; it was removed before the run.

## Results

### The numbers

| arm | sessions | tasks green | first-try | attempts | written (chars) | read (chars) | of which program text | def reads | `given` |
|---|---|---|---|---|---|---|---|---|---|
| LOVA, examples and `fault` | L1, L2, L3 | 12/12 | 12/12 | 12 | 56 / 57 / 54 = 167 | 4 646 / 4 844 / 4 754 = 14 244 | 1 192 / 1 390 / 1 300 = 3 882 | 2 / 3 / 2 | 0 |
| Python, program alone | P1, P2, P3 | 12/12 | 12/12 | 12 | 94 / 109 / 115 = 318 | 9 818 / 6 592 / 10 849 = 27 259 | 27 259 | 38 / 24 / 44 | 0 |

The LOVA read splits as fault reports 3 454 a session (the same four
reports in every session: 449, 1 178, 570, 1 257 characters) and
program text 1 192-1 390, all but 90 of it on g2048-a.

Per task, characters read:

| task | L1 | L2 | L3 | P1 | P2 | P3 |
|---|---|---|---|---|---|---|
| g2048-a | 1 551 (report + `move-cell`) | 1 749 (+ `farthest`) | 1 749 | 1 601 (2 defs) | 2 077 (5) | 2 612 (6) |
| g2048-b | 1 268 (report + `dir-of`, 90) | 1 268 | 1 178 (report only) | 1 763 (8) | 1 287 (5) | 1 783 (10) |
| ttt-a | 570 (report only) | 570 | 570 | 3 227 (all 14) | 1 862 (4) | 3 227 (14) |
| ttt-b | 1 257 (report only) | 1 257 | 1 257 | 3 227 (14) | 1 366 (10) | 3 227 (14) |

### How each repair was made

| task | LOVA, L1 / L2 / L3 | Python, P1 / P2 / P3 |
|---|---|---|
| g2048-a | the line (`dy` -> `dx` in `farthest`, "2 of 7 others; may be elsewhere; cut short") **distrusted by all three**; the fault diagnosed from the failing example's own numbers (score 12, a lone 8: a double merge) to `move-cell`, read (1 102), the missing `map-put` found on sight | read by the prompt's clause ("cannot merge again" -> `move_cell`); P1 two defs, P2 five, P3 six, one of them the comment above the def |
| g2048-b | the line (`4` -> `3`, fixes all 8) **trusted**; L1 and L2 read the 90-character def only to build a unique `--find`; L3 blind | read by elimination along the move path; the constant against a four-entry table |
| ttt-a | the line (`ge` -> `gt`, fixes all 8) **trusted blind**, three of three; the symptom (square 8 for 1 or 2) read as last-tie-wins | P1 and P3 read all fourteen defs and found it by elimination; P2 four defs; "a judgement call about tie-break convention, not a proof" (P1) |
| ttt-b | the line (`10` -> `9`, fixes all 8) **trusted blind**, three of three | read; P1 and P3 all fourteen defs again ("a diff against the copy in my head", P3) |

Blind repairs (zero program text read): L1 2, L2 2, L3 3 -- seven of
twelve; two more with a 90-character def read for patch syntax only.
The Python sessions never saw a failure message: no attempt failed.

### What the sessions said

The reports are in `experiments/results_29/*/report.md`. The LOVA
sessions, independently and in nearly the same words:

- "It is an address plus a confidence label, and the label was the
  load-bearing part." (L2) "On this set, 'fixes all N examples' was
  3/3 correct and 'fault may be elsewhere' was 1/1 wrong." (L1) "Its
  own hedge told me which [job] I was getting." (L3)
- The rule of Exp 28 again, unprompted: "is the named edit a
  restatement of something the task prompt or the failing example
  already says?" (L1); "the line and the prompt vouched for each
  other" (L3).
- On g2048-a all three found the fault from the failing example's
  *value* -- "score 12 where 4 was expected is a double merge, and a
  double merge lives wherever the merged-set is written" (L3) -- and
  the free def list, with sizes, named `move-cell`. "The `fault:`
  line pointed one def away." (L2)
- The second oracle, `[changes the answer on N of 48 nearby inputs]`,
  "did not influence a single decision" (L1); "with 'fixes all 8'
  already present it added nothing. It would have mattered if two
  candidate edits had been offered." (L2)
- Asked for: patching by the span the line already prints (all
  three: the excerpt of a bare literal is not a unique find, and two
  sessions spent 90 characters on syntax or guessed); a partial lead
  not to "wear the same dress as a repair" (L1, L3); the defs a
  failing example reaches that the passing do not (L2); a field
  writer index (L3); a scratch evaluation (L3, Q113).

The Python sessions, independently:

- All four faults by reading, every session; "the failure-message
  channel contributed nothing on this side, since nothing failed"
  (P2). "The free def list was the single most valuable instrument"
  (P1); the method was the prompt's clauses mapped to def names, four
  of four (P2).
- The confound named by P1 and P3: a and b of a pair are the same
  program, so b is repaired against a known-good copy held in
  context, "not a repair from cold" (P1); ttt-b read as a diff (P3).
- Asked for: a test run that is not an attempt, all three -- "it
  bent my behaviour: I read the whole of ttt-a def by def rather than
  test a one-character hypothesis" (P1); a grep over the program
  (P2); a diff against a sibling (P3); "notably not wanted: a fault
  locator" (P3).

## Findings

### F1. At 110-160 lines the located fault replaces the reading, where the line is a repair

Twelve of twelve on both sides, first try, and the LOVA sessions read
52% of what the Python sessions read in all and 14% of it in program
text. Exp 21's finding at 20-40 lines -- repair cost is reading, and
reading scales with length -- inverts once the program carries its
examples and the examples locate the fault: three of four faults were
repaired with no program text read, in every session, on a program
whose text the session never saw. The fourth number's repair half is
won at this size, on this evidence.

### F2. The score is the instrument; the address is what it scores

Every session used the bracket before the token. "Fixes all 8
examples" was applied blind nine times of nine and was right nine
times; "fixes this and 2 of 7 others; the fault may be elsewhere" was
distrusted three times of three and was wrong. The perturbation score
of M30 decided nothing, because no session was ever offered two full
fixes to choose between -- it is an instrument for a case that did not
arise here. The sessions' rule of Exp 28 stands and was stated again:
trust the line when its edit is a clause of the prompt.

### F3. Where the line fails, the failing value and the def list carry the repair

g2048-a is a node dropped, outside the single-node hypothesis, and the
locator said so in its hedge. All three sessions then did the same
thing: read the failing example's expected and got as a statement of
which rule was broken, looked at the free def list for the def that
owns the rule, and read that one def. 1 102 characters, against the
Python sessions' 1 601-2 612 on the same task by the same method
without the example's numbers. The example's value is the diagnosis
the line is not.

### F4. Python's reading is bounded by its def list, and its sessions asked for LOVA's instrument

No Python session read the whole program either: the free def list
with line numbers and parameters, added for LOVA in M29, cut Python's
reading to named functions too, and P1 called it "the single most
valuable instrument". What every Python session then asked for is a
test run that is not an attempt -- which is what `fault` is, and what
a program that carries its examples has by construction. The
comparison's asymmetry is the language's claim, not an artefact of
the harness; a control arm that gives Python a free test run without
a locator would separate the two (Q118).

### F5. The confound: pairs

A pair's second task is repaired by a session that has read its first
task's program. P1 and P3 said so; the LOVA sessions were blind on
every second task so it cost them nothing, but it deflates Python's
ttt-b and g2048-b reads and could deflate LOVA's had the line been a
lead there. Split the pairs across sessions next time (Q120).

### F6. The locator at this size is a minute, not a second

`fault` on the noughts-and-crosses tasks took 77 s and on g2048-a 93
s, because a probe runs the example and the example is a game-tree
search; M31's four fixes made it find three of four where it found
none, and the fourth is a class of edit it does not probe (Q119).
The time is not in the four numbers, but a session waited a minute
and a half for each line.

## Discussion

Exp 21 said repair is reading and reading is length, so LOVA's 2.35x
length was a 2.2x reading cost, and the structured anomaly never got
to speak. Exp 28 gave the anomaly an address at that size and the
sessions read anyway, because reading 20-40 lines was cheaper than
deciding whether to trust the address. Here, at three to five times
the size, the balance tips: the address with its score is trusted
where the score is full, and a session that trusts it reads nothing.
The LOVA program is still longer than the Python one -- 5 869 against
6 553 characters for 2048, 4 441 against 4 414 for ttt, so near parity
in characters here -- but the sessions did not read it.

What made the score trustworthy is the same thing that made Exp 28's
sessions distrust it: the examples. Eight examples, several failing,
several passing, and an edit that fixes every one of them is a strong
claim; three examples, as in Exp 28, was a weak one, and h02's
widened test passed all three. The score is the number of examples,
and a program with more examples has a sharper locator. That is the
argument for examples as the program's own contract, measured.

The honest limits. First, the fault class: three of the four planted
faults are a node changed, which is what the locator probes, and the
fourth is a node dropped, which it does not; a set of faults drawn
from what sessions actually write wrongly (Exp 23's F3: a swapped or
shadowed reference, well-typed and silent) would test the hypothesis
where it is weaker. Second, the sessions decided by the prompt: every
blind patch was also a clause of the task prompt, and every session
said it would not have patched a full-fix edit that contradicted the
prompt. A fault whose fix is *not* a prompt clause -- a wrong constant
in a helper -- would test whether "fixes all 8" is trusted on its own.
Third, the pairs.

What the sessions asked for is small and specific. Patch by span:
the harness has it and the brief did not say so; the brief now does.
A lead labelled as a lead: the summary now prints `lead:` where the
edit does not fix every example. The defs a failing example reaches
that the passing ones do not: the machine has the sets and prints
them only on a miss. A field writer index and a scratch evaluation
are the Q113 surface again, asked for by a fifth and sixth session.

## Next questions raised

- **Q118**: the control arm -- Python with a test run that is not an
  attempt and no locator. Separates "the tests are free" from "the
  fault is located" in F1.
- **Q119**: the dropped and added node as an edit class. g2048-a's
  fault wraps an argument in a call to an operator with in-scope
  arguments; the candidates are many, the examples' data (M30) and the
  def's own sub-expressions bound them.
- **Q120**: pairs split across sessions, and faults whose fix is not
  a clause of the prompt, so that "fixes all N" is tested on its own.
- **Q121**: examples as the locator's power -- the same faults with
  three, eight and twenty examples; the rate of confident misleads
  (Q116) as a function of the count.

## Status

At 110-160 lines a program that carries its examples is repaired in
one attempt with no program text read on three faults of four, in
every session, and on the fourth with one def read; the Python
sessions repaired the same faults in one attempt each by reading
named functions, seven times the program text. The fourth number's
repair half is won at this size, on faults the locator can express;
the control arm (Q118) and the edit class it cannot (Q119) are what
the win still owes.

## Run 2 (the same night): Q118 and Q120

### Method

**Q118, the control arm.** Three fresh Python sessions, P4-P6, the
same four tasks in the same order as P1-P3, with one command added:
`probe`, which runs the hidden tests on the current program and
prints every failing one -- inputs, expected, got or the traceback --
counted as read, not as an attempt. Nothing else changed
(`experiments/exp29/BRIEF_python_probe.md`). If P4-P6 read what P1-P3
read, the free test run is not what made the difference in run 1; if
they read what L1-L3 read, it is.

**Q120, split pairs and a fault the prompt does not name.** Two
faults added, one a program, each a wrong constant in a helper that
no sentence of the task prompt states: `g2048-c`, the cell key's row
stride (`(mul x SIZE)` -> `(mul x 3)`, so two cells share a key); and
`ttt-c`, one power of three in the board's base off by one (`729` ->
`728`, so squares 6-8 misread). Three fresh LOVA sessions, L4-L6,
two tasks each and never the same program twice: L4 `g2048-c` then
`ttt-b`, L5 `ttt-c` then `g2048-a`, L6 `g2048-c` then `ttt-c`. So
`ttt-b` and `g2048-a` are repaired cold, by a session that has not
seen the program, and the two new faults are seen twice each.

**Before the run, the locator again.** Both new faults were put to it
first and it found neither, for two reasons that are now closed in
`core/locate.py` (and two tests): a zero-parameter def is a value
computed once, so `all-cells` still held the keys the faulty `ckey`
made after a probe had fixed `ckey`, and every probe failed --
constants that reference a probed def are recomputed while the probe
is installed; and a constant is not a closure, so `powers` was never a
target -- the value node of a constant is now probed like a def's
body, first, since its edits are few. After: `g2048-c` `3` -> `4` and
`ttt-c` `728` -> `729`, both exact, both "fixes all 8". The `fault`
budget stayed at 90 s; `ttt-c` takes 112 s to locate, most of it the
impact score.

### Results

| arm | sessions | tasks green | first-try | attempts | written | read | of which program text | probe / report | def reads | blind |
|---|---|---|---|---|---|---|---|---|---|---|
| Python, program alone (run 1) | P1-P3 | 12/12 | 12/12 | 12 | 318 | 27 259 | 27 259 | -- | 106 | 0 / 12 |
| **Python with `probe` (Q118)** | P4-P6 | 12/12 | 12/12 | 12 | 389 | 3 984 / 3 489 / 3 449 = **10 922** | 2 903 / 2 408 / 2 368 = **7 679** | 1 081 a session = 3 243 | 7 / 7 / 6 = 20 | 0 / 12 |
| LOVA, examples and `fault` (run 1) | L1-L3 | 12/12 | 12/12 | 12 | 167 | 14 244 | 3 882 | 3 454 a session = 10 362 | 7 | 9 / 12 |
| **LOVA, split pairs, new faults (Q120)** | L4-L6 | 6/6 | 6/6 | 6 | 35 | 2 967 / 2 243 / 2 204 = **7 414** | 0 / 1 300 / 0 = **1 300** | 6 114 | 2 | 5 / 6 |

Per task, Q118 (read characters, defs read):

| task | P4 | P5 | P6 | probe output |
|---|---|---|---|---|
| g2048-a | 1 204 (`move_cell`) | 1 204 (`move_cell`) | 1 204 (`move_cell`) | 156 |
| g2048-b | 1 608 (`vy`, `sweep`, `dir_of`) | 1 113 (`vy`, `vx`, `dir_of`) | 1 073 (`vy`, `dir_of`) | 525 |
| ttt-a | 641 (`choose`) | 641 (`choose`) | 641 (`choose`) | 55 |
| ttt-b | 531 (`empties`, `cell`) | 531 | 531 | 345 |

Per task, Q120:

| task | session | read | program text | how |
|---|---|---|---|---|
| g2048-c | L4, L6 | 1 710 each | 0 | blind, by span, "fixes all 8"; both note the prompt's sixteen cells make a stride of 3 wrong on its face |
| ttt-c | L5, L6 | 494 each | 0 | blind, by span, "fixes all 8"; both read 729 as 3^6 from the value itself |
| ttt-b (cold) | L4 | 1 257 | 0 | blind, as the warm sessions were |
| g2048-a (cold) | L5 | 1 749 | 1 300 (`farthest`, `move-cell`) | the lead distrusted, the fault read from the failing value, exactly as L2 and L3 did warm |

### What the sessions said

Q118, the three Python sessions, independently:

- "Every one was found from `probe`, not by reading the program; the
  reads were only to confirm and get the exact text to patch." (P5)
  "In all four, `probe`'s output narrowed the search to one or two
  defs before I read any program text." (P4)
- The two traps: "the traceback *was* the address" (P5); "it pointed
  at the *victim* (`vy`), and I walked the call chain backwards
  myself" (P4). The two wrong values: "the arithmetic of the
  expected-vs-got pair named the rule that was broken, which named
  the function, in each case a rule stated in the one-line prompt"
  (P5).
- "A locator would have saved nothing here -- the failure already was
  the locator." (P5) "I did not need `fault`/locate-style help at all
  at this size: a traceback plus one def is enough." (P4) "Nothing
  else, honestly." (P6)
- Asked for: the board's cell order stated in the prompt (P5, P6);
  callers of a def (P4); a grep (P4).

Q120, the three LOVA sessions:

- All five blind repairs by `patch --span`, the span the line prints;
  no session read a def to build a find string, which two of run 1's
  did.
- The rule again, and its limit named by the sessions themselves:
  "the replacement was a number the task prompt already tells me must
  be there" (L6); "this pair of tasks did not test the locator's
  weakness, because both planted faults were constants whose correct
  value is stated by the task prompt. A fault at a place the prompt
  does not pin down would not have gone this way." (L4) "Had the line
  proposed ... a constant with no arithmetic story (say `46` in a
  comparison), I would have read the def first." (L6)
- The perturbation score: "actively uninformative: the proposed fix
  and all three runners-up scored 13" (L6); "I do not know whether
  high or low is the good sign" (L4).
- Asked for: the runners-up to say where (L4, L6); the enclosing
  expression on the line (L4, L6); a def name on every line -- the
  constant's had none (L6); the defs the failing example reaches that
  the passing ones do not (L5, as L2 before); a name-use index (L5); a
  named wrong def to be an honest null instead (L5, as L1 and L3).

### Findings of run 2

**F7. The free test run is most of run 1's reading difference, and
the located fault is the rest.** With `probe`, the Python sessions
read 10 922 characters against 27 259 without it and against LOVA's
14 244 -- less in all than LOVA, because the fault report reprints
every failing example (3 454 a session against 1 081 of probe
output). In program text the order stands: Python 7 679, LOVA 3 882,
and the kind differs: Python read a def before every patch, twelve
of twelve; LOVA patched nine of twelve without one. F1 is restated:
at this size a test run that is not an attempt, with the traceback
or the expected/got pair and a free def list, brings Python to one
attempt and one to three defs a fault; the located fault removes the
defs.

**F8. The report's size is the instrument's cost, again.** Exp 28's
"two thirds instrument" returns in a smaller form: the failing
examples printed one by one. After the run the summary groups
identical failures -- one in full, the rest by their lines -- and the
five located reports are 496-917 characters where they were 570-1 710
(ttt-b 1 257 -> 604); a LOVA session's four reports would be 2 547
against the 3 454 measured, which brings the total to parity with
the probe arm and leaves the program-text and blind-repair margins
where they are.

**F9. Split pairs change nothing on the LOVA side.** The cold ttt-b
was blind, as the warm ones were; the cold g2048-a was read the same
way, the same two defs, 1 300 characters, as by L2 and L3 warm. The
pair confound of F5 was Python's, where run 1's sessions diffed the
second program against the first in their heads; the LOVA sessions
never held the program.

**F10. "Fixes all N" was trusted on its own four times of four -- and
the sessions say the prompt still vouched.** Both new faults were
applied blind by both sessions that met them, with no reading, on
the score. But L4 and L6 both name the reason: a stride of 3 on a
board the prompt says has sixteen cells, and 728 beside 729 = 3^6,
are constants a reader can check against the task without the code.
The fault the design was after -- a constant with no arithmetic
story, where the score is the only oracle -- has still not been
planted (Q120 stays open on that half, Q122).

**F11. Constants were outside the locator.** Two of the four locator
faults found today were about zero-parameter defs: a value computed
from a probed def is stale under the probe, and a constant's own
value node was never a target. Both are the single-node hypothesis
applied to the whole program rather than to closures, and both are
closed; the fault class the locator cannot express is now only the
node added or dropped (Q119).

### After run 2, at the sessions' asking

The `fault:` line names its def on every line (`in powers, a
constant`), prints the enclosing expression (`within (range 0 10)`),
and the runners-up say where (`32 for 3 [1195, 1196) in ckey (13)`).
A lead or a miss prints the defs the failing examples reach that
fewer passing ones do, or says that every def reached is reached by
every passing example too -- which is g2048-a's case, so L5's wish
would not have pointed at `move-cell` there; the reach sets do not
separate it. The attempt label counts attempts only.

## Next questions raised by run 2

- **Q122**: a constant with no arithmetic story -- a threshold, a
  weight -- planted where the prompt says nothing, so that "fixes all
  N examples" is the only oracle a session has; the confident-mislead
  rate (Q116) at that place.
- **Q123**: the report's characters as a number in the yardstick: the
  instrument's cost beside the program's, per task, so that a change
  to the summary is measured and not argued.

## Status (after run 2)

At 110-160 lines, with a test run that is not an attempt, both
languages repair every planted fault in one attempt; the Python
session reads one to three named defs a fault from the traceback or
the expected/got pair, the LOVA session reads none on the faults its
locator can express, and the pair ordering does not move the LOVA
numbers. The repair half of the fourth number stands as won on
program text read and on attempts at parity; on total characters the
fault report's own size costs the margin, and it was cut after the
run. What the win still owes is a fault the prompt cannot vouch for
(Q122), the node added or dropped (Q119), and the report's cost as a
measured number (Q123).
