# lova-rt — the native LOVA runtime

A Rust runtime for LOVA's byte sequence. It is not a second language:
it reproduces `core/runtime.py` step for step, value for value, trap
for trap. `spec/runtime-semantics.md` is the contract,
`corpus/golden/` (1023 records) is the definition of "the same", and
`tools/conformance.py` is how you check it.

```bash
cd native/lova-rt
cargo build --release
cd ../..
PYTHONPATH=$PWD python tools/conformance.py \
    --runtime native/lova-rt/target/release/lova-rt
```

The binary speaks one JSON request per line on stdin and one reply per
line on stdout (`spec/native-runtime-protocol.md`): `ping`, `run`,
`session` / `get` / `call` / `release` / `close`. Nothing else goes on
stdout. `core/native.py` is the Python client; `--native on` on the
CLI and in the drivers uses it.

## Two evaluators

| | `rt.rs` — the tree-walker | `vm/` — the bytecode VM |
|---|---|---|
| Shape | walks the decoded arena, one Rust frame per node | compiles each unit once, then a dispatch loop, one Rust frame per *activation* |
| Steps | one charge per node | one charge per straight-line run |
| Path | pushes `(op, node)` per node | derives it from the node table and the frame stack, on the trap only |
| Names | a `Scope` chain looked up by name | slots resolved at compile time |
| Status | the reference | the default (Q128) |

Both are in the binary and either can be selected:

```bash
lova-rt --tree            # the tree-walker
lova-rt --vm              # the VM
LOVA_RT_EVAL=tree lova-rt # the same, from the environment
```

`ping` reports which one is running (`"eval": "vm"` or `"tree"`). The
flag wins over the environment variable; with neither, the VM runs.

The tree-walker is not dead weight: it is the reference the VM is
checked against, and the VM hands it back whole subtrees whose
environment is not their lexical chain (below). It stays until the VM
has been the default through a milestone with the differential harness
green (`spec/vm.md` §7).

### What the VM compiles

A **unit** is one lambda body, or the program's root. The whole tree is
compiled **eagerly**, before the program starts -- `run` pays it every
time (~5 ms for the city builder's 80 KB), a `session` once. Compiling
a unit resolves every `ref` to a `(depth, slot)` pair against the
lexical chain, allocates a slot per binding, decides the `let` chain rule of
the semantics' §4.3 statically, partitions the unit into straight-line
runs of nodes, and records a node table so a trap can say where it
happened. Nested lambda bodies are compiled with it and hang off it,
so a closure is a unit plus the frame it captured -- and the live-slot
set of that frame where the closure was made, because a `let` region
that has closed is gone for the code after it while the closure that
captured it still reads it. That set is what a delegated subtree's
flattened environment, and an `unbound-ref`'s `bound_names`, are
filtered by; `bound_names` is the names actually **written**, derived
from the frame chain at the moment of the fault.

A session keeps every named closure its program made for as long as it
lives (`Rt::named`, which `hot` reports on and which the runtime's
borrowed function pointers rely on), so a long-lived session's memory
grows slowly with the number of calls.

Five operator groups are **delegated**: `eval`, `conserve`, `trace`,
the Evolution family (0x20–0x27) and the Meta family (0x38–0x3F),
plus the operators outside this runtime's scope (`read`, `explain`,
the network). Each compiles to one `Delegate` instruction that runs
the whole subtree on the tree-walker, over a `Scope` flattened out of
the VM's frames. That is `spec/vm.md` §2.4's dynamic fallback, widened:
those operators either evaluate code whose environment is not its
lexical chain (`eval`), or re-evaluate subtrees in a runtime of their
own (`conserve`, `trace`), or are cold enough that a second
implementation would be a second place to be wrong. They cost
tree-walker speed and nothing else.

