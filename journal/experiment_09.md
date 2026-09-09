# Experiment 09 — Body-scanning DeltaTrap (Q20)

**Date:** 2026-04-24
**Script:** `experiments/experiment_09_body_offender.py`
**Status:** Done (5 canonical + N=50 fuzz). **WIN.**

## Hypothesis

Prior state: `(conserve E B)` Δ-traps named the *outer CONSERVE* as
`offending_op`. Across every case the signal was identical —
uninformative. The repair hint was a boilerplate "replace the divergent
op"; the AI had to re-scan B itself to find the real fault.

Q20 hypothesis:

- **H1** The trap anomaly can be enriched with a `body_offender` field
  that pinpoints the deepest sub-expression of B whose single-node
  replacement closes the deviation.
- **H2** Two complementary probes cover the common shapes:
  - *Operator-swap* (Pass A): for each op subnode, replace the op with
    an entry from `suggest_alternatives` (VIOLATE → IDENTITY; same-
    family swaps). If any swap restores the invariant, the op is a
    clean "wrong operator" offender.
  - *Literal-replacement* (Pass B): for each non-LIT op subnode,
    substitute its subtree with `LIT_INT(value - deviation)`. If the
    modified body evaluates to E, that sub-expression is the offender.
- **H3** The emitted offender is enough for a closed AI loop:
  trap → anomaly → apply patch → re-evaluate → pass.

## Method

Added two helpers to `core/runtime.py`:

1. `_clone_with_replacement(node, path, new_node)` — deep-clone a tree
   with the subtree at `path` replaced.
2. `_scan_body_offender(body, expected, actual, env) → dict | None` —
   collects `(path, node, depth)` for every Node-typed sub-expression,
   evaluates each in an isolated `Runtime` (env-copied, fresh surprise /
   budget / node_stack), then in deepest-first order runs Pass A
   (op-swap) and Pass B (LIT-replacement). Non-root LIT_INT nodes are
   skipped in Pass B — replacing a literal is a band-aid, not a
   semantic offender. A heuristic fallback flags the deepest subnode
   whose own value equals the deviation.

CONSERVE handler in `_eval_body` calls the scanner before raising
`DeltaTrap`, stashing the result as `anomaly["body_offender"]`. Shape:

```
body_offender = {
  op:                int,                    # token of offending op
  op_name:           str,                    # e.g. "violate"
  path:              tuple[int, ...],        # indices from body root
  depth:             int,
  observed:          int,                    # op's output in situ
  needed:            int,                    # value that would close the trap
  correction:        int,                    # needed - observed
  fix:               "operator-swap"
                    | "literal-replacement"
                    | "heuristic-value-equals-deviation",
  alternative_op:    int  (only for operator-swap),
  alternative_op_name: str (only for operator-swap),
}
```

`_enrich_trap` was adjusted: when `body_offender` is set, the generic
"replace operator `conserve`" hint is suppressed in favour of a specific
hint naming the inner offender, and `valid_alternatives` is rewritten
to come from the inner op (not from CONSERVE).

Experiment script runs three demos:

- **Demo 1 — 5 canonical shapes.** Flat / nested / deep-chain / merge-
  only / bare-literal bodies.
- **Demo 2 — N=50 fuzz.** Random `(conserve N body)` where `body` is
  `(violate (merge a b))` or `(merge (violate a) b)` or `(merge a
  (violate b))`. Verdict: does the scanner identify VIOLATE as
  offender?
- **Demo 3 — closed-loop repair.** For each canonical case, take the
  offender's `needed` value, substitute at `path`, re-evaluate. Must
  return E without trapping.

## Results

### Demo 1 — canonical shapes (5/5 correct)

| program | deviation | offender | path | depth | fix | correction |
|---|---:|---|---|---:|---|---:|
| `(conserve 77 (violate 77))` | +1 | violate | `()` | 0 | operator-swap | −1 |
| `(conserve 10 (merge 7 4))` | +1 | merge | `()` | 0 | literal-replacement | −1 |
| `(conserve 10 (merge (violate 3) 4))` | −2 | violate | `(0,)` | 1 | operator-swap | +2 |
| `(conserve 5 (violate (violate 2)))` | −1 | violate | `(0,)` | 1 | literal-replacement | +1 |
| `(conserve 10 7)` | −3 | lit | `()` | 0 | literal-replacement | +3 |

### Demo 2 — fuzz precision

| metric | value |
|---|---:|
| seed | 42 |
| N | 50 |
| scanner pinpoints VIOLATE | **50 / 50 (100%)** |
| misses | 0 |

