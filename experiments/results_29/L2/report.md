# Session L2 (LOVA) -- the session's own report, verbatim

Experiment 29, session L2 (LOVA arm). All four tasks green, one patch each -- no failed attempts, no submits, no `given`.

## 1. Per task

**g2048-a -- 1 patch. Read: `--defs` (free), `farthest` (198 ch), `move-cell` (1102 ch). READ, not blind.**
`fault` said `51:30 dy -- `dy` here should be `dx`` in `farthest`, marked "fixes this and 2 of 7 other examples; the fault may be elsewhere" (and "search cut short by the time budget"). I did not trust it: the single failing example (`"2 0 0 0 2 0 0 0 4 0 0 0 0 0 0 0"` + `"l"`, expected score 4, got score 12 / a single 8) said plainly that a tile merged this move had merged again -- a merge-flag bug, not a direction bug. I read `farthest` anyway (cheap, 198 ch) to rule the lead out; it was correct -- the `dy` at 51:30 is the recursive call's own argument. Then I read `move-cell`, where the merge branch rebuilt the state with `m (get st m)` -- it never marked the merged cell. Patch in `move-cell`: `m (get st m))` -> `m (map-put (get st m) k 1))`. Passed.

**g2048-b -- 1 patch. Read: `dir-of` (90 ch). READ (only to build a unique `--find`).**
`fault`: `118:9 the literal 4 should be 3 -> 3 [fixes all 8 examples] [changes the answer on 13 of 48 nearby inputs] [def dir-of reached by 8 of 8]`. I believed it immediately -- a domain-error plus a direction table whose fourth case is out of range is the whole story. I read the 90-character def only because `patch` needs a text that occurs once in the def and the excerpt the line gives is the bare literal `4`, which is not unique. Patch: ` 4))` -> ` 3))` (the `cond` default for `l`). Passed.

**ttt-a -- 1 patch. Read: nothing. BLIND.**
`fault`: `79:19 (ge sc (get st score)) -- `ge` should be `gt` [fixes all 8 examples] [8 of 48 nearby inputs] [def choose reached by 6 of 8]`. Trusted on sight: the failures were all "picked square 8 where 1 or 2 was expected", i.e. a tie on score letting the *later* square win, which is exactly `ge` where `gt` belongs. The excerpt was a whole unique sub-expression, so I patched it verbatim without reading `choose`. Passed.

**ttt-b -- 1 patch. Read: nothing. BLIND (with a guessed find string).**
`fault`: `37:63 the literal 10 should be 9 [fixes all 8 examples] [4 of 48 nearby inputs] [def empties reached by 7 of 8]`, with 7 of 8 examples in domain-error. A nine-square board scanned to 10 is self-evident. The excerpt is again a bare literal, so I gambled on the surrounding text being `... 0 10)` and patched `0 10)` -> `0 9)` in `empties` without reading it. It hit.

Counted reading: ~1390 characters in total, 1300 of it on g2048-a; two tasks cost zero reading.

## 2. What the `fault:` line did

It is an address plus a confidence label, and the label was the load-bearing part. Three of four lines said **"fixes all 8 examples"** and all three were the planted fault exactly; I applied them without reading the def (twice truly blind, once reading 90 characters only for patch syntax). The one line that said **"fixes this and 2 of 7 other examples; the fault may be elsewhere"** was wrong, and its hedge was accurate -- I read it as "this is a coincidence that happens to move one example", which is what it was. So the two-tier wording (repair vs lead) did its job: it told me when to spend reading and when not to.

The second oracle ("changes the answer on N of 48 nearby inputs") I read but did not act on; with "fixes all 8" already present it added nothing. It would have mattered if two candidate edits had been offered.

What the line did *not* do is diagnose. On g2048-a I found the fault from the failing example's own numbers (score 12 and a lone 8 where 4 and two 4s were due) -- the deviation named the rule that was broken ("a tile merged this move cannot merge again"), which pointed at `move-cell`; the `fault:` line pointed one def away. The `[def X is reached by N of M examples]` tag was the more useful half there: it told me `farthest` was on every path, i.e. that a real fault there would have broken more than one example -- evidence against the lead.

## 3. What I would have wanted

- **The excerpt is not a patchable find.** When the fault is a bare literal (`4`, `10`), the line gives a span but `patch` takes text that must be unique inside the def. Twice that forced me either to spend a read purely for syntax (g2048-b) or to guess the surrounding characters (ttt-b, which happened to work). `patch --span 1589-1591` -- or the line printing a few characters of context around the literal, enough to be unique -- would have made both fully blind at zero reading.
- **A wider context line when the lead is weak.** On g2048-a I would have paid for "here are the three defs the failing example ran through that the passing ones did not", which is the discriminating information and which the harness already computes (it knows reach counts per def). Instead the only way down was to read a 1102-character def.
- **Nothing about the `hot`/step machinery was needed**; every fault here was a wrong value or a domain error, and reading 1390 characters total across four 110-160-line programs means the address plus the example's own expected/got carried essentially the whole repair. The honest null finding: at this size the *structured* anomaly still barely spoke -- three of four repairs came from the `fault:` line alone, and the fourth from the example's expected/got, not from the trap.
