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
   humans review exceptionally. Text surface becomes terse / APL-dense.
   LLM fine-tuned on LOVA corpus.
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
- A substrate where **every program is a `PartitionedFile<n>`** — an
  integer with heat, lineage, and conservation metadata
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
| Mock theta (φ₃, ψ₇) driver | Token-family timing primitives |
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
0x00-0x07   Structural            partition / merge / heat / inherit
0x08-0x0F   Numerical primitives  p, τ, σ, φ₃, ψ₇, η, gcd, mobius
0x10-0x17   Conservation          budget-decl / conserve / Δ-check / respawn
0x18-0x1F   Surprise / watch      surprise / watch / when-anomaly / threshold
0x20-0x27   Evolution             defpop / variant / evolve / select / mutate
0x28-0x2F   Composition           seq / parallel / if-surprise / loop-until
0x30-0x37   Effects / IO          external-boundary / net-send / net-recv
0x38-0x3F   Meta / lineage        lineage-query / why / trace / explain
```

Full token spec to be written in `spec/tokens.md` as design progresses.

**Stage 1 text surface** is a Lisp-like s-expression syntax that maps
1:1 to token sequences. Example:

```lova
(defn square [n] (n ⊗ n))
```

compiles to a short integer sequence, e.g. `[0x20, 0x01, 0x00, ...]`.
The text form is a pretty-printer over the integer form, not the canonical
representation.

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

Early-stage. No public entry point yet. Once `core/` has a minimal
encoder + runtime:

```bash
cd /path/to/lova
export PYTHONPATH="$PWD"

# REPL (Stage-1 text surface)
python -m core.repl

# Execute an integer-sequence program directly
python -m core.runtime --program 0x20,0x01,0x00,...

# Run an experiment
python experiments/experiment_01_hello_lova.py
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

## Current state (2026-04-24 — post-M6 Day 3, M6 complete)

**10 / 10 axioms operational.** See `journal/README.md` for per-
experiment details.

| Axiom | Impl | Exp |
|---|---|---|
| 1. Programs are integers | ✅ | 01 (integer 55916975560956379404) |
| 2. No human-readability as goal | ✅ | design decision |
| 3. Type-constrained generation | ✅ | 02 (100% vs 0% well-formed) |
| 4. Conservation as type | ✅ | 01 (Budget/Delta trap) |
| 5. Lineage intrinsic | ✅ | 04 (Wright-Fisher coalescence) |
| 6. Populations over individuals | ⚠️ partial | 05 (mechanism OK, 30% convergence) |
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

**19 / 64 operators runtime-implemented**; 45 reserved. See
`spec/tokens.md` for the complete table.

**Code statistics:** ~7600 Python LOC (core + tests + corpus + experiments + apps),
122 unit tests passing, 11 experiments (pb11 has a v1 pilot + v2 re-run),
2 first-class apps, **LOVABench v2 (60 tasks, 180 cases, 20 KB JSONL)**,
1 telemetry DB (19 KB).

**Launch-ready numbers:**
- **Correctness** (Exp 07, LOVABench v1): LOVA 20/20 vs Python 19/20 pass@1, same tasks/LLM.
- **Byte density** (Exp 07): 39.2× raw, ~15-20× vs sympy-Python.
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

**M7 — MCP server / external integration** (≈ 1-2 weeks)
1. `lova-mcp` Python package exposing `lova/execute`,
   `lova/valid_next`, `lova/static_analyze` as MCP tools.
2. One-line install path: `pip install lova-lang`.
3. Demo scripts that any MCP-connected agent (Claude Desktop, Cursor,
   Claude Code) can call directly.

**M8 — Fine-tuning corpus + real-LLM benchmark** (≈ 1 month + GPU)
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