Pre-Pass-A (literal-only probe) scored 30/50 (60%) on the same fuzz —
the 20 misses were all `(conserve N (violate (merge a b)))` shapes
where the deeper MERGE's LIT-replacement fix edged out VIOLATE's op-
swap fix. Adding Pass A flips 20/20 of those to VIOLATE and preserves
all prior hits.

### Demo 3 — closed-loop repair (5/5 correct)

Every canonical case: `patched program evaluates to <expected>
(conservation holds)`. Zero residual traps.

## Findings

### F1. `body_offender` replaces the uninformative "outer CONSERVE" signal.

Before Q20 all Δ-traps had `offending_op == CONSERVE` — a constant
across every case. After Q20 the offender names a specific
sub-expression with `observed / needed / correction / fix` and, for
operator-swap fixes, an `alternative_op` pointer. This is the L2
schema's first non-uniform value for CONSERVE errors.

### F2. Two probes cover the shape space cleanly.

- Pass A (op-swap) catches "wrong operator" — chiefly VIOLATE whose
  suggested alt IDENTITY is semantically "do nothing".
- Pass B (LIT-replacement) catches "wrong value" — arithmetic errors
  where the op choice is fine but the produced value misses the
  contract.

Running A before B prefers the *semantically cleanest* fix when both
apply. Deepest-first within each pass gives minimal-scope fixes.

### F3. 100% closed-loop repair on canonical set.

Demo 3 shows the full AI cycle: receive anomaly → read
`body_offender.{path, needed}` → substitute → re-evaluate. Zero
custom parsing; zero human-formatted stack trace.

### F4. LIT_INT nodes are excluded from Pass B except at body root.

Replacing a non-root literal is always trivially possible
("just change the number") and almost never names the semantic
offender. The exclusion forces the scanner to flag the *operator* at
fault. Root-LIT_INT case is kept because a body that IS a bare literal
has nowhere else to point.

### F5. Cost negligible in practice.

O(n²) worst case where n = body node count. Typical LOVA bodies are
< 50 nodes (often < 10). The scanner only runs on Δ-trap, not on
every eval. Full experiment + 50-sample fuzz completes in under 50 ms.

## Discussion

**What this unlocks.** The original CONSERVE / DeltaTrap design was
honest that "something went wrong inside B" but gave the AI no help
localising it. Body-scanning closes that gap with a probe-based
approach that's trivially correct (by construction: "replacing S
makes the invariant hold") and uses no linguistic heuristics — just
the runtime's own semantics.

**Caveats.**

- The scan is *local*: it finds single-node fixes. A body with two
  simultaneous offenders (no single-node fix works) falls through to
  the heuristic. The heuristic is imperfect; future work (Q23?) is a
  pair-probe or a contribution-attribution scheme.
- Pass A's alternative set comes from `suggest_alternatives`, which
  currently hard-codes same-family swaps. Swaps across families (e.g.
  `MERGE → GCD` for a sum-vs-gcd confusion) are in the group; swaps
  outside (e.g. `VIOLATE → SIGMA`) are not. This is intentional —
  alternatives should be type-compatible, 1-edit changes the AI might
  plausibly have considered.
- Probe uses the *outer* env snapshot. If the body is under a LET
  whose binding depends on a mutable effect, the probe evaluates each
  subtree with the snapshot value; that's correct for pure code, and
  LOVA's current pure/effect boundary already forbids mutation in
  conserve bodies.

**Comparison to prior art.** Delta-debugging (Zeller) narrows failing
inputs by removal; our scan is narrower still — we have the
invariant's target value, so we can solve for *needed* at each node
rather than binary-searching. This is a case where LOVA's
conservation-as-type design lets the debugger be cheaper than the
general case.

## Next questions raised

→ **Q23**: Pair-probe for multi-offender bodies. When no single-node
fix exists, can we find the smallest pair `(S₁, S₂)` whose joint
replacement closes the deviation? Cost goes to O(n³) but bodies are
small; worth prototyping for the 2-offender case only.

→ **Q24**: Extend Pass A's alternative set using `valid_next` in
context (the TODO noted in `suggest_alternatives`). Would widen the
set of op-swap fixes without losing 1-edit-distance constraint.

→ **Q25**: Integrate `body_offender.{op, alternative_op}` into the
lineage of a repair mutation. If an AI patches a failing program via
the scanner's suggestion, the lineage should tag the mutation with
`mutation_kind="delta-repair"` and carry the `path + observed + needed`
as provenance.

## Status

**WIN.** Canonical set 5/5, fuzz 50/50, closed-loop repair 5/5. Q20
closed. `body_offender` is now the load-bearing Δ-trap signal; outer
`offending_op` retained for back-compat only. Two new fields expose
the fix *kind* (operator-swap vs literal-replacement vs heuristic),
so AI repair pipelines can pick their strategy explicitly.
