# Session L5 (LOVA, Q120: ttt-c then g2048-a) -- the session's own report, verbatim

Session L5, Exp 29 / Q120. Both tasks green, one attempt each, zero failed attempts.

## 1. Per task

**ttt-c -- 1 attempt, blind, 0 characters read.**
Commands: `fault` only. The line said `17:38 [859, 862) 728 -- the literal 728 should be 729 -> 729 [fixes all 8 examples] [changes the answer on 8 of 48 nearby inputs]`. I patched the span without opening a single def. Edit: `728` -> `729` (3 characters written). PASS first try.
Why blind: two independent signals agreed. "fixes all 8 examples" makes it a repair rather than a lead, and 729 = 3^6 is a constant with an obvious meaning in a board encoding -- 728 is what 729 looks like after a one-token perturbation, and nothing else. The change-count (8 of 48) told me it was a real semantic change and not a no-op.

**g2048-a -- 1 attempt, read first, ~1 300 characters read.**
Commands: `fault`, `show --defs` (free), `show --def farthest` (198), `show --def move-cell` (1 102), then `patch`.
The `fault` line was a lead, not a repair: `51:30 [2199, 2201) dy -- `dy` here should be `dx` -> dx [fixes this and 2 of 7 other examples; the fault may be elsewhere] (search cut short by the time budget) [def farthest is reached by 8 of 8 examples]`.
I did not trust it, for two reasons before reading anything. (a) Its own hedging: "the fault may be elsewhere", the search was truncated, and `farthest` is reached by 8 of 8 examples, so naming it carries no information. (b) The failure itself contradicted it. Board `2 0 0 0 2 0 0 0 4 0 0 0 ...` moved `l` gave score 12 and a single 8, where the answer is score 4 and two 4s: 2+2 merged to 4 and then that 4 merged with the 4 again. That is exactly one rule -- "a tile merged this move cannot merge again" -- and it is not a traversal-geometry rule, so a dx/dy swap in the walker could not be it.
Reading `farthest` (cheap, 198 chars) confirmed the lead was nonsense: the edit would have made the recursive call `(farthest b nx ny dx dx)`, which is not a plausible program in any direction. Then `move-cell`, the def that owns the merge rule, showed the planted fault on sight: the merge branch rebuilds the state with

    m (get st m)

i.e. it puts the merged-set back unchanged instead of recording the cell it just merged into. Edit: `m (get st m)` -> `m (map-put (get st m) k 1)` (26 characters written; `k` is the target key, already bound in the enclosing `let`). PASS first try.

## 2. What the `fault:` line did for me

It did two completely different jobs, and its own scoring told me which one it was doing.

- When it said **"fixes all 8 examples"**, it was a repair and I spent nothing: no read, no reasoning about the program, straight to `patch`. That is the whole value of the instrument -- ttt-c cost me one command and three characters, on a 110-160 line program I never looked at.
- When it said **"fixes this and 2 of 7 other examples; the fault may be elsewhere"**, plus "search cut short", it was worth roughly nothing on g2048-a, and slightly worse than nothing: the def it named (`farthest`) was the one def I could rule out from the failure text alone, and following it would have cost an attempt. The `[def farthest is reached by 8 of 8 examples]` annotation is what made that visible -- a def every example reaches cannot be where a fault that only one example sees lives. I would like that inference made by the tool, not by me.

My rule, the same one Exp 28's sessions reported: trust the line when its edit is a clause of the prompt (the merged-again rule, a 3^6 board encoding), distrust it when the edit is a variable swap that makes the surrounding expression incoherent (`dx dx`). Reading the 198-character def was the cheapest way to settle it -- a small def read is much cheaper than a wasted attempt.

Worth noting for the numbers: the expected/got pair did more locating work than the `fault:` line on g2048-a. Score 12 and one 8 where 4 and two 4s were due names the violated rule outright, and the rule names the def. The 1 102 characters of `move-cell` were the only reading that actually had to happen, and even there the fault was visible in the first third of the def.

## 3. What I would have wanted and did not have

1. **A "which defs does this failing example reach that the passing ones do not" list.** The line already computes reach counts (it printed 8 of 8 for `farthest`). Inverted -- defs reached *only* by failing examples, or reached disproportionately -- that would have pointed at `move-cell` directly and saved the `farthest` read and most of the deliberation. This is the single highest-value thing missing.
2. **Grep inside a program**, e.g. `show --find "map-put (get st m)"` returning the defs and lines that mention a name. I knew from the failure text that I was looking for wherever the merged-set `m` is written, and I had to buy a 1 102-character def to find a 12-character site. A name-use index would have cost ~50 characters instead of 1 100.
3. **A negative result from the locator when the search was truncated.** "Search cut short by the time budget" plus a low-confidence lead reads like a weak answer; I would rather it said "no single-node edit found within budget; the examples reach these defs" and named nothing, because a named wrong def is an active pull in the wrong direction. The honest null is more useful than the bad lead.
4. Nothing was missing on ttt-c. That case is already at its floor: one command, one patch, no program read at all.
