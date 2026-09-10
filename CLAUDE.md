# LOVA — AI-native Integer-Sequence Language

> A programming language designed for **AI authorship, AI review, and AI
> execution**. Human readability is an explicit non-goal of the
> substrate. Human-readable projections are tooling — they exist to
> bootstrap the project and to audit on demand, not to constrain the
> language design.

## TL;DR — 60-second orientation

**LOVA is a language where AI is the sole first-class user.** Code is
not text. Code is a **typed integer sequence** that lives in a
conservation-preserving partitioned substrate. An AI generates code by
emitting integer tokens; an AI reads code by consuming integer tokens.
The language's semantics, type system, error model, and evolution
machinery are all designed around what AI (LLM and successors) can do
well, not what humans find readable.

Three-stage roadmap:

1. **Stage 1 — Text-surface LOVA** (current). Human-readable textual
   surface syntax that compiles to integer-sequence AST. Lets humans
   bootstrap the language, generate training corpora, build tooling,
   and validate the design empirically. **Where we start.**
2. **Stage 2 — AI-primary LOVA.** AI is the dominant code author;
   humans review exceptionally. **The surface exists** as of Exp 14
   (`core/surface2.py`): the text projection of the byte encoding, one
   character per byte, no delimiters — measured at 1.13× Python on
   algorithmic code and 5.38× sympy-Python on LOVABench, lossless
   2150/2150. The fine-tuned model is still M8, and whether a model can
   *emit* this surface is untested (Q47).
3. **Stage 3 — Pure-AI LOVA.** No text. Programs are integer
   sequences. Human access only through `(explain program)` on-demand
   projection. **The north star.**

**Design thesis**: if you believe "AI writes most code by 2030-2035,"
then current languages (Python / TypeScript / Rust) are transitional —
they optimize for human readers. LOVA optimizes for AI
generation/reading while preserving machine-verifiable correctness via
conservation contracts, lineage tracking, and substrate-level integrity
invariants.

**Positioning — LOVA is paradigm evolution, not invention.** LOVA
is the **synthesis** of seven long-running PL-design trajectories:
homoiconicity (Lisp → Unison), effect tracking (Haskell → Koka → linear
Rust), program synthesis (Template Haskell → Copilot → grammar-decoding),
concurrency (Actors → CSP → dataflow), verification (types → dependent
types → proof assistants), variance/evolution (generics → GP → AutoML),
and provenance (git → Unison → SBOM). Each trajectory has a natural next
step; LOVA is where all seven next-steps converge. See
`spec/paradigm-inheritance.md` for the full ancestor map. Every design
decision from here on is assessed against paradigm lineage — if a
proposed feature has no ancestor trajectory, it is suspicious.

## What this project IS

- A language whose **core representation** is a typed integer sequence
- A substrate where **every program is an integer** that carries
  lineage and conservation metadata — and, since M14, can be held,
  hashed, explained, run, cloned and mutated *by another program*
  (`quote` / `eval` and the Meta family). "Heat" was part of this
  sentence from M1 to M14 and never had an implementation; it was
  ruled a dead concept at M14 and its slots hold `cons`/`head`/`tail`.
- A type system where **generation is constrained to well-typed
  successors** (zero syntax/type errors reachable by valid generation)
- An execution model where **functions are populations of variants**
  that compete evolutionarily at dispatch time
- A debug model where **"debug" means surprise-guided mutation**, not
  stack traces

## What this project IS NOT

- **Not a human pair-programming language.** Stage 1 has text surface
  only as a bootstrap; it is not the product. Designers should resist
  adding features motivated by "humans find it more readable."
- **Not a replacement for MCP / agent communication protocols.** LOVA
  is a **language** (expression of computation), not a wire protocol.
  It can be transported over MCP, HTTP, or anything.
- **Not a trading / quantitative system.** No PnL objective. This is
  inherited from DNA OS's Axiom 5 — surprise is the learning signal,
  not reward. (See `spec/axioms.md`.)
- **Not an OS.** LOVA is the language layer. It *assumes* a
  substrate (DNA OS is the natural fit, but LOVA can also target
  LLVM / WASM / JVM in Stage 1).
- **Not a general-purpose language for all tasks.** It targets tasks
  where AI-first authorship matters: agent tooling, self-modifying
  systems, long-running autonomous infra, safety-critical generated code.

## Parent lineage

LOVA is the conceptual descendant of **DNA OS v3**
(`../dna-os-v2.1/dna-os-v2.1/dna_os_v3/`). The architectural vocabulary
— PFS, conservation, lineage, surprise, evolution, Δ-security — is
inherited.

**Important**: LOVA does NOT import DNA OS v3 code. It reimplements
the relevant primitives cleanly, free of experiment-era technical debt.
The conceptual lineage is real; the code is independent.

See `../dna-os-v2.1/dna-os-v2.1/dna_os_v3/CLAUDE.md` for the DNA OS
vocabulary. Key transferred concepts:

