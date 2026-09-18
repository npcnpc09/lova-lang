# Session L4 (LOVA, Q120: g2048-c then ttt-b) -- the session's own report, verbatim

Session L4, Exp 29 / Q120. Both tasks green, one attempt each, no program text read beyond the `fault:` line.

## 1. Per task

**g2048-c -- 1 attempt, blind.**
- Commands: `tasks` (prompts), `fault` (once). No `show`, no `show --def`, no `given`. Nothing counted as read except the fault output.
- `fault:` said `25:31 [1195, 1196) 3 -- the literal 3 should be 4 -> 4 [fixes all 8 examples] [changes the answer on 13 of 48 nearby inputs] [def ckey is reached by 8 of 8 examples]`.
- Edit: `patch --span 1195 1196 --replacement "4"`. PASS, largest run 15 317 steps.

**ttt-b -- 1 attempt, blind.**
- Commands: `fault` (once). No reading of any def.
- All eight examples were `domain-error` trapped at the same span. `fault:` said `37:63 [1589, 1591) 10 -- the literal 10 should be 9 -> 9 [fixes all 8 examples] [changes the answer on 4 of 48 nearby inputs] [def empties is reached by 7 of 8 examples]`.
- Edit: `patch --span 1589 1591 --replacement "9"`. PASS, largest run 790 783 steps.

Totals: 2 attempts for 2 tasks, 2 `fault` runs, 0 `show`/`given` calls, 0 characters of program text read.

## 2. What the `fault:` line did

It did the whole job, and I trusted it in both cases without opening a single def. Three things made it trustworthy, in this order:

- **"fixes all 8 examples"** -- a repair, not a lead. That is the claim that matters; a partial fix would have sent me to read.
- **The def name plus a domain fact from the prompt.** This is what actually closed the decision. `ckey` with a literal 3 on a sixteen-cell board: a row stride of 3 in a 4-wide grid is wrong on its face, and the prompt says sixteen cells. `empties` with a literal 10 over nine squares, every example dying with `domain-error` (an index past the end): 9 is the only number the task allows. The line named a constant whose correct value the *prompt* fixes, so no code was needed to check it.
- **The consistency of the failures.** All examples pointing at one edit, and in ttt-b all eight trapping at the same span, said the program has one fault and this is it.

Where I would not have trusted it: g2048-c printed `runners-up, by nearby inputs changed: 32 (13); 48 (13); 50 (13)` -- three alternatives tied with the winner on the perturbation oracle. If the winner had been an arbitrary constant (say a score threshold) rather than a grid stride, that tie would have meant the examples cannot distinguish the places and I would have had to read `ckey`. The tie did not bite here only because the domain answered what the oracle could not.

## 3. What I would have wanted

- **The nearby-inputs number needs a denominator I can read.** "changes the answer on 13 of 48" was not usable evidence for me -- I do not know whether high or low is the good sign, and in g2048-c the winner and all three runners-up had the same 13. It cost nothing here, but it is currently noise; saying which direction the score favours, or simply suppressing it when it does not separate the candidates, would make the tie legible.
- **The runners-up should say where, not just what.** `32 (13); 48 (13); 50 (13)` gives me values with no def and no span, so I cannot tell whether they are three different literals in `ckey` or three places elsewhere in the program. If the tie had mattered, the line as printed would have forced me to read the whole def to find out what it was even offering.
- **A one-line echo of the enclosing expression.** The line gives me a def name and a bare literal. `ckey` + `3` was enough because I could guess the expression (`(merge (mul r 3) c)`), but the guess was mine, not the tool's. Ten characters of context around the span -- the operator the literal is an argument to -- would turn a confident guess into a check, at nearly zero reading cost.
- Nothing else. For a one-token constant fault in a 110-160 line program, the located edit plus the def name plus the task prompt is a complete repair loop; the program text was never needed.

Null finding worth recording: this pair of tasks did not test the locator's weakness, because both planted faults were constants whose correct value is stated by the task prompt. The repair was won by the *domain*, with the locator supplying only the address. A fault at a place the prompt does not pin down would not have gone this way.
