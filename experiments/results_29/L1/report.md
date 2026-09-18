# Session L1 (LOVA) -- the session's own report, verbatim

Experiment 29, session L1 (LOVA arm). All four tasks green, one patch each, no failed attempts, no `given` ever used.

## 1. Per task

**g2048-a -- 1 patch (harness printed "attempt 2"), READ.**
- Ran: `fault`, `show --defs` (free), `show --def move-cell` (1102 chars counted).
- The `fault:` line said `51:30 dy -- `dy` here should be `dx`` in `farthest`, but qualified itself: "fixes this and 2 of 7 other examples; the fault may be elsewhere", "search cut short by the time budget". Since 7/8 examples were already passing, an edit that leaves only 3 passing is a regression, not a repair -- so I did not trust it.
- Diagnosed from the one failing example instead: board (column-major) row0 = `2 2 4`, move `l`, expected `4 4` / score 4, got `8` / score 12. That is 2+2->4 then 4+4->8: the "a tile merged this move cannot merge again" rule not being recorded. That rule lives in `move-cell`, so I read `move-cell` (the 1102-char def) and nothing else.
- Fault found: on the merge branch the state was rebuilt with `m (get st m)` -- the merged-tiles map copied through unchanged, so nothing was ever marked as merged. (The guard that reads it, `(not (map-get (get st m) (ckey ...) 0))`, was correct; only the write was missing.)
- Edit: `m (get st m))` -> `m (map-put (get st m) k 1))`. Pass.

**g2048-b -- 1 patch, essentially BLIND.**
- Ran: `fault`, then `show --def dir-of` (90 chars) **only to build a unique `--find` string**, not to check the diagnosis.
- `fault:` said `118:9 literal 4 should be 3` in `dir-of`, "fixes all 8 examples". Trusted immediately: four examples were dying with `domain-error` trapped in the `vx`/`vy` region, and a direction code of 4 where 0..3 are legal explains exactly that.
- Edit: `4))` -> `3))` in `(cond (eq c 117) 0 (eq c 114) 1 (eq c 100) 2 4)`. Pass.

**ttt-a -- 1 patch, BLIND.**
- Ran: `fault` only. Nothing read.
- `fault:` said `79:19 (ge sc (get st score)) -- `ge` should be `gt`` in `choose`, "fixes all 8 examples". Trusted without looking: every miss was the right score with square `8` instead of the right square, which is precisely a best-move scan that keeps the *last* tying candidate instead of the first.
- Edit: `(ge sc (get st score))` -> `(gt sc (get st score))`. Pass.

**ttt-b -- 1 patch, BLIND.**
- Ran: `fault` only. Nothing read.
- `fault:` said `37:63 literal 10 should be 9` in `empties`, "fixes all 8 examples". Trusted without looking: seven of eight examples were `domain-error`, and a board of nine squares iterated `(range 0 10)` indexes past the end.
- Edit: `0 10)` -> `0 9)`. Pass.

Counted reading across all four tasks: **~1192 characters** (1102 + 90), of which the 90 was only to make a patch string unique. Three of four repairs were made without reading any program text.

## 2. What the `fault:` line did for me

It is an address plus a confidence label, and the label is what I actually used. The deciding clause was the scoring bracket:

- **"fixes all 8 examples"** -- I applied it blind, three times out of three, correctly. In each of those cases I still spent a few seconds asking "does the named edit explain the *shape* of the failure I can see?" (`domain-error` near `vx`/`vy` <-> a direction code of 4; `domain-error` <-> indexing a 9-cell board to 10; right score / wrong square `8` <-> `ge` keeping the last tie). All three passed that sanity test, and all three were right. The `[changes the answer on N of 48 nearby inputs]` number was interesting but did not change any decision -- it was the *example* score, not the perturbation score, that carried the weight.
- **"fixes this and 2 of 7 other examples; the fault may be elsewhere"** (g2048-a) -- a red flag, and rightly so. The line pointed at `farthest`, a def the real bug is merely adjacent to; the real fault was a missing `map-put` in `move-cell`, 1100 characters away. Worse, the proposed edit would have *reduced* the passing count from 7 to 3. The "search cut short by the time budget" note was a second, independent reason to distrust it: the locator never got to the def that mattered.

So the line paid for itself three times and cost me nothing the fourth time, because it told me it was unsure. The useful property is not that it is always right -- it is that its self-report ("fixes all" vs "may be elsewhere") was a perfectly reliable signal of when to trust it. On this set, "fixes all N examples" was 3/3 correct and "fault may be elsewhere" was 1/1 wrong.

One further note on trust: the rule I fell back on when the line was a lead rather than a repair was exactly the one that worked -- *is the named edit a restatement of something the task prompt or the failing example already says?* `dir-of` mapping four letters to 0..3, a 3x3 board having 9 squares, a first-best tiebreak -- all three are clauses of the prompt. `dy`->`dx` inside a geometry helper was not; the prompt's clause that the failing example violated was "a tile merged this move cannot merge again", and no candidate edit was offered against it.

## 3. What I wanted and did not have

- **The scoring bracket to be believed over the address.** For g2048-a the locator knew it had not found the fix ("may be elsewhere", "search cut short"), yet it still printed a concrete `-> dx` replacement in the same format as the three good ones. A line that has not fixed the examples should not hand me a replacement string at all, or should print the *rule the example violates* instead of a token. I want a "no single edit found; search incomplete" line more than I want a bad guess.
- **The locator to spend its time budget where the example failed, not where it started.** The one task where it fell short is the one where it ran out of time, and the def it never reached (`move-cell`) is the largest def and the one every failing example spends its time in. Ranking defs to probe by *steps spent* rather than by position would have found it -- the project already has `hot` doing exactly that ranking for the step trap.
- **A "which clause of the prompt does this example test?" hook.** Every one of my four decisions came down to matching the failure against a sentence in the task prompt. That matching was mine to do; nothing in the output helped. For g2048-a, `expected 4 ..., got 12 ...` plus "a tile merged this move cannot merge again" is the whole diagnosis, and the machine had both halves.
- **A dry-run / uniqueness check for `--find`.** The only reason I read `dir-of` at all was that I could not know whether my `--find` substring occurred once in that def. A `--find ... --dry-run` that just reports the match count (or letting me patch by the span the `fault:` line already prints -- it gives `[4885, 4886)`) would have made that repair fully blind and saved the 90 characters. The fault line hands me a byte span and then makes me address the patch by text instead.
- **Nothing else.** In particular I never wanted the whole program: `show --defs` (free, with sizes) plus one named def was enough reading to solve the only task the line did not solve, and the def list's sizes were what told me `move-cell` at 1102 chars was where a rule that complicated would live.

Null finding worth recording: the `[changes the answer on N of 48 nearby inputs]` second oracle (M30) did not influence a single decision in this session. With "fixes all 8 examples" present, I acted; without it, I read. The perturbation count never broke a tie because I was never offered two competing candidates.
