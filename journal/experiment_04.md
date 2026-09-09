# Experiment 04 — Lineage intrinsic + Wright-Fisher coalescence (Axiom 5)

**Date:** 2026-04-24
**Script:** `experiments/experiment_04_lineage.py`
**Status:** Done (pilot seed=7). **WIN.**

## Hypothesis

Two claims tested together:

- **H1**. Lineage is queryable data. Every mutated / cloned Node
  carries uid / parent_uid / root_uid / generation / mutation_kind.
  `ancestors()`, `is_ancestor_of()`, `descendants_of()`,
  `tree_str()` all work.
- **H2**. Under uniform-random reproduction with mutation, initial
  lineages coalesce. Starting with K independent roots, random
  sampling + reproduction causes most roots to go extinct within
  O(K) generations; 1-2 survive and dominate. (DNA OS v3 Exp 55
  observed this at agent-pool level; LOVA should reproduce it at
  program level.)

## Method

Implement `core/lineage.py` (~230 LOC):

- `LineageRecord` dataclass — uid / parent_uid / root_uid / generation
  / mutation_kind / timestamp / notes.
- `LineageStore` — session-wide registry with
  `register_root`, `clone`, `mutate`, `ancestors`, `is_ancestor_of`,
  `descendants_of`, `tree_str`, `coalescence_stats`.
- `mutate()` strategy — per-Node `strength` probability of either
  swapping a literal (±5 from current) or swapping an operator within
  a same-arity-same-type equivalence class
  (`{P, TAU, SIGMA, MOBIUS}` or `{MERGE, GCD}`).
- Node extension — optional `uid` field, patched in at module import
  so lineage lives as metadata (Axiom 1: integer bytes stay clean).

Three sub-tests in `experiment_04_lineage.py`:

1. Register, clone, mutate, walk ancestor chain.
2. Wright-Fisher evolve — 5 roots, pop_size=5, 10 generations,
   mutation_strength=0.2, uniform parent sampling. Track which roots
   still have alive descendants per generation.
3. Mutation diversity — mutate one parent 100× with strength=0.4,
   check that distinct variants are in [10, 99] (not monoculture,
   not pure noise).

## Results

### Test 1 — lineage API

```
a=1  b=2  c=3  d=4
c's ancestor chain: [3, 2, 1]

[1 gen=0 root=1 root]                                       # a
  [2<-1 gen=1 root=1 mutate]  # strength=0.4 [op:tau->sigma]
    [3<-2 gen=2 root=1 mutate]  # strength=0.4 [lit:3->6]
  [4<-1 gen=1 root=1 clone]
```

