# The bytecode VM (Q128) -- the native runtime's second evaluator

**Status:** specification, 2026-09-19. Owner's ruling: "按照你的建议来，
每个能改进速度的地方都考虑进去" -- build the compiled evaluator, and
take every speed-up that keeps the language the same.

**What it is.** `native/lova-rt` evaluates a program by walking its
tree node by node, reproducing `core/runtime.py`'s accounting one node
at a time (M33, M34). That is 4-8 million steps a second: a frame of
the FPS port is 130 000-160 000 steps and costs 30 ms, so the window
runs at 20 frames a second. The VM is a second evaluator in the same
crate: the tree is **compiled once** to a flat instruction stream with
variables resolved to slots, frames on a stack where nothing captures
them, and step charges batched where nothing can trap between them.
The tree-walker stays as the reference; the VM must be
indistinguishable from it through every interface the harness and the
drivers use.

**What it is not.** Not a new language, not a new semantics, not a
change to any step count. The golden set (`corpus/golden/`, 1023
records) and `tools/conformance.py` are the definition of "the same";
`spec/runtime-semantics.md` is the contract this document refines and
must not contradict. Where this document and that one disagree, that
one wins and this one is wrong.

## 0. The non-negotiables

Through `run`, `session`, `get`, `call` (`spec/native-runtime-protocol.md`)
the VM produces, for every program and every input:

1. **The same value**, printed by the same `format_value`.
2. **The same `steps`**, exactly, including on a trap.
3. **The same anomaly**: `kind`, `offending_op`, `position_path`,
   `position_nodes`, every `detail` key the harness compares
   (`operator`, `limit`, `expected`, `code`, `name_id`), `detail.calls`
   (the `hot` table: the same eight rows in the same order), the same
   `stdout` up to the trap.
4. **The same `hot` attribution** -- `own` steps and `calls` per named
   closure, settled at the same moments (§4.5 of the semantics).
5. **The same budget behaviour** -- Rule-1 nodes charge
   `budget_stack[-1]`, Rule-2 charges do not (quirk 21), an inner
   budget shields the outer (22), the trap is raised at the node that
   crossed.
6. **The same environment semantics** -- lexical scoping, letrec and
   binding groups by the `let` chain rule (§4.3), shadowing breaking
   the chain, `bound_names` on `unbound-ref` listing every visible
   name id, `eval` running a program value in the caller's
   environment, `trace` and the `conserve` probe seeing a flattened
   copy.
7. **Every quirk in §8** of the semantics, kept.
8. **The same surprise trace, lineage store, PRNG stream, stdout /
   stdin behaviour, capability checks** -- the VM reuses the
   tree-walker's implementations of every operator's *work*
   (`value.rs`, `text.rs`, `nt.rs`, `conserve.rs`, `evolve.rs`,
   `meta.rs`, `lineage.rs`, `rng.rs`); only *evaluation* is new.

The tree-walker is not deleted. It remains selectable (`--tree` on the
binary, `LOVA_RT_EVAL=tree` in the environment) as the reference, and
the differential harness below runs both.

## 1. Architecture

```
bytes ──decode──> Arena (nodes)            unchanged (tokens.rs)
             ──compile──> Unit per lambda body + one for the program
                          (vm/compile.rs)
Rt ──────────────────────> the same Rt: steps, budget stack, hot,
                          lineage, output, caps ...  (rt.rs)
Unit + Rt ──execute────> vm/exec.rs: the dispatch loop
traps ──────────────────> the same Anomaly (trap.rs), position_path
                          DERIVED from pc + frames (vm/path.rs)
```

