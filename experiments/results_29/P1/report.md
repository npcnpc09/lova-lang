# Session P1 (Python) -- the session's own report, verbatim

## Exp 29, session P1 (Python side) -- all four green, 4 attempts total, 0 failures

### 1. Per task

**g2048-a -- 1 attempt.**
Read: `show --defs` (free), then `--def farthest`, `--def move_cell`.
Edit: in `move_cell`'s merge branch the merged-flag map was rewritten unchanged --
`"m", get(st, "m")` -> `"m", map_put(get(st, "m"), k, 1)`.
Rationale: the prompt says "a tile merged this move cannot merge again", and `move_cell` reads `m` to veto a second merge but never wrote to it, so the flag map was dead.

**g2048-b -- 1 attempt.**
Read: `--defs` (free), then `sweep`, `order`, `vx`, `vy`, `dir_of`, `within`, `at`, `ckey`.
Edit: in `dir_of`, the fallback for `l` (108) returned `4` -> `3`.
Rationale: `vx`/`vy` are 4-element tables, so 4 is out of range; directions are 0..3 and `l` is the only one left.

**ttt-a -- 1 attempt.**
Read: `--defs` (free), then `solve_position`, `best`, `lines`, `line_owner`, `winner`, `choose`, `main`, `powers`, `cell`, `place`, `empties`, `full`, `other`, `memo_key` -- effectively the whole program, in def-sized pieces.
Edit: in `choose`, `if sc >= st["score"]` -> `if sc > st["score"]`.
Rationale: every other def was provably right, and `>=` changes only the tie-break -- it returns the *last* equal-best square instead of the first, which is exactly what a task whose answer is a specific square number is sensitive to.

**ttt-b -- 1 attempt.**
Read: `--defs` (free), then `solve_position`, `best`, `main`, then `choose`, `memo_key`, `other`, `full`, `empties`, `winner`, `line_owner`, `lines`, `place`, `cell`, `powers`.
Edit: in `empties`, `range(0, 10)` -> `range(0, 9)`.
Rationale: `powers()` has nine entries, so `cell(b, 9)` indexes off the end.

### 2. How each fault was found

**By reading, every time.** No attempt failed, so the harness never showed me a failure message and the failure format contributed nothing to this session. Three of the four faults were found by reading the def the task prompt pointed at (merge rule -> `move_cell`; direction letters -> `dir_of`; square numbering -> `empties`), and one (`>=` in `choose`) by elimination after reading everything else.

What did the pointing, in order of usefulness:
- **The prompt sentence.** "A tile merged this move cannot merge again" named the invariant; the fault was the one place that invariant is enforced. Same for "the traversal order decides which pair merges" (sent me to `sweep`/`order` first on g2048-b -- a miss, but a cheap one).
- **Internal consistency between small defs.** `dir_of` returning 4 and `empties` ranging to 10 are both wrong *relative to a table three lines away* (`vx`/`vy` of length 4, `powers()` of length 9). Neither needed the task semantics at all -- a linter or a reader with both defs in view catches them. These are the two crash faults; had I attempted blind, the traceback would probably have handed them to me for one attempt.
- **Elimination.** `>=` in `choose` is the only fault I would call genuinely hard: it is well-typed, plausible, and locally reasonable. I only trusted it after reading all fifteen defs and finding nothing else off. Even then it was a judgement call about tie-break convention, not a proof.

**The free def list (`--defs` with line numbers and parameters) was the single most valuable instrument.** It let me pick targets, and it made "read the whole program" unnecessary -- I never used `given` once. For g2048 that mattered: I read 2 of 24 defs on task a and 8 of 24 on task b.

**An honest confound in my numbers.** Each pair is the same program twice. By the time I reached ttt-b I had already read every ttt def in its correct form on ttt-a, so ttt-b was a diff against a known-good copy held in my context, not a repair from cold. That is not how a real session meets a program, and it deflates ttt-b's reading cost (and probably its attempt count). g2048-b is less affected -- I had only read 2 of the 24 defs on g2048-a -- but it is not clean either. If the comparison with the LOVA side is to hold, the ordering effect should be counted, or the pair members split across sessions.

### 3. What I wanted and did not have

- **A way to run the tests without spending an attempt.** This is the big one, and it bent my behaviour: I read the whole of ttt-a def by def rather than test a one-character hypothesis, purely because a probe costs the headline number. Reading was the cheap currency, so I spent it -- which means the attempts number here partly measures my risk aversion, not the difficulty of the faults. On `>=` I was reasonably confident but not certain; a free dry run would have cost me ~zero reading and one second.
- **Nothing else, honestly.** No fault locator, no static check, no debugger was wanted. Four programs of 110-160 lines, sliced into named 3-10 line defs, are small enough that reading the suspect region wins. Two of the four faults would have been caught by `pyflakes`-grade reasoning about constant-list lengths; a plain Python traceback would have caught the same two. That is a null finding for any richer instrument at this size: **the free def index plus the task prompt was sufficient**, and the instrument that would have helped most is the trivial one (a test run that is not an attempt).
- **One small friction:** `patch --find` needs a string unique in the whole program, so `return 4` had to be given with a line of context and exact indentation. Addressing the patch by def name (`--def dir_of --find "return 4"`) would have made that a non-issue.
