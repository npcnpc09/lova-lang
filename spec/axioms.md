# LOVA — Design Axioms

The ten load-bearing commitments of the language. Each axiom is stated,
argued for, and bounded with explicit "what this does NOT mean" to
prevent drift.

These are DESIGN invariants — they bind every feature decision from
now on. If a proposed feature violates any of these, either the feature
is rejected or the axiom is revisited with a written justification
(which becomes this document's revision history).

---

## Axiom 1 — Programs are integers, not text

**Statement.** The canonical representation of a LOVA program is a
`PartitionedFile<n>` — a typed integer with heat, lineage, and
conservation metadata. Text is a projection over this integer, not the
other way around.

**Why.**
- Modern AI reads and writes token sequences natively. Integer
  sequences ARE token sequences — the LLM's output is the program,
  without a parsing step.
- Text introduces entropy (whitespace, identifiers, comments) that adds
  inference cost without semantic value in an AI-only pipeline.
- PFS's conservation / heat / lineage primitives apply naturally to
  integer programs (heat = how often this function is called; lineage
  = provenance chain; conservation = preserved invariants during
  mutation).

**What this does NOT mean.**
- It does not mean humans cannot read programs. `explain(program)` is
  a first-class meta-operation that projects an integer program to
  natural language.
- It does not mean text surface syntax is forbidden. Stage 1 has a
  text surface as a bootstrap. Stage 3 drops it.

---

## Axiom 2 — Human readability is a non-goal of the substrate

**Statement.** The substrate's design (token choices, semantics, type
system, runtime behavior) is not constrained by "what is pleasant for a
human to read." Human-readable projections are tooling, added on top.

**Why.**
- Optimising for two audiences (human + AI) yields Pareto-suboptimal
  designs for each. Modern languages already show this: Python's
  whitespace sensitivity is a human convenience that complicates AI
  generation / diffing.
- Once AI is the sole author, "readable" becomes a property of the
  projection layer, not the substrate. You can always render a program
  into prose / pseudocode / diagrams on demand.

**What this does NOT mean.**
- It does not mean obfuscation. The substrate is deterministic and
  auditable — just not word-for-word human-friendly.
- It does not mean no documentation. Documentation is a first-class
  meta-artifact (`(explain fn)`, `(why? action)`), not a convention.

---

## Axiom 3 — Type-constrained generation

**Statement.** For any partial program (a prefix of a token sequence),
the set of well-typed next tokens is computable. AI generation
traverses this tree; ill-typed programs are unreachable from any valid
prefix.

**Why.**
- LLM generation is inherently stochastic. Post-hoc syntax checking
  produces retry loops — expensive and unreliable.
- Grammar-constrained decoding (Outlines, llguidance) already shows
  this works for structured output. LOVA scales this to the whole
  language, not just to JSON schemas.
- Result: zero syntax errors, zero type errors, at generation time.
  Effectively shifts ALL error detection to higher layers
  (conservation, surprise, behavioral correctness).

**What this does NOT mean.**
- It does not mean programs are always correct. They are always
  well-typed and well-formed, but may still fail conservation checks
  or produce incorrect behavior.
- It does not mean types are always explicit. Types are **positional**
  — determined by the preceding operator's signature. No annotation
  tokens needed.
- **It holds at the name level for generated programs, and at the
  operator level for everything else** (Exp 08; Exp 12/F4; Exp 16).
  Since M16 the generation state machine is given each literal's
  payload and keeps scope, so a reference to nothing, or to a binding of
  the wrong type, is unrepresentable by generation — 704 of 1000
  generated programs had one before, none do now. The compiler's scope
  and type passes remain the check for trees that did not come from the
  generator: hand-written, mutated, or read back from text. One shape
  the compiler accepts cannot be generated left-to-right: a mutually
  recursive `def` chain (Q64). Both paths surface the same L2 anomaly;
  what differs is *when*. State the axiom with this qualifier.
