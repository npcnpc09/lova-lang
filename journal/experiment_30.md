# Experiment 30 -- The fault in one line (Q123)

**Date:** 2026-09-23
**Scripts:** `tools/brief/replay.py`, `tools/brief/measure.py`, `tools/brief/zoo.py`, `tools/brief/trial.py`
**Status:** Done, one pilot run (15 paired cases, one session each, Claude Sonnet). **WIN on size; PARTIAL (pilot) on repair.**

## Hypothesis

The second of the four numbers -- context spent understanding each
failure -- has stood as "behind" since Exp 19 (LOVA 594 characters a
failure, Python 71). If most of what a failure prints is schema and
repetition rather than facts about this fault, a report that keeps only
the facts closes the gap without costing the session anything it used
to repair. Q123 asked for the report's size as a number.

## Method

1. **Replay.** Every logged LOVA failure of Exp 19 run 2 and Exp 21 (22
   submissions, 21 distinct programs) was re-run through today's
   runtime (native VM) and harness, and its feedback re-rendered two
   ways: the full JSON the sessions of Exp 18-29 read, and `brief`
   (`core/brief.py`): stage, kind, line:col, the `[start,end)` span
   `lova_patch` takes, the text there, and one clause saying what is
   wrong. A compile fault is no longer given the test's inputs; a run
   fault or a wrong value gets them in Python's own shape.
2. **Zoo.** One program per fault kind (17), served by the MCP server
   before and after.
3. **Repair trial.** 15 of the replayed faults (all seven step traps,
   four parse errors, two type mismatches, two unbound references),
   each given to two fresh sessions -- one per arm -- that read only the
   task, the card, their last submission and its feedback, and submit
   until the hidden tests pass (at most 5). The arms differ in nothing
   but the report every failure prints.

## Results

**Size, on the replayed faults** (characters a failure):

| | chars/fault |
|---|---|
| as logged in Exp 19/21 | 601 |
| full report, today | 877 |
| brief, today | **193** (4.5x smaller) |

| kind | n | full | brief |
|---|---|---|---|
| parse-error | 8 | 646 | 188 |
| step-limit-exceeded | 7 | 1 623 | 306 |
| type-mismatch | 4 | 393 | 85 |
| unbound-ref | 2 | 550 | 92 |
| wrong value | 1 | 92 | 75 |

Python's 71 in Exp 19 was two wrong values; a LOVA wrong value is now
75. The zoo, as served over MCP: 13 178 characters for 17 faults
before, 3 325 after (4.0x).

**Repair trial** (15 cases a arm):

| arm | fixed | attempts | first-try | feedback read | program emitted |
|---|---|---|---|---|---|
| full | 11 | 41 | 6 | 59 585 | 84 531 |
| brief | **14** | **31** | 7 | **7 774** | 57 987 |

Starting from a step trap (7 cases): full 5 fixed in 25 attempts, brief
7 in 15. Starting from a compile fault (8): full 6 in 16, brief 7 in
16. Per case, brief took fewer attempts on 5, more on 2, the same on 8.

## Findings

- **F1. Most of the full report was not about the fault.** `message`
  restated `repair_hint`; `detail.message` restated it again; the step
  trap printed `hot` twice (as a list and as prose) beside a
  700-character paragraph of advice that is identical on every trap and
  already in the card; `bound` listed what `Nearest:` had chosen; a
  compile fault carried test inputs it does not depend on. The report
  had also grown since Exp 19 (601 -> 877) as each milestone added a
  field.
- **F2. Brief did not cost repairs in this pilot.** The six compile
  faults that stayed compile faults were fixed in one attempt by both
  arms, with one exception (e2#8: full 1,
  brief 2 -- the brief session's first fix compiled and exposed a
  second, logic fault that the full session's rewrite happened to
  remove). The two compile faults that led into a search (o1#3, o3#4)
  and the seven step traps, where the most text was cut, went the
  other way: brief fixed 8 of 9, full 5. The difference in attempts is
  not significant at this n (brief fewer on 5 cases, more on 2) and a
  game-tree search varies widely between sessions; the claim that
  stands is "no worse at an eighth of the reading".
- **F3. The full report's `overrun` misled.** Seven of the eighteen
  sessions that met a step trap said they could not tell how far over
  budget the program was -- six of them in the full arm, whose report
  prints `spent: 7000001, overrun: 1`, which reads as "one step short"
  and is always that, because counting stops at the trap. Sessions
  rewrote correct-but-heavy programs by a guessed amount. Brief drops
  the field; the fact it pretended to give is still missing.
- **F4. The card and the report were saying the same thing.** Static
  advice (what a walker costs, when to change representation) is read
  once in the card; the report now carries only what differs between
  one fault and the next.

## Discussion

The second number was behind partly on content and partly on
packaging, and the packaging is now fixed: a LOVA failure costs a
session about what a Python one does when the failure is of the same
kind, and a compile fault -- which Python reports as a traceback of
comparable length -- costs about 200 characters with a patchable span.
What the report still lacks is not length but one fact (F3).

Changed in this commit: `core/brief.py`; the MCP server answers a
failure with `{ok, stage, kind, fault}` by default and the whole
anomaly under `report: "full"`, and serves compact JSON; the Python
runtime's trap sentence ("div: division by zero") now reaches the
anomaly as `message`, as the native runtime's did; the agent-loop
harness prints brief feedback (`LOVA_REPORT=full` restores the old),
so the next yardstick run measures the new report. The CLI's
multi-line report is unchanged.

## Next questions raised

- **Q141**: the step trap's missing fact -- how far over. Finish the
  run uncounted up to a multiple of the budget (say 4x) and report
  "needs ~N steps", or report the search's node count against the
  budget, so a rewrite is sized rather than guessed.
- **Q142**: the second number re-measured properly -- the Exp 19 tasks,
  ten sessions a language on one model, both arms of the report.
- **Q143**: the CLI's report in the same one-line form under `--brief`,
  or by default when stderr is not a terminal.

## Status

**The fault now costs about 190 characters to read instead of 880,
with no loss of repairs in a 15-pair pilot (brief fixed 14 against 11,
in 31 attempts against 41).** The one fact the sessions asked for -- how
far over budget -- is Q141.