**The live set.** A `let` region's slots stay written after the region
closes when a closure captured the frame -- the closure keeps reading
them -- but the reference pops its `Scope` there, so to the code after
the region, and to anything it delegates, those names no longer exist.
The compiler therefore tracks which slots belong to an *open* region
and carries that bitset on `Delegate` and `MakeClosure`; a `Frame`
records the mask its defining activation had where the closure was
made (`parent_mask`), and `flatten_masked` builds a delegated
subtree's environment, and an `unbound-ref`'s `bound_names`, from the
written slots the mask admits. The mask governs the by-name view only;
a `Load` never consults it. (`spec/vm.md` §2.4, "The live set": the
first build conflated the two and a `conserve` after a captured region
saw the region's bindings.)

### Steps, batched but exact

Rule 1 of the semantics is one step per evaluated node, pre-order,
before the node's work. The VM charges a whole run of nodes at its
head — but only when the batch fits under both the step ceiling and
the innermost budget. If it would cross either, that run is charged
node by node instead, from each instruction's own tick count, because
an eager batch cannot tell a `DomainTrap` at node *i* from a
`StepTrap` at node *j > i* when the ceiling falls between them. On any
other fault inside a batched run the counters are rewound to the
trapping node's own count before the anomaly is built.

### `position_path`, derived

The tree-walker pushes a `(op, node)` pair on every node; the VM
pushes nothing. On a trap it reconstructs the path: within one
activation the nodes still live are exactly the static ancestors of
the node in hand, and each activation below contributes the chain of
the node that made the call. A tail call replaced its frame, so it
contributes nothing; a trailing literal is trimmed, because the
reference's own path never holds one. A delegated subtree is walked by
the tree-walker, which does push per node, so the two interleave by
the `rt.path` length each activation recorded when it started.

## Speed

Measured by sending the same bytes to both evaluators alive at once,
alternating, best of six (the `run` request itself: no Python parse, no
compile of the source, no process start). The programs are frozen byte
sequences, so a library being edited cannot move the numbers.

| program | steps | tree | VM | |
|---|---|---|---|---|
| war terrain | 2 466 307 | 8.6M steps/s | **11.2M** | 1.31x |
| war terrain + 60 ticks | 3 186 457 | 8.5M | **11.0M** | 1.28x |
| citybuilder frame | 843 405 | 7.5M | **11.7M** | 1.57x |
| citybuilder 60 ticks | 877 062 | 7.6M | **11.6M** | 1.53x |
| fps, 300 ticks | 2 368 099 | 6.7M | **7.7M** | 1.16x |
| platformer frame | 145 503 | 6.3M | **7.1M** | 1.14x |
| tictactoe, full game | 2 411 809 | 7.1M | **8.0M** | 1.13x |
| maze | 204 591 | 7.6M | **8.3M** | 1.09x |
| a tail-recursive loop | 2 100 008 | 12.8M | **18.2M** | 1.42x |
| building a list | 1 100 016 | 9.3M | **12.1M** | 1.30x |
| a wide arithmetic body | 200 000 001 | 14.4M | **30.6M** | 2.12x |

`batch` (0.66x) is the shape that loses: 4 334 steps, so the whole row
is the compile pass, and `conserve` sends its body to the tree-walker
and puts every frame on the heap.

The gain is largest where a program is arithmetic over its own slots
and smallest where it is calls, map lookups and list walking -- which
is what the 3D libraries are. Two costs work against the VM on a short
run of a large program: it compiles the whole tree before it starts
(~5 ms for the city builder's 80 KB, against the tree-walker's zero),
and a program using `conserve` or the Meta family delegates. A session
compiles once and pays neither per frame.

Where the rest of the time goes (the crate's sampler). War terrain:
dispatch 19%, slot and constant loads 13%, the call path 26% (half of
it `rt::call`'s hot-attribution and depth bookkeeping, which the
tree-walker pays too), map keys 6%, the text family 9%, arithmetic 7%.
The city builder's frame: freeing what an activation built 18%, map
lookups 18% (7% making the key, 10% hashing and probing), dispatch
15%, loads 13%.

### What made it fast

The VM as first written was at parity with the tree-walker. In order of
what it bought:

1. **Operator fast paths in the dispatch loop** (`merge`, `deviation`,
   `mul`, `div`, `mod`, `threshold`, `cons`, `head`, `tail`, `nil?`,
   `identity`, and `Coerce` as a type check). The work had been three
   non-inlined calls and drop glue per node: a wide arithmetic body
   went 13M -> 26M steps/s.
2. **Fused operands** (`Bin` / `Un` read a slot or a constant for
   themselves) -- three instructions become one.
3. **A tail call that allocates nothing** (the pair goes on the
   runtime, not in an `Rc`): a tail-recursive loop 0.91x -> 1.23x
   against the tree-walker.
4. **A size-class allocator** (`alloc.rs`) in front of the system heap.
5. **`rt.current` and `ClosureData.owner` as borrowed pointers** --
   two refcount pairs off every call that changes function.
6. **Stack frames** for units nothing captures, and inline slots for
   the frames that are captured.
7. **A cheaper compile pass**: no parent table (a trap walks the arena
   for the chain), a flat run table, cached visible-name lists, and no
   vector allocated per node.
8. **A two-integer map key without a vector**, and forgetting a `let`
   region's slots when it closes, so values die where the reference
   drops them.

## Checking a change

```bash
cargo test --release                     # the unit tests, including vm/tests.rs
python tools/conformance.py --runtime <binary>        # 989 of 1023, 29 out of scope
python tools/differential.py                          # both evaluators, every program
python tools/bench_native.py 3                        # speed, against the Python runtime
```

`tools/differential.py` is the VM's own gate: it runs every `.lova`
under `apps/`, `lib/`, `tools/bench/` and `corpus/`, every golden byte
sequence, and 2 000 generated programs through both evaluators at four
step ceilings — about 12 000 runs, two fifths of them trapping — and
compares the value, the steps, stdout and every field of the anomaly,
`position_nodes` and the `hot` table included. Zero differences is the
bar.

## Layout

```
src/
  main.rs        the line protocol, the evaluator choice, `run` / `session`
  alloc.rs       the size-class allocator small values come from
  session.rs     sessions: values kept alive and handed out as handles
  rt.rs          the tree-walker: accounting, coercions, calls, operators
  vm/
    mod.rs       the instruction set, units, frames, the VM's state
    compile.rs   tree -> units: slots, the let chain rule, runs
    exec.rs      the dispatch loop
    ops.rs       operator work over evaluated operands (shared with rt.rs)
    path.rs      position_path, derived on a trap
    tests.rs     both evaluators on one tree, compared whole
  value.rs       the value model, the persistent map, `format_value`
  tokens.rs      the byte encoding: decode, encode, the arena
  trap.rs        anomalies and the trap classes
  text.rs nt.rs int.rs conserve.rs evolve.rs lineage.rs meta.rs rng.rs
  fx.rs prof.rs  a fast hasher; a sampling profiler (`--features prof`)
```
