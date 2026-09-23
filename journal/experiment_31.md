# Experiment 31 -- How far over: the step trap measures the run (Q141)

**Date:** 2026-09-23
**Scripts:** `tools/brief/trial.py` (arms `brief` and `needed`), `tools/brief/replay.py`
**Status:** Done, 36 sessions (Claude Sonnet). **WIN, suggestive (pilot n).**

## Hypothesis

Exp 30 F3: a step trap stops counting at the budget, so it could not say
how far over the program was, and sessions rewrote correct-but-heavy
programs by a guessed amount. If the trap says how many steps the run
needs, a session sizes its rewrite -- a tweak for 1.1x, a new algorithm
for 4x -- and search tasks take fewer attempts.

## Method

`lova_execute`, on a `step-limit-exceeded` trap, runs the program again
under 4x the budget (`probe`, default 4; 0 turns it off) and puts
`needed` (the steps the run took, or `null` for "still running at 4x")
and `probe_limit` into the anomaly's detail; the one-line fault reads
"the run needs 23.6M steps (3.4x the budget)" or "still running at 28.0M
steps (4x the budget): non-terminating, or far too costly". The repeat
happens only when the program touches nothing outside the process --
static analysis finds no `read-fs`, `write-fs`, `read-clock`, `net-send`
or `net-recv` -- so no effect is ever doubled. On the native runtime the
probe cost the costliest replayed case 0.9 s.

The nine search-shaped faults of Exp 30 (seven step traps, two compile
faults that lead into a search), two sessions an arm: `brief` (Exp 30's
report; its Exp 30 session is one of the two) and `needed` (the same,
with the probe). Everything else as Exp 30: card, task, last submission,
feedback, at most 5 attempts.

What the probe says about the seven replayed traps: 1.1x, 1.2x, 1.4x,
2.1x, 3.4x, 3.8x, and one over 4x.

## Results

| arm | sessions | fixed | attempts (a failure counted 6) | first-try |
|---|---|---|---|---|
| brief | 18 | 14 | 62 | 4 |
| needed | 18 | **17** | **49** | 4 |

Per case (attempts, X = not fixed), brief / needed:

| case | a | b | c | d | e | f | g | h | i |
|---|---|---|---|---|---|---|---|---|---|
| brief | 2, X | 2, 5 | 1, 1 | 1, 5 | 3, X | 4, 2 | 2, 1 | X, X | 4, 5 |
| needed | 2, 3 | 3, X | 1, 1 | 1, 3 | 2, 3 | 3, 2 | 1, 2 | 3, 5 | 4, 4 |

By case mean, needed is better on six, worse on one (b), level on two.

## Findings

- **F1. The number was used.** Sessions quoted it back ("needing only
  1.2x the budget, which correctly pointed to a missing efficiency
  optimization rather than a logic bug"; "the required-vs-budget ratio
  (3.4x, then 2.0x)"), and tracked progress by it across attempts ("28M
  -> 17.5M -> 7.3M -> pass"). At 1.1-1.4x the sessions made one local
  change; at 3-4x they changed the representation or the algorithm.
- **F2. Fixed 17 of 18 against 14 of 18, attempts 49 against 62.** The
  direction held on six of nine cases. A sign test over the cases gives
  p = 0.125: suggestive, not established. The game-tree search varies
  widely between sessions of one model on one input.
- **F3. The card had a wrong fact, found six times.** Six sessions (in
  both arms) spent an attempt on `pow`: the card listed it beside `inc`
  and `abs` and said "an operator costs 1 step", but `pow` is a prelude
  loop -- 37 steps plus 21 per unit of exponent, `(pow 3 8)` 205 against
  `mul`'s 1. The card now says so. The trap's `hot` list found it every
  time; the card should have prevented it.
- **F4. What the sessions still asked for** is "why", not "how much":
  node counts, pruning quality, which fix buys what. That is the
  algorithm's business rather than the language's, and a report that
  guessed at it would mislead as often as help.

## Discussion

With Exp 30 the step trap went from 1 600 characters to 300; with this
it carries the one fact those characters never held. The second number
(context per failure) is at parity with Python on like failures, and
the search tasks where the first number (attempts) fell behind in Exp 19
now fail less and cost fewer attempts in this pilot. Whether that gap is
closed is Q142's run, with Python beside it -- Python's own answer to
"too slow" is a timeout that says nothing at all, so this is the first
place the report could give LOVA a lead rather than parity.

Changed: `core/mcp_server.py` (`_probe_needed`, `probe` in the
`lova_execute` schema), `core/brief.py` (the needed clause),
`corpus/language_card.tmpl.md` and the generated card (the probe, and
`pow`'s cost), `tests/test_brief.py` (four tests: measured, runaway,
an effectful program not repeated and its file written once, probe
off).

## Next questions raised

- **Q144**: the same arm against Python with a wall clock on the Exp 19
  search task -- does "needs 3.4x" beat "timed out after 10 s"?
- **Q145**: `pow` and the other prelude loops that read like operators
  (`digits`, `gcd2`): native operators, or a cost column in the card
  generated from measured steps, as the card's examples already are.

## Status

**A step trap now says how many steps the run needs; on nine search
faults, 17 of 18 sessions fixed them against 14 of 18 without it, in 49
attempts against 62 (pilot, p = 0.125).** The card no longer calls
`pow` cheap.
