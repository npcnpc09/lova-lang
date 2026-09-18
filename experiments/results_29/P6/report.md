# Session P6 (Python, Q118: with `probe`) -- the session's own report, verbatim

Session P6, Experiment 29 (Q118), Python side. All four tasks green, one patch each, no failed attempts.

## 1. Per task

**g2048-a** -- 1 attempt.
Read: `probe` (1 failing test), `show --defs` (free), `show --def move_cell`.
Edit: in the merge branch of `move_cell`, `"m", get(st, "m")` -> `"m", map_put(get(st, "m"), k, 1)` -- the merged-tile flag was carried over unchanged instead of being set for the destination cell.

**g2048-b** -- 1 attempt.
Read: `probe`, `show --defs` (free), `show --def vy`, `show --def dir_of`.
Edit: in `dir_of`, the fall-through `return 4` -> `return 3` (the direction index for `l`; 4 is off the end of the `[-1,0,1,0]` vectors).

**ttt-a** -- 1 attempt.
Read: `probe`, `show --defs` (free), `show --def choose`.
Edit: in `choose`, `if sc >= st["score"]` -> `if sc > st["score"]` -- with `>=` the last equal-scoring move wins the tie instead of the first.

**ttt-b** -- 1 attempt.
Read: `probe`, `show --def empties`, `show --def cell` (both in one call).
Edit: in `empties`, `range(0, 10)` -> `range(0, 9)` -- ten squares walked over a nine-entry `powers()` table.

Never used `given` (the whole program) on any task, and never read a second function except where the traceback's caller frame made it obvious which two to look at.

## 2. How each fault was found

- **g2048-a** -- from `probe`'s *values*, not from reading. Expected `4 1 4 0 0 0 4 0 0 0 ...` against got `12 1 8 0 ...`: the score 12 is 4+8, i.e. one tile scored twice in a single move, and the board shows a single 8 where two 4s were expected. That is exactly the "a tile merged this move cannot merge again" clause of the prompt, so the merged-set update was the only place to look. The arithmetic on the score (4 then 8) told me which rule, and the prompt named the rule; `show --defs` then named the function (`move_cell`) and one read confirmed it. Deducing the cell order (the tests' board is column-major) was needed to read the expected value, and cost a minute of thought -- `probe` gave no help there.
- **g2048-b** -- from the traceback, entirely. `IndexError` at `vy`, one line: `[-1,0,1,0][d]`. `vy` itself was correct, so the bad value came from its caller's `d`; the failing input's moves were `"l"`, and `dir_of` is the only thing that turns a move character into `d`. Two short reads, no guessing.
- **ttt-a** -- from `probe`'s values plus the prompt. Score matched (`0` both sides), square did not (expected 1, got 8: the first vs the last empty square). A tie-break-direction fault, so `choose`/`best` was the only candidate; `choose` had the `>=`.
- **ttt-b** -- from the traceback. `cell` -> `empties` -> `full`, `IndexError` on the `powers()` lookup: an out-of-range square index inside `empties`. One read showed `range(0, 10)`.

So: two found by traceback (address given directly by the frame list), two found by comparing expected against got and matching the deviation to a clause of the task prompt. In neither of the value cases did I read more than one function.

## 3. What I would have wanted

- **The cell order stated.** g2048-a's prompt says "cell order as `board-of` takes them", which is a pointer into code I was trying not to read. I had to reverse-engineer column-major order from the expected value before the failure meant anything. One sentence of prose, or one worked example in `tasks`, would have removed that step.
- **Nothing else, honestly.** At 110-160 lines the traceback's frame list *is* the fault address for the two crashing faults, and for the two wrong-value faults the expected/got pair plus the one-paragraph task prompt narrowed it to a single named function out of ~15 before I read anything. `--defs` (a free index of names, line numbers and parameters) was doing most of the localisation work; it is the cheapest thing in the harness and I used it on three of four tasks.
- A minor note on the harness: each successful patch prints `[<task> attempt 2]` although it was my first attempt on that task -- the counter appears to be one-based over something else. My true count is 1 attempt per task, 4 total, 0 failures.