* **A `Unit`** is the compiled form of one lambda body (or the
  program's root, or a `trace` body, or an `eval`ed program): an
  instruction vector, a constant pool, a **frame layout** (which names
  live in which slots), a **node table** (instruction index -> arena
  node id, for `position_path` / `position_nodes`), and the static
  parent chain of every node in the unit.
* **Compilation is eager** (as built; the first draft said lazy):
  every unit of a program is compiled at `run` / `session` before
  evaluation starts, because the analysis -- which units are captured
  and so live on the heap, and the depth of every load -- is
  whole-program. A `session` compiles once for its life; a `run` of a
  large program pays a few milliseconds (§8.1). Lazy *emission* per
  unit is a possible later saving, measured at under 5% (§8.1).
* **The program's root unit** is compiled at `run` / `session` before
  evaluation starts; a compile error (only malformed trees can
  produce one: a non-literal `let` name slot, etc.) is **not** raised
  at compile time -- it is compiled into an instruction that raises
  the tree-walker's exact `malformed` anomaly when reached, because
  the tree-walker only raises it when the node is evaluated.

## 2. Frames and variables

### 2.1 Slots

Every `ref` whose binding can be found lexically at compile time is
compiled to `Load(depth, slot)`: `depth` frames up the *lexical* chain
(0 = this unit's frame), `slot` the name's index in that frame's
layout. What is lexical:

* the unit's own parameter (slot 0 of a lambda body's frame);
* every `let` in the unit that, by the chain rule of §4.3, writes
  into the frame the unit is running in -- the "extend" case: a `let`
  that is the body of a `let` (chained), with the enclosing frame a
  real frame and the name **not already bound anywhere up the chain**;
  all three conditions are decidable at compile time because the
  chain is the lexical chain (the root environment is the plain dict,
  which binds nothing -- `Runtime.env` starts empty and nothing in the
  language writes to it; a host that pre-binds names is outside the
  golden set and gets the dynamic fallback of §2.4);
* every `let` that opens a fresh frame (not chained, or shadowing):
  the fresh frame is **also a slot region of the same activation** --
  the semantics of a fresh frame differ from an extended one only in
  what a name resolves to, which slot assignment already encodes:
  the shadowing binding is a new slot, and a closure made before it
  still refers to the old slot. (Rationale: a Python `Scope` object is
  observable only through resolution, `bound_names`, and
  `flatten_env`; all three are reproduced from the layout.)
* names of enclosing units, through the captured chain.

### 2.2 Heap frames and stack frames

A unit's frame lives **on the VM stack** unless something can hold a
reference to it after the activation returns. That happens iff a
`lambda` node lexically inside the unit refers (at any depth of
nesting) to a slot of this unit -- decided by the compiler, per unit.
Such a frame is heap-allocated: `Rc<Frame>` with slots the closure
can read *after* they are written (letrec: the closure is created,
then the binding is written -- so slots are interior-mutable;
`RefCell<Vec<Value>>` or an `UnsafeCell` behind a safe API, the
implementer's choice, with the invariant that a slot is written at
most once per activation... except loop bodies, which re-enter the
unit and get a fresh frame each iteration, as Python gets a fresh
`Scope` per call).

A closure value captures `Rc<Frame>` of the defining activation (and,
transitively, the chain), `caps`, `enclosed`, the `owner` for `hot`,
and its unit. A `Load(depth, slot)` with `depth > 0` walks `depth`
captured frames -- it never walks by name.

A unit whose frame is on the stack and whose body makes no call can
keep its slots in registers of the dispatch loop; the implementer may
add a register-window design, but the spec only requires the two
tiers.

### 2.3 The `let` chain, compiled

For a `let` node the compiler decides `extend` as §4.3 does, with the
lexical chain standing in for the runtime chain:

* `chained` iff this `let` node is the *body* child of a `let` node
  (static).
* `saved_env is Scope` iff we are not at the root: the first `let`
  under the program root, and the first `let` in a lambda body whose
  enclosing environment is the root dict, opens a frame. Since the
  root dict binds nothing, this only affects the frame *identity*,
  never resolution -- the compiler treats it as "open a region".
* `not saved_env.bound(name)` iff no enclosing region or unit in the
  lexical chain has bound `name` yet **at this point in the chain**
  (a later `let` in the same group does not count: bindings are
  written in order).

The value is compiled with the slot already allocated (so a `lambda`
in the value slot captures the frame and resolves the name to that
slot: letrec); the `Store(slot)` instruction follows the value; then
the body. The **naming of closures** (`value is a Closure and
value.name is None -> value.name = name_id; rt.named.append`) is done
by `Store` at runtime exactly as `_n_let` does, since it depends on
the value.

### 2.4 The dynamic fallback

Three things evaluate code whose environment is not the lexical chain
of a compilation unit:

* `eval` of a program value runs it **in the caller's environment**
  (§5.6). Its `ref`s name bindings of the *caller*, which the value's
  tree cannot know. The compiler compiles such a unit with every
  unresolved `ref` as `LoadDyn(name_id)`: walk the current
  activation's frame chain **by name**, which every frame can answer
  because its layout carries the names (slot -> name id). The root
  env is walked last. An unbound name raises `unbound-ref` with
  `bound_names` = every name in the chain (deduplicated, sorted),
  which is `flatten_env`'s key set.
* `trace` (§5.8) runs its body in a sandbox `Rt` on the remaining
  ceilings with a **flattened** environment: compile the body as a
  unit whose outer chain is one synthetic frame holding the flattened
  bindings (inner frames winning), in insertion order of
  `flatten_env` -- the order is observable only through `bound_names`,
  which is sorted, so any order will do.
* the `conserve` body probe (`_scan_body_offender`, `conserve.rs`)
  re-evaluates subtrees with a fresh runtime and a flattened env: the
  same synthetic-frame device. The probe runs on the tree-walker if
  that is simpler -- it is not on any hot path and its steps are not
  charged to the run (check `conserve.rs`: the probe uses its own
  `Rt`).

`LoadDyn` must also serve a `ref` inside the main program whose name
is bound by **no** lexical binder (the unbound-ref error path): the
compiler emits `LoadDyn` so that the runtime raises the exact
`unbound-ref` anomaly with the exact `bound_names`.

**The live set (review of 2026-09-19, F1).** A region's slots stay
physically written after the region closes when a closure captured
the frame -- the closure must keep reading them -- but the reference
pops the `Scope` at that point, so to the caller, and to anything the
caller delegates (`eval`, `conserve`, `trace`, the Meta and Evolution
families), those names **no longer exist**. The flattened environment
a delegated subtree receives, and the `bound_names` an `unbound-ref`
reports, are therefore built from the **lexically live** bindings at
that point -- the compiler hands each `Delegate` (and each by-name
load) the set of slots in scope there -- and from what is actually
*written*, never from the compiler's visibility list alone (which
admits a binder still pending in its own group). The first build
conflated the two: `(let yy 5 (seq (let yy 1 (lambda q yy)) (conserve
10 (merge yy yy))))` passed on the reference and trapped on the VM.

