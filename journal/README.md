# LOVA — Research Journal

Rolling log of LOVA's design and empirical validation.

This journal is the source of truth for *why* the language does what it
does and *what we still do not know*. Code without journal is sculpture;
the journal is what makes it an experiment.

## The vision

See `../CLAUDE.md` for the one-page project orientation and
`../spec/axioms.md` for the ten design invariants.

## Current state (2026-09-09)

### Design stage
- CLAUDE.md written; paradigm-evolution positioning added
- 10 axioms documented in `spec/axioms.md`
- Paradigm lineage traced per axiom + primitive in
  `spec/paradigm-inheritance.md` — LOVA is the synthesis of 7
  long-running PL trajectories (homoiconicity, effect tracking, program
  synthesis, concurrency, verification, variance/evolution, provenance)
- Token architecture sketched (64 operators, 8 families); detailed
  spec pending in `spec/tokens.md`

### Milestone 1 (2026-04-23) — Stage-1 substrate operational
MVP substrate in 790 LOC (`core/tokens.py` + `core/surface.py` +
`core/conservation.py` + `core/runtime.py`). Exp 01 exhibits Axioms
1, 4, 7, 8 in one run: 11 round-trip programs lossless, 8 number-
theory primitives at reference values, `BudgetTrap` and `DeltaTrap`
raised with structured metadata, surprise trace emits 3 structured
events. `(merge (p 3) (tau 12))` = 9 bytes = integer 55916975560956379404.

### Milestone 2 (2026-04-24) — Axiom 3 validated
`core/types.py` + `core/generator.py` (320 LOC). Exp 02 demonstrates
type-directed generation: 1000/1000 constrained programs are
well-formed (100%), 0/1000 unconstrained are well-formed (0%), delta
+100pp. Sharp-constraint concretely shown: after `LET`, valid_next
narrows from 18 tokens to 1.

### Milestone 3 (2026-04-24) — LOVABench v1 + corpus starter kit
`corpus/tasks.py` (20 parametrised number-theory tasks) + evaluator +
JSONL export (`corpus/lovabench_v1.jsonl`). Exp 03: three baselines
across 20 tasks. Reference 20/20 (100%); unguided constrained-random
1/2000 (0.05%); Claude-as-oracle 20/20 (100%). Gap quantified, corpus
shipped, fine-tuning path explicit (Q09).

### Milestone 4 Day 1-2 (2026-04-24) — Lineage intrinsic (Axiom 5)
`core/lineage.py` (~230 LOC). Exp 04: lineage API (register/clone/
mutate/ancestors) + Wright-Fisher coalescence (5 roots → 1 survivor
after 10 gens, matching DNA OS Exp 55 at program level) + mutation
diversity (49/100 distinct variants, structured not chaotic).
**8/10 axioms now operational.**

### Milestone 4 Day 3-5 (2026-04-24) — Populations / defpop (Axiom 6)
`core/populations.py` (~240 LOC). Exp 05: self-healing demo. Start
with 5 variants all WRONG (distances 12-35 from target=42).
Fitness-weighted evolve over 12 rounds. Best seed converges 35→1
distance (97% gap closed); 3/10 seeds hit ±2; all 10 seeds improve
(mean 80% gap closure). Mechanism works (dispatch/retire/reproduce
observable in lineage); convergence not guaranteed under current
mutation landscape. **9/10 axioms now operational** (Axiom 6 partial,
deferred items tracked as Q16-Q19 for M5).

### Milestone 5 L1-L3 (2026-04-24) — Observability for AI
`core/observability.py` (~260 LOC) + conservation/runtime enrichment.
Exp 06: three APIs ship. **L1** `valid_next_with_stats` returns
`TokenChoice` objects with arity / depth_delta / terminating / effects
/ cost. **L2** trap anomalies carry `kind / detail / position_path /
offending_op / valid_alternatives / repair_hint` — AI pattern-matches,
doesn't parse tracebacks. **L3** `static_analyze` returns effects /
budget bound / determinism / uses-of-{conservation,surprise,lineage}
without running the program. Result: LOVA error surface narrows
to *semantic only* — syntax/type/arity errors physically unreachable.
**10/10 axioms operational; substrate speaks machine.**

### Exp 07 (2026-04-24) — Claude-vs-Claude Python vs LOVA benchmark
Same 20 LOVABench tasks, same LLM, two languages. Headline:
- **Pass@1: LOVA 20/20 vs Python 19/20.** The lost Python task
  failed on keyword-arg / scope-shadowing — a structural Python weakness.
- **Error-class subset**: Python's reachable errors are
  `{syntax, name, type, import, attribute, ..., semantic}`; LOVA's
  are `{semantic, conservation, unbound-ref}`. Substrate property.
- **Density**: 39.2× raw (hand-rolled Python), ~15-20× adjusted (vs
  sympy-equivalent). LOVA's 64-op number-theory vocab is very
  packed.

*Superseded 2026-09-09.* This section reports the original 20-task run.
The script was extended to all 60 v2 tasks at M13: **60/60 vs 59/60**,
**25.8×** raw. The error-class subset result is unchanged. See "Q30
closed" below — including why the pass rate measures less than it
looks like it does.

