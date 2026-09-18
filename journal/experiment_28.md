# Experiment 28 -- The located fault in the repair loop (Q96)

**Date:** 2026-09-18
**Script:** `experiments/experiment_21_repair.py` (the examples arm: a session named `e*`, and the `fault` command)
**Status:** In progress. Three fresh Opus sessions, e1-e3, LOVA, against Exp 21's r1-r3 in both languages.

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

*(pending)*

## Findings

*(pending)*

## Discussion

*(pending)*

## Next questions raised

*(pending)*

## Status

In progress.