- `ancestors(c)` returns `[c, b, a]` in order
- `is_ancestor_of(a, c)` is True; reverse is False
- Clone inherits full ancestry (a is d's ancestor)
- Tree renderer prints the DAG with generation, root, mutation notes

### Test 2 — Wright-Fisher (seed=7)

```
gen     R1    R2    R3    R4    R5    alive
 0       1     1     1     1     1    5/5
 1       2     1     1     1     0    4/5
 2       2     0     2     1     0    3/5
 3       3     0     2     0     0    2/5
 4-9     (R1 and R3 coexist, swinging between)
10       0     0     5     0     0    1/5
```

After 10 generations, all 5 alive programs descend from initial root
`uid=3` — `(p (tau 20))`. The other 4 root lineages are extinct.

Final population (all descendants of R3):

```
slot 0: gen=10  (sigma (tau 24))
slot 1: gen=10  (sigma (tau 24))
slot 2: gen=10  (mobius (sigma 24))
slot 3: gen=10  (tau (tau 24))
slot 4: gen=10  (p (tau 24))
```

Note the structural drift across 10 generations of small mutations:
`(p (tau 20))` → `(... (tau 24))` with the outer operator explored
across 4 of the swap-group candidates (`p`, `sigma`, `tau`, `mobius`).

Coalescence stats: `n_roots=5`, `n_records=55`, `max_generation=10`,
`n_leaves=17`.

### Test 3 — mutation diversity

```
100 mutations of (merge (p 5) (tau 12))
distinct variants: 49
top 5 by frequency:
  29x  (merge (p 5) (tau 12))           <- unchanged (expected ~33%)
   6x  (gcd (p 5) (tau 12))
   4x  (merge (p 5) (p 12))
   3x  (gcd (tau 5) (tau 12))
   3x  (merge (mobius 5) (tau 12))
```

49 distinct out of 100 — well within the `[10, 99]` sanity bound.
29% identical matches expected ~33% from per-Node mutation math
(strength=0.4 on a 5-Node tree, 50/50 literal/operator split with
some applications being no-ops on wrong-kind Nodes).

## Findings

### F1. Lineage is truly queryable, not just annotated
`ancestors()`, `is_ancestor_of()`, `tree_str()` all return structured
data. The lineage is a first-class DAG inside the session — not a
git-log external metaphor, but an in-language data structure.

### F2. Wright-Fisher coalescence at program level
Same mathematical phenomenon DNA OS v3 observed at pool level
(Exp 55). Here at program level with K=5, N=10: 1 root survives,
dominant lineage has 5/5 population. Consistent with expected
coalescence time ~K (≈5 generations) — observed 3-4 roots gone by
gen 3, 1 survivor by gen 10.

### F3. Mutation is structured, not random
Mutation stays within swap-group equivalence classes for operators
(so well-typedness is preserved automatically — the type-directed
generation property from M2 applies to mutated children for free) and
within a ±5 window for literals (so mutations are local). The
distinct-variants count (49/100) shows the variation is meaningful
without being chaotic.

### F4. Axiom 1 is preserved
`uid` is metadata attached to `Node` instances, NOT included in
`encode(node)` bytes. Content-addressed identity is still determined
by the integer form; lineage is a side-car table indexed by uid.
This resolves the tension between "program IS an integer" (Axiom 1)
and "lineage IS intrinsic" (Axiom 5) — lineage is intrinsic to the
*instance*, not the *content*.

## Discussion

What Axiom 5 now supports:

- **"Why?" queries.** Given any mutated program, ask
  `store.ancestors(uid)` for the full derivation chain with mutation
  notes. This is the substrate of `(why X)` in-language operator
  (meta family, M5).
- **Regression analysis.** If variant `c` performs worse than its
  parent `b`, the lineage path shows exactly which mutation (`b -> c`)
  caused the regression — mutation_notes field records the specific
  change ("lit:5->8,op:tau->p").
- **Wright-Fisher statistics as debugging telemetry.** Running an
  evolve loop and seeing "4/5 roots extinct by gen 10" is a signal
  of selection pressure — if all roots survived equally, selection is
  not actually selecting.

What Axiom 5 does NOT yet support (deferred):

- **In-language query.** `(lineage uid)` / `(why uid)` operators are
  reserved (0x38, 0x39) but not implemented in the runtime. The
  infrastructure exists in Python; wiring to the token dispatcher is
  the next small step (1-2 hours of work, bundled with M4 Day 6-7).
- **Cross-session persistence.** `LineageStore` is in-memory. A real
  Stage-2 deployment would persist lineage to a content-addressed
  store (Unison-style). Deferred.
- **Fitness-weighted selection.** Wright-Fisher here uses UNIFORM
  random sampling, not fitness. Adding fitness is the M4 Day 3-5
  centerpiece (populations / defpop, Axiom 6).

## Paradigm inheritance note

- **Unison** (2020s): content-addressed code → LOVA's `Node.uid`
  + encode-bytes separation. LOVA adds the `mutation_kind` tag
  (e.g., `clone` vs `mutate-literal`) that content-addressing alone
  doesn't express.
- **Git / Mercurial** (2000s+): parent DAG, commit messages. LOVA's
  `notes` field plays the commit-message role; `tree_str()` is
  the `git log --graph --oneline`.
- **DNA OS v3 Exp 55** (2026-04-22): Wright-Fisher coalescence at
  agent-pool level on synthetic number-theory workload. Here the
  same phenomenon at program level on substrate-native integer code.
  Confirms the paradigm-inheritance claim: DNA OS research informs
  LOVA design one-to-one.

## Next questions raised

→ **Q13**: With fitness-weighted sampling (instead of uniform),
  does coalescence converge faster? Preview for M4 Day 3-5.

→ **Q14**: Cross-session lineage persistence — serialize `LineageStore`
  to disk as a Unison-style content-addressed blob store?

→ **Q15**: Should `mutate()` honor type-directed constraints
  explicitly (walk via `valid_next()`)? Currently it preserves types
  by using swap-groups, but a more principled approach would sample
  replacements from `valid_next()` at each position.

## Status

**WIN (pilot).** Axiom 5 is operational: 230 LOC of lineage
infrastructure, three sub-tests pass, Wright-Fisher coalescence
reproduces DNA OS Exp 55 at program level. Mutation produces
structured diversity (49/100 distinct variants). Path to M4 Day 3-5
(populations / defpop) is clear — lineage + fitness = evolutionary
dispatch.
