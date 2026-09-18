# Session P5 (Python, Q118: with `probe`) -- the session's own report, verbatim

Exp 29 / Q118 -- session P5, Python side. All four tasks green; **4 patches, 4 tasks, zero failed attempts** (the harness labelled each one "[task attempt 2] PASS", but I made exactly one patch per task and no submits).

## 1. Per task

**g2048-a** -- 1 attempt.
Read: `tasks`, `probe`, `show --defs` (free), `show --def move_cell`.
Edit: in the merge branch of `move_cell`, `"m", get(st, "m"))` -> `"m", map_put(get(st, "m"), k, 1))` -- the merge was never recorded in the merged-this-move map.

**g2048-b** -- 1 attempt.
Read: `probe`, `show --defs` (free), `show --def vy`, `show --def vx`, `show --def dir_of`.
Edit: `dir_of`'s fallthrough `return 4` -> `return 3` (the index for `l`; the vectors are 4-element lists).

**ttt-a** -- 1 attempt.
Read: `probe`, `show --defs` (free), `show --def choose`.
Edit: `if sc >= st["score"]:` -> `if sc > st["score"]:` in `choose` -- the `>=` made the *last* tied square win instead of the first.

**ttt-b** -- 1 attempt.
Read: `probe`, `show --def empties`, `show --def cell`.
Edit: `range(0, 10)` -> `range(0, 9)` in `empties`.

Total reading: four `probe`s, two free `--defs` listings, and seven single-function `--def` reads. I never used `given`; I never read a whole program.

## 2. How each fault was found

Every one was found **from `probe`**, not by reading the program; the reads were only to confirm and get the exact text to patch.

- **g2048-a** -- the only failure by value, and the value said everything: expected `4 ... 4 4 0 0` (row `2 2 4` -> `4 4`), got score 12 and `8`. 4+8 = 12 is exactly "the merged tile merged again", which is the one rule the prompt spells out. That pointed at the merged-flag map, so I read `move_cell` and the omission was visible in one line -- the branch that merges passes `get(st,"m")` through unchanged where every other field is updated.
- **g2048-b** -- a traceback, and the traceback *was* the address: `vy` at line 70, `IndexError`, on the move `l`. `vy`/`vx` were 4-element lists indexed by `d`, so `d` was out of range; the only producer of `d` is `dir_of`, and its fallthrough (the `l` case) returned `4`. Two reads to rule the vectors in, one to find it.
- **ttt-a** -- expected `1 0`, got `8 0`: same score, different square, and 8 is the last empty square while 1 is the first. "Same score, last instead of first" is a tie-break comparison, i.e. `>=` where `>` was meant. Confirmed in `choose` on the first read.
- **ttt-b** -- traceback through `full` -> `empties` -> `cell`, `IndexError` on the power table. Nine squares, so a 10-wide range; the read confirmed `range(0, 10)`.

The general shape: for the two tracebacks the frame list named the faulty function directly, and the fault was one token in it. For the two wrong-value failures, the *arithmetic of the expected-vs-got pair* named the rule that was broken (double merge; tie-break order), which named the function, in each case a rule stated in the one-line prompt.

## 3. What I would have wanted and did not have

Honestly: very little at this size. Specifics --

- The board encoding cost me a minute on g2048-a: the prompt says "cell order as `board-of` takes them" without saying what that is, and the sixteen cells turned out to be column-major. I inferred it from the expected string rather than being told; reading `board_of` would have cost me a charged read. A one-line statement of the input encoding in `tasks` would be free and would not give the fault away.
- `probe` prints only failing tests but does not say how many tests exist per input class; knowing that exactly 1 of 8 failed in every task made me confident the fault was narrow and local, which is real information -- that was useful and I would keep it.
- What I did *not* need: `given`. At 110-160 lines the traceback or the expected/got pair narrowed the program to one function every time, and `--defs` (free) was enough to turn a function name into a read target. A locator would have saved nothing here -- the failure already was the locator.
- The only thing that would genuinely have helped: for the wrong-value failures, the *second* failing test would be worth showing even when only one fails, because with a single example I had to reason about whether `8` was "last tied" or "wrong search"; two examples would have settled it without reasoning. Null finding, though -- the reasoning was cheap.