## 3. Calls

`Call` reproduces `_call` (§4.1) instruction for instruction:

* `LoopFn` values iterate inside `Call` with the `+1` per round
  charged to `steps` (not the budget), checked against `max_steps`
  inline, then the predicate, then the step.
* a non-callable head raises `_not_callable`'s anomaly.
* **hot**: `calls += 1` on a named closure; `me = fn or fn.owner`;
  if `me is not rt.current`: settle `outer.own += steps - mark`,
  `mark = steps`, `current = me` -- and the mirror in the epilogue.
  This is one pointer comparison per call in the common
  self-recursive case; keep it that cheap.
* **depth**: `call_depth += 1; if > max: raise DepthTrap` (with the
  decrement-before-raise quirk).
* a **frame** per activation: stack or heap by §2.2; `caps` and
  `enclosed` from the closure (lexical boundaries).
* `TailCall`: a unit compiled in tail position ends in `TailApply`
  which, instead of pushing a frame, **replaces** the current one
  (pops it and re-enters `Call` with the new closure and argument),
  exactly where `_code_tail` passes tail position (lambda body,
  both `if` branches, the last of `seq`, the body of `let`; nothing
  else). `(apply f)` with no arguments is not a tail call.
* a call charges **no step**.

Multi-argument `apply` is curried: `(apply f a b)` is
`Call(Call(f, a), b)`; in tail position the last application is the
tail one and the earlier ones are ordinary (§4.4).

## 4. Steps, batched but exact

Rule 1: one step per evaluated node, pre-order, before the node's
work, charged to `budget_stack[-1]` if any, then `steps += 1`, then
the ceiling check. The VM keeps the *observable* behaviour while
paying for it once per **run** of nodes:

