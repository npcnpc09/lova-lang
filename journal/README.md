# LOVA — Research Journal

Rolling log of LOVA's design and empirical validation.

This journal is the source of truth for *why* the language does what it
does and *what we still do not know*. Code without journal is sculpture;
the journal is what makes it an experiment.

## The vision

See `../CLAUDE.md` for the one-page project orientation and
`../spec/axioms.md` for the ten design invariants.

## Current state (2026-04-24)

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
**This is the benchmark to cite in launch materials.**

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

## Experiment log

| # | Date | Title | Status | Key finding |
|---|---|---|---|---|
| 01 | 2026-04-23 | Hello LOVA (MVP substrate) | Done (pilot) | **WIN.** 4 axioms (1, 4, 7, 8) operational in 790 LOC. Round-trip lossless 11/11; conservation + Δ traps emit structured metadata; surprise trace emits 3 structured events. Programs literally integers: `(merge (p 3) (tau 12))` → 9 B → 55916975560956379404. |
| 02 | 2026-04-24 | Type-directed generation (Axiom 3) | Done (N=1000 each) | **WIN (STRONG).** Constrained generation 1000/1000 = 100% well-formed. Unconstrained 0/1000 = 0%. Delta +100pp. Sharp constraint: after LET, valid_next goes from 18 tokens to 1. Paradigm synthesis of grammar-decoding + dependent types + positional typing. |
| 03 | 2026-04-24 | LOVABench v1 + corpus starter kit | Done (20 tasks × 3 baselines) | **WIN (STRONG).** Reference 20/20; unguided constrained-random 1/2000 (0.05%, one degenerate task); Claude 20/20. Gap 0% → 100% across capability spectrum. JSONL corpus shipped at `corpus/lovabench_v1.jsonl`. 2 Claude solutions are semantic variants (commutative merge, associative gcd) — pass by behavior not by template match. |
| 04 | 2026-04-24 | Lineage intrinsic + Wright-Fisher (Axiom 5) | Done (pilot) | **WIN.** `core/lineage.py` 230 LOC: uid/parent_uid/root_uid/generation/mutation_kind. Wright-Fisher coalescence at program level: 5 roots → 1 survivor after 10 gens (matching DNA OS Exp 55). Mutation produces 49/100 distinct variants. Axiom 1 preserved — lineage is metadata, encoded bytes stay clean. |
| 05 | 2026-04-24 | Self-healing population (Axiom 6) | Done (N=10 seeds) | **PARTIAL WIN.** 5 variants all WRONG (distances 12-35 from target=42). After 12 evolve rounds: best seed 35→1 distance (97% gap), 3/10 seeds converge ±2, all 10 improve substantially (mean 80% gap closure). Mechanism (dispatch/retire/reproduce) demonstrably works; convergence not guaranteed under current mutation landscape (Q16-Q19 open for M5). |
| 06 | 2026-04-24 | Observability (L1+L2+L3) | Done (pilot) | **WIN.** Three AI-preference levers. **L1** `valid_next_with_stats`: TokenChoice with arity/depth/terminating/effects/cost. **L2** enriched anomalies: `offending_op=0x09(tau)`, `valid_alternatives=(P,SIGMA,MOBIUS)`, `repair_hint`. **L3** `static_analyze`: pre-execution effects/cost/determinism. Error surface narrows to semantic-only (syntax/type/arity physically unreachable). Foundation for Claude-vs-Claude benchmark. |
| 07 | 2026-04-24 | Claude-vs-Claude (Python vs LOVA) | Done (N=20×2) | **WIN (STRONG).** Same 20 tasks, same LLM. **pass@1: LOVA 20/20 vs Python 19/20** (pb20 Python failed on keyword-arg / scope-shadowing — structural Python weakness). **Error-class subset**: Python's {syntax,name,type,import,attribute,semantic} vs LOVA's {semantic,conservation,unbound-ref}. **Density: 39.2× raw** (vs hand-rolled pure Python), ~15-20× adjusted (vs sympy-equivalent). This is the launch pitch. |
| 08 | 2026-04-24 | Compiler passes (scope + type + fold) | Done | **WIN.** `core/compiler.py` adds 3 static passes. Scope-check moves `unbound-ref` from runtime to compile-time with full L2 anomaly. Constant folding on LOVABench v1: **58.5% node compression, 43.9% bytes saved** (82→34 nodes, 155→87 bytes). Pure-program tasks collapse to single LIT_INT. `CompileError.anomaly` shares 7/7 L2 fields with `BudgetTrap` / `DeltaTrap` — uniform AI error handler. Error surface after M6: compile {unbound-ref, type-mismatch}, runtime {budget-exceeded, conservation-violated, semantic}. |
| 09 | 2026-04-24 | Body-scanning DeltaTrap (Q20) | Done (5 canonical + N=50 fuzz) | **WIN.** Δ-trap anomaly gains `body_offender = {op, path, depth, observed, needed, correction, fix}`, replacing the uniform `offending_op == CONSERVE` signal. Two-pass probe: **Pass A** tries operator-swap from `suggest_alternatives` (VIOLATE→IDENTITY); **Pass B** falls back to literal replacement. Canonical shapes 5/5; fuzz **50/50 = 100%** (pre-Pass-A was 60%). Closed-loop repair 5/5: receive anomaly → apply `needed` at `path` → conservation holds. Q20 closed; Q23/Q24/Q25 raised. |
| 10 | 2026-04-24 | Pass-rate telemetry (Q22) | Done (20 refs + N=300 bootstrap; N=50 demo) | **WIN.** `core/telemetry.py` + `TokenChoice` extension. Bootstrap DB (20 LOVABench refs + 300 random) surfaces sharp context-specific divergences: LIT-as-child-of-CONSERVE **3%** vs global **65%** pass rate. **Weighted sampler +20 pp over uniform** (96% vs 76% pass-without-trap, N=50). `MAX_NT_INPUT=2000` DoS guard added for random-fuzz safety. `corpus/token_telemetry.json` shipped (19 KB). Q22 closed; Q26-Q29 raised. |
| 11 | 2026-04-24 | LLM-token density (LOVA vs Python) v1 | Done (20 tasks × 3 baselines) | **WIN (pilot, v1).** Measured with tiktoken cl100k_base (GPT-4/Claude-class). Aggregate across 20 LOVABench v1 tasks: **Stage-1 LOVA text surface uses 2.5× fewer LLM tokens than sympy-Python (60% savings), 13.3× fewer than pure-Python (93%)**. Stage-2 projection: **4.0× vs sympy, 21× vs pure**. 18/20 tasks win vs sympy. |
| 11b | 2026-04-25 | LLM-token density v2 re-run | Done (60 tasks, 5 categories) | **WIN (v2, broader & honest).** Re-run on LOVABench v2 (60 tasks = v1's 20 + 4 × 10 extensions). Aggregate density drops to **Stage-1 2.0× vs sympy (50%), 8.5× vs pure (88%)** — v1's narrower set over-represented LOVA's strongest shapes. Per-category: deep-compose **13.5×/2.8×** (LOVA peak), conserve 7.2×/2.3×, surprise 5.5×/1.4×, let-heavy 4.9×/1.4×. Stage-2 projection **3.2× vs sympy (68%)**. Launch copy updated; v1 preserved as historical slice. |

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