| DNA OS v3 concept | LOVA realisation |
|---|---|
| PFS `PartitionedFile<n>` | Program representation |
| Conservation `sum(n) ≡ budget` | Type system + runtime check |
| Δ-security (conservation + plasticity) | Effect type enforcement |
| Mock theta (φ₃, ψ₇) driver | *(not realised — the 0x0B / 0x0C slots reserved for it were reallocated to `mul` / `mod` in M9, unimplemented)* |
| Surprise (per-theory, Exp 78) | Debug / mutation signal |
| Evolution engine (dedup, clone, mutate) | `defpop` / variant dispatch |
| Lineage (uid/parent/root, Exp 55) | Program provenance chain |

## Axioms (design invariants — DO NOT violate)

These are the load-bearing commitments. See `spec/axioms.md` for the
full argument behind each.

1. **Programs are integers, not text.** Text is a projection layer.
   The substrate manipulates `PartitionedFile<n>` directly.
2. **Human readability is a non-goal of the substrate.** Stage 1 text
   syntax is a bootstrap, not an invariant. Do not entrench
   human-pleasing syntax into the semantics.
3. **Type-constrained generation.** For any partial program, the set of
   well-typed next tokens is computable. AI generation traverses this
   space only. Ill-typed programs are not representable.
   *Precision (Exp 12 F4, Exp 16):* for **generated** programs this
   now holds at the name level too — since M16 the state machine is
   given literal payloads and keeps scope, so an unbound or wrongly
   typed reference is unrepresentable (704/1000 → 0 at M16; 226 → 0
   at the M23 re-run). For hand-written
   or mutated trees the compiler's scope and type passes are the check.
   Mutual recursion is compilable but not generatable (Q64). Quote the
   axiom with that qualifier.
4. **Conservation is a type, not a runtime afterthought.** Every
   function declares its effect / budget / surprise bounds in its
   signature. Violations are type errors at declaration-site and
   Δ-traps at runtime.
5. **Lineage is intrinsic.** Every program artifact carries provenance
   (which AI, when, why, from what parent). Provenance is queryable in
   the language (`why?`, `lineage`).
6. **Populations over individuals.** A function is a pool of variants,
   not a single definition. Dispatch selects per workload; losers are
   retired, winners are cloned + mutated.
7. **Surprise is the debugger.** No stack traces in the substrate.
   Runtime deviation is emitted as structured surprise traces;
   AI-driven repair mutates at the offending token position.
8. **Small core, dense tokens.** Core operator set ≤ 64 (1 byte each).
   Every byte carries semantic weight. Sugar is a Stage-1 bootstrap
   concession, not a language feature.
9. **No PnL / reward objective.** The language is neutral to
   optimization targets. Users declare their objectives (via
   conservation contracts and surprise budgets); the substrate enforces
   compliance.
10. **Stage-coherent design.** Every design decision must be coherent
    under all three stages. If a feature makes Stage 1 nicer but
    breaks Stage 3's pure-integer representation, reject it.

## Token architecture (draft)

Exactly 64 core operators, grouped into 8 families of 8. Each token is
1 byte. Arguments follow as typed-slot tokens (types are determined
positionally by the preceding operator's signature — no explicit type
annotations).

```
0x00-0x07   Structural            partition / merge / cons / head / tail
0x08-0x0F   Numerical primitives  p, τ, σ, mul, mod, div, gcd, mobius
0x10-0x17   Conservation          budget-decl / conserve / nil / Δ-check
0x18-0x1F   Surprise / watch      surprise / nil? / threshold / deviation
0x20-0x27   Evolution             defpop / variant / evolve / select / mutate
0x28-0x2F   Composition           seq / parallel / if-surprise / loop-until
                                  lambda / apply / let / ref
0x30-0x37   Effects / IO          external-boundary / net-send / net-recv
                                  fs-read / fs-write / stdout / stdin / clock
0x38-0x3F   Meta / lineage        lineage-query / why / trace / explain
```

**Slot budget.** 31 of 64 implemented, 33 reserved — but of those 33,
24 belong to the Evolution / Effects-IO / Meta families, each of which
carries an axiom, leaving **8 genuinely free slots**.
`spec/token-budget.md` is the standing ledger: what was spent, what
remains, and what is still awaiting a decision. Read it before
proposing any new operator.

`spec/tokens.md` is the authoritative table and is **generated** from
`core/tokens.py` by `spec/generate_tokens_md.py`. Rerun that script
after touching the table; do not hand-edit the Markdown.

Reallocated slots, all of them placeholders that carried a name and an
arity for nine milestones and never an implementation:

| Byte | Was | Now | When |
|---|---|---|---|
| 0x0B / 0x0C | `φ₃` / `ψ₇` (mock theta) | `mul` / `mod` | M9 |
| 0x04 / 0x05 / 0x06 | `heat-inc` / `heat-get` / `inherit` | `cons` / `head` / `tail` | M10 |
| 0x0D | `η` (Dedekind eta) | `div` | M10 |
| 0x15 | `sum-invariant` | `nil` | M10 |
| 0x19 | `watch` | `nil?` | M10 |
| 0x1E | `normal-range` | `read` | M18 |
| 0x12 | `delta-check` | `signal` | M22 |
| 0x13 / 0x14 / 0x16 | `respawn` / `budget-remaining` / `preserve` | `map-put` / `map-get` / `map-pairs` | M22 |

