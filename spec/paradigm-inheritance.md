# LOVA — Paradigm Inheritance

> **Positioning.** LOVA is not a random reinvention. It is the
> **synthesis** of seven programming-language-design trajectories that
> have been running, each in isolation, for decades. The claim is not
> "LOVA has better syntax" — the claim is that these trajectories,
> taken together, converge on something that looks like LOVA,
> and that the convergence makes sense specifically in an AI-authored
> world.
>
> This document traces each LOVA primitive and axiom to its paradigm
> ancestors, so that the design is grounded in the history of
> programming languages rather than floating above it.

## The seven trajectories

Seven long-running design trajectories in programming languages. Each
has been answering a different question for decades. LOVA is where
they meet.

### T1 — Homoiconicity (code is data)

- **Lisp (1958)** — code is s-expressions; programs are first-class
  data; macros operate on this. First generation of "code = data".
- **Scheme / Clojure** — refined macro systems, syntax-case, hygienic
  macros.
- **Unison (2020s)** — code is content-addressed; every definition has
  a stable hash identity; refactoring is structural, not textual.
- **Gödel numbering (1931)** — mathematical ancestor: any syntactic
  object can be encoded as an integer. Never seriously implemented as
  a programming substrate, but conceptually exact.

**LOVA extends the trajectory** by making the integer form — not a
syntax tree, not a hash — the canonical representation. Lisp's
s-expression was an abstraction over characters; LOVA's integer is
the substrate. This is the terminal point of the homoiconicity
trajectory: code and data are not just isomorphic, they are the same
object.

### T2 — Effect tracking

- **Pure functional** (Haskell, SML, ML) — pure vs impure; IO monad
  as binary gate.