* The compiler partitions each unit into **straight-line node
  sequences**: maximal runs of nodes evaluated in a fixed pre-order
  with **no call, no branch, no loop, no budget push/pop and no
  operator that can trap** between them... except that any operator
  can trap (`div` by zero, a type fault), so the rule is instead:
  a run is a sequence of nodes `n_1..n_k` such that if evaluation
  reaches `n_1`'s tick it will reach `n_k`'s tick **unless a trap
  occurs in between**, and the run's ticks are all charged **at the
  start**, with the number of steps that would have been charged
  by the time of any trap recoverable.
* Concretely `Tick(k)` at the head of a run charges `k` to the budget
  and `steps`. If the budget or the step ceiling is crossed during
  the batch, the trap's node is `n_j` with `j = limit_remaining + 1`
  (the first node whose tick would have crossed), and `steps` /
  `spent` are set to the value they would have had **at that node's
  tick** -- i.e. `steps_before + j`, not `steps_before + k`. The
  `position_path` is derived for `n_j` (§6).
* If an operator in the run traps for its own reason (a `DomainTrap`
  at `n_j`), `steps` must read `steps_before + j` -- the nodes after
  `n_j` were never evaluated. So a run charges eagerly but the VM
  records `steps_before` and the run's node list, and **on any trap
  inside a run it rewinds `steps` (and the budget's `spent`) to the
  trapping node's own count** before enriching. This is the one place
  the VM does bookkeeping the tree-walker does not, and it is only on
  the trap path.
* A run never crosses: a `Call` (the callee's ticks are its own and
  `hot` settles at the boundary), an `if` (only one branch runs), a
  `LoopFn` round, a `budget` push or pop (the charge target changes),
  a `when-anomaly` (a caught trap resumes *after* the handler, and the
  nodes after the caught one in the same run must not have been
  charged -- so a `when-anomaly` body starts a new run and the
  when-anomaly instruction itself rewinds on catch), `trace`
  (separate `Rt`), `eval` (dynamic code), `seq` children are fine
  (straight line), `let` value and body are fine (straight line).
* Rule-2 extras stay where they are: per element in the list family,
  per round in loops, per match in `text-match-all`, `trace`'s
  import -- charged to `steps` only, never the budget, checked
  against the ceiling as the semantics say (`trace`'s not checked).

`hot`'s `own` is `steps - mark` differences; batching does not move
steps across a `Call` boundary, so the intervals are unchanged.

### 4.1 Amended at implementation (2026-09-19)

The rule above is unsound as written: an operator earlier in a run can
trap for its own reason (`(merge (div 1 0) (foo))`) before the node
the eager charge would trap at ever ticks, and an eager batch would
raise `step-limit-exceeded` where the reference raises the
`domain-error`. The implementation therefore **batches a run only when
the whole run fits under both the step ceiling and the innermost
budget**, and otherwise charges node by node; the rewind on a fault
inside a fitted batch stands. The semantics spec wins; this is the
half of the rule the first draft got wrong.

Also decided there: `eval`, `conserve`, `trace`, the Evolution and
Meta families and the out-of-scope operators are **delegated to the
tree-walker** over a `Scope` flattened from the VM's frames, rather
than compiled as §2.4's dynamic units -- the same values, steps,
anomalies and `bound_names` by construction, and no second
implementation of `eval`'s scoping, the probe or the sandbox. The
cost, a program using them runs those subtrees at tree-walker speed
and keeps its frames on the heap, is accepted.

## 5. Values

* `Value` stays the crate's enum (`value.rs`); the `Int` fast path
  (`i64` with checked ops, promotion on overflow) is already there.
* **Constant pool**: every literal node's value is built once at
  compile time. A `LIT_TEXT` constant that is used as a map key
  (`map-get` / `map-put` / `get` / `put` on a record) carries its
  **precomputed key hash**, so `(get w p)` does not hash `"p"` per
  access. The map's own hashing must produce the same value for the
  cached hash (it is the same function, run early).
* **Superinstructions** the compiler may emit when the shape matches,
  each semantically identical to the node sequence it replaces and
  charged the same ticks: `(get REC "field")` -> `GetField(slot,
  const)`; `(put REC "field" v)`; `(merge Load Load)` /
  `(sub Load Load)` / `(mul Load Load)` / comparisons on two loads or a
  load and a constant -> one instruction with the int fast path and
  the bignum fallback; `(if (COMPARE a b) x y)` -> a compare-and-branch;
  `(nth xs k)` on a small `k`; `(mod x 2)` and `(div x 2)` by a
  constant. Each is optional; each must keep the ticks (§4) and the
  `position_path` derivation (§6) for every node it covers.
* `Cons` lists and the persistent map are unchanged. `list_to_python`
  shape, `format_value`, `map-pairs` order -- unchanged.

## 6. `position_path` and `position_nodes`, derived

The tree-walker pushes and pops a `(op, node)` pair on **every node**
(D8). The VM pushes nothing per node. On a trap it reconstructs the
path:

* every unit's node table gives, for the trapping instruction, the
  arena node `n`;
* the unit's **static ancestor chain** gives the nodes from the unit's
  root to `n` -- and that is exactly the set of nodes "being
  evaluated" in that activation, because within one activation the
  nodes on the Python stack are the static ancestors of the node in
  hand (a parent's `_n_*` frame is live while a child evaluates);
* each activation on the VM's frame stack contributes its chain, from
  the outermost activation inward, with the **call site** (the `apply`
  node -- or the list-family / `loop-until` / `evolve` node that made
  the call) being the last node of the caller's chain: it is an
  ancestor of nothing in the callee, but it is on the Python stack,
  so it is in the path -- the frame records the node that made the
  call;
* a **tail call replaced its frame**, so the replaced activation
  contributes nothing (D8: "a tail call pops the frame it replaces");
* literals are excluded... **no**: quirk 15 says the port's explicit
  stack must exclude literals *because Python's `_node_path` only sees
  frames with a `node` local, and literals have none* -- the trap can
  never be raised *at* a literal except the step ceiling, and there
  the tree-walker reports the path up to the enclosing non-literal
  (§3.2: `(merge 1 1)` with `max_steps=2` reports `(3,)`). The VM
  reproduces this by trimming a trailing literal from the derived
  chain. The golden `traps` group has the cases.
* `position_nodes` is the same chain as preorder ordinals (`null` for
  nodes not from the program's bytes: an `eval`ed / `trace`d program
  value's nodes, a conserve probe's rewrite).
* `detail.calls` (`hot`) is `_cost_by_function` over `rt.named`,
  unchanged.

The derivation must be checked against the tree-walker on **every
trap record** of the golden set and on the differential run (§8),
because it is the part most likely to be subtly wrong.

## 7. What may be made faster, and what may not

**May (and should):**

1. Frames on the stack when nothing captures them (§2.2); a frame
   pool for heap frames (already there for `Scope`).
2. Slot loads instead of name lookups (§2.1); `LoadDyn` only where
   §2.4 requires.
3. Tick batching (§4); no per-node path push (§6).
4. Constant pool, pre-hashed keys, superinstructions (§5).
5. Threaded / match-based dispatch, compact instruction encoding,
   `#[inline]` on the hot handlers, no `Rc` clone on a `Load` that is
   immediately consumed (move semantics where the slot is dead --
   the compiler knows the last use of a slot in straight-line code).
6. The `hot` bookkeeping as one pointer compare per call.
7. Anything else that the golden set and the differential run
   cannot see.

**May not:**

1. Change any count in §3 of the semantics -- not `sort-by`'s
   Timsort comparison count, not `range`'s pre-charge, not the
   prelude's 80.
2. Skip evaluating a node the tree-walker evaluates (no dead-code
   elimination of a node that ticks: an unused `let` value still
   costs its steps; an argument to a function that ignores it is
   still evaluated). Constant folding is the Python compiler's job
   and has already happened in the bytes.
3. Reorder evaluation (children left to right, `apply` head then
   arguments, `let` value then body, `sort-by`'s `(less a b)` then
   `(less b a)`).
4. Change what a closure captures or when a binding becomes visible.
5. Change `format_value`, the map's order, the PRNG, `hash`,
   `explain`'s text (`explain` stays unsupported anyway).
6. Drop the tree-walker before the VM has been the default through
   at least one milestone with the differential harness green.

## 8. Verification -- the gates, in order

1. `cargo test --release`: unit tests for the compiler (slot
   resolution on the §4.3 cases: letrec, mutual recursion, shadowing
   breaking the chain, a fresh frame in an argument position), for
   tick batching (a trap inside a run reports the right `steps`), and
   for path derivation (the `traps` group's expectations as unit
   tests).
2. `python tools/conformance.py --runtime <binary>` with the VM as
   default: **989 + the clock record, the same 29 out of scope**, the
   failure list byte-identical to the tree-walker's.
3. **The differential run**: `tools/differential.py` (new, stdlib):
   every `.lova` under `apps/`, `lib/` (through `tools/bench/*.lova`
   and the drivers' `SOURCE` strings), `corpus/`, `tests/` fixtures,
   plus 2 000 generated programs from `core.generator.constrained_random`
   with the prelude, each run through the binary **twice** (`--tree`
   and the VM) with `max_steps` set low enough that half of them trap,
   comparing value, steps, stdout, anomaly (all fields the harness
   compares plus `position_nodes`), and the `hot` table. Zero
   differences.
4. **Sessions**: the three drivers' headless outputs (`--shot`,
   `--ticks`) byte-identical under `--native on` between VM and tree.
5. **The Python suite**: `pytest tests -q` green (it uses the binary
   through `--native auto`).
6. **Speed**: `python tools/bench_native.py 3` before and after, and
   the A/B harness from Q124 (both binaries alive, alternating). The
   target that makes the FPS window smooth: a 150 000-step frame
   under **10 ms**, i.e. **15 million steps a second or better** on
   the war terrain and the city frame. Report what was reached and
   where the remaining time goes (the crate's `prof` sampler).

### 8.1 What the first build reached (2026-09-19)

Gates 1-5 passed on the first build (16 unit tests; 988 + the clock
record; 3 042 programs x 4 ceilings, 12 168 runs, 0 differences; the
drivers byte-identical; the suite green). Gate 6 was not met: 1.16x
over the tree-walker on the apps (war terrain 7.0 -> 8.5 M steps/s,
city frame 6.1 -> 9.1, fps 5.4 -> 6.5), 2.0x on a wide arithmetic
body (24.7 M). The profile after the first optimisation round: the
call path 32% (17% the reference's own hot / depth / caps bookkeeping
in `rt::call`, 15% the VM's activation setup), dispatch 14%, loads
10%, closures 6%, map keys 5-17%, activation teardown up to 18% on
the city builder (dropping the lists a frame held). The next levers,
in order: a faster allocator (every cons cell, closure and captured
frame is a Windows `HeapAlloc`); `rt.current` and `owner` as raw
pointers (two `Rc` clones per call); slots inline in the frame; a map
key carrying its hash; one shared value stack; lazy per-unit
emission for `run` (5.9 ms of compile on the platformer, which a
session pays once).

## 9. Deliverables

`native/lova-rt/src/vm/{compile.rs, exec.rs, path.rs, mod.rs}`; the
binary's `--tree` flag and `LOVA_RT_EVAL`; `tools/differential.py`;
the unit tests; a section in `native/lova-rt/README.md` (create it)
on the two evaluators and how to switch; version `lova-rt 0.4.0`.
The tree-walker's files are edited only where the VM must share them
(`rt.rs` fields, `trap.rs`), and every such edit keeps the tree-walker
conformant.

## 10. Beyond the VM (not this milestone)

* **Q129 -- the renderer's own cost.** `lib/scene3d.lova` spends ~200
  steps a triangle; a frame's world-to-camera transform of static
  geometry is recomputed every frame. Caching placed geometry in the
  world record, culling by object before by face, and a coarser
  per-object depth sort would halve the steps of a frame without
  touching the runtime. A library change, checked by the drivers'
  `--shot` still matching the transliteration tests.
* **Q130 -- ahead-of-time compilation** (Cranelift or C source) of
  units the VM has already compiled, with the tick and trap logic
  inlined. Built on the VM's units, not on the tree; only after the
  VM is the default.
* **Q131 -- the crossing.** A session `call` returns a frame as JSON
  (a few hundred faces, a few thousand numbers); measure it, and if it
  is more than 2 ms move to a length-prefixed binary array for lists
  of integers, behind the same `NativeSession` API.
