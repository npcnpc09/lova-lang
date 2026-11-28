# LOVA — a language built for an AI to write, check and repair

> Orientation for a session working in this repository. It says what
> holds **now**. The history — every milestone, experiment and ruling —
> is in `journal/README.md`; this file was 82 KB of it until
> 2026-11-28 and that text is in git (`git show 6a96281:CLAUDE.md`).
> When a milestone lands, write the journal entry and change the facts
> here; do not append the story here.

## What it is

Code is a **typed integer sequence** (one byte a token), not text. A
program is written as a tree, stored and identified as an integer,
checked before it runs, run under a step budget and a capability
boundary, and when it fails it says where and what would fix it.
Human readability is not a goal of the substrate; the s-expression
surface is a projection.

It is a language, not a protocol, an OS, or a trading system. It does
not import DNA OS v3 code (its conceptual parent,
`../dna-os-v2.1/dna-os-v2.1/dna_os_v3/`); concepts transfer, code does
not.

## The goal (owner's ruling, 2026-09-10)

**An AI uses LOVA more conveniently than any other language.** Every
axiom is a means to it and yields to it. Measured on the same tasks
against Python, fresh sessions, by four numbers:

| number | standing | evidence |
|---|---|---|
| 1. attempts from writing to running correctly | parity on most tasks; behind on search-heavy ones | Exp 17-20, 31 (pilot) |
| 2. context spent on each failure | parity on like failures (193 characters a fault; a wrong value 75 against 71) | Exp 30; proper re-measure is Q142 |
| 3. scaffolding to run the code safely | **won** — a call under a budget and a boundary, against a subprocess | Exp 18 |
| 4. reusing, repairing, tracing | repair **won** at 110-160 lines; reuse and trace unmeasured | Exp 29 |

`spec/ai-convenience.md` is the yardstick and its protocol.

## The design method (owner's ruling, 2026-09-11)

Left to itself, the model doing this design builds another human
language, because human code is all it has learned from. So:

1. **Design from the AI's operations** — read the task, emit, check,
   run, observe the deviation, repair, leave evidence. Nothing enters
   because another language has it; an ancestor is not a reason.
2. **Text takes no part in design.** Decide on the integer sequence.
3. **The model's behaviour decides, not the designer's taste.** A
   design that has not been put against an alternative in a measured
   run is a proposal, not a decision.

What the experiments have settled under these rules:

- A current model **composes a tree and transcribes it** (Exp 24,
  eight of eight sessions). The integer substrate is storage,
  transport and identity; Stage 2 and Stage 3 are serialisation
  formats until Q110 (a model trained on the stream) says otherwise.
  The tree is the authoring form and the s-expression its projection.
- A fault found by **the program's own examples and a located edit**
  beats reading (Exp 28-29): nine of twelve repairs applied with no
  program text read.
- Density is spelling and syntax, not the token table (Exp 13, 14).
  Prefer a macro to a byte.
- The one mistake the type constraint cannot catch is a well-typed
  wrong value. The answer in use is relation examples and
  `check --strength` (M40), not a richer type.

## Axioms

Standing: **3** type-constrained generation (for generated programs,
at the name level since M16; the compiler is the check for everything
else), **4** conservation is a type, **5** lineage is intrinsic, **6**
populations over individuals, **7** surprise is the debugger, **9** no
PnL or reward objective.

Design preferences since 2026-09-10: **1** programs are integers, **2**
no human readability in the substrate, **8** small core, **10**
stage-coherent. They do not refuse a change the four numbers call for.

The audit of 2026-09-18 found the Evolution family, the lineage half
of Meta, number theory and telemetry held **by lineage only** — almost
no real program uses them. No byte was taken back; whether Axioms 5
and 6 stand without yardstick evidence is the owner's open question.
`spec/axioms.md` has the arguments.

## The token table

98 tokens, one byte each. `spec/tokens.md` is authoritative and
**generated** from `core/tokens.py` by `spec/generate_tokens_md.py` —
rerun it, never hand-edit. `spec/token-budget.md` is the ledger; read
it before proposing an operator.

```
0x00-0x3F  the core 64: structural, numerical, conservation,
           surprise, evolution, composition, effects/IO, meta
0x40-0x4F  text (M25, M32)        0x58-0x5E  fixed point (6b)
0x50-0x57  list (M27)             0x5F-0x61  swarm (6c, 6d)
```

The **swarm family is on probation** (Q153, Q154): it holds one
game's rules and a walk of any length costs one step. No further
domain family enters on a single program's profile.

The text, list, fixed and swarm families are admitted by the
validator and not emitted by the samplers. Adding a byte means: the
Python runtime (the reference), `native/lova-rt` (both evaluators),
the Stage-2 symbol, the card, `spec/runtime-semantics.md`, the golden
set — and rebuilding lova-rt, the Godot extension and the wasm module,
which refuse a byte they were built before.