- It does not mean curried arity is tracked. `Fn` distinguishes
  callable from integer and nothing finer, so a partial application
  placed in an integer slot fails at run time (Q35).

---

## Axiom 4 — Conservation is a type, not a runtime afterthought

**Statement.** Every function declares its effect / budget / surprise
bounds in its type signature. These are not optional metadata — they
are checked at declaration site (static) and at runtime (Δ-trap).

**Why.**
- In an AI-authored ecosystem, behavior changes silently if not
  constrained. A conservation contract is the minimum defense against
  "AI edited this function and now it uses 10× more resources."
- Aligns with DNA OS's pillar 4 (Δ-security): `sum(n) ≡ budget` is not
  a target — it is a constraint violation = panic.
- Makes behavior changes visible: a function whose budget changes
  requires an explicit lineage event, not a silent diff.

**What this does NOT mean.**
- It does not mean conservation is the only correctness criterion. It
  is one of several (type, conservation, property, behavior).
- It does not mean all functions have complex contracts. `pure`
  functions with no effects and constant budget need only 1 byte of
  contract metadata.

---

## Axiom 5 — Lineage is intrinsic

**Statement.** Every program artifact carries provenance — which AI
authored/modified it, when, based on what prompt, derived from what
parent. Provenance is queryable in the language itself (`why?`,
`lineage`, `ancestor-of?`).

**Why.**
- In an AI-authored ecosystem, the question "who made this change and
  why" is asked constantly. Current tools (git, audit logs, traces)
  are external bolt-ons with semantic loss.
- DNA OS's Exp 55 (Wright-Fisher coalescence, uid/parent_uid/root_uid)
  showed lineage can be first-class at the object level. LOVA does
  the same at the program level.
- Enables regression analysis, attribution, and rollback as substrate
  operations, not as engineering practice.

**What this does NOT mean.**
- It does not mean code signing. Provenance is structural (this
  program derived from that program via this mutation), not
  cryptographic identity.
- It does not mean history is immutable. Lineage nodes can be retired
  (deprecated variants), but the historical record is preserved.

---

## Axiom 6 — Populations over individuals

**Statement.** A function, in LOVA, is not a single definition —
it is a population of variants. Dispatch at call time selects the
best-fit variant for the current workload; losing variants are retired,
winning variants are cloned and mutated.

**Why.**
- AI naturally generates 3-10 candidates per problem. Current
  workflows discard 90% of them ("pick one and commit"). This is
  waste.
- DNA OS's evolution engine showed evolutionary dispatch beats static
  selection on heterogeneous workloads (Exp 23 dispatch_quality
  0.983, Exp 37 -20.7% MAE).
- Makes long-running systems self-improving: your `map` function in
  year 3 is not the same as `map` on install day — it evolved against
  your specific workload.

**What this does NOT mean.**
- It does not mean populations are always large. `pool-size=1` is
  valid; it is just a degenerate population.
- It does not mean non-determinism is rampant. A dispatched variant is
  deterministic for its inputs; the *selection* across calls may vary,
  but each call's trace is reproducible.

---

## Axiom 7 — Surprise is the debugger

**Statement.** The substrate emits surprise traces — structured
deviations from declared behavior — rather than stack traces.
AI-driven repair mutates at the offending token position,
surprise-minimising. There is no `breakpoint`, no `print`, no `gdb`.

**Why.**
- Stack traces are human-debugger artifacts. An AI reads them and
  translates to "this deviated from expected behavior" — a lossy,
  expensive translation.
- DNA OS's Exp 75-78 showed surprise scales naturally with rarity.
  Using it as the debug primitive means bigger bugs produce bigger
  signals, small bugs are naturally deprioritised.
- Repair is automatic: runtime emits a surprise trace, a
  LOVA-fluent AI consumes it and patches the token at the
  offending position. No IDE required.

**What this does NOT mean.**
- It does not mean humans can never debug. `explain(trace)` projects
  a surprise trace to human-readable form on demand.
