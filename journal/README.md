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
- **Q33**: LOVABench v3 with an algorithmic category — the present 60
  tasks cannot express recursion, so the benchmark cannot detect a
  regression in it.
- ~~**Q34**~~: *closed by M12.* A chain of `LET`s shares one frame, so a
  group of `def`s is mutually recursive. No new token.
- **Q35**: Partial application is statically unchecked — `Fn` does not
  track curried arity. Does an arity-indexed `Fn<n>` pay for itself?
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
- **Q42**: `cons` takes an `Int`, so a list of lists is not
  constructible. That keeps `head : List -> Int` *sound* rather than
  merely permissive, but it rules out trees and nested structure.
  Parameterised `List<T>` is the fix; what does it cost in a type system
  whose whole virtue is being tiny?
- **Q43**: A lambda parameter's type is unknown — LOVA has no parameter
  annotations, so the checker accepts a reference to a parameter in any
  slot and leaves misuse to the runtime. Third member of the family with
  Q35 (curried arity) and Exp 08's `unbound-ref`. Is there a cheap
  inference that closes it, or is unityped-parameters the honest
  position?
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
- **Q61**: `evolve` at strength 0.30 needs ~30 generations for what
  Exp 05 did in 12 rounds at 0.45. A `defpop` parameter, or a prelude
  `evolve-with` written from the primitives?
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
- **Q50**: The prelude is prepended textually because LOVA has no module
  system. That is adequate for one library and will not stay adequate.
  What is the smallest thing that is not a module system but solves the
  same problem — a `use` form, a name-mangling convention, or nothing?
- **Q51**: `apply` is now transparent in its result type, which means a
  call in the wrong slot fails at run time rather than at compile time.
  Third member of the family with Q35 and Q43. Would tracking a
  function's *return* type (not its arity) close all three at once?
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
| 16 | 2026-09-09 | Scope-aware generation | Done (N=1000 × 2) | **WIN.** `step` takes the literal payload; the machine keeps scope and offers `ref` only where a bound, type-compatible name exists. Unbound references in generated programs **704/1000 → 0**; compile-and-run **16% → 37%**; `Fn` slots filled by references 74 → 5, all bound (Q54 closed). Axiom 3 now holds at the **name level for generated programs**; the compiler's scope pass remains for hand-written and mutated trees. Boundary: mutual recursion compiles but cannot be generated left-to-right (Q64). Exp 10 with real names: +32 pp. Exp 02's 100% measured the generator with its own scope-blind validator (Q66). Q64-Q66 raised. |
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