## Layout

```
core/      tokens, types, surface (Stage 1), surface2 (Stage 2),
           compiler, runtime (the reference evaluator), generator,
           examples, locate, strength, query, brief, profile, cache,
           native (client of lova-rt), cli, mcp_server,
           conservation, lineage, populations, telemetry
native/    lova-rt (Rust: bytecode VM, the default; tree-walker
           behind --tree), lova-godot (GDExtension), lova-wasm
lib/       prelude.lova and the libraries, written in LOVA
apps/      programs and their hosts (Godot FPS, web/neon, SDL hosts)
spec/      axioms, tokens, token-budget, ai-convenience,
           runtime-semantics, native-runtime-protocol, vm
corpus/    LOVABench v3, golden/ (1033 conformance records), the
           fine-tune corpus, language_card.md (generated)
tools/     conformance, differential, golden, bench_native, lova_sugar
experiments/, journal/   numbered scripts and their entries
docs/      the portal (EN / 中文)
```

Python keeps the parser, macros, compiler, locator, examples, MCP and
CLI; Rust executes the compiled bytes. The two must agree on value,
anomaly, stdout **and the exact step count** on every golden record.

The game 东方天球谭 lives in `D:\SSH\touhou-tenkyuutan` (its own
repository since 2026-10-01) and uses this checkout through
`LOVA_HOME` / `LOVA_PATH`. Mentions of the danmaku in the journal are
history.

## How to run

```bash
export PYTHONPATH="$PWD"
python -m core.cli run apps/is_prime.lova 1999      # --native auto|on|off
python -m core.cli check FILE [--native] [--strength]
python -m core.cli analyze | emit --form stage2 | show | scope | callers
python -m core.cli profile PROG --init EXPR --step EXPR --ticks A..B
python -m core.cli repl | mcp
python -m pytest -q                                 # the suite
python tools/conformance.py                         # golden set, both runtimes
python tools/differential.py                        # VM against tree-walker
python -m corpus.make_card                          # regenerate the card
```

## Working here

- Create and edit files freely; run experiments without asking;
  install a package only when an experiment needs it.
- Commit and push when a batch is finished (the owner's standing
  preference); never rewrite pushed history.
- **Ask first:** deleting journal files or experiment results; any
  change to the six standing axioms; importing DNA OS v3 code.
- Verification of engine-core changes goes to a separate reviewer
  agent with a fixed checklist; the author does not review itself.
- No security, network-attack or sandbox-escape subjects in
  experiments or apps.

## Constraints

1. Nothing that cannot be said in the integer form; surface sugar
   must compile to the core and add no semantics.
2. No human-pleasing naming in the runtime; the substrate references
   by integer.
3. No PnL / reward / profit logic.
4. No mutable global state; every effect is typed and under a
   declared boundary.
5. No silent failures: every deviation is a structured anomaly.
6. A step count is contractual: an optimisation that changes it
   re-harvests the golden records and says so.
7. No forking of DNA OS v3 code.

## Journal conventions

Every experiment gets `journal/experiment_NN.md` (Hypothesis, Method,
Results, Findings, Discussion, Next questions, Status) and a row in
the journal's log; milestones and rulings go in `journal/README.md`,
newest first in its dated section.

- Honesty over optimism; a NULL result is load-bearing.
- Numbers in Results, meaning in Discussion.
- Every experiment raises a next question (`Qnn`, numbered on).
- One trajectory is a pilot; ten seeds or sessions before a finding
  carries weight.
- The README shows strengths; weaknesses live in the journal and the
  Q-list.

## Where the work stands (2026-11-28)

Done and holding: the language (M9-M32: recursion, data, text, lists,
records, tail calls, boundaries, examples, the locator), the native
runtime and VM (M33-M37, over ten million steps a second), embedding in Godot
and in a page (M39, M41), relation examples and strength (M40), the
step profiler and the flat session (2026-10-31).

Open, in the order the review of 2026-11-28 put them:

1. **Q153 / Q154** — the swarm family against a general form, and
   what a native walk is charged.
2. **The compiler front end in Rust** — the parse of a 3D library is
   1-2 s; MCP `lova_check` still builds per example; a page cannot
   edit its rules (Q146).
3. **Q135** (LOVA against GDScript on one host — `Fix`, Q140, waits
   on it), **Q142** (number 2 measured properly), and number 4's reuse
   and trace halves, which have no experiment.
4. The by-lineage-only families: the owner's decision.
5. Small and certain: Q138, Q139, Q143, Q145, Q107, Q147, Q155.

Suite: 1158 pass, 1 fails -- `tests/test_neon.py`'s page test, until
`native/lova-wasm` is rebuilt with the two new families (Q155).
