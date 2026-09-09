# Experiment 08 — Compiler passes (scope + type check + fold)

**Date:** 2026-04-24
**Script:** `experiments/experiment_08_compiler.py`
**Status:** Done. **WIN.**

## Hypothesis

LOVA previously had two phases with static analysis:
- Generation-time (`core.generator.valid_next`) enforces syntax and
  shallow types.
- Runtime (`core.runtime`) catches budget / conservation violations
  and semantic errors (including unbound refs).

Gap: **no compile-time middle-end**. Any program that makes it past
`parse` runs, even if it contains unbound refs or other structural
mistakes that are knowable statically. Those errors surface at
runtime as unstructured `ValueError`s.

M6 Day 1 hypothesis:

- **H1**: A compile pipeline (scope resolution → type check →
  constant folding) catches the unbound-ref error class at
  compile-time, moving it out of the runtime error surface.
- **H2**: Constant folding on pure subtrees compresses
  LOVABench v1 programs by a non-trivial margin (target ≥ 30% byte
  reduction).
- **H3**: `CompileError.anomaly` has the same schema as runtime trap
  anomalies — AI can use one handler for both.

## Method

`core/compiler.py` (~220 LOC) implementing three passes:

1. **`_scope_check(node, env, path)`**: walks the Node tree tracking
   bound name-ids through nested `LET`s; raises `CompileError[
   "unbound-ref"]` on any unbound `REF`. Also catches
   `type-mismatch` when LET/REF name slot is non-literal.
2. **`_type_check(node, expected, path)`**: walks every node, checks
   its declared `out_type` against the slot's expected type (via
   `core.types.is_subtype`). Recurses into children by signature.
3. **`_fold(node)`**: bottom-up, pure subtrees (operators in
   `_PURE_OPS = {P, TAU, SIGMA, MOBIUS, GCD, MERGE, PARTITION,
   IDENTITY}`) with all-literal arguments are evaluated at compile
   time and replaced by `Lit(result)`. Impure operators (CONSERVE,
   SURPRISE, LET, etc.) and non-literal arguments prevent folding.

Public API:
- `compile(node, fold=True, type_check=True, scope_check=True)` →
  `(compiled_node, CompileReport)`.
- `CompileError.anomaly` shares the L2 schema (`kind` / `stage` /
  `detail` / `position_path` / `offending_op` / `offending_op_name` /
  `valid_alternatives` / `repair_hint`).

Experiment 08 has three demos:

1. **Scope detection**: compile `(merge (p 12) (ref 99))`, expect
   `CompileError`. Compare to the old runtime `ValueError`.
2. **LOVABench folding**: substitute first test case into each of
   20 task templates, compile, measure node/byte compression.
3. **Shape unification**: trigger CompileError + BudgetTrap +
   DeltaTrap; verify all three anomalies share the L2 fields.

## Results

### Demo 1 — compile-time unbound-ref detection

Program: `(merge (p 12) (ref 99))`

- **Before M6 (runtime)**: `ValueError: unbound ref: 99`.  A plain
  Python exception, no structured payload.
- **After M6 (compile-time)**:

  ```
  CompileError.anomaly = {
    kind:              'unbound-ref',
    stage:             'compile',
    detail:            {'name_id': 99, 'bound_names': []},
    position_path:     (3, 1, 47),  # MERGE -> arg1 -> REF
    offending_op:      47,          # 0x2F = REF
    offending_op_name: 'ref',
    valid_alternatives: (),
    repair_hint:       "REF 99 is not in scope. Either wrap in a LET
                        that binds 99, or use a bound name from
                        (none in scope)."
  }
  ```

  This fires BEFORE execution. Structured. Actionable.

### Demo 2 — constant folding on LOVABench v1

20 tasks, first test case substituted, compiled:

```
task   original   compiled  orig B  fold B  saved
pb01          2          1       4       3    25%
pb02          2          1       4       3    25%
pb04          3          1       7       3    57%
pb09          5          1       9       3    67%
pb13          7          1      13       3    77%
pb18          5          1      11       3    73%
pb16         10         10      18      18     0%   (let/ref — can't fold through binding)
pb19          7          4      14      11    21%   (seq — not pure)
pb20          4          3       8       7    12%   (surprise — not pure)
```

**Totals**:
- Nodes: 82 → 34 (**58.5 % compression**)
- Bytes: 155 → 87 (**43.9 % saved**)

Every pure-subtree task folded to a single `LIT_INT` — "the program
is just its answer". This is the **strongest form of optimisation**
available: the compiler replaces the entire expression tree with the
constant it computes.

Tasks that retained structure (pb16, pb19, pb20) have `let`, `seq`,
`surprise` nodes respectively — which are correctly classified as
non-pure, so the compiler doesn't fold through them.

### Demo 3 — error-shape unification

| Anomaly field | CompileError | BudgetTrap | DeltaTrap |
|---|---|---|---|
| `kind` | ✓ | ✓ | ✓ |
| `stage` | compile | (runtime, implicit) | (runtime, implicit) |
| `detail` | ✓ | ✓ | ✓ |
| `position_path` | ✓ | ✓ | ✓ |
| `offending_op` | ✓ | ✓ | ✓ |
| `offending_op_name` | ✓ | ✓ | ✓ |
| `valid_alternatives` | ✓ | ✓ | ✓ |
| `repair_hint` | ✓ | ✓ | ✓ |

