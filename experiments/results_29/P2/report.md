# Session P2 (Python) -- the session's own report, verbatim

All four tasks green. 4 attempts total (1 per task, 4/4 first-try). `given` never used; no failure output was ever produced, so no repair was driven by harness feedback.

## 1. Per task

**g2048-a -- 1 attempt.**
Read (after the free `--defs` listing): `vx`, `vy`, `order` (one call), then `farthest`, `move_cell`.
Edit: in `move_cell`'s merge branch, the merged-this-move flag was never set -- the record was rebuilt with `"m", get(st, "m")`. Patched to `"m", map_put(get(st, "m"), k, 1)`.

**g2048-b -- 1 attempt.**
Read: `sweep`, then `ckey`, `within`, `at`, `dir_of`.
Edit: `dir_of` returned `4` for `l` (the fall-through case) where the direction numbering is 0-3. Patched the `return 4` to `return 3` (found with a two-line anchor `return 2 / return 4` to keep the match unique).

**ttt-a -- 1 attempt.**
Read: `solve_position`, `best`, then `choose`, `main`.
Edit: `choose`'s tie-break was `if sc >= st["score"]`, which makes the *last* equally-good square win. Patched to `>`, so the first maximal square is chosen.

**ttt-b -- 1 attempt.**
Read: `lines`, `line_owner`, `winner`; then the small helpers in one call -- `powers`, `cell`, `place`, `empties`, `full`, `other`, `memo_key`.
Edit: `empties` iterated `range(0, 10)` over a nine-square board (and `powers()` only has nine entries, so square 9 is an IndexError as well as a phantom move). Patched to `range(0, 9)`.

## 2. How each fault was found

All four by reading, before any feedback -- the harness never showed me a failure, because no attempt failed.

The reading was cheap because the `--defs` listing is free and gives names, line numbers and arities: that alone lets you rank suspicion and read three to ten small functions instead of a 110-160-line file. My ranking rule each time was "read the defs the task prompt's hard clauses live in":
- 2048's prompt says *a tile merged this move cannot merge again* and *the traversal order decides which pair merges* -- so `move_cell`, `farthest`, `order`, `vx`/`vy`, `sweep`. Both 2048 faults fell inside that set; the -a fault is literally the clause about double merging, and the -b fault was the last unread thing on the move path (`dir_of`) after the traversal came out clean.
- Tic-tac-toe's prompt says *memoised negamax*, *chosen square*, *score for the side to move* -- so the search first. In -a the search was correct except the `>=`, which is visible as a tie-break policy, not a bug, so I had to reason about "which square would the reference pick" rather than "is this wrong"; I patched it on that reasoning and it held. In -b the search and the win detection were clean, so I read the whole helper layer (all tiny) and `range(0, 10)` over nine squares is self-evident.

Two of the four faults (`dir_of` -> 4, `empties` -> range 10) would have crashed with an IndexError and so would have been located instantly by a failure trace too; the other two (missing merge flag, `>=`) are silent wrong values, and only reading found them.

## 3. What I would have wanted and did not have

- **A grep over the program.** The one thing I repeatedly wanted was "show me every line mentioning `m`" or "every `range(`" -- a cheap, targeted read that is narrower than a whole def. Reading a def is the smallest unit on offer, so a 23-line `move_cell` is read in full to check one field.
- **The prompt's clauses linked to defs.** I did this by hand (prompt clause -> likely def name) and it worked four times out of four; it is the whole method and nothing in the harness supports it.
- **A dry run.** There is deliberately no way to run the tests without spending an attempt, so a patch you are unsure of (the `>=` tie-break) is a gamble. I would have wanted one free "run with this edit" -- though note the measured number is attempts, so this is exactly the thing the experiment is pricing.
- Honest null: the failure-message channel contributed nothing on this side, since nothing failed. If the numbers are compared with the LOVA side, the comparable quantity here is characters read, not diagnostics used.
