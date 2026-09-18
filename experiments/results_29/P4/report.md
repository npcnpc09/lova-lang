# Session P4 (Python, Q118: with `probe`) -- the session's own report, verbatim

Exp 29 / Q118, session **P4**, Python side. All four tasks green, **one attempt each (4 patches, 4/4 first-try)**, no submits, no `given` calls, no full-program reads.

## 1. Per task

**g2048-a -- 1 attempt.**
Read: `probe` (1), `show --defs` (free), `show --def move_cell` (1 def).
Edit: in `move_cell`'s merge branch, `put(... "m", get(st, "m")) ...` -> `put(... "m", map_put(get(st, "m"), k, 1)) ...` -- the merged-this-move flag was carried through unchanged, so nothing was ever marked merged.

**g2048-b -- 1 attempt.**
Read: `probe` (1), `show --defs` (free), `show --def vy`, `show --def sweep`, `show --def dir_of` (3 defs).
Edit: `dir_of`'s fall-through `return 4` -> `return 3` (the code for `l`; the direction vectors are 4 long, so 4 indexed off the end).

**ttt-a -- 1 attempt.**
Read: `probe` (1), `show --defs` (free), `show --def choose` (1 def).
Edit: `if sc >= st["score"]:` -> `if sc > st["score"]:` in `choose` -- with `>=` every tying move overwrote the previous one, so the last equal-scoring square won instead of the first.

**ttt-b -- 1 attempt.**
Read: `probe` (1), `show --defs` (free), `show --def empties` + `show --def cell` (2 defs).
Edit: `empties`: `range(0, 10)` -> `range(0, 9)`.

Note on counting: every patch printed `[task attempt 2]` even though it was my first patch, so the harness's attempt counter appears to number the probe as attempt 1 (the brief says probe is not an attempt). Worth checking before the numbers are tallied.

## 2. How each fault was found

- **g2048-a -- from the value, then one def.** `expected=4 ... 4 0 0 0 4 0 0 0` vs `got=12 ... 8`: score 12 = 4 + 8, i.e. the new 4 merged again with the other 4 in the same sweep. "A tile merged this move cannot merge again" is a clause of the prompt, so the fault had to be in whatever marks a tile merged. `--defs` named `move_cell`; its merge branch writes `"m"` back unchanged, which is visible in one read. The failing test was maximally diagnostic -- it was also what told me the cell order is column-major, which I needed to confirm the merge reading.
- **g2048-b -- from the traceback, top frame down.** `IndexError` in `vy` at `[-1,0,1,0][d]`, i.e. a bad direction, not bad geometry. `vy` itself was clean, `sweep` just passes `d` through, so the producer was `dir_of`; the missing case was `l`/108 falling through to a literal `4`. Three defs, each one frame of the traceback. The traceback was an address, not a diagnosis -- it pointed at the *victim* (`vy`), and I walked the call chain backwards myself.
- **ttt-a -- from the shape of the wrong value.** Score correct (`0`, a draw), square wrong: `8` where `1` was wanted, and 8 is the *last* empty square while 1 is the first. "Last instead of first among equals" is a tie-break, so `choose` was the only place to look, and `>=` was on the first line I read of it.
- **ttt-b -- from the traceback.** Index error inside `cell` reached from `empties`; `empties`'s own `range(0, 10)` against a nine-square board is self-evident once the def is on screen. I read `cell` too, only to confirm `powers()` is indexed by `k` (9 entries) rather than `cell` being at fault -- that read was arguably unnecessary.

Pattern: in all four, `probe`'s output (a value diff or a traceback) narrowed the search to one or two defs before I read any program text; the `--defs` listing then supplied the name. I never read a whole program, and I never guessed -- each edit was made after seeing the offending line.

## 3. What I would have wanted and did not have

- **`probe` should show more than the first/one failure per call when several differ.** Here exactly one test failed each time, so it did not bite, but with two failures the second one is often what disambiguates.
- **A way to see a def's *callers* cheaply.** For g2048-b I walked `vy` -> `sweep` -> `dir_of` by reading each def in full, when what I needed was "who produces `d`". The traceback gave callers for free in that case; if the bad value had been stored and used later, I would have had to read much more.
- **Grep across the program, charged as a read.** For "where is `"m"` written", one search would have replaced reading a def. `--defs` + `--def NAME` assumes I can already name the function.
- **Nothing about the failures was misleading**, which is worth recording: no confident-but-wrong signal, and the two tracebacks pointed at the victim rather than the cause but never at a wrong *area*. Null finding on that front.
- I did not need `fault`/locate-style help at all at this size: a traceback plus one def is enough. That is the honest comparison point for the LOVA side -- Python's cost here was 1 probe + 1-3 defs per fault, and the traceback did the locating for two of the four.
