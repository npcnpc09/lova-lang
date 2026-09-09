# LOVA

**An AI-native integer-sequence programming language.**

*Status: early research prototype. 10/10 design axioms have a working
implementation and an experiment behind them; the language is not yet
usable for general-purpose work.*

## The one-paragraph pitch

Current programming languages (Python, TypeScript, Rust) were designed
for human readers. As AI takes over code authorship, those design
constraints become overhead. LOVA is designed from the opposite
assumption: **AI is the first-class reader, writer, and executor**.
Code is not text — it is a typed integer sequence living in a
conservation-preserving substrate. The semantics, type system, error
model, and evolution machinery are all built around what AI does well.

```lova
(defn square [n] (n ⊗ n))
```

...is a Stage-1 *projection*. The program itself is an integer sequence;
the text is a pretty-printer over it, and round-trips losslessly.

## Three stages

| Stage | Surface | Status |
|---|---|---|
| **1 — Text-surface LOVA** | Lisp-like s-expressions compiling 1:1 to tokens | **current** |
| **2 — AI-primary LOVA** | terse / APL-dense; LLM fine-tuned on a LOVA corpus | planned (M8) |
| **3 — Pure-AI LOVA** | no text; programs are integer sequences, humans read via `(explain program)` | north star |

## What's actually implemented

- **64-token core ISA** (8 families × 8), 1 byte per operator — 19 operators
  have runtime semantics, 45 are reserved (`spec/tokens.md`)
- **Type-directed generation** — for any partial program the set of
  well-typed next tokens is computable, so ill-typed programs are not
  representable (`core/types.py`, `core/generator.py`)
- **Conservation as a type** — budget/effect bounds live in the signature;
  violations are compile errors or runtime Δ-traps (`core/conservation.py`)
- **Surprise instead of stack traces** — deviations surface as structured
  anomalies; the Δ-trap scanner pinpoints the deepest offending
  sub-expression *and* the correction value (`core/runtime.py`)
- **Lineage** — every artifact carries provenance, queryable in-language
  (`core/lineage.py`)
- **Populations** — a function is a pool of competing variants, not a
  single definition (`core/populations.py`)
- **Compiler** — scope-check, type-check, constant-fold passes; compile
  errors share the runtime anomaly schema so an agent has one error
  handler (`core/compiler.py`)
- **LOVABench** — 60 tasks / 180 cases across 5 categories, with a
  reference evaluator (`corpus/`)

## Quick start

Requires Python ≥ 3.10. The core has **no dependencies**.

```bash
git clone <this-repo> lova && cd lova
export PYTHONPATH="$PWD"

# run the test suite (122 tests, stdlib unittest only)
python -m unittest discover -s tests

# run an experiment
python experiments/experiment_01_hello_lova.py

# run a real LOVA program end-to-end
#   (parse → analyse → compile → encode → evaluate)
python apps/is_perfect.py 28
```

Experiment 11 additionally needs `tiktoken`:

```bash
pip install -e ".[experiments]"
```

## Measurements

All numbers come from `journal/`; each links to a reproducible script in
`experiments/`. These are **research-scale results, not benchmarks with
statistical guarantees** — sample sizes are stated for each.

| Metric | Result | Source |
|---|---|---|
| pass@1, same tasks & same LLM | LOVA 20/20 vs Python 19/20 | Exp 07 (LOVABench v1, 20 tasks, single run) |
| Raw byte density vs Python | 39.2× | Exp 07 |
| LLM-token density vs sympy-Python | **2.0×** (50% fewer tokens) | Exp 11b (LOVABench v2, 60 tasks, tiktoken cl100k_base) |
| LLM-token density vs pure Python | 8.5× | Exp 11b |
| Constant-folding compression | 58.5% fewer nodes, 43.9% fewer bytes | Exp 08 |
| Telemetry-weighted vs uniform sampling | +20 pp pass-without-trap (96% vs 76%) | Exp 10 (N=50) |

Note on honesty: Exp 11's first run on the narrower 20-task set reported
2.5×/13.3×; re-running on the broader 60-task v2 set dropped it to
2.0×/8.5×. The v2 number is the one quoted above. NULL and weakened
results are kept in the journal on purpose.

## Repository layout

```
core/          reference implementation (tokens, types, runtime,
               conservation, lineage, populations, compiler, telemetry)
spec/          design documents — axioms, token table, paradigm inheritance
corpus/        LOVABench tasks, JSONL export, evaluator, telemetry DB
experiments/   numbered, reproducible validation scripts
journal/       research log — one entry per experiment, NULLs included
apps/          first-class LOVA programs
tests/         122 unit tests, stdlib only
```

## Reading order

1. `spec/axioms.md` — the 10 design invariants and the argument for each
2. `spec/paradigm-inheritance.md` — the seven PL trajectories LOVA synthesises
3. `spec/tokens.md` — the 64-operator table
4. `journal/README.md` — the experiment log
5. `CLAUDE.md` — full project orientation (written for an AI session)

## Lineage

LOVA inherits its architectural vocabulary — PFS, conservation, lineage,
surprise, evolution, Δ-security — from **DNA OS v3**, a separate
(unpublished) research project by the same author. The concepts are
shared; the code here is an independent reimplementation, not a fork.

## Design philosophy

Human readability is an explicit **non-goal of the substrate**. The
Stage-1 text surface exists to bootstrap the project and to audit
programs on demand — it is tooling, not the language. Contributions
that make LOVA nicer for humans at the cost of Stage-3's pure-integer
representation will be rejected on principle (see Axiom 10).

There is also no PnL / reward objective anywhere in the language. Users
declare their own objectives through conservation contracts and surprise
budgets; the substrate only enforces compliance.

## License

MIT — see [LICENSE](LICENSE).