### Milestone 6 Day 1 (2026-04-24) — Compiler (scope + type + fold)
`core/compiler.py` (~220 LOC). Three static passes over Node tree:
scope resolution (catches unbound-ref at compile-time), type check
(validates slot types independently of valid_next), constant folding
(pure subtrees with literal args evaluate at compile-time).
`CompileError.anomaly` has the same L2 schema as `BudgetTrap` /
`DeltaTrap` — uniform AI error handler. Exp 08 measures:
**LOVABench v1 programs compress 58.5% in nodes / 43.9% in bytes**
via folding; pure-program tasks collapse to single LIT_INT ("the
program is its answer"). `unbound-ref` moves from runtime to
compile-time error surface. Project health: strong, launch-ready.

### Milestone 6 Day 2 (2026-04-24) — Body-scanning DeltaTrap (Q20)
`core/runtime.py` gains `_scan_body_offender` + `_clone_with_replacement`
(~90 LOC). When `(conserve E B)` Δ-traps, the scanner probes B
deepest-first with two passes: **Pass A** swaps each op for an entry
from `suggest_alternatives` (VIOLATE→IDENTITY catches the canonical
conservation-break case); **Pass B** substitutes sub-expressions with
`LIT_INT(value - deviation)` for "wrong-value" shapes. `anomaly["body_offender"]`
now carries `{op, op_name, path, depth, observed, needed, correction, fix}`,
replacing the uninformative `offending_op == CONSERVE` signal that
was uniform across every Δ-trap. Exp 09: **5/5 canonical shapes,
50/50 fuzz, 5/5 closed-loop repair**. Q20 closed; three new questions
raised (Q23/Q24/Q25).

### Milestone 6 Day 3 (2026-04-24) — Pass-rate telemetry (Q22)
`core/telemetry.py` (new, ~180 LOC) adds a per-token and per-(token,
parent_op) pass/miss counter, JSON-serialisable. `Slot.parent_op`
added so `valid_next_with_stats(state, telemetry=DB)` can look up
context-specific stats. `TokenChoice` gains four optional fields
(`prior_pass_rate / prior_sample_count / prior_pass_rate_ctx /
prior_sample_count_ctx`); existing call sites unaffected. Runtime
`MAX_NT_INPUT = 2000` DoS guard added (unaffects LOVABench; prevents
random `(p (p N))` bombs). Exp 10 bootstraps a 320-program DB (20
LOVABench refs + 300 constrained_random); finds LIT-as-child-of-
CONSERVE pass rate is **3%** vs global 65% (20× divergence signals
the hostile contract slot). **Weighted sampler +20 pp over uniform
(96% vs 76% pass-without-trap on N=50 fresh samples).** Q22 closed;
Q26-Q29 raised (task-level pass, termination weighting, incremental
merge, richer conditioning). `corpus/token_telemetry.json` shipped
as seed DB (19 KB).

### Milestone 9 (2026-09-09) — Abstraction and iteration
(Numbered 9 because M7 — MCP server — and M8 — fine-tuning corpus —
were already named in `CLAUDE.md`. M9 landed first because both of
them depend on it: there is no point exposing or fine-tuning a
language that cannot express a loop.)

The language could not express a function, a call, or a loop until
this milestone: `LAMBDA` / `APPLY` raised `NotImplementedError`,
`LOOP_UNTIL` had no implementation, and `LET` was a plain let. Every
program in `corpus/` and `apps/` was a fixed-depth expression over
built-ins, so LOVA was not computationally universal — which no amount
of corpus or fine-tuning work would have fixed.

M9 lands unary closures with currying (`(lambda p body)`, arity 2 as
already declared), `APPLY` as a variadic with a typed `Fn` head, `LET`
as a **letrec** (backward-compatible: a self-reference used to be an
`unbound-ref` compile error), and `LOOP_UNTIL` as a *combinator* —
`(loop-until pred step)` returns the function that iterates, so an
unbounded loop costs one call frame. Types gain `Fn` and a `Value` top
type for the one slot that may hold either. Non-termination becomes
reachable, so two always-on ceilings arrive: `MAX_CALL_DEPTH` →
`DepthTrap`, `MAX_STEPS` → `StepTrap`, both `BudgetTrap` subclasses
carrying the L2 schema.

Arithmetic came from reallocating two slots that had carried a name
and an arity since M1 and never an implementation: **0x0B `phi3` →
`mul`, 0x0C `psi7` → `mod`**. Ordering came from implementing two
already-declared surprise-family slots — `deviation` (signed sibling
of `surprise`) and `threshold` (sign test) — so `a < b` is
`(threshold (deviation b a))`. **No new tokens; the core is still 64.**
Implemented operators 18 → 25. Stage-1 sugar added (`defn`, call
syntax, bare-name references, `⊗`), all desugaring to existing tokens.

Exp 12: **44/44 algorithmic cases pass, 0/10 were representable
before**; μ-recursive basis exhibited; 5/5 runaway shapes trapped with
a full anomaly. And a **negative density result** — see the log row.
Tests 122 → 188. Two new apps (`is_prime.lova`, `collatz.lova`).
`spec/tokens.md` is now genuinely generated, by
`spec/generate_tokens_md.py`.

### Milestone 10 (2026-09-09) — Data
Acts on `spec/token-budget.md`. **Six of the fourteen free slots spent**;
implemented operators 25 → 31 of 64. The number-theory family was not
reallocated.

One cons cell — `cons` (0x04), `head` (0x05), `tail` (0x06), `nil`
(0x15), `nil?` (0x19) — ends the era in which the only LOVA value was a
scalar integer, and buys three things at once: pairs (a cell *is* a
pair, so `partition` could finally return what it means), lists, and
**strings as codepoint lists**, so `"abc"` is surface sugar costing zero
slots. `div` (0x0D, the never-implemented Dedekind-η slot) replaces
O(a/b) repeated subtraction that had been burning call depth to do
arithmetic. A new type `List`, disjoint from `Int` and `Fn`; `apply`'s
argument slots widened from `Int` to `Value` so a function can take a
list at all.

**The proposal revised itself on its own evidence.** `lt` and `sub` were
costed at one slot each and shipped as **macros instead, at zero slots**:
a macro captures the identical *surface* token saving (which is what the
9% measurement was), and gives up only the node-count saving, which the
same experiment put at 2%. `gt`, `(list ...)` and `"..."` shipped the
same way. And the zero-slot lever Exp 13 found landed as eight one-token
spellings (`if`, `dev`, `tr`, `loop`, `keep`, `dist`, `mu`, `def`) —
canonical names unchanged, so these are additional spellings, not
renames.

Held back, deliberately: `quote` / `eval` (2 slots — a real design
commitment, and the only route to Axiom 1's programs-as-data and Stage
3's `(explain program)`) and the **Axiom 8 revision**, which per
`CLAUDE.md` needs the owner's approval and has not been applied.

`apps/palindrome.lova` is the first LOVA program that operates on data
rather than on a number. Tests 188 → 239.

### Found during M10: the generator could not terminate
`constrained_random` hung. Two bugs, layered, and the second is the
instructive one.

1. **No Fn-producing operator is "terminating".** `LOOP_UNTIL` pushes
   two `Fn` slots and `LAMBDA` pushes none, yet both have a stack delta
   of +1, so the depth-delta test could not separate them. Sampling
   uniformly between them is a *critical* branching process — mean one
   offspring — which terminates with probability 1 and infinite expected
   time. Exp 02 seed 808. This arrived with M9 and went unnoticed
   because reaching an `Fn` slot was rare until M10 widened `apply`.
2. **"Pushes no slot of the type I am filling" is not enough either.**
   The first fix used that test; in an `Int` slot `APPLY` pushes no
   `Int`, so it looked safe while actually opening an `Fn` slot *and* a
   variadic `Value` tail that closes only on `END`. Exp 02 seed 2: 358
   slots still open after 4096 tokens, growing without ever repeating a
   type.

The fix is a **minimum-completion-cost** bias: for each candidate,
compute the fewest tokens still needed to finish, and past `max_depth`
sample only from the cheapest. Choosing a minimum-cost token strictly
decreases the work remaining, so generation closes within `cost` further
steps. Costs come out as `Int`/`Value`/`List`/`LiteralInt` = 1, `Fn` = 3.
A hard `MAX_GENERATED_TOKENS` ceiling now raises rather than spins,
because a sampler that cannot terminate is a bug, not a slow path.
1000 seeds: 2.3s, worst 12ms.

Same shape of bug, three sites, in the runtime: `violate`, `budget`,
`surprise` and `conserve` did arithmetic on `_eval` results without
coercion. A *well-typed* generated program can hand them a closure,
because `APPLY` declares `Int` while a partially applied function
evaluates to a callable — `Fn` does not track curried arity (Q35). Every
arithmetic site now routes through `_as_int`.

### Milestone 22 (2026-09-10) — A language a real program can stand on
The gap between "the core is complete" and "usable" was measured
before it was closed. The probe: a word-frequency program — read a
file, split it into words, count, sort, print the top n
(`apps/wordfreq.lova`). Everything it needed was missing or broke.

**Ceilings.** `max_call_depth=200` meant a recursive `len` of a
300-element list trapped; `max_steps=1_000_000` meant a 200 000-round
loop trapped after five seconds. The depth default is now 10 000
(Python's stack was never the limit: the runtime raises its recursion
limit per run, and 30 000 LOVA frames ran). The CLI and the MCP server
run real programs and default to 20 000 000 steps; the library default
stays at 1 000 000, because the generation experiments run thousands
of random programs and need a tight guard.

**The prelude iterates.** There is no tail-call elimination, so every
recursive list function cost one frame per element. `iterate` —
`loop-until` over a `(cons n rest)` or `(cons rest acc)` state, the
two shapes `cons`'s typed second slot allows — replaces recursion in
every O(n) function; `(merge 0 (head s))` keeps the result an `Int`
for the checker, so the M20 shapes survive. New: `take` / `drop` /
`zip` / `any` / `all` / `sort` / `sort-by` (merge sort, log-depth
halves, iterative merge) / `split` / `lines` / `words` / `join` /
`parse-int` / `text-of` / `text-lt` / `inc`, and `lib/assoc.lova`.
`last` is loud on the empty list now, as `nth` has been since M14.

**`signal` (0x12).** A library that meets bad input had no way to say
so: LOVA could catch (M13) but not raise. `(signal code)` raises a
`signalled` anomaly whose handler receives the program's own code;
codes below 16 are the substrate's kinds and are refused. `parse-int`
of `"12a"` signals 16. Never returns, so it fits any slot.

**The map, on the last three free slots.** The association list did
the count in O(keys) per word: **a thousand lines did not finish in
twenty million steps** (two minutes). A LOVA-side tree would have
bought ten or twenty times; the interpreter runs ~300 000 steps a
second, so that is still minutes. `map-put` / `map-get` / `map-pairs`
(0x13 / 0x14 / 0x16; persistent by dict copy; keys integers or lists;
`map-get` takes a default, so presence is always testable; the empty
list is the empty map) do the same thousand lines in **3.4 million
steps**. That measurement spent the slots, with the owner's yes. The
table is full: 63 operators and `END`; the reserve position is the
number-theory family (Q74).

**The interpreter, three times faster.** A profile of the count showed
the evaluator walking a chain of fifty `if op ==` comparisons to reach
`ref`, a wrapper call per node, and a call each for the step and
budget accounting. Table dispatch, one function per node with a
literal fast path, inlined accounting, direct `Cons` checks in `head`
/ `tail` / `nil?` / `cons`, slots on `Cons`: **27.7 s → 11.6 s** on a
thousand lines, step count unchanged. `eq` / `ne` now compare with
`deviation` rather than `surprise`, which had been recording an event
per comparison — a hundred thousand for the thousand-line count, all
meaningless. Where it stands: **10 000 lines, 21.9 million steps, 73
s** (`--max-steps` raised). The per-node floor is the node stack, the
accounting and the dispatch, ~3 µs; `_call` copies a ~90-entry
environment per call (Q75).

Exp 12's ceilings section now pins `max_call_depth=200`, the value it
was written against; at 10 000 the argument-doubling shape overflows
the integer-size guard first, which is also a structured stop.

Tests 618 → 665. The README's "initially usable" claim rests on this
entry and its numbers.

### Experiment 21 (2026-09-11) — The repair leg: a fault planted in a program already written
Q88, the yardstick's fourth number, first value. Exp 19's eight tasks,
each with a program written for it (LOVA: session o5's, as it passed;
Python: the reference) and one semantic fault planted at the analogous
place in both -- a dropped `neg`, a period not stripped, a sort key's
sign, a duplicated win line, a count for a sum, `<` for `<=` twice, an
edge relaxed one way. Three Opus sessions per language: LOVA 24/24 in
30 attempts, Python 24/24 in 28; emitted 672 chars against 391, read
27 108 against 12 069, for given programs 2.35× longer. **47 of 48
faults were found by reading the program before any feedback**; the
harness's failure feedback located an original fault zero times on
either side, so Axiom 7's channel never got to speak. Nine of the ten
extra attempts were the instrument -- character-offset spans, CRLF on
the console, a hand count off by one -- and every one of those bad
patches was located exactly by the anomaly (LOVA) or the `SyntaxError`
(Python) and undone in one attempt. **NULL for the language at this
size**: repair cost is reading, and reading scales with length, so
density is charged on every repair. `patch --find <text>` and
`--dry-run` in the harness; `given` is not an attempt.
`journal/experiment_21.md`; Q88 measured; Q95 (repair at a size where
reading fails, run-time faults, the span and `hot` against a
traceback), Q96 (programs that carry `example` forms), Q97 (density as
a repair cost; the Stage-2 surface). Tests 783 → 787.

### Experiment 20 (2026-09-11) — Does cost attribution turn a blind rewrite into a read one?
Q91. Exp 19's tasks and rules, three more Opus sessions (o4-o6) with
`hot` in the step trap: 24/24 green, 31 attempts against run 2's 35,
the game-tree search 3, 2, 4 attempts against 6, 3, 4 -- and every
session says the list changed what it rewrote (all three would have
attacked the node count; the list said the cost was per node, in list
access). One session was misled by the list itself: it ranked by
calls, so a three-step helper (`inc`, 53 485 calls) led a
two-hundred-step walk, and the session inlined helpers and trapped
again. So the trap now ranks by **steps spent in each function's own
body** (an anonymous lambda charged to the def that wrote it), which
read on run 2's program: `nth` 3.9M of 7M, list access three quarters
of the budget, the user's own function five percent. `text-slice` and
`text-cat` keep a list's shape now, so `nth`, `take`, `drop`, `last`
and `append` are native at zero slots (13-19 steps where the walk cost
80-400); the natural first attempt costs 1.3-3.1× fewer steps and
still does not fit 7M (9.9M-36.6M). `Closure` and `Runtime` got
`__slots__`, which paid for the attribution and 15% more. Card: a
cost section with the measured numbers and six facts the sessions
guessed (mutual recursion, `(nil)` as the empty map, `words` yields
texts, negative literals, `\n`, field names as symbols). Harness:
`check` (compile and the program's examples, no attempt spent),
`tasks` states the budget, `patch --out`. `journal/experiment_20.md`;
Q91 answered; Q93 (one rewrite, or none?), Q94 (native walkers or a
native evaluator: Q90 sharpened). Tests 781 → 783.

### Experiment 19 (2026-09-10 / 11) — The loop where first attempts fail
Q87. Eight bigger tasks -- a calculator with precedence, reports, the
best tic-tac-toe move under perfect play, shortest paths, ledgers --
three fresh sessions per language, twice. **Run 1** (Fable) found
the instrument's defects before it found the language's: the input
`"7"` arrived as the integer 7 (three sessions lost their first
attempt to it), the LOVA budget was thirty times tighter than the
Python clock, the step trap's hint asserted non-termination when
eleven of fourteen trapped programs were correct, and parse errors
had no position. All four fixed: `s="7"` is a text on any command
line, budget parity, an honest hint, `ParseError` with a span.
**Run 2** (Opus, both languages): LOVA 24/24 green in 35 attempts,
Python 24/24 in 26. On seven of the eight tasks the languages do not
separate (LOVA 20 of 21 first-try, Python 22 of 24); on the game-tree
search LOVA took 6, 3 and 4 attempts against 1, 1, 1, every extra one
a rewrite for cost after a step trap that said where it stopped and
not where the budget went -- Q76's speed floor, measured as attempts.
Every compile fault (five) was fixed at the next submission; the
sessions called the diagnostics "excellent" and the step trap "the
one place the language gives an outcome but no diagnosis". So the
trap now attributes: `hot`, the most-called functions by name with
counts, in the anomaly and the hint; `PASS` reports the largest run's
steps against the budget; the card shows a zero-parameter `def`'s
call site, the gap all three sessions hit. `journal/experiment_19.md`;
Q87 answered; Q90 (speed as attempts: PyPy, a native evaluator), Q91
(does attribution turn two blind rewrites into one), Q92 (ten
sessions on one model). Tests 767 → 781.

### Experiment 18 (2026-09-10) — The agent loop, the four numbers
Q82's experiment, run the day the design list it was waiting on was
done. Ten tasks that need loops, lists and text (parentheses, reverse
Polish, Roman numerals, binary search, coin change ...), hidden tests
from Python oracles; two fresh Claude sessions with no repository
access, one per language, one command -- `submit`, which prints
`PASS` or the first failure with the structured anomaly (LOVA) or the
traceback (Python) -- and `patch` on the LOVA side; the LOVA session
had the generated card and nothing else. **LOVA 10/10 in 11 attempts,
Python 10/10 in 10.** The one LOVA miss was `merge` passed by name to
a helper -- an operator is not a value -- which the card had not said;
the compile error named the excerpt and gave the lambda wrapper, and
the second submission passed ("I did not have to reason about it at
all"). Emitted 3 184 chars against 2 431; feedback read 1 114 chars
for the one failure, none in Python because nothing failed, so the
yardstick's second number has one side only; the fourth (reuse) was
not exercised. The number the loop did separate is scaffolding: the
LOVA runner is a function call with a budget and no grant, the
Python runner a subprocess and a wall clock. Every hindrance the
session named was a sentence missing from the card (`nth`'s base,
operators as values, `map-count`) or a list of fifty name ids in the
anomaly; all closed the same day, the hint for an unbound name now
speaking in names -- an operator used as a value gets its wrapper, a
misspelling its nearest neighbours. `journal/experiment_18.md`; Q82
measured in part; Q87 (the loop at `apps/` size, ten sessions), Q88
(the reuse leg), Q89 (is the bound-name list worth its bulk). Tests
766 → 767.

### Milestone 27 (2026-09-11) — The walkers are operators
Q94, the owner's choice after Exp 21: close the one measured deficit
before testing the claim where it might hold. Exp 20 had left the
natural game-tree search at 10-37M steps against 7M, the cost being
the prelude's `map` / `filter` / `fold` / `any` / `range` at 20-40
steps an element over `loop-until`. A list family at 0x50-0x57 --
`map`, `filter`, `fold`, `reverse`, `range`, `any`, `sort-by`, `zip`
-- one step an element plus the function called, with the function's
steps charged (Exp 20) to the def that wrote it; the validator admits
it and the samplers do not emit it, like the text family. Semantics
are the prelude's: `fold` calls `(f acc x)`, `range` is a..b-1, `any`
stops at the first hit, `sort-by` is stable and takes `lt` or `le`
alike (the merge sort was stable under `le` only, and Python's sort
with a `le` comparator is not a strict weak order -- so a precedes b
when `(less a b)` and not `(less b a)`). Programs are unchanged
textually; `sum`, `product`, `contains`, `all` are one-line idioms
over the operators; `rev-onto` and `merge-by` are gone. Per element:
`map` 5 (was 39), `filter` 5 (35), `fold` 5 (22), `reverse` 2 (17),
`range` 2 (20), `sort` 8 (213). The Stage-2 surface takes eight more
Greek capitals. 86 tokens; `spec/tokens.md` and the card regenerated.
One thing to watch (Q98): a program's own `(def range ...)` now
defines a name that the parser reads as the operator at every call
site, silently; no corpus program does this today. **Q99, replayed
the same day:** the six natural first attempts at the game-tree search
cost 6.3M, 6.8M, 9.5M, 23.6M, 26.9M and 29.3M steps (native `nth`
alone: 9.9M-36.6M; the M22 prelude: 24M to over 40M). Two of six fit
the 7M budget where none did. In the four that do not, the cost is the
program's own win-check and board-rebuild loops (`winloop`,
`line-win`, `setat`: 2-4M each) with `nth` at 8 steps a call a third
of it -- the algorithm's node visits, at ~400 000 steps a second. What
remains is Q90's question, not the library's. Tests 787 → 805.

### Milestone 26 (2026-09-10) — A boundary is a region
The third tax the twelve programs paid: a boundary is lexical (M19),
which is what lets the compiler refuse an undeclared effect before
the run, and `def` was a top-level form, so an effectful helper had to
be a `let`-bound lambda inside the boundary. Three programs were
rewritten around it. The dynamic alternative -- an effect permitted
wherever the *call chain* is inside a boundary -- would have given up
the static check.

The form that keeps the check: **`(boundary "kind" (def ...) ... body)`**.
The parser reads `def` forms after the capability spec and binds them
inside the boundary, as the `let` chain the top level would have made;
a helper written there carries the declared effect, lexically, and
the region ends where the boundary does. The capability error's hint
now says so. `guess.lova`, `ping.lova` and `pong.lova` are back to
`def`s. `tests/test_boundary_region.py`; Q86 closed.

**The card is generated.** `corpus/make_card.py` renders the one-page
card from a narrative template, the prelude's own section headers and
`def` signatures (a one-line comment above a `def` becomes its note),
and the token table's text family; `tests/test_card.py` fails when
the checked-in card is stale, when a public prelude function is
missing from it, or when an example on it does not run. The card and
the library can no longer drift apart, which the yardstick asked for
(`spec/ai-convenience.md`, section 4).

**A program carries its examples.** `(example expr expected)` forms
stand wherever a `def` may. They are not part of the program -- the
run, `hash` and `explain` ignore them -- they are what the program
says about itself. `core/examples.py` runs each as the program with
its own expression replaced by `(conserve expected expr)`, from
source with the example forms blanked to spaces so every span holds,
so a miss is the conservation anomaly the substrate already reports:
expected, got, the example's line and column, and the sub-expression
at fault when the probe finds one. `lova check file.lova` and the MCP
tool `lova_check` are the doors; `tictactoe.lova` carries six. The
yardstick's "not being able to check at once" ends here: the check is
inside the program, one command away, structured. Tests 753 → 765.

### Milestone 25 (2026-09-10) — Text is a value
The second work under the one goal: the tax every text program paid
for the representation. Since M10 a string was a list of codepoints,
which cost no slot and made `words` twenty nodes and three calls a
character (M23). Under the demoted Axiom 8 the slot count is no
longer the reason to refuse a value kind.

**The text family, 0x40-0x4D.** The first tokens past 0x3F: a text
literal (`text`, 0x40: two-byte length, UTF-8 payload) and thirteen
operators -- `text-len` `text-cat` `text-slice` `text-find`
`text-split` `text-join` `text-chars` `text-of-chars` `text-cmp`
`text-int` `int-text` `text?` `text-trim`. A text is a Python `str` in
the reference runtime. Where an operator says Value it takes a text or
a codepoint list, so nothing written against the list form loses.

**Every list operator reads a text as its codepoints**: `head`, `tail`,
`nil?`, `cons` (a codepoint onto a text is a text), `len`, `map`,
`filter`, the folds. A map keys a text like the list it stands for, so
records and word counts built either way agree. `eq` compares two
texts, which needed one relaxation in the checker (`deviation` admits
any value; the runtime reports a non-comparable pair). `Text` is a
subtype of `List` for the checker, because the runtime makes it one.

**The prelude's text functions became one operator each**: `len`,
`same`, `append`, `words`, `lines`, `split`, `join`, `parse-int`,
`text-of`, `text-lt`, `chomp`. `fs-read`, `stdin`, `net-recv`,
`explain` and `why` yield a text. `parse-int` keeps signal 16. The
Stage-2 projection prints a text literal as a quoted string and gives
the family Greek capitals, since printable ASCII had eight characters
left. The validator admits the family; the samplers do not yet emit
it (`valid_next(generate=False)` is the validation view), so
Exp 16's figures stand.

**Numbers.** The thousand-line word count: 2 462 492 → 598 404 steps,
3.39 s → 1.12 s. Ten thousand lines: **28 s → 5.5 s on CPython** (73
s at M22). The twelve programs run unchanged; `tictactoe.lova`'s
board setter had already become `place`. Tests 747, all passing; the
token table is 78 entries and `spec/tokens.md` is regenerated. Q85
closed.

### Milestone 24 (2026-09-10) — A fault says where; a fix is a patch; a record has names
The first work under the one goal (`spec/ai-convenience.md`), aimed
at the two largest costs the yardstick names: re-emitting a program to
fix one expression, and taking state apart by position.

**Spans.** Every node parsed from text carries its (start, end)
offsets: the tokenizer's tokens are a `str` subclass that remembers
where it came from, and every form, atom, macro expansion and call
takes the span of the text it was read from. The prelude's copies
have none, so a fault inside a library function reports the *call*
that reached it -- the expression the author can change. The compiler
keeps spans through constant folding and drop-unused; a compile error
carries the span of the offending node; every run-time trap kind is
now enriched (domain traps included, which until now reported no
position) with the innermost node that came from the program's text.
The CLI prints `at: 2:14  (div 10 (sub 3 3))`; the MCP server adds
`span`, `excerpt`, `line` and `col` to every anomaly.

**`lova_patch`.** The fifth MCP tool: `(source, span, replacement)`
→ the patched source, compiled to check it, or the anomaly of the
patch. The loop an AI runs is execute → read the span → patch that
span → execute: a fix costs the size of the fix. `tests/test_spans.py`
runs the loop on a division by zero: the anomaly says `(div 10 (sub 3
3))` at 2:14, the patch replaces eighteen characters, the second run
returns 8.

**Records (Q84).** `(rec x 1 y 2)`, `(get r x)`, `(put r x v)`: three
macros over the persistent map with the field's name as a string key,
zero slots. A missing field is signal 17, catchable. `tictactoe.lova`'s
search now threads `(rec score s move k memo m)` and reads `(get st
memo)` where it read `(nth st 2)`; the game's own board setter became
`place`, since `put` is the macro. 11.07 → 11.45 million steps for the
first move: named fields cost three percent and remove the least
readable code in the repository. The language card teaches them.

Tests 727 → 747.

### Experiment 23 (2026-09-11) - does the substrate form hold at size? (Q104)
Six tasks under Exp 22's rules but 2x-5x the size, each needing
recursion through a let-bound self-referencing lambda, the last with
eight distinct names. Five Opus sessions (s1 x2, s2 x2, tok x1):
**30 of 30 first-try, no wrong values, no failures of any kind** -- the
silent-corruption scaling failure Q101 predicted did not appear. Cost
separated further: Stage-2 is 1.68x cheaper than the s-expression on
the canonical solutions and 2.0x on what the sessions actually emitted
(33 tokens a task against 66), the byte form 2.6x dearer. But the
number hides the finding: **neither Stage-2 session composed in
Stage-2.** Both built a tree first and flattened it, keeping an
external name-to-letter table -- "the stream was a serialisation step,
not an authoring step" -- and both said linear emission is where a slip
would land. All three substrate sessions independently named the same
structural risk: a swapped or shadowed reference is still well-typed,
so it yields a wrong value with no diagnostic, the one mistake the form
invites and the one Axiom 3 cannot catch. The tok session's verdict was
the opposite of the expected one: the byte encoding is the easy part
(prefix plus fixed arity re-synchronises structurally, a missing END is
a parse error), and the cost is the missing vocabulary -- hand-currying
and expanded comparison -- at 1.5-2x Python's authoring effort. For the
third time in this family a card defect, not the form, distorted a
result: the Stage-2 card printed six reference letters where the form
has ten, so one session inlined a sub-expression three times rather
than name it. Fixed. `journal/experiment_23.md`; Q104 answered -- the
substrate is vindicated as a storage and transport form, untested as an
authoring one; Q105 (linear authoring), Q106 (a diagnostic for the
silent reference error), Q107 (regenerate the cards from the token
table; `let` and `apply` are absent from all of them).

### Experiment 22 (2026-09-11) - the three-form experiment (Q100)
The first experiment under the design-method ruling: put the three
forms of a LOVA program against each other as the thing the model must
emit -- s1 the s-expression, s2 the Stage-2 surface, tok the raw token
bytes -- on ten closed operator-only programs. Cost axis (no model):
s2 costs 141 LLM tokens to s1's 192 (1.36x cheaper on dense code, far
below the number-theory 5.38x), tok costs 520 (2.71x MORE -- the
substrate as bytes is the costliest form to emit, not the cheapest).
Generation axis (Opus 4.8): first-try 100% / 85% / 60% for s1 / s2 /
tok, attempts a task 1.00 / 1.25 / 2.00 -- reliability degrades toward
the substrate. But the s2/tok greens are contaminated: the cards were
projected from the s-expression, so nine comparison/branch macros
(sub, neg, eq, ne, lt, gt, le, ge, if) with no byte vanished while the
prose still promised them, and the arities that parentheses give for
free had to be reverse-engineered from decode errors. One s2 session
synthesised comparison from integer division; another hard-coded three
answers; the tok session learned fold/lambda/sort-by arities from the
"trailing bytes" error. That is rule 1 and rule 2 of the ruling shown:
a card made on the text does not transfer to the substrate. For a
current model the s-expression is the authoring surface; nothing
supports authoring in raw tokens. **Q101, same day:** the s2/tok cards
were rebuilt from the substrate's own operators (compare/branch as
deviation/threshold/if-surprise, every arity stated, the reference
scheme corrected) and three fresh sessions went 20/20 (s2) and 10/10
(tok) first-try, all honest -- the Exp-22 gap was the card, not the
form. At this size the three forms tie on reliability and separate on
cost, with Stage-2 dominating the s-expression (same success, a quarter
fewer tokens). The text layer is not required to author small closed
programs. `journal/experiment_22.md`; Q100 answered in part, Q101
answered; Q102 (should compare and if be operators, not text macros),
Q103 (the repair axis), Q104 (does s2 stay as reliable at
tictactoe size, where global lambda numbering and silent spacing
bite).

### The ruling (2026-09-11) — the design method
After M27, the owner asked what the remaining experiments would yield
and got the estimate: parity with Python on writing and repairing
small programs, one structural advantage (execution under a budget
with declared capabilities), nothing that reads "more convenient
than any other language". The owner's diagnosis, accepted: **LOVA
was designed with existing languages as its template**, not from the
purpose outward. The Stage-1 surface is a Lisp, the prelude a
standard library, M24-M27 each made LOVA more like Python, the
yardstick measures Python's own workflow against Python, and every
experiment's judge was a human-written hidden test -- a reviewer
under another name. The model doing the design, left to itself, will
build another human language. Three rules, recorded in `CLAUDE.md`
("The design method"): design from the AI's operations, not from
syntax, and the paradigm-lineage criterion is reversed; text takes no
part in design, decisions are made on the integer sequence and
experiments have the model emit tokens; the model's behaviour decides
between representations by measured experiment, not the designer's
taste. The limit is stated with them: the output will still carry the
shape of human code, and what the rules buy is that every part holds
its place by an experiment. First step: the three-form experiment --
the same tasks in Stage-1 text, the Stage-2 surface and raw tokens,
generated and repaired -- so the numbers say whether the text layer
stays at all. Q100.

### The ruling (2026-09-10) — one goal, four numbers
An outsider's review of the architecture at the end of M23 found that
the project's goal had been two goals folded together since the first
day: (a) an AI uses the language more conveniently, and (b) programs
are integer sequences, dense, unreadable by design, converging on
Stage 3. The axioms wrote (b) as the means to (a) and nobody measured
whether it was. The measurements now in hand say it is not: a
frontier model writes the text surface as reliably as Python (Exp 17,
79/80 vs 79/80); the Stage-1 surface costs 1.5× Python's tokens on
algorithmic tasks (Exp 12); the generator's programs are refused by
the type checker a quarter of the time (Exp 16's re-run); and every
friction the twelve programs met -- strings as codepoint lists, no
pairs, lexical boundaries, the full table -- was a tax paid to (b).
The implementation did not drift; it executed the axioms faithfully.
The drift was in the axioms.

**The owner ruled: one goal.** *An AI uses it more conveniently than
any other language, and so, later, do we.* Measured by four numbers on
the same tasks in LOVA and in another language: attempts from writing
to running correctly; context spent understanding each failure;
scaffolding a host needs to run the code safely; the cost of reusing,
repairing and tracing what was written. Axioms 3, 4, 5, 6, 7, 9 stand
as the goal's mechanisms. **Axioms 1, 2, 8, 10 are demoted to design
preferences**: the integer stays as the format and the identity, and
stops being a veto. `spec/axioms.md` carries the ruling above the
axioms; CLAUDE.md carries it above everything.

What changes first, each a tax the programs paid and measured:
- **Q84** — a pair or record type, so a fold's state is not `(nth st 2)`.
- **Q85** — native text, so a word count is not twenty nodes a character.
- **Q86** — a helper inside a boundary, so an effectful `def` need not
  be rewritten as a `let`-bound lambda.
- **Q82** stays the experiment that measures the goal itself: a real
  agent, both languages, the four numbers.

`spec/ai-convenience.md` is the yardstick written out: the steps a
person's absence removes, where the cost fell for the AI that wrote
the twelve programs (the feedback loop's re-emission, names,
positions, not knowing what exists, not checking at once, threading
state), the protocol that produces the numbers, and what the measure
asks of the design -- patch-by-path editing, faults with fixes, fewer
names and named fields, programs that carry their examples, a card
generated from the prelude, intent in the lineage. Other languages
are a parts bin from now on, not a precedent.

### Q33 and the M8 groundwork (2026-09-10)
The order was decided in the M23 retrospective: the benchmark first,
because a fine-tune on LOVABench v2 would learn a sublanguage of
straight-line arithmetic (Exp 12), then the corpus and the harness.

**LOVABench v3.** Twenty algorithmic tasks, pb61-pb80 (`ALGORITHMIC`,
`TASKS_V3`; `TASKS` stays v2 so Exp 03 / 07 / 11 measure what they
measured): factorial, Fibonacci, primality, Collatz, sums over
ranges, digits, powers, Euclid, bit counts, sorted digits. Every
prompt says what to compute and not how (a test enforces that no
prompt names an operator -- Exp 13 F3's complaint about v1/v2). The
evaluator now compiles with the prelude in scope, so a solution is
judged the way a program runs: 80/80 LOVA references and 80/80
Python references pass (`tests/test_lovabench.py`). Q33 closed.

**The corpus.** `corpus/finetune.py` makes (prompt, program) pairs
from twelve families that render an English prompt, a LOVA program
and a Python oracle from the same parameters; each pair is run
against three oracle-made tests through the benchmark evaluator and
kept only if it passes, so the corpus cannot teach a wrong program.
The compositional family -- an aggregate of a transform of a filter
of a source, each fragment carrying its own English -- is where the
variety comes from. Held out by construction: a program that is a
benchmark template, or a family setting that reproduces a benchmark
task (each family names its own), is dropped. 3 000 pairs in 7
minutes, 87 failures dropped (all of them the oracle refusing a
parameter), 1 255 held-out, 4 236 duplicates: the families make a
few thousand distinct programs and no more, which is the corpus's
honest size. Two chat formats: with the one-page language card in
every example (the prompt a base model gets) and without it (a
sentence; what a fine-tuned model is trained and then judged with).
Training tokens: 257 000 without the card, 3.1 million with it.

**The card.** `corpus/language_card.md`: the language on one page,
for a model that has never seen it -- syntax, arithmetic, lists and
text, the library, six examples, all of which a test runs.

**The harness.** `experiments/experiment_17_llm_benchmark.py` asks a
model twice per task, LOVA and Python, runs each answer against the
tests -- Python in a subprocess with a timeout, so a hang is a
failure -- and reports pass@1 per category. Any OpenAI-compatible
endpoint; `--dry-run` sends the references through the same pipe
(80/80 LOVA, 79/80 Python: pb20's keyword-argument weakness, as in
Exp 07). `experiments/m8_finetune.py` estimates, submits and polls a
hosted fine-tune: **~$2.31 for three epochs on gpt-4o-mini** without
the card, ~$28 with it.

**Also.** `parse_with_prelude` caches the prelude's parse per name
base and copies its definitions in: 68 ms → 6.7 ms a parse,
identical trees on 98 sources; the evaluator is now the compiler's
time, 48 ms.

**The first data point, without a key (Exp 17).** The owner's
framing -- most people write code with Claude, so the model that
matters is Claude -- put the run within reach: a fresh Claude session
with no tools and no repository, given the one-page card (its
examples first changed so none is a benchmark task) and the 80
prompts, one answer each, no execution. A second session wrote
Python. **LOVA 79/80, Python 79/80**, the same miss in both: pb19's
v1 prompt said "return p(5)" while its tests vary n, and a blind
reader read the prompt (now fixed). The algorithmic category is 20/20
in both. For this model the language costs no reliability and the
benchmark is at its ceiling; the case for LOVA moves to what a program
gets at run time. `journal/experiment_17.md`; Q82 (a benchmark that
separates the languages for a frontier model), Q83 (is the small-model
fine-tune still the question). The OpenAI key in this environment
returns 401; the fine-tune path stays three commands away. Tests 716
→ 725.

### Milestone 23 (2026-09-10) — The tree walk removed
Q75 asked which of two levers pays first: frame chains, or compiling
the tree away. Both were pulled, in that order of payoff reversed.

**Measured before touched.** A micro-benchmark of the three evaluator
shapes on the same tree, same accounting (`_eval` + node stack as at
M22; the walk without the stack; closures): **1115 / 910 / 586 ns per
node**. The stack was 18%; the walk itself -- `node.op`, the handler
table, `node.args[i]` per child, a call into a handler -- was another
30%. The profile of the thousand-line count agreed: `_eval` held 42%
of the self-time and the env copy in `_call` about 10%, not the other
way round as the Q75 note guessed.

**Compile to closures.** `_eval` now compiles a node the first time a
run meets it -- one Python closure per node, the children's closures
bound in as free variables -- and evaluation is a call. Twenty-two
operators (literal, `ref`, the arithmetic, the list and map
operators, `if`, `seq`, `let`, `lambda`, `apply`, `loop-until`) have a
hand-inlined template; the other forty-one run their unchanged M22
handler inside a generic wrapper, and a handler that evaluates a child
calls back through `_eval`, which is how a quoted program or text
`read` at run time is compiled on first sight. The cache is a run's
(`Runtime.code_cache`, cleared by `evaluate`), so a tree edited in
place between runs meets fresh closures. What every node still pays
is the accounting -- the active budget and the step ceiling.

**The node stack is gone.** It existed so a trap could report its
`position_path`. The Python stack already holds it: every compiled
closure is named `_n_*` and closes over its node, and `_node_path`
reads the path off the frames at trap time, filtering by runtime so a
body-offender probe or a `trace` sandbox does not see the outer
program. Zero cost until a trap asks.

**Frames chain.** `Scope` holds its own bindings and a parent pointer;
a miss falls through (`__missing__`, one Python call however deep). A
call opens a one-entry frame where it copied ninety. The `let_chain`
flag every node had to clear became a token naming the one closure
allowed to join the binding group, so only `let` touches it. `Cons`
lost `frozen` (its constructor was `object.__setattr__` per field) and
keeps its hash; it is never mutated.

**Numbers.** Thousand-line count (`apps/wordfreq.lova`, 2 574 877
steps, unchanged to the step): **7.87 s → 3.57 s**. Ten thousand
lines, 21.8 million steps: **73 s → 33.7 s**, ~650 000 steps a
second. Every trap position, step count and bound-name list in the
new `tests/test_compiled.py` was recorded on the M22 walker first;
Exp 09 (50/50 fuzz, 5/5 repair) and Exp 12 (44/44) reproduce.
Python frames per LOVA call fell from two per node to one, so the
recursion-limit formula is now generous rather than tight; 9 000
recursive frames run under the default ceiling.

**Noticed, not caused.** Exp 16 rerun on the M22 code and on this one
gives the same numbers -- unbound references 226/1000 → 0, runnable
134 → 156 -- where `journal/experiment_16.md` records 704 → 0 and 16%
→ 37%. The generator has changed since M16 (M17–M22 added operators
it samples); the experiment's findings hold in direction and not in
figure, and the journal entry has not been re-run (Q77).

**Two things tried and dropped.** Inlining `_call` into the `apply`
template, one Python frame per LOVA call instead of two: 3.57 → 3.56
s, not worth twenty duplicated lines. Merging a curried application's
frames: a LOVA-level profile showed 250 000 of the 337 000 closure
calls are `iterate`'s anonymous predicate and step (`words` costs
three calls per character), and only 13% land on a lambda whose body
is a lambda, so the fast path would touch too little.

**The host, not the substrate.** Q75's second question -- at what
point does a substrate stop being the reference interpreter -- has an
answer that keeps it one. The core is stdlib-only, so it runs under
PyPy unchanged: 1000 lines **3.56 s → 1.8 s**, 10 000 lines **33.7 s
→ 5.2–6.4 s** (of which about a second is start-up and JIT warm-up),
~4 million steps a second on the long run. One accommodation was
needed: CPython 3.11+ spends no C stack on a Python-to-Python call,
PyPy does, and a Windows main thread has a megabyte of it, so ten
thousand LOVA frames killed the process without a traceback. On PyPy
`evaluate` now runs on a daemon thread whose stack is sized to the
depth ceiling (4 KB a frame, 64 MB floor; 1.6 KB a frame measured).
All 679 tests pass under PyPy 3.11 (7.3.20); 25 000 recursive frames
run with `--max-depth 30000`. CPython is untouched by the branch.

**The map reroots.** M22's `map-put` copied the dict -- O(n) a put,
quadratic over a vocabulary. `MapValue` now keeps one dict per family
of versions and moves it to whichever version is read (Baker's
rerooting, as OCaml's persistent arrays): the newest version owns the
dict, an older one holds the one difference that leads back toward
it. A map threaded through a fold never reroots -- O(1) a put -- and
a program that reads old versions alternately pays the chain between
them, which is what the copy cost before. `tests/
test_map_persistence.py` checks 20 random histories of 200 puts over
live versions against a copying model, entries and insertion order
both. **Measured honestly, the copy was not the CPython cost**: 3 000
lines over a 20 000-word vocabulary (14 000 keys, 24 000 puts, 27.9
million steps) take 42.7 s copying and 44.1 s rerooting -- noise; a
dict copy is a memcpy, and at these sizes it is under a second. Under
PyPy the same run goes **8.2 s → 3.8 s**, because there the
interpreter is fast enough for the copies to be half the time. The
asymptotics are the reason to keep it; PyPy is the measurement.

**The prelude, one call less per character.** `words` called `space`
on every character; written out as `(le c 32)`, a macro, the loop
saves a call and pays six nodes: 2 574 877 → 2 462 492 steps on the
thousand lines, 3.57 → 3.39 s.

Ten thousand lines now: **CPython 28 s, PyPy 5.5 s**.

**Two programs, to see what a program finds.** After the speed work
the question was usability, and the only way to measure it is to
write something. `apps/tictactoe.lova` (memoised negamax, the memo a
persistent map threaded through the search as a value, the board one
base-3 integer) and `apps/guess.lova` (the clock under a boundary, a
parsed line, a counting loop). Both worked at the first run of the
game logic; what stopped were the edges, and each stop is a finding:

- **`stdin` cannot tell a blank line from the end of input** (Q78).
  Both are the empty list, because `""` *is* `nil`. An interactive
  program cannot ask again on Enter; the games treat an empty line as
  quitting and say so. The M11 choice -- end of input is `nil`, never
  a fault -- was made for generated programs that must not block, and
  it costs every interactive one this.
- **A zero-parameter `def` is a constant, evaluated at definition**
  (Q79). `(def read-guess [] (... (read-guess)))` read a line of input
  *while being defined*, then trapped on its own name: the strict
  letrec self-reference Exp 16's re-run had just counted at 8/1000 in
  generated programs, met by hand within the hour. The compiler
  accepts it; the runtime reports `unbound ref: 86`, an integer, at
  the first use. A function that takes nothing has to take something.
- **A boundary is lexical, so a helper cannot hold an effect.**
  `(def secret [n] (inc (mod (clock) n)))` at top level, called from
  inside `(boundary "clock" ...)`, is refused by the compiler --
  correctly, per M19, and with a repair hint that says to wrap the
  use. The cost is that every effectful helper must be defined inside
  the boundary or take its effect's value as an argument; the guess
  program does the latter.
- **No pairs, so state is `(nth st 2)`.** Threading a memo and a best
  move through a fold means every step builds and takes apart a
  three-element list by position. It works; it is the least readable
  code in the repository, and it is what Axiom 8's one cons cell
  buys.
- **Cost.** The first computer move solves the game: 11.07 million
  steps, 18.5 s on CPython, ~3 s under PyPy; every later move is a
  lookup. Twenty games against random legal play under PyPy: 19 wins,
  1 draw, no loss, 103 s in all. A test cannot afford the first move,
  so the program takes its starting board as an argument and the
  tests play endgames (`tests/test_apps.py`, 6 tests).

**Three more scenarios**, one per claim the project makes about where
LOVA fits:

- *Data pipeline* -- `apps/logstats.lova`: a request log, parsed,
  grouped per service in a map, aggregated (count, mean, max,
  errors), sorted, printed. 2 000 lines plus 7 bad ones: 4.6 million
  steps, 8 s on CPython, every figure right. Worked at the first run.
  The one thing it cannot print is a mean with a decimal point:
  integers only, so `div` rounds down. Not a fault; a fact to know.
- *Two processes on the network* -- `apps/pong.lova` answers every
  datagram, `apps/ping.lova` sends k and prints the answers. Three
  pings, three answers, 1 369 and 1 773 steps, by hand. The unit test
  then found a race the hand run had been too slow to hit: the
  listening socket was bound lazily by the first `net-recv`, so an
  answer that came back between `net-send` and `net-recv` had nowhere
  to land and was lost. **Fixed**: the listener is bound by the first
  network operation of either kind, and `net-send` sends *from* it
  when one is granted, so a peer sees the port an answer can go to --
  a first step toward Q72 without a new value kind.
- *The agent's sandbox* -- `apps/sandbox.lova`: one untrusted program
  per line of input, `read` into a value, run under a `budget`, and
  reported by hash and value or by fault name. Fourteen lines
  including an infinite loop (budget exceeded), a file read without a
  boundary (capability denied), a division by zero, text that is not a
  program, a `signal 42`, a `def`-sugared program -- every one
  reported, nothing reached the sandbox, and the sandbox itself needs
  no grant. 488 112 steps. This is the scenario the project's pitch
  rests on, and it is the one that worked with the least friction:
  `when-anomaly` + `budget` + `read` + `eval` compose exactly as the
  axioms say.

Two more things the three found. **`hash` is the program's encoding,
not a digest** (Q80): the hash of `(stdout "hi from inside\n")` is a
150-digit integer, because a string is a cons chain of literals and
the integer *is* the byte sequence. Exp 01 wanted that identity; a
sandbox's log wants a fixed-width id. And a `def` cannot appear
inside a boundary, so the effectful helper of `ping.lova` is a
`let`-bound lambda -- the third time the lexical boundary asked for a
rewrite in five programs.

**Four scenarios on the axioms themselves.** The eight programs so far
used the language as a language. These four use what no other
language has, one axiom each:

- *A function is a population* (Axiom 6) -- `apps/evolve.lova`: five
  arithmetic programs seeded into a pool scored by distance from a
  target, evolved for k generations with `lib/evolution.lova`'s
  helpers, and the winner asked to account for itself from inside:
  `explain`, `eval`, `generation`, `why`, `lineage-query`. Target 42,
  60 generations: `(mul (p 5) (tau 12))`, distance 0. Target 1000,
  200 generations: `(merge (mul 33 30) 9)` = 999, twenty-second in
  its line, "mutate strength=0.3 [lit:6->9]". 16 555 steps.
- *Surprise is the debugger* (Axiom 7) -- `apps/repair.lova`: a
  patient program, a `conserve` contract it violates, and a repairer
  that mutates it and keeps a mutation only if the surprise against
  the target shrinks. Targets 42, 100 and 7 from `(merge (mul 6 9)
  1)`: fixed in 39, 37 and 20 attempts, reproducibly, and each fix
  reports its descent and its `why`. A random walk without the
  surprise signal gave up at 200; with it, hill-climbing converged
  every time. Nothing here is Python.
- *Conservation is declared in the program* (Axiom 4) --
  `apps/batch.lova`: 300 Collatz jobs, each under its own 2 000-node
  `budget`, the over-budget ones caught per job and counted rather
  than left to run. 219 finished, 81 over budget -- exactly the 219
  Python counts as reaching 1 in 75 steps. The batch survives its
  expensive items and says which they were.
- *Programs are integers* (Axiom 1) -- every app run from its
  Stage-2 projection: 12/12 identical outputs and values, the game
  included (2 977 characters, no parentheses). `tests/test_apps.py`
  keeps the game's round trip.

One thing the four found (Q81): a `{placeholder}` is filled from the
command line in the order of its *first appearance in the code*, so
`batch 300 2000` once meant 2 000 jobs at 300 nodes and `repair`
once took its attempts for its strength. The idiom that fixes it is
to declare the arguments first -- `(def jobs [] {jobs})` -- which
is what the three programs now do; whether the CLI should take
names is the question.

**What the twelve found, fixed the same day.** Q78: `stdin` keeps
the terminator, so Enter is `(10)` and only the end of the input is
`nil`; the games ask again on a blank line. Q79: the scope pass
carries the names of a binding group whose values are not yet
computed and refuses a reference to one anywhere but under a lambda
-- `(def f [] (... (f) ...))` is now a compile error that says
`read-guess`, not `86` -- and the generator no longer offers such a
name: Exp 16's 8/1000 runtime unbound references became 0. Q80:
`(digest p)`, eighteen digits from `hash` at zero slots. Q81:
`name=value` arguments. `tests/test_self_reference.py` pins the six
shapes (strict self, under lambda, later sibling, earlier sibling,
mutual recursion, zero-parameter def) on the compiler and the
generator both.

Where it stands on CPython: `_call` at ~1.5 µs (a frame, six
attribute saves and restores, the depth check) is the largest single
item, then the per-node prologue at ~0.3 µs. Tests 665 → 716. Q75
answered; Q76 asks what the next floor is; Q78–Q81 were what the
twelve programs found, and are closed.

### Milestone 7 (2026-09-09) — LOVA as a tool for agents
Named at M6 and delivered after M21, because everything it exposes had
to exist first. `core/mcp_server.py` speaks the Model Context
Protocol's stdio transport — JSON-RPC 2.0, one object per line — with
no dependency outside the standard library, and serves four tools:

- **`lova_execute`**: run a program (Stage 1 or Stage 2, placeholders,
  stdin lines, explicit capability grants), and get the value in every
  shape an agent might want (`value`, `value_int`, `value_list`,
  `value_text`), the output, the step count, and — on a trap or a
  compile error — the structured anomaly with its repair hint, flagged
  `isError` so a host can branch on it.
- **`lova_static_analyze`**: the static analysis, the compiler report,
  the compiled form, its bytes and its Stage-2 projection.
- **`lova_valid_next`**: Axiom 3 as a service. Give a partial program
  as bytes or as tokens; get every token that may follow, with types,
  effects, termination flag and telemetry priors, which tokens finish
  soonest, and — in a reference slot — the names in scope (M16). A host
  that constrains its decoding with this cannot emit an ill-typed or
  unbound program.
- **`lova_emit`**: Stage 2, s-expression, bytes, or one integer.

`lova mcp` starts it; `apps/mcp_demo.py` drives it through pipes and
calls each tool. `pip install .` now builds a wheel (0.2.0) that ships
`core`, `lib/*.lova` — a package now, so the prelude and `evolution`
install next to `core` in the same layout as a checkout — and the
corpus, with a `lova` console script. Tests 595 → 618.

The one deviation from the M7 plan: no `lova-mcp` package and no MCP
SDK. The transport is small enough to write, and a stdlib-only core
was the rule already; a second package would have been a second thing
to version for no second thing to say.

### Milestone 21 (2026-09-09) — The network, as datagrams
The IO family's last two slots, activated as named: **`net-send`
(0x31)** sends one UDP datagram — `(net-send "host:port" value)`, the
value as UTF-8 text or an integer as its digits — and yields the bytes
sent; **`net-recv` (0x32)** yields the next datagram on the granted
listening port as a codepoint list, or `nil` when none arrives within
the runtime's timeout, the end-of-input shape `stdin` has, because a
receive that can hang is a receive that can hang the substrate.

Q69 asked what the declaration looks like when the world has more than
one place in it. The answer keeps text out of the core: **the program
declares the kind, the host names the places.** `(boundary "net" ...)`
is the whole program-side declaration — one bit; `--allow
net=host:port` grants sending there, `--allow net=:port` grants
listening there, `net=*` grants any destination, and a datagram to a
place the host did not name is a `capability-denied` fault even inside
a granting boundary. `--allow all` does not include the network,
because a network grant without a place is not a grant. Datagrams
rather than streams because a datagram is one value in and one value
out — the shape every other operator has — and a stream would need a
handle, which is a value kind the language does not have (Q72).

**59 / 64 operators.** The token table is now spent but for the four
free slots (0x12, 0x13, 0x14, 0x16) that have been waiting on a
decision since M10; nothing else is reserved. Tests 574 → 595.

### Milestone 20 (2026-09-09) — Function shapes
No new operator, no new byte: a compiler inference. `Fn` said
"callable" and nothing more, so three misuses could only fail at run
time — a partial application in an integer slot (Q35), a call with too
many arguments (Q35), a call result in the wrong slot (Q51). The
checker now infers a **shape**, `Fn<arity,ret>`, from any
syntactically visible lambda: the curried arity, and the static type
of the innermost body. The shape flows through `let` into the names
that hold it, through `apply` into what a call produces — a shorter
shape for a partial application, the return type for a full one —
and through both branches of an `if` when they agree. A `when-anomaly`
handler's return type is checked against the slot the same way, so
`(merge (try x (nil)) 1)` is refused.

Where the tree does not say, the answer is still *unknown*, and
unknown is still accepted anywhere: a parameter (Q43 — no annotations,
so the honest position stands), a `head`, an `eval`, a recursive call
whose binding is still being typed. Every claim the inference makes
is one the tree supports, so nothing that ran before is refused now:
the whole suite, the prelude, and LOVABench compile unchanged — and
the prelude's `len` is now `Fn<1,Int>`, its `map` `Fn<2,List>`, so
`(head (len xs))` is a compile error where it was a run-time trap.

A shape is a subtype of plain `Fn`, and the generator is untouched: it
sees operator bytes, not shapes, and offers `apply` on the `Fn` level
as before (Q71). Q35 and Q51 closed; Q43 answered. Tests 543 → 567.

### Milestone 19 (2026-09-09) — The world, under a declared boundary
Four activations of the IO family's own slots, no free slot spent, and
the first time Axiom 4's "effect bounds in the signature" is concrete
for effects that touch the world.

**`external-boundary` (0x30)** is the declaration. `(boundary "fs-read
clock" body)` — surface sugar for `(external-boundary 5 body)`, the
mask a literal byte — says which of the world's effects `body` may
use, the way `budget` says what it may cost. **`fs-read` (0x33)**,
**`fs-write` (0x34)** and **`clock` (0x37)** are the effects: a file as
a codepoint list, a value written to a path, milliseconds since the
epoch.

The contract is checked twice, which is what the axiom asks for. The
compiler's new **capability pass** refuses any use outside a boundary
that declares it (`capability-denied`, code 9), before drop-unused, so
a lie about effects is refused even where it would be dropped. The
runtime checks the other half: a boundary the host did not **grant**
traps *before its body runs* — nothing is granted unless asked, the
CLI grants with `--allow fs-read,clock` or `--allow all`, and a test or
an experiment cannot touch the world by accident. Quoted code and
`read` text are invisible to the static pass and are checked when they
run, under the same rule.

The boundary is **lexical**: a closure keeps the capabilities of the
place it was written, wherever it is applied, and a lambda written
outside a boundary may not use the world even when applied inside.
That is the only rule a static pass can enforce, so the runtime keeps
the same one by capturing the mask in the closure — static and dynamic
never disagree. An inner boundary may only *narrow* the outer: what a
body may do is decided by the boundary around it, not by a declaration
inside it, and the compiler, the runtime and the generator all refuse
an escalation (Q70, ruled the same day). A function's own top-level
boundary is its own declaration, gated by the host's grant.

The generator learned the rule too: a slot carries the innermost
boundary's mask and an effect operator is offered only where its bit
is set, so **a generated program cannot use the world without
declaring it** — Axiom 3 at the effect level. `validates` agrees with
the compiler on all three cases. `stdout` / `stdin` stay ambient, as
M11 shipped them (Q68). The two network slots are the last of the
family and stay reserved (Q69).

**57 / 64 operators**; free slots unchanged at four. Tests 497 → 543.

### Milestone 18 (2026-09-09) — `read`, `use`, and a library of rules
Three things, one slot.

**`read` (0x1E)** is the inverse of `explain`: Stage-1 text, as a
codepoint list, to a `Program`. With both, a LOVA program can construct
a program from text and run it — `(eval (read "(mul 12 12)"))` is 144 —
which is what an agent writing LOVA from inside LOVA needs, and what a
module system needs underneath. `read` takes the full surface (`def`,
macros, strings, `use`), so a program authored in the sugar reads back
to the same core; malformed text is a `malformed` anomaly, catchable
with `when-anomaly`. It sits in the Surprise family on the old
`normal-range` placeholder because the Meta family is full (Q39 again).

**`(use "name")`** is the module system, and it is not an operator.
The prelude has been prepended textually since M11; `use` makes the
same mechanism addressable: `lib/name.lova`, or a path, spliced in
where it is named, once per program however many times it is named,
transitively, and a cycle terminates. `drop-unused` keeps it free — a
program that uses the prelude and calls nothing compiles to the same
tree as one that did not. Q50 asked for the smallest thing that is not
a module system but solves the same problem; this is it.

**`lib/evolution.lova`** is the first library the mechanism was built
for, and it answers Q61 without a slot: `evolve-with` is a custom
evolution rule — retire the least fit, add a mutation of the best at a
chosen strength — written in nine lines over `defpop` / `fitness` /
`variant` / `select` / `retire` / `mutate`. Writing it exposed two
gaps. `defpop` is variadic, so a pool could not be rebuilt from a list
of its variants; it now splices list arguments. And a pool does not
expose its own scorer, so the rule takes it as a parameter (Q67).

**53 / 64 operators**, four free slots left: 0x12, 0x13, 0x14, 0x16.
Tests 467 → 497.

### Milestone 17 (2026-09-09) — Lists hold any value
A cons cell takes a `Value` (Q42 closed the cheap way). Trees, lists of
programs, lists of functions are representable; strings are unchanged.
The price is that `head`'s result type is no longer written on the
operator — it follows the list, which the checker and the generator
cannot see — so `head` joins the result-follows-operands set and a
misuse fails at run time with a structured error. The same trade
`apply` and `ref` made. `List<T>` would recover the static answer and
now has a working baseline to be measured against (Q63).

**It broke the termination bias, instructively.** Once `head` fit any
slot, `(head (nil))` became the cheapest way to close an `Fn` slot —
two tokens against `lambda`'s three — so the depth bias would reach for
a guaranteed run-time trap. The bias now chooses among **certain**
closers only: END, a literal, an operator whose declared type is the
slot's, or a `ref` to a bound name of *known* compatible type. Every
slot type has one (`lit` / `nil` / `lambda` / `quote` / `defpop`), so the
fallback never fires. Transparent operators remain available in the
free-sampling phase, where a gamble belongs.

That change moved Exp 16's *baseline*: with the bias no longer choosing
`ref` in the old machine either, pre-M16 unbound references read
248/1000 (was 704) and runnable 29% (was 16%). The M16 column is what
matters and is unchanged in kind: **0 unbound, 38% runnable**. The
journal entry carries both readings. Tests 447 → 467.

### Milestone 16 (2026-09-09) — Scope-aware generation
`GenState.step` takes the literal's payload. A LET or LAMBDA opens a
frame, its binder names it, the binding's first token types it (unknown
for calls and parameters, matching the compiler), and the frame closes
with the form. `ref` is offered only where a bound, type-compatible name
exists; `literal_for` hands a sampler a fresh name for a binder and a
bound one for a ref. **An unbound reference is now unrepresentable for
generated programs** — Axiom 3 at the name level, which Exp 12 F4 said
it lacked.

Exp 16: unbound references in 1000 generated programs **704 → 0**;
programs that compile and run **16% → 37%**; `Fn` slots filled by
references 74 → 5, all bound (Q54 closed). The generator is now
strictly more conservative than the compiler — a mutually recursive
`def` chain compiles but cannot be generated left-to-right (Q64). Exp 10
re-measured with real names: **+32 pp** (88% vs 56%). Tests 425 → 447.

### Milestone 15 (2026-09-09) — Populations; Axiom 6 completed
The last axiom living in Python. A `Population` is a value with its own
type — a scorer plus program variants — because the language had no
collection but a list of integers (Q58), and parameterising lists (Q42)
was a larger change than a fifth value kind. Six operators on the
Evolution family's own reserved slots, activated as named: `defpop`
builds a pool from an `Fn` scorer and any number of programs,
`fitness` scores it (lower is fitter — a surprise magnitude is a score
without translation), `variant` / `select` index by pool order / by
rank, `retire` drops the least fit, and `evolve` applies
`core/populations.py`'s own rule: retire the bottom 20%, refill from
survivors with sharpness-3 fitness weighting, clone 30% / mutate 70% at
strength 0.30, drawing on the lineage store's seeded generator so a run
replays. A variant whose scorer traps scores `UNFIT` and is recorded,
never silent; the step ceiling is not a fitness signal and propagates.

**Exp 15 re-runs Exp 05 as a LOVA program** — 9/10 seeds improve,
3/10 converge, best seed 35 → 1, mean 85% of the worst-case gap closed
— with Python doing nothing but seeding and printing. Same rule as
April, different setting (0.30 vs 0.45), so the same shape rather than
the same run. Every winner can say where it came from: `generation` and
`why` read the store `evolve` wrote to, which is Axioms 5 and 6
composing.

**52 / 64 operators. Evolution 8/8, Meta 8/8. All ten axioms are now
realised in the language**, with Axiom 3 carrying its measured
qualifier and Axiom 8 its pending revision. Five free slots remain.
Tests 398 → 425.

### Milestone 14 (2026-09-09) — Programs as values; Axiom 5 enters the language
The design audit at M13 found the honest count was **8/10 axioms in the
language, 2/10 in Python**: provenance (Axiom 5) was queryable only via
`core/lineage.py`, populations (Axiom 6) only via `core/populations.py`,
and Stage 3's sole human interface — `(explain program)` — did not
exist. All three share a root cause: nothing in LOVA produced a program
as a value, so nothing in LOVA could operate on one.

**`quote` / `eval`.** Two of the seven free slots (0x29, ex-`par`; 0x1C,
ex-`predict`). `quote` yields its operand *unevaluated*, as a copy, so
registering or mutating the value never reaches back into the program
containing it; `eval` runs one in the current environment, charging the
run's own budget and ceilings. The compiler treats a quote as opaque —
no folding (the value is the tree, not its result), no rewriting, no
scope check (references resolve at eval time, with the same structured
error) — while still checking that the quoted body is well-formed.

**The Meta family, 8/8, activated for what the table named it.**
`explain` renders a program as text — **Stage 3's human interface,
reached from inside the language for the first time.** `hash` returns
the program's integer: `(hash (quote (merge (p 3) (tau 12))))` is
**55916975560956379404**, the exact integer Exp 01 quoted as proof of
Axiom 1, now producible by a LOVA program. `uid`, `generation`,
`ancestor-of`, `lineage-query` and `why` query the run's `LineageStore`,
which stopped being a placeholder list. `trace` runs a program in a
sandbox that inherits what is left of the run's ceilings and returns its
surprise deviations — introspection over Axiom 7's signal.

**Axiom 6 begins.** `clone` and `mutate` (strength as a percentage;
deterministic for the store's seed, so a derivation replays). The other
six Evolution slots need a *population* as a value, and a list holds
only integers (Q42). Q58.

Implemented operators **34 → 46 of 64**. Five free slots remain.

**Three rulings, owner-delegated ("你自己裁决吧"):**
- *heat is a dead concept.* The PFS "heat" metaphor had no implementation
  from M1 to M14 and no program ever needed it; 0x04-0x06 stay
  `cons`/`head`/`tail`. `CLAUDE.md`'s "every program carries heat"
  bullet is rewritten to what is true.
- *The Axiom 3 qualifier stays.* Without it the axiom is false; with it,
  it is measured. Recorded here because `CLAUDE.md` reserves axiom
  edits for the owner and this one was made at M9 without asking.
- *`nth` no longer returns a silent 0 past the end.* It falls through to
  `head`/`tail`'s domain-error — the standard library's one violation of
  Constraint 5, closed.

Tests 354 → 398.

### Milestone 13 (2026-09-09) — The error model, made uniform and reachable
The last gap on the basic-language list: a LOVA program could not
respond to its own anomaly. Axiom 7 says surprise is the debugger and
that AI-driven repair happens at the offending position — and the
language had no way for a program to see that anything had gone wrong.

**First, the model was not actually uniform.** Exp 08 established "one
error handler for compile-time and runtime alike", but only
`BudgetTrap` and `DeltaTrap` carried the L2 schema. Division by zero,
the head of an empty list, a reference to nothing, a value used at the
wrong type — twenty-two sites — raised a bare `ValueError` with a
sentence in it and no `kind`. So the property held for two of four
fault classes. `DomainTrap` fixes that, and **subclasses `ValueError`**
so every handler and test written against the old shape keeps working
and gains structure it can use.

**Then `when-anomaly` (0x1A).** `(when-anomaly body handler)`: evaluate
the body; if it traps, call the handler with the anomaly's integer code
and return that. The handler is an `Fn` rather than a plain expression
because a handler told nothing can only guess, and the anomaly is the
signal. `(try body fallback)` is the macro for when the code does not
matter — zero slots, like the rest.

The result type follows the body, so a guarded expression stands
wherever the unguarded one could. A handled anomaly is **not an
invisible one**: it lands in `rt.caught` and emits a surprise event, so
an agent reading the run afterwards sees what the program swallowed.

**One fault is deliberately not catchable.** `StepTrap` — the step
ceiling is the substrate's guarantee that a program terminates, and a
guarantee a program can mask is not one. Depth *is* recoverable, the
way a host language lets you catch stack exhaustion.

One slot spent, from the Surprise family's own reserved range, for what
the original table named it. 33 → **34 of 64**; seven free slots left.

**It found a bug in Experiment 10, and changed its headline number.**
Both of that experiment's samplers had reimplemented the termination
bias as "prefer END, else LIT_INT" — which reads like a rule and is
not one, since neither is valid in an `Fn` slot. It did nothing exactly
where it was needed, and hung the moment M13 made `Fn` slots common.
The bias now lives in the library as
`core.generator.cheapest_to_finish`, and both samplers call it, so the
comparison isolates the weighting instead of confounding it with two
different termination strategies. **Weighted vs uniform moved from
+20 pp to +40 pp** (100% vs 60%, N=50) — a better-controlled
experiment, not a better sampler. The 2026-04-24 row below reports the
confounded number; this is the one to quote.

Tests 329 → 354.

### Milestone 13 (2026-09-09) — The error model, made uniform and reachable
The last gap on the basic-language list: a LOVA program could not
respond to its own anomaly. Axiom 7 says surprise is the debugger and
that AI-driven repair happens at the offending position — and the
language had no way for a program to see that anything had gone wrong.

**First, the model was not actually uniform.** Exp 08 established "one
error handler for compile-time and runtime alike", but only
`BudgetTrap` and `DeltaTrap` carried the L2 schema. Division by zero,
the head of an empty list, a reference to nothing, a value used at the
wrong type — twenty-two sites — raised a bare `ValueError` with a
sentence in it and no `kind`. So the property held for two of four
fault classes. `DomainTrap` fixes that, and **subclasses `ValueError`**
so every handler and test written against the old shape keeps working
and gains structure it can use.

**Then `when-anomaly` (0x1A).** `(when-anomaly body handler)`: evaluate
the body; if it traps, call the handler with the anomaly's integer code
and return that. The handler is an `Fn` rather than a plain expression
because a handler told nothing can only guess, and the anomaly is the
signal. `(try body fallback)` is the macro for when the code does not
matter — zero slots, like the rest.

The result type follows the body, so a guarded expression stands
wherever the unguarded one could. A handled anomaly is **not an
invisible one**: it lands in `rt.caught` and emits a surprise event, so
an agent reading the run afterwards sees what the program swallowed.

**One fault is deliberately not catchable.** `StepTrap` — the step
ceiling is the substrate's guarantee that a program terminates, and a
guarantee a program can mask is not one. Depth *is* recoverable, the
way a host language lets you catch stack exhaustion.

One slot spent, from the Surprise family's own reserved range, for what
the original table named it. 33 → **34 of 64**; seven free slots left.

**It found a bug in Experiment 10, and changed its headline number.**
Both of that experiment's samplers had reimplemented the termination
bias as "prefer END, else LIT_INT" — which reads like a rule and is
not one, since neither is valid in an `Fn` slot. It did nothing exactly
where it was needed, and hung the moment M13 made `Fn` slots common.
The bias now lives in the library as
`core.generator.cheapest_to_finish`, and both samplers call it, so the
comparison isolates the weighting instead of confounding it with two
different termination strategies. **Weighted vs uniform moved from
+20 pp to +40 pp** (100% vs 60%, N=50) — a better-controlled
experiment, not a better sampler. The 2026-04-24 row below reports the
confounded number; this is the one to quote.

Tests 329 → 354.

### Milestone 12 (2026-09-09) — Mutual recursion, and the generator catching up
Two debts, both closed with **no new tokens**.

**Q34 — mutual recursion.** A group of `def`s desugars to a chain of
`LET`s in body position, and a closure captures its environment frame
*by reference*. So the fix is to let that chain share one frame: the
first function then sees the last, and `even?` / `odd?` becomes
writable. A `LET` joins the group only when it is directly in another
`LET`'s body — a `LET` in an argument position, or inside a lambda,
opens its own frame, so nothing leaks a binding into a sibling
expression. Shadowing also starts a fresh frame, or re-binding a name
would reach back and change what an earlier closure sees.

Strictly widening, like the letrec change in M9: a forward reference
used to be an `unbound-ref` *compile* error, so every program that
compiled before compiles and means the same thing.

It broke `drop-unused` on the way in, which is the interesting part.
That pass asked "does my body mention me", and with mutual recursion a
binding can be reachable only from an **earlier sibling's value** —
`od` is called by `ev` and by nothing else. Liveness is now a fixpoint
over the whole group. An unused mutually recursive pair is still
dropped: reachability, not mere mention.

**Q52 — the generator had fallen behind the checker.** M11 made `if`,
`let`, `seq` and `apply` take their result type from their operands,
but `valid_next` still read one declared `out_type` per operator. So
the compiler accepted `(if (nil? xs) (nil) (cons ...))` while the
generation state machine could not produce it — meaning **no generated
program could have the shape of `map`**, which would have quietly
shaped every corpus M8 might build.

Two kinds of operator now fit any non-literal slot, and the reasons are
kept apart: `RESULT_FOLLOWS_OPERANDS` (`if` / `let` / `apply`) is a
typing rule, while `REF` is a limit on what the state machine can *see*
— a reference's type is its binding's, and name ids live in `LIT_INT`
payloads the machine never inspects (Exp 12, F4). Admitting `ref` is
what lets a generated program call a bound function at all.
`validates` now starts from `Value` rather than `Int`, matching the
compiler's top-level type since M11.

A full `map` definition now passes the state machine; `constrained_random`
is still 100% well-formed (300/300). Completion cost for an `Fn` slot
dropped 3 → 2, because naming a function is cheaper than writing one.

Tests 320 → 329.

### Milestone 11 (2026-09-09) — A usable language
Not an experiment; the four things that stood between LOVA and being a
language somebody could pick up. Two token slots, both taken from the
IO family's own reserved range — an activation, not a reallocation.

**Output.** `stdout` (0x35) and `stdin` (0x36), the first operators
that touch the world. `stdout` takes a `Value` because it writes both
shapes — an integer as its digits, a list as the text of its codepoints,
which is what makes `"abc"` print as `abc` — and returns the number of
codepoints written, so a write sits anywhere an Int does. Output is
collected on the `Runtime` by default and only forwarded when a caller
sets `out_stream`, so a generated program can never spray a terminal;
input is a queue before it is a handle, so nothing can block on one.
`stdin` is the language's only non-deterministic operator and
`static_analyze` says so.

**Logic.** `not` / `and` / `or` / `eq` / `ne` / `le` / `ge` / `neg` /
`abs` / `min` / `max` / `cond`, all as macros, **zero slots** — on
Exp 13's finding that an expansion buys the same tokens as an operator
for none of the budget. `and` and `or` short-circuit; anything that
mentions an argument twice binds it first, which was free before `stdout`
existed and is not any more.

**A standard library.** `lib/prelude.lova`, ~20 definitions written *in
LOVA* — `len`, `append`, `reverse`, `nth`, `sum`, `map`, `filter`,
`fold`, `range`, `pow`, `digits`, `println` and the rest. Nothing in it
is a builtin, which is the real test of whether the core is adequate.
It is free: a new compiler pass, **drop-unused**, removes any binding
the program never mentions, so a program that calls none of it compiles
to what it would have anyway — **474 nodes → 1**. The pass refuses to
drop a binding whose value has an effect, which was vacuous before
`stdout` and is load-bearing now.

**A way to run a file.** `core/cli.py`: `run`, `repl`, `emit`,
`analyze`. Until now every program in `apps/` shipped with a
hand-written Python driver doing the same forty lines. The result goes
to stderr as `=> value` so what the program writes is the only thing on
stdout; traps print their structured anomaly and exit non-zero.
`CLAUDE.md` promised `python -m core.repl` since M1; it exists now, as
`python -m core.cli repl`.

**One real type-system fix fell out of it.** `if-surprise` declared
`[Int, Int, Int] -> Int`, so **every list-returning conditional was
unrepresentable** — `map`, `filter` and `reverse` could not be written,
because each is `(if (nil? xs) (nil) (cons ...))`. `if`, `let`, `seq`
and `apply` are now *transparent*: the checker pushes the expected type
into the position that determines the result. Strictly more precise for
the first three; for `apply` strictly less, since a call's result type
is unknown for the same reason curried arity is (Q35). A program's
top-level type became `Value` too — a program is an expression, not an
integer expression, and `"hi"` is a legal program.

Tests 265 → 319.

### Exp 14 (2026-09-09) — The Stage-2 surface, built and measured
Closes Q37, the largest open item in the project. Stage 2 had been on
the roadmap since the first design document and had never existed;
every number quoted for it was a projection from AST node counts.

`core/surface2.py` is the text projection of the byte encoding: one
printable character per byte, no delimiters, because **the encoding
never had any** — `decode` recovers the tree from arity alone, and
Stage 1's parentheses were re-stating something the substrate already
knew. That makes Stage 2 stage-coherent by construction (Axiom 10)
rather than a second syntax to keep in sync. One compression rule
beyond one-char-per-byte: `(ref k)` for k in 0..9, which is 22% of AST
nodes.

**Losslessness 2150/2150** (60 bench + 10 algorithmic + 5 apps + 1000
generated, with and without the digram; bytes compared, not just
trees). **Algorithmic density 0.66× → 1.13× — LOVA is denser than
Python on real programs for the first time**, past the 0.76× ceiling
Exp 13 proved no token-table change could beat. **LOVABench 2.00× →
5.38× vs sympy-Python, 22.89× vs pure.** Parentheses fall from 25% of
the token cost to zero.

Exp 11's Stage-2 projection predicted 546 tokens where the built
surface needs 322 — it **understated density by 70%**, having erred in
the *opposite* direction on algorithmic programs in Exp 12. Node count
is a poor proxy in both directions, and two experiments quote it.

Also the first time Axiom 2 was cashed in rather than asserted:
`W0\1*LL$A7;` is unreadable without the table, and that is the point.

Untested and now load-bearing: **whether a model can emit Stage 2**
(Q47). Constrained decoding should make it easier than Stage 1 — no
delimiters to misplace — but nothing here shows it.

### Exp 13 (2026-09-09) — Token budget re-derived
Not a milestone; a measurement taken before spending the remaining
slots. Census over three corpora (LOVABench v2 / Exp 12 algorithmic /
`apps/`) plus a decomposition of where the Stage-1 tokens actually go,
then three density levers measured separately. Proposal in
`spec/token-budget.md`, including an **Axiom 8 revision awaiting the
owner's approval** (not applied).

Headline: the experiment **refuted its own hypothesis**. Exp 12's F7
said the density lever was the operator set; it is not. One-token
operator spellings close **30%** of the algorithmic gap for **zero
slots**; `lt` + `sub` close **9%** for two slots; the remaining **61%**
is parentheses and identifiers, which no allocation of 64 slots can
reach. Best case under any table change is 0.76× — still below Python.
The instrument for the residual is the Stage-2 surface, which has never
been built (Q37).

Second finding: **LOVABench cannot testify about the table.** Its own
docstring says tasks were chosen to be expressible in LOVA's *present*
power, so operator-use statistics drawn from it are circular — the
number-theory family is 33% of benchmark use and 3-5% everywhere else,
with `p` / `tau` / `mobius` at zero outside it. This circularity is
inherited by Exp 10's telemetry priors, which weight generation (Q40).

Proposal: spend 10 of 14 free slots — `nil`/`cons`/`head`/`tail`/`nil?`
(pairs, lists **and** strings-as-codepoint-lists in one purchase),
`div`, `quote`/`eval` (Axiom 1 and Stage 3's `explain` are currently
unreachable from inside the language), `lt`/`sub`. Keep the
number-theory family; reallocation is the reserve position.

### Q30 closed (2026-09-09) — Exp 03 and Exp 07 run again
Both had been dead since the corpus grew from twenty tasks to sixty in
May: `CLAUDE_SOLUTIONS` and `PYTHON_SOLUTIONS` covered pb01-pb20, so
Exp 03 died on a coverage assertion and Exp 07 on `KeyError: 'pb21'`.
Four months, while the README quoted their headline number.

The root cause was duplication, not absence. Exp 07 kept an *inlined
copy* of Exp 03's LOVA solutions, and the v2 Python solutions already
existed in `corpus/python_solutions.py` — written for Exp 11's density
measurement and never wired back. So: one table per language, Exp 07
imports rather than copies, and a coverage assertion now fails loudly
instead of four months later. The forty missing LOVA solutions were
written from the prompts, same protocol as the original twenty.

**Numbers on the full 60-task set, superseding the v1 slice:**

| | v1 (20 tasks) | v2 (60 tasks) |
|---|---|---|
| Reference | 20/20 | **60/60** |
| Claude-as-oracle | 20/20 | **60/60** (180/180 cases) |
| Unguided constrained-random | 1/2000 | ~3/6000 |
| pass@1, LOVA vs Python | 20/20 vs 19/20 | **60/60 vs 59/60** |
| test cases, LOVA vs Python | — | **180/180 vs 177/180** |
| raw byte density | 39.2× | **25.8×** |

The single Python failure is still pb20 — the same keyword-argument /
scope-shadowing weakness the v1 run found. Forty more tasks added no
new Python failure and no LOVA failure. Density fell 39.2× → 25.8× on
the broader set, the same direction Exp 11's v1 → v2 re-run went, and
for the same reason: the v1 slice over-represented LOVA's best shapes.

**And a caveat that changes how this should be quoted** (Exp 13, F3).
LOVABench's tasks were authored *in* the language, and the v2 prompts
state the formula outright — "Compute p(tau(sigma(n)))". So the
Claude-as-oracle baseline measures **transcription into s-expressions**,
not program synthesis. It is real evidence that the surface is
writable. It is not evidence that an LLM can program in LOVA, and the
60/60 should never be quoted as if it were. Q33's algorithmic corpus is
what would measure the latter.

All 14 experiments now run.

### Known broken
Nothing. All 14 experiments run as of 2026-09-09.

Kept as a section because it earned one: Exp 03 and Exp 07 sat dead
here from M9 to M13 while the README quoted their headline. The failure
mode was two copies of one table drifting from a corpus neither of them
imported. Both now import; a coverage assertion fails on the spot if
the corpus grows again.

### Lineage
- Parent project: DNA OS v3 (`../dna-os-v2.1/dna-os-v2.1/dna_os_v3/`)
- DNA OS v3 is a research artifact validating the conceptual
  vocabulary (PFS / conservation / surprise / lineage / evolution).
  LOVA takes these concepts and builds a language around them.
- LOVA does NOT import DNA OS v3 code. Concepts transfer; code does
  not.

### Open design questions
- Exact 64-token table — which operators are in the core, which are
  stdlib? First draft in CLAUDE.md and `spec/tokens.md`. Revisit after
  M3/M4.
- Q05: Clean interface between `valid_next()` and LLM logits mask
  (raised by Exp 02).
- Q06: Frequency-calibrated sampler for corpus bootstrap (raised by
  Exp 02; uniform random is not what a fine-tuned LLM produces).
- Q07: Phasing schedule for the 46 reserved operators — which land in
  M3 (effects / IO), which in M4 (evolution / populations), which in
  M5 (meta / lineage).
- Q08: Information-theoretic compression measurement — bits/token
  saved by type-directed generation vs unguided.
- Corpus generation strategy — synthetic programs from type system,
  translation from existing corpora, or RL self-play?
- Fine-tuning budget — what's the minimum training data to get a
  LOVA-fluent model? Order-of-magnitude estimate needed.

### Raised by Exp 12 (M9)
- ~~**Q30**~~: *closed 2026-09-09.* Both run on all 60 tasks; the
  headline moved to 60/60 vs 59/60. See the entry above, including the
  caveat about what the Claude baseline actually measures.
- **Q31**: Should the number-theory family give up more slots? `div`
  and a comparison operator remove the two costliest idioms Exp 12's
  F7 identifies. Measure the density gain before deciding.
- **Q32**: Is there a terser Stage-1 surface that closes the negative
  density result without touching semantics? F7 suggests mostly no,
  but it is measurable.
- ~~**Q33**~~: *closed 2026-09-10.* LOVABench v3 adds pb61-pb80, an
  algorithmic category whose prompts say what and not how; `TASKS_V3`
  is what M8 trains toward and is judged by. The question as raised:
  LOVABench v3 with an algorithmic category — the present 60
  tasks cannot express recursion, so the benchmark cannot detect a
  regression in it.
- ~~**Q34**~~: *closed by M12.* A chain of `LET`s shares one frame, so a
  group of `def`s is mutually recursive. No new token.
- ~~**Q35**~~: *closed by M20.* `Fn<arity,ret>` is inferred from a
  visible lambda; too many arguments, and a partial application in a
  non-function slot, are compile errors. It paid for itself in one
  afternoon: no byte, no operator, a compiler pass.
- **Q36**: `constrained_random` can now emit lambdas, so Exp 03's
  well-formedness rates and Exp 10's telemetry DB were measured against
  a different token distribution than the current one. Both need a
  re-run before their numbers are quoted again.

### Raised by Exp 13 (token budget)
- **Q37**: Build the Stage-2 terse surface and measure it. It carries
  61% of the algorithmic density gap and exists only as a node-count
  projection — which Exp 12 showed is pessimistic in the wrong
  direction. Until it is real, the density pitch rests entirely on the
  number-theory regime.
- **Q38**: Ship the one-token operator aliases? Zero slots, verified on
  ten programs, 30% of the gap. The only argument against is that it
  makes the surface uglier for humans, which Axiom 2 says is not a
  consideration — so the axiom and the reluctance cannot both stand.
- **Q39**: Does the 8x8 family structure earn its keep? It forces
  operators into semantically wrong families and it is not what makes a
  token one byte (a byte holds 256 values; 64 is self-imposed).
- **Q40**: Every statistic drawn from LOVABench inherits the corpus's
  self-selection, including Exp 10's telemetry priors, which are used
  to *weight generation*. What does the +20 pp become on a corpus not
  authored in the language?
- **Q41**: `loop-until` has zero uses in any corpus. Is a single-value
  loop combinator the right iteration primitive, or should it thread an
  accumulator — which is what every program that iterates needs?

### Raised by M10 (data)
- ~~**Q42**~~: *closed the cheap way by M17.* `cons` takes a `Value`
  and `head` is transparent. `List<T>` would make `head` static again;
  Q63 holds the measurement.
- ~~**Q43**~~: *answered by M20: unityped parameters are the honest
  position.* A shape says what a function returns, not what it takes;
  a parameter's misuse is caught where its value is used, at run time,
  with a structured error. Inferring parameter types from use would be
  the next step and would need a unifier, which is the thing a tiny
  type system is not.
- **Q44**: `MAX_GENERATED_TOKENS` is a generator ceiling the way
  `MAX_STEPS` is a runtime ceiling. Should it be part of the substrate
  contract — i.e. should `valid_next` itself expose completion cost, so
  *any* sampler (an LLM included) can see which choices terminate?
- **Q45**: Should `partition` (0x02) now return a real pair? It returns
  `n // 2` with a comment promising a pair "when we have Pair types".
  We have them. Changing it would alter Exp 01's headline integer, so it
  is a decision, not a cleanup.

### Raised by Exp 14 (Stage-2 surface)
- **Q46**: More digrams? `$&0` and `\1` are the next most frequent
  subtrees, each free in slots and each fitting the surface a little
  harder to the corpus that motivated it. What is the principled
  stopping rule — a frequency threshold, or a held-out corpus?
- **Q47**: **Can a model actually emit Stage 2?** Everything Exp 14
  measured is contingent on this and none of it tests it. Constrained
  decoding through `valid_next` should make Stage 2 *easier* than
  Stage 1 (no delimiters to misplace); measure pass@1 on LOVABench,
  same model, constrained decoding, no fine-tuning. The most
  load-bearing open question in the project.
- **Q48**: Should Stage 1 be relegated to audit-only in the docs and
  `apps/`? Two live surfaces cost something, and Axiom 2 says which is
  the product.
- **Q49**: LOVABench was selected for what Stage-1 LOVA could express
  (Exp 13 F3), so the 5.38× inherits that circularity. A v3 corpus with
  an algorithmic category (Q33) would measure both regimes on one task
  set.

### Raised by M16 (Exp 16)
- **Q64**: Mutual recursion is compilable (M12) but not generatable: a
  left-to-right machine cannot reference a name bound later. A
  forward-declaration token, or a two-pass generator?
- **Q65**: 63% of generated programs now trap at run time — the
  semantic layer Axiom 3 said errors would move to. Which traps are
  avoidable at generation (`div` by a literal zero, `head` of a literal
  `nil`), and would a value-aware machine be Axiom 3's next level or
  overreach?
- **Q66**: Exp 02's 100% vs 0% measured the generator with its own
  scope-blind validator. Re-run with the compiler as judge: 37%
  runnable vs ~0%, which is the honest form.

### Raised by M15 (Exp 15)
- ~~**Q61**~~: *answered by M18 the second way.* `lib/evolution.lova`
  holds `evolve-with [pop score strength]`, written from the primitives;
  no parameter was added to `defpop` or `evolve`.
- **Q62**: The scorer runs every variant on every `select` / `retire`
  / `evolve`; Exp 05 had rolling fitness windows and dispatch counts.
  Is memoised fitness a population concern or a scorer concern?
- **Q63**: With a `Population` type in hand, would `List<T>` (Q42)
  have made it unnecessary? Rewrite `evolve` from list primitives once
  they exist and compare.

### Raised by M14
- ~~**Q58**~~: *closed by M15.* A `Population` is its own value type;
  the six operators are implemented and Exp 15 reproduces Exp 05 from
  inside the language. `List<T>` (Q42) remains the better long-term
  shape and now has something to be measured against (Q63).
- **Q59**: `eval` runs quoted code in the *caller's* environment, which
  makes `(quote (ref 0))` mean different things in different places.
  That is Lisp's `eval` and it is what made `trace` and `explain` easy;
  it is also dynamic scope by the back door. Should a program value
  close over its environment at `quote` time instead?
- **Q71**: Shapes live in the compiler. The generation state machine
  still records a lambda binding as `Fn`, so it can generate
  `(apply f 1 2)` for a unary `f` — well-formed at the operator level,
  refused by the checker. Carrying the shape in the `Frame` would make
  the misuse unrepresentable (the M16 move, for arity), at the cost of
  the machine inferring body types as it goes. Is the generator's
  runnable rate (Q65) limited by this?
- ~~**Q70**~~: *ruled: nested boundaries narrow.* An inner boundary
  declaring more than the enclosing one is a compile error, a run-time
  trap for evaluated code, and unrepresentable by generation; a closure
  carries "enclosed" with its mask. A function written *outside* any
  boundary still declares for itself — that is a library saying what
  it needs, and the host's grant is the authority across the call.
- ~~**Q69**~~: *closed by M21.* The program declares the kind (`net`,
  one bit); the host names the places (`--allow net=host:port`,
  `net=:port`). Where is host policy, not program text, so the byte
  sequence stays free of addresses and Stage 3 is untouched.
- ~~**Q77**~~: *closed 2026-09-10; re-run and re-recorded.* Exp 16's
  journal entry now carries three readings (M16: 704 → 0, 16% → 37%;
  M17: 248 → 0, 29% → 38%; M23: 226 → 0, 13% → 16%). The zero holds at
  every reading. The runnable rate fell because the language grew:
  250/1000 generated programs are now refused by M20's arity-aware
  checker (`type-mismatch` -- Q71's missing measurement) and 172 trap
  on a capability the sandbox does not grant. Eight programs in a
  thousand are a strict `let` self-reference the compiler accepts and
  the runtime traps; the M9 letrec left that open.
- ~~**Q86**~~: *closed by M26.* A boundary is a region: `def` forms
  may follow its capability spec and are bound inside it. The question
  as raised: a boundary is lexical, so a top-level `def` cannot use an
  effect even when called from inside one; three of the twelve
  programs were rewritten around it. Under the goal, what is the
  cheapest form that lets a helper carry an effect -- a `def` inside a
  boundary, a boundary on the `def`, or dynamic scope for the grant?
- ~~**Q85**~~: *closed by M25.* A text family at 0x40-0x4D, a text
  literal, every list operator reading a text as its codepoints; the
  thousand-line count 2.46 → 0.60 million steps. The question as
  raised: text is a list of codepoints, so `words` costs about twenty
  nodes and three calls a character and every text program pays for
  the representation. Under the goal: a native text value (one slot,
  or a `Value` kind with no slot), with the list view kept for
  programs that want it?
- ~~**Q84**~~: *closed by M24.* `rec` / `get` / `put`, macros over the
  map with string keys; a missing field is signal 17. The question as
  raised: there are no pairs; two results come back as a list and are
  taken apart by position, and `tictactoe.lova` threads a three-element
  state through a fold that way -- the least readable code in the
  repository and the kind an AI gets wrong. Under the goal: a pair or a
  record, and destructuring in the surface?
- **Q83**: Exp 17's fine-tune half (`m8_finetune.py`, ~$2.31 on
  gpt-4o-mini) would answer whether a model that cannot write LOVA from
  a page can be taught to. The model most people use needs no
  teaching (79/80 from the page). Is the small-model question still
  worth the run, and what would its answer change?
- **Q82** *(measured in part by Exp 18, 2026-09-10)*: Pass@1 on eighty short tasks saturates at the top (79/80
  in both languages, the same miss). What separates the languages for
  a frontier model: programs the size of `tictactoe.lova` written
  blind from a specification, or a repair loop -- the model fixing its
  own failure from the structured anomaly versus from a traceback,
  scored on attempts to green? Axiom 7's claim is the second. Exp 18
  ran the loop on ten tasks: 11 attempts against 10, the one miss
  fixed from the hint in one try, scaffolding a function call against
  a subprocess; feedback and reuse still one-sided. The rest is Q87
  and Q88.
- ~~**Q87**~~: *answered by Exp 19, 2026-09-11.* Eight bigger tasks,
  three sessions per language, two runs: parity on seven tasks; on the
  game-tree search LOVA took two to five more attempts, all rewrites
  for cost after a step trap with no attribution. The trap now names
  where the budget went. Ten sessions is Q92.
- **Q90** *(sharpened by Exp 20)*: the interpreter's speed as an
  attempts number. The natural minimax over a list board costs 10-37
  million steps with native list access (was 24 to over 40) at
  ~400 000 a second, against a second of Python; PyPy is not on this
  machine. Is a native evaluator the change, or Q94's native walkers?
- ~~**Q91**~~: *answered by Exp 20, 2026-09-11.* Yes, qualified: h04
  13 → 9 attempts over three sessions, every session rewriting from
  the list rather than guessing -- and one misled by it, because it
  counted calls. It ranks by steps now.
- **Q93**: with steps in the ranking, native `nth`, and a cost section
  on the card, does the natural h04 pass in one rewrite, or in none?
  Three sessions, the same tasks.
- ~~**Q94**~~: *closed by M27, 2026-09-11.* A list family of eight at
  0x50-0x57; 4-25× per element; the natural search's cost is Q99.
- ~~**Q100**~~ *(answered in part by Exp 22-23, 2026-09-11)*: the
  three-form experiment. On the emit axis, once each form has a card
  built from its own operators, all three are written first-try at both
  sizes tested; they separate on cost, Stage-2 saving 1.36x on
  one-liners and 2.0x at size. The repair axis is still Q103.
- ~~**Q101**~~ *(answered, 2026-09-11)*: a substrate-native card took
  s2 to 20/20 and tok to 10/10 first-try. The Exp-22 gap was the card.
- ~~**Q102**~~ *(costed, 2026-09-11, `spec/token-budget.md`)*: making
  compare and subtract operators would save 5-6% of substrate bytes;
  the common `(sub n 1)` already folds free and a model builds the rest
  from the recipe first-try. Not worth the slots on current evidence.
- ~~**Q104**~~ *(answered by Exp 23, 2026-09-11)*: at 2x-5x the size
  all three forms were written first-try (30/30) with no wrong values.
  The qualification is the finding: neither Stage-2 session authored in
  Stage-2; both composed a tree and serialised it.
- **Q105**: linear authoring -- can a model emit Stage-2 left-to-right
  without composing a tree first, and at what cost? The experiment that
  actually tests the substrate as an authoring surface.
- **Q106**: a diagnostic for the silent reference error -- can the
  compiler flag a reference whose binder is plausibly wrong (a shadow,
  an out-of-scope number, a binding never used)? It is the one mistake
  the substrate form invites and the one Axiom 3 cannot catch.
- **Q107**: the cards are not self-sufficient -- `let` and `apply` are
  absent from the operator table of all three, and the tok card has no
  text literal. Generate every card from the token table itself.
- **Q98**: a `def` whose name is an operator's (`range`, `any`, `map`
  ...) is read as the operator at every call site, silently. A compile
  warning, or an error?
- **Q99** *(replay half answered by M27)*: the natural game-tree
  search under the list family: two of six first attempts fit 7M
  (6.3M, 6.8M), four do not (9.5M-29.3M), their cost now the program's
  own loops at ~400 000 steps a second. What Q93's session count
  becomes is the open half.
- **Q92**: ten sessions per language on one model, Exp 18's and 19's
  tasks together, so the per-task attempt distribution is load-bearing.
- **Q88** *(measured in part by Exp 21, 2026-09-11)*: the reuse leg
  of the yardstick. The repair half: eight one-token faults in
  programs of 20-40 lines, three sessions per language -- 30 attempts
  against 28, 672 characters against 391, 27 108 read against 12 069,
  every fault found by reading before feedback. NULL at this size;
  the variant-task half and `why` on the result are still open, and
  the size where reading fails is Q95.
- **Q95**: the repair leg at a size where reading fails: faults with
  run-time symptoms in `apps/`-sized programs, the span and `hot`
  against a traceback, on the same faults.
- **Q96**: is a program that carries `example` forms repaired in fewer
  attempts than the same program without them?
- **Q97**: density as a repair cost -- 2.2× read per touch at Stage 1;
  what does the Stage-2 surface do to it?
- **Q89**: is the list of names in scope worth its place in an
  unbound-name anomaly, when the card lists them and the hint carries
  the nearest? It is most of the 823 chars such a fault costs to read.
- ~~**Q81**~~: *closed 2026-09-10.* `name=value` on the command line
  fills the placeholder it names, the rest fill positionally, and a
  missing one is named in the error. The question as raised: a
  `{placeholder}` is filled positionally in the order of
  its first appearance in the code, which a reader cannot see and a
  comment cannot fix (M22 ruled comments out so they could not decide
  the order). Two of the twelve programs got their arguments crossed.
  The declare-first idiom, `(def jobs [] {jobs})`, makes the order
  visible; should the CLI also accept `jobs=300`, or a header the
  program states?
- ~~**Q80**~~: *closed 2026-09-10, at zero slots.* `(digest p)` in the
  prelude is `(hash p)` modulo the Mersenne prime 2^61 - 1: eighteen
  digits, stable, one line. `sandbox.lova` reports by it. The
  question as raised: `hash` yields the program's own integer -- Exp 01's
  identity, `(merge (p 3) (tau 12))` = 55916975560956379404 -- which
  for a program holding a fifteen-character string is 150 digits.
  A sandbox's report, a lineage record, a population's roster all
  want a fixed-width id. A digest is a second notion of identity;
  is it worth having, and if so is it an operator (the table is
  full: Q74) or a library function over the bytes `hash` gives?
- ~~**Q79**~~: *closed 2026-09-10.* The scope pass tracks the names of
  a binding group whose values are not yet computed and refuses a
  reference to one anywhere but under a lambda (`unbound-ref`, reason
  `strict-self-reference`, with the surface name in the CLI's report);
  the generator no longer offers such a name, so Exp 16's 8/1000
  became 0 (the one runtime `unbound-ref` left is `eval` of text
  `read` at run time, which is the runtime's to check). A
  zero-parameter `def` stays a constant. The question as raised:
  `(def f [] body)` is a constant evaluated where it is
  defined, and a recursive reference inside it is a strict letrec
  self-reference: accepted by the compiler, an `unbound-ref` naming
  an integer at run time (found by hand in `guess.lova`; counted at
  8/1000 generated programs by Exp 16's re-run). Should the scope
  pass distinguish a self-reference under a lambda from one evaluated
  strictly and refuse the latter at compile time, with the name?  And
  should a zero-parameter `def` be a thunk -- which needs a way to
  apply a function to nothing, and `(apply f)` already means `f`?
- ~~**Q78**~~: *closed 2026-09-10.* `stdin` keeps the line's
  terminator; a blank line is `(10)` and only the end of the input
  is `nil`. `chomp` in the prelude strips the terminator; `words`
  never needed it. The games ask again on Enter. The question as
  raised: `stdin` yields `nil` both at end of input and for an empty
  line, because the empty string is the empty list. An interactive
  program cannot ask again on Enter. Keep the newline on the line (a
  blank line is then `(10)`, and every consumer strips), signal end
  of input as an anomaly a program can catch, or accept that Enter
  quits? The M11 choice served generated programs; the two games pay
  for it.
- **Q76**: After M23 the interpreter runs ~650 000 steps a second. The
  remaining floor is `_call` (~1.5 µs: a frame, the capability and
  environment saves and restores, the depth check) and the per-node
  accounting (~0.3 µs: budget, steps). Lexical addressing would make a
  reference a fixed chain of attribute loads instead of a `__missing__`
  walk; carrying the capability mask in the frame would halve what a
  call saves and restores; charging a straight-line subtree at its
  root would remove most of the accounting but move where a step trap
  fires. Which of these is worth a semantic wrinkle, now that the host
  VM buys 6× for none (PyPy, M23)? And is the PyPy path -- a run on a
  thread with a sized stack -- the right shape for the MCP server,
  which serves many runs from one process?
- ~~**Q75**~~: *answered in part by M23, with a measurement.* Compile-
  to-closures paid first and most (the walk and its node stack were
  ~48% of the per-node cost; 1115 → 586 ns on the micro-benchmark);
  frame chains paid ~15% more. 7.87 s → 3.57 s on a thousand lines,
  73 s → 33.7 s on ten thousand. The second question -- when does the
  substrate stop being the reference interpreter -- answered itself:
  it does not have to. The same Python under PyPy runs the ten
  thousand lines in ~5.5 s. What remains of the question is in Q76.
- **Q74**: The token table is full — 63 operators and `END` — and
  every slot was spent on a measurement or an axiom. The reserve
  position `spec/token-budget.md` has held since Exp 13 is the
  number-theory family: `p`, `tau`, `sigma`, `mobius` underpin LOVABench
  and nothing else. When the next operator earns its slot, that is
  where it comes from; which of them is the first to go?
- ~~**Q73**~~: *closed by M22, with a measurement.* An association
  list could not count the words of a thousand lines in twenty million
  steps; a native map counts them in 3.4 million.
- **Q72**: The network is datagrams because a datagram is one value
  in, one value out, and a stream needs a handle — a value kind LOVA
  does not have. Neither does a file: `fs-read` reads whole. Is a
  *handle* the sixth value kind the language eventually needs, or is
  whole-value IO the honest limit of a substrate whose programs are
  integers?
- **Q68**: `stdout` / `stdin` are ambient — M11 shipped them without a
  boundary and M19 left them so, because every experiment and the REPL
  would otherwise need a grant to print. But the terminal *is* the
  world, and Axiom 4 does not have an exception for it. Should the
  terminal move under the boundary, with the CLI granting it by
  default?
- **Q67**: A `Population` carries its scorer but does not expose it, so
  a custom rule that rebuilds a pool (`evolve-with`) has to be handed
  the scorer again. A `scorer-of : Population -> Fn` would close that
  at the cost of a slot — the Evolution family is full, so it would be
  the first operator placed outside its family on purpose. Or a rule
  could be an `Fn` that `evolve` takes, in which case the pool keeps
  the scorer and the rule never needs it. Which is the smaller change?
- **Q60**: `mutate` still draws from `core/lineage.py`'s `_SWAP_GROUPS`,
  which know only the M1 operators. A mutation of a program using
  `cons`, `div` or `apply` can only touch its literals. The swap table
  should be derived from the token table's type signatures, not
  hand-listed.

### Raised by M13
- **Q56**: `when-anomaly` hands the handler a code and nothing else. The
  anomaly carries `detail`, `position_path` and `repair_hint` — the
  fields an *agent* uses to repair a program. Should a handler be able
  to reach them, and in what shape, given that LOVA has no records and a
  list holds only integers?
- **Q57**: A program can now swallow a `conservation-violated` trap.
  Conservation is Axiom 4's contract with the substrate; catching it is
  either a legitimate recovery or a way to opt out of the contract.
  Which, and should `conserve` be able to declare that it is not
  catchable?

### Raised by M13
- **Q56**: `when-anomaly` hands the handler a code and nothing else. The
  anomaly carries `detail`, `position_path` and `repair_hint` — the
  fields an *agent* uses to repair a program. Should a handler be able
  to reach them, and in what shape, given that LOVA has no records and a
  list holds only integers?
- **Q57**: A program can now swallow a `conservation-violated` trap.
  Conservation is Axiom 4's contract with the substrate; catching it is
  either a legitimate recovery or a way to opt out of the contract.
  Which, and should `conserve` be able to declare that it is not
  catchable?

### Raised by M12
- ~~**Q54**~~: *closed by M16.* A reference is offered only where a
  bound function fits, so an `Fn` slot is filled by `lambda` unless one
  exists (74 → 5 references, all bound).
- **Q55**: `seq` is transparent in the compiler but not in the
  generator, because a variadic may be empty and `(seq)` evaluates to 0.
  The compiler checks that case; the generator just refuses `seq` in
  non-Int slots. Should a variadic be able to declare a minimum arity?

### Raised by M11 (a usable language)
- ~~**Q50**~~: *closed by M18.* `(use "name")` — textual inclusion,
  once, transitive, free after `drop-unused`. No name mangling: two
  libraries defining the same name shadow in inclusion order, which is
  what `let` chains already do, and is the honest limit of the design.
- ~~**Q51**~~: *closed by M20.* The return type is tracked, and it
  closed Q35 with it; Q43 it answered rather than closed.
- ~~**Q52**~~: *closed by M12.* `valid_next` is slot-type-aware for the
  result-follows-operands set, and admits `ref` anywhere, so a `map`-
  shaped program is now generatable.
- **Q53**: `apps/` still has five Python drivers that the CLI makes
  redundant. Keeping them costs a reader time; deleting them loses
  `is_perfect.py`'s parse-analyse-compile-encode-evaluate walkthrough.
  Move that walkthrough into `lova analyze` and delete the rest?

## Experiment log

| # | Date | Title | Status | Key finding |
|---|---|---|---|---|
| 01 | 2026-04-23 | Hello LOVA (MVP substrate) | Done (pilot) | **WIN.** 4 axioms (1, 4, 7, 8) operational in 790 LOC. Round-trip lossless 11/11; conservation + Δ traps emit structured metadata; surprise trace emits 3 structured events. Programs literally integers: `(merge (p 3) (tau 12))` → 9 B → 55916975560956379404. |
| 02 | 2026-04-24 | Type-directed generation (Axiom 3) | Done (N=1000 each) | **WIN (STRONG).** Constrained generation 1000/1000 = 100% well-formed. Unconstrained 0/1000 = 0%. Delta +100pp. Sharp constraint: after LET, valid_next goes from 18 tokens to 1. Paradigm synthesis of grammar-decoding + dependent types + positional typing. |
| 03 | 2026-04-24 | LOVABench v1 + corpus starter kit | Done (20 tasks × 3 baselines); **re-run on 60 tasks at M13** | **WIN (STRONG).** Reference 20/20; unguided constrained-random 1/2000 (0.05%, one degenerate task); Claude 20/20. Gap 0% → 100% across capability spectrum. JSONL corpus shipped at `corpus/lovabench_v1.jsonl`. 2 Claude solutions are semantic variants (commutative merge, associative gcd) — pass by behavior not by template match. |
| 04 | 2026-04-24 | Lineage intrinsic + Wright-Fisher (Axiom 5) | Done (pilot) | **WIN.** `core/lineage.py` 230 LOC: uid/parent_uid/root_uid/generation/mutation_kind. Wright-Fisher coalescence at program level: 5 roots → 1 survivor after 10 gens (matching DNA OS Exp 55). Mutation produces 49/100 distinct variants. Axiom 1 preserved — lineage is metadata, encoded bytes stay clean. |
| 05 | 2026-04-24 | Self-healing population (Axiom 6) | Done (N=10 seeds) | **PARTIAL WIN.** 5 variants all WRONG (distances 12-35 from target=42). After 12 evolve rounds: best seed 35→1 distance (97% gap), 3/10 seeds converge ±2, all 10 improve substantially (mean 80% gap closure). Mechanism (dispatch/retire/reproduce) demonstrably works; convergence not guaranteed under current mutation landscape (Q16-Q19 open for M5). |
| 06 | 2026-04-24 | Observability (L1+L2+L3) | Done (pilot) | **WIN.** Three AI-preference levers. **L1** `valid_next_with_stats`: TokenChoice with arity/depth/terminating/effects/cost. **L2** enriched anomalies: `offending_op=0x09(tau)`, `valid_alternatives=(P,SIGMA,MOBIUS)`, `repair_hint`. **L3** `static_analyze`: pre-execution effects/cost/determinism. Error surface narrows to semantic-only (syntax/type/arity physically unreachable). Foundation for Claude-vs-Claude benchmark. |
| 07 | 2026-04-24 | Claude-vs-Claude (Python vs LOVA) | Done (N=20×2); **re-run on 60 tasks at M13: 60/60 vs 59/60, 25.8×** | **WIN (STRONG).** Same 20 tasks, same LLM. **pass@1: LOVA 20/20 vs Python 19/20** (pb20 Python failed on keyword-arg / scope-shadowing — structural Python weakness). **Error-class subset**: Python's {syntax,name,type,import,attribute,semantic} vs LOVA's {semantic,conservation,unbound-ref}. **Density: 39.2× raw** (vs hand-rolled pure Python), ~15-20× adjusted (vs sympy-equivalent). This is the launch pitch. |
| 08 | 2026-04-24 | Compiler passes (scope + type + fold) | Done | **WIN.** `core/compiler.py` adds 3 static passes. Scope-check moves `unbound-ref` from runtime to compile-time with full L2 anomaly. Constant folding on LOVABench v1: **58.5% node compression, 43.9% bytes saved** (82→34 nodes, 155→87 bytes). Pure-program tasks collapse to single LIT_INT. `CompileError.anomaly` shares 7/7 L2 fields with `BudgetTrap` / `DeltaTrap` — uniform AI error handler. Error surface after M6: compile {unbound-ref, type-mismatch}, runtime {budget-exceeded, conservation-violated, semantic}. |
| 09 | 2026-04-24 | Body-scanning DeltaTrap (Q20) | Done (5 canonical + N=50 fuzz) | **WIN.** Δ-trap anomaly gains `body_offender = {op, path, depth, observed, needed, correction, fix}`, replacing the uniform `offending_op == CONSERVE` signal. Two-pass probe: **Pass A** tries operator-swap from `suggest_alternatives` (VIOLATE→IDENTITY); **Pass B** falls back to literal replacement. Canonical shapes 5/5; fuzz **50/50 = 100%** (pre-Pass-A was 60%). Closed-loop repair 5/5: receive anomaly → apply `needed` at `path` → conservation holds. Q20 closed; Q23/Q24/Q25 raised. |
| 10 | 2026-04-24 | Pass-rate telemetry (Q22) | Done (20 refs + N=300 bootstrap; N=50 demo) | **WIN.** `core/telemetry.py` + `TokenChoice` extension. Bootstrap DB (20 LOVABench refs + 300 random) surfaces sharp context-specific divergences: LIT-as-child-of-CONSERVE **3%** vs global **65%** pass rate. **Weighted sampler +20 pp over uniform** (96% vs 76% pass-without-trap, N=50). `MAX_NT_INPUT=2000` DoS guard added for random-fuzz safety. `corpus/token_telemetry.json` shipped (19 KB). Q22 closed; Q26-Q29 raised. |
| 11 | 2026-04-24 | LLM-token density (LOVA vs Python) v1 | Done (20 tasks × 3 baselines) | **WIN (pilot, v1).** Measured with tiktoken cl100k_base (GPT-4/Claude-class). Aggregate across 20 LOVABench v1 tasks: **Stage-1 LOVA text surface uses 2.5× fewer LLM tokens than sympy-Python (60% savings), 13.3× fewer than pure-Python (93%)**. Stage-2 projection: **4.0× vs sympy, 21× vs pure**. 18/20 tasks win vs sympy. |
| 11b | 2026-04-25 | LLM-token density v2 re-run | Done (60 tasks, 5 categories) | **WIN (v2, broader & honest).** Re-run on LOVABench v2 (60 tasks = v1's 20 + 4 × 10 extensions). Aggregate density drops to **Stage-1 2.0× vs sympy (50%), 8.5× vs pure (88%)** — v1's narrower set over-represented LOVA's strongest shapes. Per-category: deep-compose **13.5×/2.8×** (LOVA peak), conserve 7.2×/2.3×, surprise 5.5×/1.4×, let-heavy 4.9×/1.4×. Stage-2 projection **3.2× vs sympy (68%)**. Launch copy updated; v1 preserved as historical slice. |
| 12 | 2026-09-09 | Abstraction and iteration (M9) | Done (10 tasks × 44 cases; 5 runaway shapes) | **WIN on expressiveness, NEGATIVE on density.** 10 tasks that need recursion or iteration: **44/44 cases pass under M9, 0/10 were representable before it**. μ-recursive basis exhibited (zero test, successor, predecessor, primitive recursion, unbounded minimisation via `loop-until`); μ-search runs under `max_call_depth=4` because iteration consumes no frames. Runaway shapes **5/5 trapped, 5/5 with the full L2 anomaly schema**. Zero new tokens — 0x0B/0x0C reclaimed from the never-implemented mock-theta stubs. **NEGATIVE:** on tasks with no built-in shortcut on either side, the Stage-1 surface costs **1.5× MORE LLM tokens than Python** (0.66×), and the Stage-2 projection does not rescue it (0.65×); bytes stay mildly positive at 1.19×. The 8.5× headline was measuring the number-theory built-ins, not the language. Q30-Q36 raised. |
| 23 | 2026-09-11 | Does the substrate form hold at size? (Q104) | Done (5 sessions, Opus, 6 tasks 2x-5x larger) | **PARTIAL.** 30/30 first-try in all three forms, no wrong values; Stage-2's cost edge grew to 2.0x the s-expression on what was emitted. But neither Stage-2 session authored in Stage-2 -- both composed a tree and serialised it with an external binding table, so the substrate is shown as a storage/transport form, not an authoring one (Q105). All three substrate sessions named the same silent risk: a swapped reference is well-typed, so it is a wrong value with no diagnostic (Q106). The byte encoding proved the easy part; the missing vocabulary is the cost. A card defect (six reference letters where the form has ten) distorted one program -- the third card confound in this family (Q107). |
| 22 | 2026-09-11 | The three-form experiment (Q100) | Done (5 sessions, Opus, cost + generation axes) | **PARTIAL.** Cost: s2 1.36x cheaper than s1 in LLM tokens on dense code, tok 2.71x MORE. Generation first-try s1 100% / s2 85% / tok 60%, attempts/task 1.00 / 1.25 / 2.00 -- reliability degrades toward the substrate. The s2/tok cards, projected from the s-expression, dropped nine comparison/branch macros (no byte) and the arities parentheses supply, so those greens are contaminated (synthesis, hard-coding, reverse-engineering from decode errors) -- the ruling's point shown. For a current model the s-expression is the authoring surface. Q101-Q103. |
| 21 | 2026-09-11 | The repair leg: a planted fault | Done (3 sessions × 2 languages, 8 faults) | **NULL for the language, WIN for the measurement.** LOVA 24/24 in 30 attempts, Python 24/24 in 28; emitted 672 vs 391 chars, read 27 108 vs 12 069 (programs 2.35× longer). 47 of 48 faults found by reading before any feedback; failure feedback located an original fault 0 times on either side. 9 of 10 extra attempts were offset arithmetic in the harness (fixed: `--find`, `--dry-run`). Repair cost is reading, so density is charged per repair. Q95-Q97. |
| 20 | 2026-09-11 | Cost attribution: blind rewrite to read one | Done (3 sessions, LOVA, Opus, 8 tasks) | **PARTIAL.** With `hot` in the step trap, h04 3/2/4 attempts against run 2's 6/3/4 (31 vs 35 in all); every session rewrote from the list, one was misled by it (ranked by calls: `inc` led). The trap ranks by steps in each function's own body now; that read `nth` as 3.9M of 7M. `nth`/`take`/`drop`/`last`/`append` native at zero slots via shape-keeping `text-slice`/`text-cat`; the natural first attempt 1.3-3.1× cheaper, still over budget. Slotted `Closure`/`Runtime`: interpreter 15% faster net. Card: cost section, six facts. Harness: `check`. Q93, Q94. |
| 19 | 2026-09-11 | The loop where first attempts fail | Done (3 sessions × 2 languages × 2 runs, 8 tasks) | **PARTIAL.** Run 1 found four instrument defects (a numeric-looking text as an integer, a budget 30× tighter than the Python clock, a hint asserting non-termination, parse errors without a position), fixed. Run 2: LOVA 24/24 in 35 attempts, Python 24/24 in 26; parity on seven tasks, the game-tree search 6/3/4 vs 1/1/1, every extra attempt a rewrite for cost. Compile faults fixed in one attempt every time. The step trap now attributes cost by function. Q90-Q92. |
| 18 | 2026-09-10 | The agent loop: the four numbers | Done, pilot (1 session × 2 languages × 10 tasks) | **PARTIAL.** A fresh Claude session with the card and a `submit` command: LOVA 10/10 in 11 attempts, Python 10/10 in 10; the one LOVA miss (an operator passed by name) fixed from the hint in one try; emitted 3 184 vs 2 431 chars; feedback 1 114 chars for the one failure, none on the Python side, so that number is one-sided; scaffolding a function call with a budget vs a subprocess with a timeout. Every hindrance named was a card gap, closed. Q87-Q89 raised. |
| 17 | 2026-09-10 | A model writes LOVA from one page | In progress (Claude, blind, N=80 × 2 languages) | **PARTIAL.** A fresh Claude session with no tools, given the one-page card and 80 LOVABench v3 prompts, single-shot: **LOVA 79/80, Python 79/80**, the same miss (pb19's misleading v1 prompt, fixed). Algorithmic 20/20 in both. The language costs the model no reliability; the benchmark is at its ceiling; the case for LOVA is what a program gets at run time. Harness, corpus (3 000 verified pairs) and fine-tune driver ready; the paid runs wait on a key. Q82, Q83 raised. |
| 16 | 2026-09-09 | Scope-aware generation | Done (N=1000 × 2) | **WIN.** `step` takes the literal payload; the machine keeps scope and offers `ref` only where a bound, type-compatible name exists. Unbound references in generated programs **704/1000 → 0**; compile-and-run **16% → 37%**; `Fn` slots filled by references 74 → 5, all bound (Q54 closed). Axiom 3 now holds at the **name level for generated programs**; the compiler's scope pass remains for hand-written and mutated trees. Boundary: mutual recursion compiles but cannot be generated left-to-right (Q64). Exp 10 with real names: +32 pp. Exp 02's 100% measured the generator with its own scope-blind validator (Q66). Q64-Q66 raised. *Re-run at M23 (Q77): 226 → 0, runnable 13% → 16%; 250 generated programs refused by the M20 arity checker (Q71).* |
| 15 | 2026-09-09 | Populations: Exp 05 from inside LOVA | Done (10 seeds × 30 gens) | **WIN.** Axiom 6 in the language: `defpop` / `fitness` / `variant` / `select` / `retire` / `evolve` on the Evolution family's own slots, `Population` as a fifth value kind. Exp 05 rewritten as one LOVA program: **9/10 seeds improve, 3/10 converge, best seed 35 → 1 (97%), mean 85% of the worst-case gap closed** — Exp 05 had 3/10, 97%, 80%. Same rule (retire 20%, sharpness 3, clone 30%), different setting (strength 0.30 vs 0.45), so the same shape, not the same run. Winners report their own provenance via `generation` / `why`. Trapping variants score UNFIT and are recorded, not silent. **All ten axioms now realised in the language.** Q61-Q63 raised. |
| 14 | 2026-09-09 | Stage-2 surface, built and measured | Done (2150 round-trips; 3 corpora) | **WIN (STRONG).** Closes Q37. Built `core/surface2.py`: the text projection of the byte encoding, one character per byte, **no delimiters — because the encoding never had any**, `decode` recovering the tree from arity alone. Losslessness **2150/2150** (trees *and* bytes, incl. 1000 generated programs, with and without the reference digram). **Algorithmic density 0.66x -> 1.13x: LOVA is denser than Python on real programs for the first time**, past the 0.76x ceiling Exp 13 proved no table change could reach. **LOVABench 2.00x -> 5.38x vs sympy, 8.51x -> 22.89x vs pure.** Parentheses 25% -> **0%** of token cost. One compression rule (`(ref k)`, 22% of nodes) was worth **27%**, three times what two new token slots were worth. **Exp 11's Stage-2 projection understated density by 70%** (546 predicted vs 322 measured) having erred the *other* way in Exp 12 — node count is a poor proxy in both directions. First time Axiom 2 was cashed in rather than asserted. Untested and now load-bearing: whether a model can emit it (Q47). Q46-Q49 raised. |
| 13 | 2026-09-09 | Token budget re-derived | Done (3 corpora; 10 tasks x 3 levers) | **WIN on diagnosis — refuted its own hypothesis.** Where the Stage-1 tokens go: **51% names, 25% parens, 10% literals**. Three levers measured separately: one-token operator spellings close **30% of the algorithmic density gap for 0 slots** (verified by execution, 10/10 programs identical); `lt`+`sub` close **9% for 2 slots**; **61% is s-expression syntax** and unreachable by any table change (best case 0.76x, still below Python). So Exp 12's F7 — "the lever is the operator set" — is wrong by 3x; spelling was never measured and is the biggest term. Census: number-theory family is **33% of LOVABench use vs 3-5% elsewhere**, `p`/`tau`/`mobius` zero outside it — but the benchmark's own docstring says tasks were picked for what LOVA can express, so **it cannot testify about the table** (circularity inherited by Exp 10's generation priors, Q40). Proposal: 10 of 14 free slots; strings cost 0 once `cons` exists. Axiom 8 revision proposed, **not applied** — needs owner approval. Two methodology bugs recorded: a regex that matched 1 of 5 sites, and an AST re-render that measured the desugared form (+67%). Q37-Q41 raised. |

## How to run / extend

Set PYTHONPATH first:

```bash
cd /path/to/lova
export PYTHONPATH="$PWD"
```

Add a new experiment:

1. Create `experiments/experiment_NN_<topic>.py`
2. Use multi-seed runner by default; single-seed is only for debugging
3. Write `journal/experiment_NN.md` following the template below
4. Add a row to the experiment-log table above
5. If the experiment raises or closes a question, update the "Open
   design questions" section

## Journal entry template

```markdown
# Experiment NN — <Title>

**Date:** YYYY-MM-DD
**Script:** `experiments/experiment_NN_<topic>.py`
**Status:** Done (N=X). **WIN/PARTIAL/NULL.**

## Hypothesis
<what we expected, why>

## Method
<setup, conditions, verdict criteria — be explicit>

## Results
<tables, numbers, per-seed if useful>

## Findings
### F1. <headline finding>
### F2. ...

## Discussion
<what this means, caveats, what's NOT shown>

## Next questions raised
→ QNN: ...

## Status
<WIN/PARTIAL/NULL + single-sentence takeaway>
```

## Journal conventions (inherited from DNA OS v3)

- **Be honest.** Record failed hypotheses and null results. That is
  the whole point of the journal.
- **Distinguish observation from interpretation.** Numbers that came
  out of the run go in Results. What they mean goes in Discussion.
  Tag interpretations as tentative if they are.
- **Every experiment carries its next question(s) forward.** If an
  experiment leaves no new question, it was not pushed hard enough.
- **Multi-seed by default.** Single-trajectory results are marked
  `(pilot)` and must be rerun with ≥ 10 seeds before any finding is
  treated as load-bearing.
- **Keep axioms honest.** If an experiment finding is inconsistent
  with an axiom in `spec/axioms.md`, document the conflict and trigger
  the axiom drift protocol. Do not silently weaken the axiom.