The DNA OS lineage for the *architecture* is unaffected; these slots
changed hands, and the core is still exactly 64 operators.

**Surface spelling is not free real estate but it is free density.**
Exp 13 measured operator *names* at 51% of the Stage-1 LLM-token cost
and found that one-token spellings (`if`, `dev`, `loop`, `def`, ...)
close 30% of the algorithmic density gap against Python for zero
slots — three times what two new operators were worth. `lt`, `sub`,
`gt`, `(list ...)` and `"strings"` are therefore **macros**, not
operators: they expand into the core (Constraint 6) and cost nothing.
Prefer a macro over a slot unless the node count matters.

**Stage 1 text surface** is a Lisp-like s-expression syntax that maps
1:1 to token sequences. Example:

```lova
(defn square [n] (⊗ n n))
(square 7)
```

is Stage-1 sugar. It desugars to core tokens only —

```lova
(let 0 (lambda 1 (mul (ref 1) (ref 1))) (apply (ref 0) 7))
```

— and compiles to a short integer sequence. The text form is a
pretty-printer over the integer form, not the canonical
representation; identifiers are interned to integer name ids at parse
time and printed back as integers, because the integer is the
program.

## File layout

```
lova/
├── CLAUDE.md              ← this file
├── README.md              ← minimal project description
├── core/                  ← reference implementation
│   ├── tokens.py          ← 64-token spec + encoder/decoder
│   ├── types.py           ← type system (position-directed)
│   ├── runtime.py         ← evaluator (token-sequence interpreter)
│   ├── conservation.py    ← Δ-check + budget enforcement
│   ├── lineage.py         ← provenance tracking
│   └── surface.py         ← Stage-1 s-expression ↔ token sequence
├── spec/                  ← design documents
│   ├── axioms.md          ← full argument behind each axiom
│   ├── tokens.md          ← complete token reference
│   └── grammar.md         ← type-directed grammar rules
├── experiments/           ← empirical validation
│   └── experiment_NN_*.py
├── journal/               ← research log
│   ├── README.md
│   └── experiment_NN.md
└── corpus/                ← (future) training data for LLM fine-tune
    └── (empty initially)
```

## How to run / test

The `lova` command line is the entry point (`core/cli.py`).

```bash
cd /path/to/lova
export PYTHONPATH="$PWD"

# Run a program
python -m core.cli run apps/is_prime.lova 1999

# REPL, with lib/prelude.lova loaded
python -m core.cli repl

# Project into the Stage-2 surface, bytes, or one integer
python -m core.cli emit apps/coprime.lova 14 15 --form stage2

# Static analysis without running it
python -m core.cli analyze apps/collatz.lova 27

# Serve the language to an MCP host (execute / analyze / valid_next / emit)
python -m core.cli mcp

# Run an experiment
python experiments/experiment_01_hello_lova.py

# The same, ~6x faster on long runs: the core has no dependencies, so
# any PyPy 3.10+ runs it unchanged (M23)
pypy -m core.cli run apps/wordfreq.lova notes.txt 10 --allow fs-read
```

## Autonomous operation

Claude should operate autonomously on this project.

- **Create / edit files freely** inside `lova/`.
- **Run experiments directly** without asking — pick reasonable
  defaults for seeds / sizes / iterations.
