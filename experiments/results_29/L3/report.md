# Session L3 (LOVA) -- the session's own report, verbatim

Exp 29, session L3 (LOVA arm) -- all four tasks green, one patch attempt each, no failed attempts.

## 1. Per task

**g2048-a -- 1 attempt, READ (~1 300 chars)**
- Ran `fault`. One example failed (7/8 pass): board `2 0 0 0 2 0 0 0 4 0 0 0 ...` moved `l`, expected score 4 / tile 4+4, got score 12 / tile 8. The line was a *lead*, not a repair: `51:30 dy -- `dy` here should be `dx` [fixes this and 2 of 7 other examples; the fault may be elsewhere] (search cut short by the time budget)`.
- I did not trust it, for two reasons: the qualifier said so, and the symptom already named the rule that was broken -- "a tile merged this move cannot merge again" (2+2->4 then 4+4->8 in one move, score 4+8=12). A direction-vector bug cannot produce a double merge.
- `show --defs` (free) -> read `farthest` (198 ch) to kill the lead: its recursive call is `(farthest b nx ny dx dy)`, and the proposed `dx dx` is plainly wrong. Then read `move-cell` (1 102 ch), the only per-cell mover.
- Fault found on sight: in the merge branch the state is rebuilt with `m (get st m)` -- the merged-tile map is copied unchanged, so the new tile is never marked as having merged.
- Edit: `patch --def move-cell --find "m (get st m))" --replacement "m (map-put (get st m) k 1))"`. PASS.

**g2048-b -- 1 attempt, BLIND (0 chars read)**
- `fault`: 4/8 examples fail with `domain-error`, trapped at [1624,1647) -- which the free def list showed as inside `vy`, i.e. an index out of range. Line: `118:9 the literal 4 should be 3 [fixes all 8 examples] [changes the answer on 13 of 48 nearby inputs]` in `dir-of`.
- Trusted it without reading: "fixes all 8", and a direction table indexed 0..3 with a trap in the direction lookup is self-consistent.
- Edit: `--def dir-of --find " 4" --replacement " 3"`. PASS.

**ttt-a -- 1 attempt, BLIND (0 chars read)**
- `fault`: 3/8 fail, chosen square 8 where 1/2 expected. Line: `79:19 (ge sc (get st score)) -- `ge` should be `gt` [fixes all 8] [changes 8 of 48 nearby]` in `choose`.
- Trusted it: `ge` keeps the *last* best square, `gt` the first, and "8 instead of 1" is exactly a last-vs-first tie-break with the prompt's square-0-first order.
- Edit: `--def choose --find "(ge sc (get st score))" --replacement "(gt sc (get st score))"`. PASS.

**ttt-b -- 1 attempt, BLIND (0 chars read)**
- `fault`: 7/8 fail, all `domain-error`. Line: `37:63 the literal 10 should be 9 [fixes all 8] [changes 4 of 48 nearby]` in `empties`.
- Trusted it: nine squares is a clause of the prompt; `(range 0 10)` walks off the board.
- Edit: `--def empties --find "0 10" --replacement "0 9"`. PASS.

Totals: 4 attempts, 4 tasks; ~1 300 characters read (all of it on g2048-a); ~40 characters written. Three of four repaired blind. (The harness labelled each successful patch "attempt 2"; I issued exactly one patch per task.)

## 2. What the `fault:` line did

It did two different jobs, and its own hedge told me which one I was getting.

- When it said **"fixes all 8 examples"** plus a nearby-input count, I patched without opening the file -- three times, three first-try passes, zero characters read. In each of those the edit was also a *clause of the task prompt* ("nine characters", four directions, "the chosen square"), so the line and the prompt vouched for each other. That combination is what I acted on; I would not have acted on "fixes all examples" alone if the edit had contradicted the prompt.
- When it said **"fixes this and 2 of 7 other examples; the fault may be elsewhere"** -- and added "search cut short by the time budget" -- it was worth nothing as a diagnosis and something as a signal. Its named token (`dy`->`dx` in `farthest`'s recursion) was wrong in a way I could refute in 198 characters. What actually located the fault was the *failure value*: score 12 where 4 was expected is a double merge, and a double merge lives wherever the merged-set is written. The line cost me one 198-char read to dismiss; the free `--defs` list then made `move-cell` the obvious and only candidate.
- Useful side effect I did not expect: `trapped at [span)` cross-checked against the free def list (spans and sizes) told me *which def* trapped without reading anything. On g2048-b that turned the fault line from a claim into a corroborated claim for free.

So: an address when it is confident, and when it is not, a prompt to read the failing *value* instead. It never misled me into a wrong patch, but on g2048-a it pointed at the wrong def entirely -- it is only as good as the single-node-edit hypothesis, and this fault (a dropped `map-put`, i.e. an argument replaced by a sub-expression of itself) is not reachable by the edits it probes.

## 3. What I wanted and did not have

1. **A field/writer index for the state record.** Once I knew "the merged map is never written", I still had to read 1 102 characters to find where. A free listing of "which defs read/write `m`, `s`, `moved`, `b`" would have cut that read to nearly zero -- the equivalent of the free `--defs` list, one level down. That single read is my whole reading cost for the experiment.
2. **`--find` by span.** The fault line prints the exact span (`[2199, 2201)`), but the patch command takes a substring that must be unique in the def. My first g2048-b patch was rejected because `4` also occurs inside the codepoint `114`. No attempt was burned, but the tool already knows the span it wants patched and made me reconstruct it.
3. **A scratch evaluation.** To confirm the double-merge hypothesis I would have liked to run one sub-expression (`(move-cell st 0 0 3)`) and look at the state, instead of reading the whole def and reasoning statically. There is no way to evaluate anything without submitting.
4. **A wider net when the search is cut short.** The g2048-a line admitted the time budget truncated it. I would rather have had "no single-node edit fixes this; the examples that fail share <symptom>" than a best-of-a-partial-search edit in the wrong def -- the partial answer is the one shape of output that can cost reading rather than save it.