- It does not mean surprise is the only signal. Conservation
  violations, property test failures, and explicit assertions coexist.

---

## Axiom 8 — Small core, dense tokens

**Statement.** The core operator set is exactly 64 tokens (1 byte each),
grouped into 8 semantic families. Every token carries semantic weight;
no token is sugar.

**Why.**
- Small vocabulary = dense embedding per token = parameter-efficient
  for LOVA-specialised LLMs.
- 64 operators are enough for Turing completeness (µ-recursive
  functions need <10). The extra 50+ are for ergonomic expression of
  the specific patterns LOVA cares about (conservation, surprise,
  evolution, lineage).
- Forcing the core to be small prevents "kitchen-sink" bloat (Python's
  ~35 keywords + 70 built-in functions + countless stdlib modules).

**What this does NOT mean.**
- It does not mean only 64 operations exist. Standard library
  functions compose these. `defpop` + mutation generates variants of
  stdlib functions over time.
- It does not mean 64 is fixed forever. The count may be revised with
  written justification and a migration path for existing corpora.

---

## Axiom 9 — No PnL / reward objective

**Statement.** The language is neutral to optimisation targets. The
substrate does not privilege profit, reward, loss, or any specific
objective function. Users declare their objectives via conservation
contracts and surprise budgets; the substrate enforces compliance.

**Why.**
- Inherited directly from DNA OS's Axiom 5 ("No External Objective").
  A language that bakes in a reward model is a subset of a language
  that does not.
- Makes LOVA a general-purpose substrate for AI-authored code —
  not a trading system, not an optimiser, not an RL framework.
- Prevents misuse-by-design. A language that privileges "maximise X"
  is a language that can be turned against arbitrary X.

**What this does NOT mean.**
- It does not mean you cannot write optimisers in LOVA. You can.
  They just have to declare their objective explicitly; the substrate
  does not infer it.
- It does not mean LOVA is objective-free at the application level.
  Applications express their own fitness / loss / goal; the substrate
  stays neutral.

---

## Axiom 10 — Stage-coherent design

**Statement.** Every design decision must remain coherent across all
three stages (text-surface / AI-primary / pure-integer). If a feature
makes Stage 1 nicer but breaks Stage 3's integer-only representation,
it is rejected.

**Why.**
- LOVA has a committed trajectory: text is a bootstrap, integer is
  the endpoint. Features that are "nice in text but hard in integer"
  would force a V2 rewrite when the transition happens — a known
  language-death failure mode.
- Forces discipline: every surface construct must have a clear
  integer encoding, checked during review.

**What this does NOT mean.**
- It does not mean Stage 1 tooling is forbidden. Pretty-printers,
  REPLs, editor plugins are all allowed — they are projections over
  the integer form, not extensions of it.
- It does not mean Stage 3 must arrive tomorrow. The transition can
  take 5-15 years. But every design today is made with Stage 3 as
  the reference.

---

## Axiom drift protocol

If an axiom needs revision (empirical evidence contradicts it,
design work reveals it was wrong), the revision procedure is:

1. Write a journal entry documenting the evidence
2. Propose the revised axiom in this file, with a clear diff and
   justification
3. Review implications for existing code and future work
4. Update CLAUDE.md to reference the new axiom
5. Record the date and reason in the revision history below

## Revision history

- 2026-04-23 — initial draft. All ten axioms stated. Project
  bootstrap. No revisions yet.
- 2026-04-24 — **10 / 10 axioms operational in code.** Validated by
  experiments 01-07. Axiom 6 (populations) is marked *partial*:
  the dispatch / retire / reproduce mechanism is operational and
  demonstrable, but convergence rate under the current mutation
  landscape is ~30% on the self-healing benchmark (Exp 05). Q16-Q19
  are open for M6 to improve convergence via structural mutation
  (not literal-only) and diversity pressure (port DNA OS
  `enforce_diversity`). No axioms retracted.