- **Effect rows** (Koka, Eff, Frank, Scala's effect handlers) —
  fine-grained tagging of what a function can do. Row-polymorphism.
- **Algebraic effects** (Multicore OCaml) — resumable effects.
- **Linear types** (Clean, Linear Haskell, Rust ownership) — resources
  used exactly once, not discarded, not duplicated.
- **Session types** (research, 2010s+) — protocol types for
  communication.

**LOVA extends the trajectory** via conservation contracts (Axiom 4)
that unify effect rows + linear types + budget tracking into a single
type-level construct. A function declares not only *what* it can touch
but *how much* of each resource it consumes. Violation is a Δ-trap at
runtime, not a silent deviation.

### T3 — Program synthesis

- **Metaprogramming** (Lisp macros, Template Haskell, MLton) — programs
  that write programs, at compile time.
- **Program search** (MOSES, inductive programming, Hazel, Copilot) —
  search for a program that satisfies given constraints.
- **Grammar-constrained decoding** (Outlines, llguidance, JSON mode) —
  LLM generation under a regular/context-free grammar.
- **Structured prediction** (DSPy, Guidance, LMQL) — program structures
  inferred by LLMs under declarative specifications.

**LOVA extends the trajectory** by making AI-generation the
**primary authorship mode**. Type-directed generation (Axiom 3) is
grammar-constrained decoding lifted to the full language: from any
prefix, the set of well-typed next tokens is computable, so an LLM
generating LOVA cannot produce ill-formed programs. Synthesis is
not an external tool — it is the default way code is written.

### T4 — Concurrency / parallelism

- **Shared memory + locks** (C/Java threads)
- **Actor model** (Erlang/OTP, Akka) — isolated mailbox-based processes
- **CSP** (Go's channels, occam) — channel-based communication
- **STM** (Haskell, Clojure) — software transactional memory
- **Dataflow** (LabVIEW, Reactive Extensions, Flink) — values
  propagating through a graph

**LOVA extends the trajectory** via populations (Axiom 6). A
function is not a single definition — it is a **population of variants
competing at dispatch time**. The runtime picks the best-fit variant
per workload; losers retire; winners mutate. This is not another
concurrency model added to the others — it is a **replacement** for
"function = single definition" that the others all inherit from.

### T5 — Verification / correctness

- **Assertions** (C `assert`, Python `assert`)
- **Type systems** (Haskell's Hindley-Milner, ML's types, Rust's
  borrow checker)
- **Dependent types** (Agda, Idris, Lean, F\*) — types can depend on
  values; proof assistants
- **Formal verification** (Coq, Lean, Isabelle, TLA+) — machine-checked
  proofs of correctness
- **Property-based testing** (QuickCheck, Hypothesis) — randomized
  specification satisfaction
- **Fuzzing / differential testing** (American Fuzzy Lop, etc.) —
  discover correctness gaps statistically

**LOVA extends the trajectory** via surprise (Axiom 7). Instead of
requiring pre-run proofs (dependent types) or after-the-fact asserts
(property testing), LOVA runs code and emits **structured deviation
traces** when declared behavior mismatches observed behavior. AI uses
these traces to mutate at the offending token — a kind of **"proof by
iterated surprise minimization"**.

### T6 — Variance / evolution

- **Generic types** (Ada, Java generics) — parameterization over types
- **Polymorphism** (ML type variables, Haskell type classes) —
  function works over many types
- **Ad-hoc polymorphism** (Haskell type classes, Rust traits) —
  different implementations per instance
- **Evolutionary computation** (Genetic Programming, NEAT) — explicit
  population-based search for programs
- **AutoML / NAS** (neural architecture search) — automated
  hyperparameter + structure search

**LOVA extends the trajectory** by folding evolutionary computation
back into the language itself. `defpop` (Axiom 6) is genetic
programming as a first-class language construct, not an external
framework. Fitness, mutation, selection, reproduction are native
operators.

### T7 — Provenance / attribution

- **git / Mercurial** — file-level version control
- **Unison** — content-addressed code; every definition has an
  identity
- **Dataflow provenance** (research from databases) — track where each
  datum came from
- **Software bill of materials (SBOM)** — for security supply chain
- **Code attribution** (Copilot / Claude Code artifacts) — who wrote
  what

**LOVA extends the trajectory** by making lineage **intrinsic to
every program object** (Axiom 5). Every function, variant, and mutation
carries provenance (uid / parent_uid / root_uid, generation, mutation
record, fitness-at-divergence). `why?` and `lineage` are language
operators, not external tools.

---

## The axioms through the paradigm lens

Each of LOVA's 10 axioms has a clear lineage and a clear extension.

| # | Axiom | Paradigm roots | LOVA's step forward |
|---|---|---|---|
| 1 | Programs are integers, not text | Lisp (1958), Gödel (1931), Unison (2020s) | Integer is the substrate, not an abstraction over one |
| 2 | Human readability is non-goal | Assembly, bytecode, APL, K/kdb+ | First language to **design for** non-readability |
| 3 | Type-constrained generation | Dependent types, grammar-decoding | Full-language grammar constraint by position |
| 4 | Conservation as type | Effect rows, linear types | Unified: effects + budgets + invariants in one contract |
| 5 | Lineage is intrinsic | Unison, git, provenance research | Lineage embedded **in every object**, queryable as data |
| 6 | Populations over individuals | Genetic programming, type classes, AutoML | Evolution is **substrate**, not a library |
| 7 | Surprise is debugger | Active inference, predictive coding | Structured surprise traces replace stack traces |
| 8 | Small core, dense tokens | Scheme R7RS-small, Forth, APL | Exactly 64 tokens, each 1 byte; principled ceiling |
| 9 | No PnL / reward objective | Pure FP, separation of concerns | Objectives are declarations, not defaults |
| 10 | Stage-coherent design | Staged programming, MetaOCaml, Terra | Text ↔ integer coherent across 3 authorship stages |

---

## The primitives through the paradigm lens

### partition / merge (0x02 / 0x03)

- **Inherits from**: Lisp cons/car/cdr; Haskell pattern matching; algebraic data types.
- **Extends**: the **semantic** of decomposition is number-theoretic, not structural. `a + b = n` is an arithmetic invariant, not a type-constructor invariant. This makes decomposition meaningful over any integer, not just over values of predeclared types.

### conservation / budget (0x10 / 0x11)

- **Inherits from**: Haskell IO monad, Koka effect rows, Rust
  lifetimes, Clean's unique types, linear Haskell.
- **Extends**: contracts are **numerical** (budgets) + **structural**
  (invariants) + **temporal** (across sub-computations) in one. The
  Δ-layer makes violation a **runtime-detectable event with structured
  metadata**, not a panic or an undefined-behavior point.

### defpop / variant / evolve (0x20-0x22)

- **Inherits from**: Koza's Genetic Programming (1992); NEAT
  (neuroevolution); Haskell type classes; Rust traits.
- **Extends**: lifecycle (clone, mutate, retire, resurrect) is
  **substrate-level**. `defpop` is not a DSL embedded in a host — it is
  the host.

### surprise / watch (0x18 / 0x19)

- **Inherits from**: Karl Friston's active inference; predictive coding
  (Clark 2013, 2015); RL intrinsic motivation (Schmidhuber);
  change-point detection (CUSUM, BOCPD).
- **Extends**: surprise is **first-class I/O primitive**, not a
  research concept. A function's signature can declare surprise budgets;
  runtime emits traces; AI consumes traces for repair. The entire
  debug loop runs on surprise.

### lineage / why / hash (0x38 / 0x39 / 0x3C)

- **Inherits from**: Unison's content addressing; git's commit DAG;
  provenance research in databases.
- **Extends**: lineage is **intrinsic to evaluation**, not a post-hoc
  annotation. Every mutation event is a lineage event; every call is a
  provenance point. The DAG is queryable as a data structure.

### SEQ / LET / IF_SURPRISE / LAMBDA (0x28 / 0x2E / 0x2A / 0x2C)

- **Inherits from**: Lisp S-expressions; ML's let-binding; Haskell's
  `do` notation; continuation-passing style (Scheme).
- **Extends**: IF-SURPRISE **replaces** traditional if/else. Branching
  on surprise magnitude unifies "conditional" with "learning-in-the-
  loop" — a program's control flow depends on whether what just
  happened surprised it.

### p / τ / σ / φ₃ / ψ₇ / η (0x08 / 0x09 / 0x0A / 0x0B / 0x0C / 0x0D)

- **Inherits from**: Mathematica's number-theory primitives;
  SageMath's NT module; Pari/GP.
- **Extends**: number-theory is **not a library import** — it is part
  of the core 64 tokens. This is deliberate: an AI working in LOVA
  has a richer semantic vocabulary over integers than any mainstream
  language provides natively.

---

## What LOVA synthesises that no predecessor has

Each trajectory above, in isolation, has been pursued by a successful
language. Haskell perfected T2 (effect tracking). Lisp perfected T1
(homoiconicity). Koza's GP and NEAT perfected T6 (evolution). Agda/Lean
pushed T5 (verification) to the limit. **But no predecessor unified
them.**

LOVA's synthesis claim:

1. **Homoiconicity (T1) × Conservation (T2)** — a language where code
   IS data AND the mutation of that data is budget-tracked. Self-
   modifying programs with resource guarantees. Never done before —
   Lisp's macros are uncatalogued, Haskell's effects don't apply to
   TH-level code.

2. **Synthesis (T3) × Evolution (T6)** — AI-generated programs aren't
   a one-shot output; they enter a population and compete. AutoML meets
   Codex meets genetic programming, at the language level.

3. **Verification (T5) × Surprise (T7)** — formal correctness is
   expensive; surprise is cheap. A program whose declared behavior
   matches its observed behavior within budget is "correct enough" —
   rigorous when you need it, lightweight when you don't.

4. **Provenance (T7) × Populations (T6)** — variants have parents;
   parents have parents. Wright-Fisher coalescence (observed in DNA OS
   v3 Exp 55) becomes a normal debugging lens: "which ancestor of this
   variant first exhibited this behavior?"

These four crosses are the novel territory. LOVA is not
"Haskell with surprise" or "Lisp with lineage" — it is the territory
where all four crosses land.

---

## What this means for the project

Every design decision from here on is assessed against paradigm
lineage:

- **If a proposed feature has no ancestor trajectory**, it is suspicious.
  Either it is the 8th trajectory (genuinely new), or it is incidental
  sugar that should be dropped.
- **If a feature extends multiple trajectories at once**, it is
  promising — that is where the synthesis lives.
- **If a feature is identical to something in a predecessor**, it
  should be named honestly (e.g., LOVA's `LAMBDA` is exactly Scheme's
  lambda; there is no reason to dress it up).

### The counterfactual to check

For each paradigm lineage, ask: **"if the paradigm-originator today saw
LOVA, would they recognise their trajectory's next step?"**

- Alan Kay on Lisp → programs as integers. Obvious continuation.
- Simon Peyton Jones on effect rows → conservation contracts with
  budgets. Obvious continuation.
- John Koza on GP → defpop as substrate. Obvious continuation.
- Karl Friston on active inference → surprise as I/O primitive. Obvious
  continuation.
- Edwin Brady on dependent types → type-directed generation. Obvious
  continuation.

**None of these are revolutions from within their trajectories.** They
are the natural next step if you take each trajectory seriously.
LOVA's novelty is only in putting them together.

---

## Revision history

- 2026-04-24 — document created alongside Milestone 2. Establishes the
  paradigm-evolution framing for the whole project.