- **Install pip packages** when experiments require them (prefer
  minimal deps; justify each in the experiment's docstring).
- **Commit only when explicitly asked** — this is a research project,
  not a continuously-deployed service.

### Still requires confirmation

- Deleting existing journal files or experiment results
- Pushing to a remote
- Any design change that modifies the 10 axioms above
- Importing DNA OS v3 code directly (should be reimplemented, not forked)

## Constraints (DO NOT break)

1. **No text-centric design leakage.** If a feature would be hard to
   port to Stage 3 (integer-sequence-only), it does not belong in the
   substrate. Stage 1 sugar is explicitly allowed but must compile
   cleanly to the integer form.
2. **No human-pleasing naming conventions in the runtime.** Identifiers
   are optional Stage-1 tags; the substrate references by hash/integer.
3. **No PnL / reward / profit-maximising logic.** The language is
   objective-neutral. Conservation contracts express invariants, not
   objectives.
4. **No mutable global state.** Every effect is typed and local to a
   function's declared effect set.
5. **No silent failures.** Every deviation from declared contract is a
   surprise event with structured metadata.
6. **No parser-level sugar that changes semantics.** Surface syntax may
   differ from underlying token form by layout but must not introduce
   semantics not expressible in the core 64 tokens.
7. **No forking of DNA OS v3 code.** Reimplement primitives cleanly;
   reference the DNA OS documentation for concepts.

## Journal conventions

Mirrors DNA OS v3's journal structure. For every experiment, create
`journal/experiment_NN.md`:

```markdown
# Experiment NN — <Title>

**Date:** YYYY-MM-DD
**Script:** `experiments/experiment_NN_<topic>.py`
**Status:** Done / In progress / Parked. **WIN/PARTIAL/NULL.**

## Hypothesis
## Method
## Results
## Findings (F1. ..., F2. ...)
## Discussion
## Next questions raised (→ QNN: ...)
## Status (one-sentence takeaway)
```

Journal conventions (inherited from DNA OS):

- **Honesty over optimism.** NULL results are load-bearing — they
  document architectural boundaries.
- **Observation ≠ interpretation.** Numbers in Results; meaning in
  Discussion.
- **Every experiment raises a next question.** If not, it wasn't pushed
  hard enough.
- **Multi-seed / multi-run by default.** Single-trajectory results are
  marked `(pilot)` and must be rerun with ≥ 10 seeds before any finding
  is treated as load-bearing.

## Memory system

This project shares the memory substrate at
`C:\Users\Administrator\.claude\projects\...\memory\`. Relevant
existing memories:

- `feedback_os_not_regressor.md` — DNA OS's "OS not regressor" reframe.
  **LOVA inherits this**: do not benchmark LOVA on prediction-MAE
  tasks. Measure it on code-correctness / LLM-generation-reliability /
  substrate-integrity metrics.
- `project_v3_canonical_stack.md` — DNA OS's canonical OS-era config.
  LOVA mirrors several of the same defaults (enforce_diversity,
  conservation, Δ-monitor).

Add to memory when:
- A design axiom is validated or retracted empirically
- A canonical configuration emerges for a LOVA module
- A non-obvious user preference is revealed

Do NOT add to memory when:
- The fact is captured in CLAUDE.md or `spec/`
- The information is ephemeral (current experiment state, in-progress
  work)

## Current state (2026-09-10 — post-M23)

**10 / 10 axioms operational.** See `journal/README.md` for per-
experiment details.

| Axiom | Impl | Exp |
|---|---|---|
| 1. Programs are integers | ✅ | 01 (integer 55916975560956379404) |
| 2. No human-readability as goal | ✅ | design decision |
| 3. Type-constrained generation | ✅ | 02 (100% vs 0% well-formed) |
| 4. Conservation as type | ✅ | 01 (Budget/Delta trap) |
| 5. Lineage intrinsic | ✅ in the language (M14) | 04; `uid`/`why`/`lineage-query` are operators |
| 6. Populations over individuals | ✅ in the language (M15) | 05 from Python, 15 from inside; the Evolution family is 8/8 |
| 7. Surprise as debugger | ✅ | 01 + 06 (structured anomaly) |
| 8. Small core, dense tokens | ✅ | 64 tokens × 1 byte |
| 9. No PnL objective | ✅ | design decision |
| 10. Stage-coherent | ✅ | text ↔ integer lossless |

**Milestones completed:**
- **M1** (Stage-1 substrate): core/tokens, core/surface, core/runtime,
  core/conservation operational. Axioms 1/4/7/8 validated.
- **M2** (type-directed generation): core/types, core/generator.
  Axiom 3 validated.
- **M3** (LOVABench): corpus/ with 20 tasks + JSONL + evaluator.
  Three baselines quantified (0% / 100% / 100%).
- **M4** (lineage + populations): core/lineage, core/populations.
  Axioms 5 and 6 validated.
- **M5** (AI observability): core/observability (L1 valid_next_with_stats,
  L2 enriched anomalies, L3 static_analyze).
- **Exp 07** (Claude-vs-Claude): pass@1 20/20 LOVA vs 19/20 Python;
  density 39.2×; error-class subset property empirically demonstrated.
  *(v1 slice. Superseded by the 60-task re-run at M13: 60/60 vs 59/60,
  25.8×. The error-class result is unchanged.)*
- **M6 Day 1** (compiler): core/compiler with three static passes —
  scope-check, type-check, constant-fold. `CompileError.anomaly` shares
  L2 schema with runtime traps (uniform AI error handler).
- **Exp 08** (compiler passes): LOVABench v1 folds to 58.5% fewer nodes
  / 43.9% fewer bytes; pure-program tasks collapse to single LIT_INT.
  `unbound-ref` moves from runtime to compile-time.
- **First real programs** shipped in `apps/` — `is_perfect.lova` and
  `coprime.lova` (first non-benchmark LOVA code; drivers demonstrate
  full parse → analyse → compile → encode → evaluate pipeline).
- **M6 Day 2** (body-scanning DeltaTrap): `_scan_body_offender` +
  `_clone_with_replacement` in `core/runtime.py`. Δ-trap anomaly
  now carries `body_offender` pinpointing the deepest sub-expression
  whose single-node replacement closes the deviation. Two probes
  (operator-swap, literal-replacement). Q20 closed.
- **Exp 09** (body-offender): 5/5 canonical shapes, 50/50 fuzz
  precision (pre-Pass-A was 60%), 5/5 closed-loop repair. Δ-trap
  offender signal upgraded from "uniform CONSERVE" to precise
  sub-expression + correction value.
- **M6 Day 3** (pass-rate telemetry): `core/telemetry.py` + `Slot.parent_op`
  + four new `TokenChoice` fields (`prior_pass_rate{,_ctx} /
  prior_sample_count{,_ctx}`). `valid_next_with_stats(state,
  telemetry=DB)` fills them from a persisted JSON DB. Runtime
  `MAX_NT_INPUT=2000` DoS guard added. Q22 closed.
- **Exp 10** (telemetry): 20 LOVABench refs + 300 random samples →
  `corpus/token_telemetry.json` (19 KB). Context divergence surfaces
  (LIT-in-CONSERVE **3%** vs global 65%). **Weighted sampler +20 pp
  over uniform** (96% vs 76% pass-without-trap, N=50).
- **M9** (abstraction and iteration): `LAMBDA` / `APPLY` / `LOOP_UNTIL`
  implemented, `LET` upgraded to a letrec, `mul` / `mod` on the
  reclaimed 0x0B / 0x0C, `deviation` / `threshold` giving ordering,
  `Fn` and `Value` types, `DepthTrap` / `StepTrap` ceilings, and
  Stage-1 sugar (`defn`, call syntax, bare-name references). Zero new
  tokens. Numbered 9 because M7 (MCP) and M8 (fine-tuning) were
  already named below; M9 landed first because both depend on it.
- **Exp 12** (abstraction): **44/44 algorithmic cases pass, 0/10 were
  representable before M9**; μ-recursive basis exhibited; 5/5 runaway
  shapes trapped with the full L2 schema. **NEGATIVE result on
  density** — see below.
- **Exp 13** (token budget): re-derived the table before spending the
  rest of it. Density is **30% spelling / 9% operators / 61%
  s-expression syntax**, so a table change was the wrong instrument —
  and the benchmark cannot testify about the table, because its tasks
  were selected for what LOVA could already express. Proposal in
  `spec/token-budget.md`; **Axiom 8 revision proposed and NOT applied**
  (needs owner approval).
- **M10** (data): 6 of 14 free slots spent — `cons` / `head` / `tail` /
  `nil` / `nil?` and `div`. One cons cell buys pairs, lists **and**
  strings-as-codepoint-lists, so `"abc"` is sugar at zero slots. New
  `List` type; `apply` arguments widened to `Value`. `lt` / `sub` /
  `gt` / `(list ...)` shipped as macros rather than slots, on Exp 13's
  own evidence. `quote` / `eval` held pending a decision.
- **Fixed in M10**: `constrained_random` could fail to terminate — no
  Fn-producing operator is "terminating", making generation a critical
  branching process in an `Fn` slot. Replaced by a
  minimum-completion-cost bias, which strictly decreases remaining
  work. Related: four runtime arithmetic sites trusted their slot type
  and could receive a closure, because `APPLY` declares `Int` while a
  partial application evaluates to a callable (Q35). All now coerce.

**M23** removed the tree walk. `_eval` compiles a node to a Python
closure the first time a run meets it (`Runtime.code_cache`, per
run); twenty-two hot operators have inlined templates and the rest run
their unchanged handlers inside a generic wrapper. The node stack is
gone -- a trap's `position_path` is read off the Python stack by
`_node_path` -- and `Scope` frames chain by parent pointer instead of
copying the environment per call. Step counts and trap positions are
unchanged (`tests/test_compiled.py` pins values recorded on the M22
walker). The map reroots instead of copying (O(1) a put through a
fold, where M22 was O(keys)), and `words` saves a call per character.
**1000 lines 7.87 s → 3.39 s; 10 000 lines 73 s → 28 s**,
~700 000 steps a second on CPython. The core is stdlib-only and runs
under **PyPy** unchanged, where the same count takes **~5.5 s** (~4
million steps a second); `evaluate` runs on a sized-stack thread
there, because PyPy spends C stack per frame and Windows gives the
main thread a megabyte. Two programs written to measure usability --
`apps/tictactoe.lova` (memoised negamax, never lost in 20 random
games) and `apps/guess.lova` -- found that `stdin` cannot tell a blank
line from end of input (Q78) and that a zero-parameter `def` is a
constant whose recursive reference the compiler accepts and the
runtime traps (Q79). Three more -- `apps/logstats.lova` (a log
grouped and summarised), `apps/ping.lova` / `apps/pong.lova` (two
processes over UDP), `apps/sandbox.lova` (untrusted programs run
under a budget and reported by fault name, the agent scenario) --
worked, found a lost-datagram race (fixed: the listener is bound by
the first network operation of either kind) and that `hash` is a
150-digit integer for a program holding a string (Q80). Q75
answered; Q76 (the next floor), Q77 (Exp 16's figures have drifted
from its script; closed by re-running).

**M22** made LOVA a language a real program can stand on, measured by
one: `apps/wordfreq.lova`. Ceilings raised (depth 10 000; CLI/MCP
20 000 000 steps, library 1 000 000); the prelude iterates instead of
recursing and grew the text and list functions a program needs;
`signal` (0x12) raises what `when-anomaly` catches; a persistent map
on the last three free slots (0x13 / 0x14 / 0x16) after an association
list failed to count a thousand lines in twenty million steps; the
interpreter three times faster (table dispatch, one function per node,
fast paths). **63 / 64 operators; the table is full.** 10 000 lines
count in 73 s. Q73 closed; Q74 (the reserve family), Q75 (speed floor).

**M7** (named long ago, delivered last) made LOVA a tool for agents:
`core/mcp_server.py` serves `lova_execute` / `lova_static_analyze` /
`lova_valid_next` / `lova_emit` over the MCP stdio transport with no
dependency outside the standard library — `lova mcp` starts it,
`apps/mcp_demo.py` drives it — and `pip install .` builds a wheel that
ships `core`, `lib/*.lova` and the corpus with a `lova` command
(0.2.0 then; **1.0.0 released 2026-09-10**). `lova_valid_next` is Axiom 3 as a service: a host can
ask, at every step, which tokens may follow.

**M21** activated the network on the IO family's last two slots:
`net-send` / `net-recv` over UDP datagrams, under the `net` bit of the
boundary. The program declares the kind; the host names the places
(`--allow net=host:port`, `net=:port`), so no address enters the byte
sequence (Q69 closed). A receive that gets nothing yields `nil`, never
hangs. **59 / 64 operators; the IO family is 8/8; only the four free
slots remain.** Q72 (handles as a value kind?).

**M20** gave the checker function shapes: `Fn<arity,ret>` inferred
from a visible lambda, flowing through `let` and `apply`, so a partial
application in an integer slot, a call with too many arguments, or a
call result in the wrong slot is a compile error (Q35, Q51 closed).
Parameters stay untyped — the honest answer to Q43 — and the generator
still sees plain `Fn` (Q71). No new byte.

**M19** put the world under a declared boundary: `external-boundary`
(0x30) declares, as a literal capability mask, which effects its body
may use — `(boundary "fs-read clock" body)` in the surface — and
`fs-read` / `fs-write` / `clock` (0x33 / 0x34 / 0x37) are the effects.
The compiler's capability pass refuses a use outside a boundary that
declares it; the runtime refuses a boundary the host did not grant
(`--allow`, nothing by default); the boundary is lexical, captured by
closures; the generator offers the world only where it is declared.
Axiom 4, concrete for effects that touch the world. Q68–Q70.
**57 / 64 operators at M19; M21 took the network slots.**

**M18** added `read` (0x1E), the inverse of `explain`, so a program
can construct a program from text and `eval` it; `(use "name")`, a
module system that is textual inclusion — once, transitive, free after
`drop-unused` — and not an operator (Q50 closed); and
`lib/evolution.lova`, whose `evolve-with` is a custom evolution rule
written from the primitives (Q61 answered without a slot). `defpop`
splices list arguments so a pool can be rebuilt by library code. Q67.
**53 / 64 operators, four free slots.**

**M17** let a cons cell hold any value — trees, lists of programs,
lists of functions — with `head` joining the result-follows-operands
set (Q42 closed the cheap way; `List<T>` is Q63). The termination bias
was restricted to *certain* closers on the way, because `(head (nil))`
had become the cheapest way to close an `Fn` slot.

**M16** made generation scope-aware. `GenState.step` takes the
literal's payload, keeps frames, and offers `ref` only where a bound,
type-compatible name exists. Exp 16: unbound references in generated
programs 704/1000 → 0, runnable 16% → 37% (re-run at M23: 226 → 0,
13% → 16%, the drop being M20's arity checker refusing a quarter of
generated programs -- Q71's measurement; Q77), `Fn` slots filled by
references 74 → 5 (Q54 closed). Axiom 3 now holds at the name level for
generated programs; the compiler remains the check for everything else.
Exp 10 with real names: +32 pp. Q64–Q66.

**M15** completed Axiom 6. A `Population` is a value; `defpop` /
`fitness` / `variant` / `select` / `retire` / `evolve` are operators on
the Evolution family's own slots, and `evolve` applies
`core/populations.py`'s rule from inside. Exp 15 rewrites Exp 05 as a
LOVA program and reproduces its shape (3/10 converge, best seed 35 → 1,
mean 85% of the gap closed) with Python only seeding and printing.
**52 / 64 operators; every axiom is now realised in the language.**

**M14** put programs into the language as values. `quote` / `eval` on
two free slots; the **Meta family 8/8** on the slots the table named
for it — `explain` is Stage 3's human interface, reached from inside
for the first time; `hash` produces Exp 01's integer from a LOVA
program; `uid` / `generation` / `ancestor-of` / `lineage-query` / `why`
make Axiom 5 true *in the language*, not only in `core/lineage.py`.
`clone` and `mutate` start Axiom 6; the rest of Evolution waits on a
population value (Q58). **46 / 64 operators, five free slots.** Three
owner-delegated rulings recorded in the journal: heat is dead, the
Axiom 3 qualifier stays, `nth` is loud.

**M13** made the error model uniform and reachable. Twenty-two runtime
faults — division by zero, the head of an empty list, an unbound
reference — raised bare `ValueError`s with no `kind`, so Exp 08's "one
handler for every fault" held for two of four classes; `DomainTrap`
(a `ValueError` subclass, so nothing broke) closes that. `when-anomaly`
(0x1A) lets a program catch its own anomaly and branch on its code,
which Axiom 7 always implied. `StepTrap` alone is uncatchable: a
termination guarantee a program can mask is not one. **34 / 64
operators**, seven free slots left.

**M12** closed two debts with no new tokens: a chain of `LET`s shares
one environment frame, so a group of `def`s is **mutually recursive**
(Q34) — and `drop-unused` had to become a fixpoint over the group,
because with mutual recursion a binding can be reachable only from an
earlier sibling's *value*. And `valid_next` caught up with the type
checker (Q52): `if` / `let` / `apply` fit any slot because their result
type follows their operands, and `ref` fits any slot because its type
is its binding's — which the generation state machine cannot see. A
`map`-shaped program is now generatable, where before **no generated
program could have that shape at all**.

**M11** made the language usable: `stdout` / `stdin` on the IO
family's own reserved slots, logic macros at zero slots, a standard
library written in LOVA (`lib/prelude.lova`, free because of the new
`drop-unused` compiler pass — 474 nodes to 1 when unused), and a command
line (`python -m core.cli run|repl|emit|analyze`) so a `.lova` file can
be invoked without a hand-written Python driver. It also fixed a real
type-system defect: `if-surprise` forced its branches to `Int`, which
made every list-returning conditional — `map`, `filter`, `reverse` —
unrepresentable. `if` / `let` / `seq` / `apply` now take their result
type from their operands.

**Exp 14** built the Stage-2 surface and closed Q37, the largest open
item: parentheses were 25% of the Stage-1 token cost and were never
necessary, because the byte encoding has no delimiters. Density on
algorithmic code went 0.66× → **1.13×** (past the 0.76× ceiling Exp 13
proved the token table could not beat) and on LOVABench 2.00× →
**5.38×** vs sympy-Python. Exp 11's Stage-2 *projection* understated
density by 70%; node count is a poor proxy in both directions.

**63 / 64 operators runtime-implemented**; the table is full (the
64th is `END`), and the reserve position is the number-theory family (see the slot-budget note above). See
`spec/tokens.md` for the complete table (generated) and
`spec/token-budget.md` for the ledger.

**Code statistics:** ~10 000 Python LOC (core + tests + corpus + experiments + apps),
697 unit tests passing, 16 experiments (pb11 has a v1 pilot + v2 re-run),
11 first-class apps, **LOVABench v2 (60 tasks, 180 cases, 20 KB JSONL)**,
1 telemetry DB (19 KB).

**All 14 experiments run** as of 2026-09-09. Exp 03 and Exp 07 had
been dead for four months (solution tables covering 20 tasks against a
60-task corpus, Q30); they were extended and de-duplicated — Exp 07 now
imports Exp 03's table rather than keeping a copy of it, which is what
let them drift apart in the first place.

Headline moved with the fix: **pass@1 LOVA 60/60 vs Python 59/60**
(180/180 vs 177/180 test cases), raw byte density **25.8×** where the
20-task slice said 39.2×. The one Python failure is still pb20, the
same keyword-argument weakness. Quote the correctness number with Exp
13's F3 attached: the prompts state the formula, so the baseline
measures transcription, not synthesis.

**Launch-ready numbers:**
- **Expressiveness** (Exp 12): 44/44 cases across ten recursion- or
  iteration-requiring tasks; 0/10 were representable before M9.
- **Correctness** (Exp 07, LOVABench v2): LOVA 60/60 vs Python 59/60 pass@1, same tasks/LLM — but see the transcription caveat above.
- **Byte density** (Exp 07, v2): 25.8× raw (39.2× on the narrower v1 slice).
- **LLM-token density** (Exp 11, tiktoken cl100k_base):
  - **Aggregate across LOVABench v2 (60 tasks, 5 categories):**
    - Stage 1 text surface: **2.0× fewer tokens than sympy-Python (50% savings)**,
      **8.5× vs pure-Python (88%)**.
    - Stage 2 (fine-tuned projection): **3.2× vs sympy (68%)**,
      13.5× vs pure (93%).
  - **Per-category (Stage 1 vs sympy):** deep-compose 2.8×, v1-core 2.5×,
    conserve 2.3×, surprise 1.4×, let-heavy 1.4×.
  - v1 slice preserved (2.5×/13.3×) as historical reference; v2 aggregate
    is the honest broader number.
- **Density, honestly** (Exp 14): quote the surface, not a single
  number. Stage 2 is **5.38× vs sympy-Python on LOVABench** and
  **1.13× vs Python on algorithmic tasks**; Stage 1 is 2.00× and 0.66×
  respectively. The old 8.5× was Stage-1-vs-pure-Python on
  number-theory tasks — a real number answering a question nobody asked.
- **Density does not generalise at Stage 1** (Exp 12): on ten algorithmic tasks
  where neither language has a built-in shortcut, Stage-1 LOVA costs
  **1.5× MORE LLM tokens than Python** (0.66×), and the Stage-2
  projection does not rescue it (0.65×). Bytes stay mildly positive
  (1.19×). The 8.5× above measures the number-theory built-ins, not
  the language. Quote both or quote neither; `journal/experiment_12.md`
  has the mechanism.

## Next milestones (proposed)

**M6 — AI-preference hardening** (complete, all three items delivered)
1. ✅ Body-scanning DeltaTrap — probe-based scanner with two passes
   (operator-swap + literal-replacement) identifies the deepest
   sub-expression at fault; fuzz 50/50, closed-loop repair 5/5
   (Exp 09; Q20 closed).
2. ✅ Scope-aware static analysis — shipped as compile-time scope-check
   pass in `core/compiler.py` (Exp 08); unbound-ref now raised at
   compile time with full L2 anomaly schema (Q21 closed).
3. ✅ Historical pass-rate telemetry — `core/telemetry.py` + TokenChoice
   extension; weighted sampler +20 pp over uniform (Exp 10; Q22 closed).

Bonus already delivered: **constant-folding pass** (58.5% node
compression on LOVABench v1) and **type-check pass** in Day 1;
**fix-kind tagging** (operator-swap / literal-replacement /
heuristic) in Day 2; **DoS guard** `MAX_NT_INPUT=2000` in Day 3
(unaffects LOVABench; prevents random `(p (p N))` bombs).

New questions raised by M6: Q23 (pair-probe for multi-offender
bodies), Q24 (alt-op set via `valid_next` in context), Q25 (lineage
tagging for delta-repair), Q26 (task-level pass signal), Q27
(principled termination weighting), Q28 (incremental telemetry
merge), Q29 (richer conditioning — grandparent / sibling-type).

**M10 — data** (complete; see `spec/token-budget.md`)
One cons cell, `div`, and the zero-slot surface levers. Open decisions
it leaves: placement of `nil` / `nil?` (they sit in the wrong families
because Structural was full), `quote` / `eval`, and the Axiom 8
revision. New questions: Q42 (`List<T>` for nested structure), Q43
(unknown lambda parameter types), Q44 (should `valid_next` expose
completion cost so any sampler can see which choices terminate), Q45
(should `partition` now return a real pair).

**M9 — abstraction and iteration** (complete; see Exp 12)
Landed ahead of M7/M8 because both depend on it. Follow-ups it
raised: ~~Q30~~ (fixed at M13), Q31 (does the number-theory family owe
slots to `div` / `<`?), Q32 (terser Stage-1 surface), Q33 (LOVABench
v3 with an algorithmic category), Q34 (mutual recursion), Q35
(arity-indexed `Fn<n>`), Q36 (re-run Exp 03/10 — `constrained_random`
now emits lambdas, so their distributions are stale).

**M7 — MCP server / external integration** (complete, 2026-09-09)
1. ✅ `core/mcp_server.py` exposes `lova_execute`, `lova_valid_next`,
   `lova_static_analyze` (and `lova_emit`) as MCP tools over stdio —
   inside the package rather than a separate `lova-mcp`, and with no
   MCP SDK dependency, because the transport is one JSON object per
   line and the core is stdlib-only by design. Tool names use `_`
   rather than `/` because hosts validate names against
   `[a-zA-Z0-9_-]`.
2. ✅ `pip install .` builds a wheel with `core`, `lib/*.lova` and the
   corpus, and a `lova` console script (1.0.0 on GitHub Releases). Publishing to PyPI is
   the owner's call.
3. ✅ `apps/mcp_demo.py` drives the server through its pipes; the
   README carries the host configuration.

**M8 — Fine-tuning corpus + real-LLM benchmark** (≈ 1 month + GPU)
0. **Prerequisite from Exp 12:** every LOVABench task predates M9, so
   a corpus derived from them teaches a sublanguage of straight-line
   arithmetic. Add an algorithmic category first (Q33) or the
   fine-tune measures the wrong language.
1. Synthetic corpus generator: 10k+ `(prompt, program)` pairs derived
   from `constrained_random` + task-template expansion.
2. Fine-tune a 7B-70B open model (Qwen3, Llama4) on the corpus.
3. Measure pass@1 delta on held-out LOVABench v2. Target: fine-
   tuned model's LOVA pass@1 > its Python pass@1 on same tasks.

Everything beyond M8 is future work conditioned on MVP traction.

## Author & history

- LOVA conceptualised 2026-04-23 in conversation between the project
  owner and Claude.
- Parent lineage: DNA OS v3 (`../dna-os-v2.1/dna-os-v2.1/dna_os_v3/`).
- The concept arose from the observation that **DNA OS's 4 pillars are
  architecturally aligned with what AI-native code generation needs**
  (conservation → contract, surprise → debug, evolution → variants,
  lineage → provenance). Rather than treat this as a coincidence, the
  project takes the alignment seriously and builds the language
  explicitly.
- First design doc: this CLAUDE.md.
- Follow-on design docs: `spec/axioms.md` (full argument for each
  axiom), `spec/paradigm-inheritance.md` (seven PL trajectories),
  `spec/tokens.md` (complete 64-operator reference).
- M1-M5 landed 2026-04-23 / 2026-04-24. 10 / 10 axioms validated or
  partially validated with experiments 01-07 in `journal/`.
