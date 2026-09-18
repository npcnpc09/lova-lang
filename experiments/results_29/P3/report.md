# Session P3 (Python) -- the session's own report, verbatim

Session P3, Experiment 29, Python side. All four tasks green, one attempt each (4 attempts total, 0 failed). No `given` call and no `submit`; every repair was a one-token `patch` found by reading named defs only. The harness log has the exact character counts.

## 1. Per task

**g2048-a -- 1 attempt.**
Read: `--defs` (free), then `--def vx`, `vy`, `order`, `farthest`, then `--def move_cell`, `sweep`. Six defs, ~2 000 characters.
Edit: in `move_cell`'s merge branch, `"m", get(st, "m"))` -> `"m", map_put(get(st, "m"), k, 1))` -- the merged-this-move flag was never set, so a merged tile could merge again.

**g2048-b -- 1 attempt.**
Read: `--defs` (free), then the ten defs I had *not* seen in task a -- `ckey`, `within`, `at`, `all_cells`, `board_of`, `cells_of`, `dir_of`, `step`, `play`, `report`. ~1 900 characters.
Edit: `dir_of`'s default `return 4` -> `return 3`. Direction 4 indexes off the end of `vx`/`vy`'s four-element lists.

**ttt-a -- 1 attempt.**
Read: `--defs` (free), then `line_owner`, `winner`, `other`, `memo_key`, `solve_position`, `best`, then `choose`, `main`, `powers`, `cell`, `place`, `lines`, `empties`, `full` -- effectively the whole program in def-sized pieces, ~3 200 characters.
Edit: in `choose`, `if sc >= st["score"]` -> `if sc > st["score"]` -- with `>=` the fold keeps the *last* best square, not the first, so the chosen square is wrong wherever the game is a tie among several optimal moves.

**ttt-b -- 1 attempt.**
Read: the same fourteen defs again (the layout was identical, so I diffed against the repaired ttt-a in my head): search defs first, then the six helpers. ~2 800 characters.
Edit: `empties`, `range(0, 10)` -> `range(0, 9)` -- a tenth square that `cell` reads as 0, so the board is never `full` and the search explores a phantom move.

## 2. How each fault was found

All four by reading, before any feedback -- the harness never showed me a failure, because no attempt failed. What pointed where in each case:

- **g2048-a**: the *comment above the def* did the locating. `move_cell`'s preamble says `st` carries "the cells that have already merged this move", and the merge branch threaded `"m"` through unchanged while computing a `k` it used only for the board. A field that is read (`map_get(... m ...)`) and never written is visible at a glance.
- **g2048-b**: again the comment -- "anything else is a push to the left, which is the last of them" -- sitting directly above `return 4`, against `vx`/`vy` lists of length four that I had already read in task a. The prose and the constant contradicted each other.
- **ttt-a**: no comment helped; this one came from knowing the shape of the idiom. `best` used `max` (tie-break irrelevant) and `choose` used `>=` (tie-break load-bearing) -- a first-best fold is the convention and the prompt's example output ('4 0') implies a deterministic square.
- **ttt-b**: cheapest of the four, because I had a correct copy of the same program in context from ttt-a. Fourteen defs read as a diff; `range(0, 10)` against nine squares everywhere else (`powers()` of length 9, `main`'s `range(0, 9)` twice) was the only line that disagreed with itself.

Two of four faults were caught by the *program's own prose* contradicting its code; one by an intra-program inconsistency; one by idiom knowledge alone.

## 3. What I would have wanted and did not have

- **A diff against a sibling.** Tasks a and b are the same program with different plants. For ttt-b I paid full reading price for a program I had already read and repaired, when one `diff` would have printed one line. This is an artefact of the pairing, but it is also the realistic case: repairing a program you have a known-good relative of.
- **More than one def per command.** Fifteen separate `show --def` invocations to cover a 160-line program is more shell than reading. A `--def a,b,c` or `--defs-body` would not change what I read, only the ceremony. (I worked around it with a `for` loop in one Bash call.)
- **Something that runs the tests without spending an attempt.** The brief is explicit that none exists, and the design point is clear, but the honest consequence is that I never once looked at a failure message -- I over-read rather than risk an attempt. If the measured numbers are attempts *and* characters, the incentive as set pushes reading up. A free "which of the hidden tests fail, without a patch" would likely have halved my reading on ttt-a.
- **Not wanted, notably:** a fault locator. On 110-160 lines of Python with named defs and comments that state the intent, reading found all four faults on the first pass. At this size the free `--defs` list plus per-def reading was enough; the null finding is that the failure channel was never needed.
