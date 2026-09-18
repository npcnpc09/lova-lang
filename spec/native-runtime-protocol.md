# The native-runtime protocol

A native LOVA runtime is a binary that reads **one JSON object per line
on stdin** and writes **one JSON object per line on stdout**, in order.
Nothing else goes on stdout; a diagnostic goes on stderr.  This is the
whole interface `tools/conformance.py` needs to check a port against
`corpus/golden/*.jsonl`.  The binary is started with the repository
root as its working directory, because a program's `fs-read` path is
relative to it.  `tools/mock_runtime.py` is the protocol made
executable -- the Python runtime behind this interface -- so a port can
be developed against something that already answers:

    python tools/conformance.py --runtime "python tools/mock_runtime.py"

## Requests

```json
{"op": "ping"}
{"id": 1, "op": "run", "bytes": "<hex>", "stdin": "...", "allow": 0,
 "max_steps": 1000000, "max_depth": 10000}
```

`bytes` is the hex of the compiled program as `core.tokens.encode`
writes it -- the tree the Python runtime runs, prelude inlined,
`drop-unused` and constant folding already applied.  The runtime
decodes it (`core.tokens.decode` is the reference) and evaluates it.
`stdin` is the whole input, lines with their terminators kept; a read
past the end yields `nil`.  `allow` is the capability mask the host
grants (`core.tokens.CAPABILITY_BITS`: fs-read 1, fs-write 2, clock 4,
net 8); `max_steps` / `max_depth` are the ceilings for this run.

## Responses

```json
{"ok": true, "version": "lova-rt 0.1.0"}

{"id": 1, "ok": true, "value": "42", "steps": 1234, "stdout": "..."}

{"id": 1, "ok": false, "steps": 1234, "stdout": "...",
 "anomaly": {"kind": "domain-error", "offending_op": 13,
             "offending_op_name": "div", "position_path": [46, 45, 13],
             "detail": {"operator": "div"},
             "repair_hint": "guard the divisor with `(if d (div a d) fallback)`"}}

{"ok": false, "error": "decode: unknown token 0xFE at position 7"}
```

* **`value`** is the printed form, character for character what
  `core.cli.format_value` gives: an integer bare, a text in double
  quotes with LOVA's escapes, a list as `(1 2 3)` -- and with
  `  "abc"` appended when every element is a codepoint in
  `32..0x10FFFF` -- a closure as `<closure param=8>`, a map as
  `#<map n=2 {"a": 1 "b": 2}>` (first eight entries, then ` ...`), a
  program as `#<program uid=3 (merge 1 2)>`, a population as
  `#<population n=4 gen=1>`.
* **`steps`** is the evaluated-node count, *also when the run trapped*.
  It is compared exactly: a port that charges a different number of
  steps for the same program is not conformant, however fast it is.
* **`stdout`** is everything the program wrote with `stdout` /
  `println`, as one string.  It is not written to the real stdout,
  which carries the protocol.
* **`position_path`** is the chain of **token bytes** from the root
  node to the node that raised, outermost first (not child indices):
  `[46, 45, 13]` is `seq` → `apply` → `div`.
* **`offending_op`** is the last element of that chain, and
  `offending_op_name` its name in `core.tokens.SIGNATURES`.
* A **decode failure**, or any fault outside a program's semantics,
  is `{"ok": false, "error": "..."}` with no `anomaly` and no `id`
  requirement.  It is never an anomaly: an anomaly is the *language's*
  answer to a fault, and an undecodable byte stream is not a program.

## Which fields the native side owes

It must produce: `value` (or `anomaly`), `steps`, `stdout`, and inside
an anomaly `kind`, `offending_op`, `position_path`, `detail` and
`repair_hint`.

* **`kind`** is one of the ten in `core.conservation.ANOMALY_CODES`:
  `budget-exceeded`, `recursion-depth-exceeded`, `conservation-violated`,
  `domain-error`, `type-violation`, `unbound-ref`, `malformed`,
  `step-limit-exceeded`, `capability-denied`, `signalled`.
* **`detail`** is the fault's own dictionary.  The conformance harness
  compares `operator`, `limit`, `expected`, `code` and `name_id` where
  the golden record has them; the rest is for a reader.
* **`detail.calls`** must be produced by the runtime when the kind is
  `step-limit-exceeded` or `recursion-depth-exceeded`: `[[name_id,
  own_steps, calls], ...]` for the eight costliest named functions,
  costliest first, a function's own body only (an anonymous lambda
  charged to the `let` that named the closure it was written in).  The
  Python driver spells the ids into words and moves it to
  `detail.hot`, which is what a reader sees -- the golden records carry
  the spelled form in their own `hot` field.  Without it a port
  reproduces the trap but not the one thing the trap is for.
* **`repair_hint`** is written at the raise site and differs per fault,
  not per operator, so it cannot be derived: a port produces its own,
  and the reference strings are in `core/runtime.py` (each
  `DomainTrap(...)`'s fourth argument) and `core/conservation.py`
  (`Budget.charge`, `DepthTrap`, `StepTrap`, `_op_CONSERVE`).  It is
  not compared by the harness.
* **`offending_op_name`** may be sent or left empty; the driver can
  fill it from `offending_op`.

## Which fields Python adds, and the native side must not send

* **`valid_alternatives`** -- derived by the driver from
  `offending_op` through `core.observability.suggest_alternatives`
  (same-family swap groups; `identity` for `violate`).  For a
  `conservation-violated` trap that carries a `body_offender`, the
  Python runtime re-derives it from the inner operator instead.
* **`span`, `excerpt`, `line`, `col`** -- the place in the *source
  text*.  Bytes carry no spans, so these are added by
  `core.cli.describe_span` / the MCP server from the program's text
  when there is one.  A native runtime never produces them.
* **`body_offender`** -- the Δ-trap's single-node probe
  (`_scan_body_offender`).  A port may produce it; the driver does not
  require it.
* The **names** in an anomaly: `detail.name`, `detail.bound` and the
  rewritten `repair_hint` for `unbound-ref`, and `detail.hot`, are
  written by `core.cli.name_anomaly` from the symbol table, which lives
  in the *source*, not in the bytes.  A native runtime reports name
  **ids**.

## Rules the harness holds a port to

1. A run is a pure function of `(bytes, stdin, allow, max_steps,
   max_depth)` -- and of the files under the working directory, for
   `fs-read`.  The golden records flag every program that reads the
   clock or the network as `deterministic: false`; nothing else may
   vary between runs.
2. `step-limit-exceeded` is the one anomaly `when-anomaly` may not
   catch.  Every other kind is catchable, including
   `recursion-depth-exceeded`.
3. Effects are refused twice: by the capability bit the enclosing
   `external-boundary` declares, and by the `allow` mask the host
   granted.  A boundary declaring what the host did not grant traps on
   entry, before the body runs.
4. `id` is echoed back on every `run` reply; the driver sends one
   request at a time, but a port may not reorder replies.
