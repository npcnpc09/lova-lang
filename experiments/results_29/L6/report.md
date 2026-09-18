# Session L6 (LOVA, Q120: g2048-c then ttt-c) -- the session's own report, verbatim

Session L6, Exp 29 / Q120 -- both tasks green, one attempt each, zero defs read.

## 1. Per task

**g2048-c -- 1 attempt, blind, PASS**
- Ran: `tasks`, then `fault`. Nothing else. No `show --defs`, no `show --def`, no `given`.
- `fault:` reported `25:31 [1195, 1196) 3 -- the literal 3 should be 4 -> 4 [fixes all 8 examples] [changes the answer on 13 of 48 nearby inputs] [def ckey is reached by 8 of 8 examples]`, with runners-up 32/48/50 all also at 13 nearby inputs.
- Edit applied blind by span: `3` -> `4` at [1195,1196). All hidden tests passed (largest run 15 317 steps).

**ttt-c -- 1 attempt, blind, PASS**
- Ran: `fault` only.
- `fault:` reported `17:38 [859, 862) 728 -- the literal 728 should be 729 -> 729 [fixes all 8 examples] [changes the answer on 8 of 48 nearby inputs]`. No `def ... reached by` line on this one.
- Edit applied blind by span: `728` -> `729`. All hidden tests passed (largest run 790 783 steps).

Total: 2 attempts, 2 tasks green, characters read = the two `fault` outputs (~2.2 KB combined); characters written = two span replacements, 4 characters.

## 2. What the `fault:` line did for me

It did the whole job in both cases, and the reason I trusted it without opening a def is the same in both: **the replacement was a number the task prompt already tells me must be there.**

- g2048-c: the task is a 4x4 board. A def named `ckey` -- a cell key -- containing the literal `3` where the arithmetic wants the row stride is wrong on its face; `(mul r 3)` on a four-wide grid is not a judgement call. The `[def ckey is reached by 8 of 8 examples]` line confirmed the address sits on the path every example takes, and `[fixes all 8 examples]` made it a repair rather than a lead. I did not need to see the expression.
- ttt-c: `728` -> `729` is `3^6`, and a nine-square base-3 board encoding is made of powers of three. 728 is not a power of anything. Again the prompt supplies the constant, so the line is verifiable without the code.

So my rule, unprompted, was Exp 28's: **trust the line when its replacement is a clause of the prompt.** Both fired. Had the line proposed a swap of two operands, a branch flip, or a constant with no arithmetic story (say `46` in a comparison), I would have read the def first, because then the examples are the only oracle and a few examples are a weak one.

The second oracle (`changes the answer on N of 48 nearby inputs`) did **not** change either decision, and on g2048-c it was actively uninformative: the proposed fix and all three runners-up scored 13, so the ranking was a tie and the only thing separating the winner was the semantic story I brought myself. On ttt-c the number (8) had no scale I could read it against. I would not have been able to use either number alone.

## 3. What I would have wanted and did not have

- **A reason attached to the runners-up.** On g2048-c I got four candidates tied at 13 nearby inputs and only the first one spelled out. If the line had said what the other three are (`32`, `48`, `50` are bare numbers with no context -- which def, what edit), I could have checked in one glance whether the tie was between four genuinely different hypotheses or four spellings of the same stride mistake. As printed, the runners-up are noise: they tell me the oracle is undecided without telling me between what.
- **The enclosing expression, one line of it, inline in the `fault:` line.** The excerpt it prints is the literal itself (`3`, `728`), which is the least informative part. `(merge (mul r 3) c)` would have been ~20 characters and would have turned "I believe this on prompt grounds" into "I have seen it". That is the cheapest possible read and it is currently not offered at any price short of `show --def`.
- **A def name on every fault line.** ttt-c's had none. I inferred the site was an encoding function from the value alone; if the constant had been less self-describing I would have had to spend a `show --defs` just to learn where I was being sent.
- Null finding worth recording: at this size, on these two faults, **I never needed the program**. Both faults were single wrong constants whose correct value is stated in the task prompt. That is the easy end of the repair distribution -- I would not generalise from two one-attempt blind hits that reading is unnecessary at 110-160 lines; it says these two planted faults were of the kind the locator is best at and the prompt is a sufficient oracle for.