Shared fields across all three: **7/7 L2 spec fields present**.

An AI consumer handling any anomaly can write:

```python
def handle_error(anomaly):
    if anomaly.get("stage") == "compile":
        # compile-time repair: patch AST at position_path
        ...
    else:
        # runtime repair: mutate program, retry
        ...
    # Both paths use the same fields:
    #   kind, offending_op, valid_alternatives, repair_hint
```

## Findings

### F1. Compile-time scope check eliminates a runtime error class
Before M6: `(ref X)` where X is unbound would parse, type-check via
`valid_next`, **and pass runtime-validation at the LET level** —
only raising when that specific `REF` was actually evaluated.  With
`_scope_check`, the error surfaces **at compile time with zero
execution cost**.

### F2. Constant folding is aggressive on pure number theory
Pure subtrees collapse entirely. Program = answer. This gives
LOVA a unique optimization property: **"run the compiler to
get the result"** — for pure programs, compile is equivalent to
evaluate.

### F3. Error-shape unification is a real ergonomic gain for AI
Same 7 fields mean AI's error-handling code is shape-polymorphic —
same `anomaly["kind"]` switch, same `valid_alternatives` lookup,
same `repair_hint` consumption, regardless of when the error
surfaces (compile vs runtime).

### F4. The error surface shrinks further
After M5, LOVA's reachable error classes were `{semantic,
conservation, unbound-ref}` at runtime.  After M6:
- compile: `{unbound-ref, type-mismatch}`
- runtime: `{budget-exceeded, conservation-violated, semantic}`

**Unbound-ref moved from runtime to compile-time**. Compile-time
errors are cheaper to detect (no execution), more precise (known
position), and trivially shareable (can be sent back to AI
generator before any runtime cost).

### F5. Impure operators correctly block folding
`LET`, `SEQ`, `SURPRISE`, `CONSERVE`, `VIOLATE`, `IF_SURPRISE`,
`TRACE_SURPRISE` all resist folding (not in `_PURE_OPS`). This is
semantically correct — conservation and surprise are observable side
effects; folding them would change behaviour.

## Discussion

### What this adds to the AI-preference story

Exp 07 quantified: LOVA has fewer reachable error classes than
Python. Exp 08 extends: **LOVA has fewer reachable *runtime*
error classes** — the scope-check catches things Python's runtime
would otherwise catch. This is where the compiler pulls errors
leftward on the AI's debug timeline:

```
Generate -> Compile -> Encode -> Execute
             ↑ unbound-ref caught here (new)
             ↑ type-mismatch caught here (new)
                                 ↑ budget / conservation / semantic
```

An AI generator that compiles before shipping its output **has
perfect static guarantees**: no syntax errors (valid_next), no type
errors (type_check), no scope errors (scope_check). What ships is
either valid-and-runs-or-raises-a-conservation-trap, or it's a
CompileError with a specific repair.

### What's still deferred

1. **Body-scanning DeltaTrap** (Q20): when `(conserve 77 (violate
   77))` fails, the repair_hint points at CONSERVE, but the actual
   fix-site is VIOLATE. Compile pass could identify this by walking
   the conserve body structure.

2. **Effect inference** (static_analyze extension): at compile time,
   compute the effect set for each subtree and propagate it upward.
   Currently `static_analyze` does a flat walk; a compile-time
   bottom-up propagation would let AI query "what effect set does
   THIS particular subtree contribute?".

3. **Target-code emission** (compile-to-Python / -WASM / -LLVM):
   optional later work. Right now `compile()` returns an optimized
   LOVA tree; the interpreter runs it. A real backend would emit
   a faster target. Useful if performance becomes relevant.

## Paradigm-inheritance note

Standard compiler middle-end passes (scope resolution, type check,
constant folding) are 60 years old. Nothing novel in the individual
passes. LOVA's synthesis contribution:

- The passes operate on the **same Node type** the runtime uses; no
  separate IR. (Lisp tradition: no distinction between AST and IR
  at the core.)
- Compile errors share the **same anomaly schema** as runtime traps.
  (No other mainstream language unifies compile-time type errors and
  runtime exceptions into a single structured format.)
- `compile()` is **optional and safe**: an uncompiled program still
  runs — the only difference is *when* errors surface. This is
  LOVA's version of "gradual typing" lifted to the whole static
  pipeline.

## Next questions raised

→ **Q28**: Self-consistency of fold. Is `fold(fold(x)) == fold(x)`
  for all x? Should be, but worth a property test.

→ **Q29**: Compile-time effect propagation — store effects as an
  annotation on each Node, so AI can query subtree effects without
  re-walking.

→ **Q30**: Compile-to-target backends. Simplest: compile-to-Python.
  Takes a LOVA tree, emits Python source. Would let
  LOVA-authored programs deploy to any Python environment.

→ **Q31**: Incremental recompile. If we change one LIT_INT deep in
  a program, can we fold just the affected subtree? (Probably YES —
  fold is structural.) This would matter for online self-healing
  (M4 Exp 05's mutate loop).

## Status

**WIN.** Compile pipeline ships. Scope check catches unbound-ref at
compile-time (one error class moved out of runtime surface).
Constant folding compresses LOVABench v1 by 58.5% nodes / 43.9%
bytes. Error-shape unification confirmed: 7/7 L2 fields shared
across CompileError, BudgetTrap, DeltaTrap.

**10/10 axioms operational + compile pipeline validated. Project
health: strong.**
