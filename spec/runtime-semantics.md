# LOVA — Runtime Semantics (the port contract)

> **Status: descriptive.** This document states what
> `core/runtime.py` (with `core/tokens.py`, `core/conservation.py`,
> `core/lineage.py`, `core/populations.py`) actually does, at the
> level of detail a second implementation needs in order to produce
> **the same values, the same step counts, the same traps and the
> same anomaly fields**. Every statement here was read out of the
> code; where the behaviour looks accidental it is still specified,
> marked `(quirk)`.
>
> Step counts are part of the contract. Budgets are declared in
> steps, `tests/test_compiled.py` pins counts and trap positions, and
> the journal quotes step figures. A port that computes the right
> answer with a different step count is wrong.
>
> Reference: CPython 3.11+, `core/runtime.py` at M32.

---

## 0. Orientation

A run is:

```
bytes --decode--> Node tree --compile--> per-node Python closures --call--> value
```

- `decode` (§1) turns the byte sequence into a `Node` tree.
- The evaluator (`_eval` / `_code`) compiles each node, **on first
  sight, once per run**, into a closure that (a) charges the active
  budget, (b) increments `rt.steps` and checks the ceiling, (c) runs
  the operator. A port need not compile; it must keep the order.
- The reference interpreter has **two code paths per operator**: a
  hand-inlined *template* (`_compile_*`, 23 operators) used when the
  node has the declared arity and shape, and a *generic handler*
  (`_op_*`) reached through `_compile_generic` for everything else.
  **The template is authoritative** for the 23 operators that have
  one; the generic handler for the same operator is reachable only
  from a hand-built tree of the wrong arity (`decode` cannot produce
  one, since arity is fixed by `SIGNATURES`), and where the two
  differ the differences are flagged below.

Naming in this document: `rt` is the runtime state, `steps` its step
counter, `NIL` the empty-list singleton.

---

## 0.1 Porting decisions (2026-09-19)

Where the Python runtime's behaviour was the host's rather than the
language's, the language now says which it is. Each decision below is
applied to `core/runtime.py` in the same commit, so the golden set
records the decided behaviour. These override anything later in this
document that says otherwise (§3.4 and quirks 7, 10, 12 in particular).

- **D1 — `sort-by` is a specified merge sort.** Top-down: a list of
  length ≤ 1 is itself; otherwise split at `len // 2`, sort both
  halves, and merge by taking the right element only when
  `before(right, left)` holds, else the left, so ties keep their
  order. `before(a, b)` is one step, then `(less a b)` and `(less b
  a)` applied in that order, and holds when the first is non-zero and
  the second is zero. The number and order of comparator invocations
  is therefore defined by the language, not by the host's sort. The
  Timsort anchors in §3.4 and quirk 12 no longer apply.
- **D2 — `text-int` takes ASCII digits only**, after the trim of D6,
  with an optional leading `-`. Any other character, including
  another script's digits or a superscript, is the `signalled` fault
  with code 16. Quirk 7 is closed.
- **D3 — `text-cmp` on elements that are not mutually comparable** (an
  integer against a text or a list inside the lists) is a
  `type-violation` DomainTrap, message `text-cmp: the elements are not
  comparable (an integer against a text or a list)`. Quirk 10 is
  closed.
- **D4 — the evolution PRNG is contractual** (amended 2026-09-19, at
  phase 3; it read "not contractual" from phase 1 to phase 2, and no
  golden record was in fact marked non-deterministic for it).  A port
  reproduces the Mersenne Twister stream of CPython's `random.Random`
  as §5.5 "Randomness" specifies -- `random()`, `randint` through
  `_randbelow` on `getrandbits`, `choice` -- seeded with 0 per
  `LineageStore`.  Three reasons: the algorithm is fully written down
  and is ~150 lines; `apps/repair.lova` and `apps/evolve.lova` promise
  a reproducible run, and that promise should not depend on which
  runtime ran it; and the golden records that pin a mutation stay
  exact instead of being relaxed.
- **D5 — the pattern engine is the subset, not the host.** A native
  runtime may use any engine that gives leftmost-first alternation,
  greedy quantifiers with `?` for the shortest, and non-overlapping
  scanning that advances one character past an empty match (the
  `regex` crate does). Conformance on the golden set is the check.
- **D6 — whitespace, for `text-trim`, `text-int`'s trim and
  `text-split` with `""`, is Python's `str.isspace` set**, fixed here:
  U+0009–U+000D, U+001C–U+001F, U+0020, U+0085, U+00A0, U+1680,
  U+2000–U+200A, U+2028, U+2029, U+202F, U+205F, U+3000.
- **D7 — phase 2 scope of the native runtime.** Everything except the
  Meta family (0x38–0x3F), the Evolution family (0x20–0x27),
  `trace` / `trace-surprise`, `read` / `explain`, and the network
  (`net-send` / `net-recv`). A program containing an unsupported
  operator is answered with `{"ok": false, "error": "unsupported:
  <name>"}` before evaluation starts; the Python side scans the tree's
  operator set and runs such programs on the Python runtime. Phase 3
  adds `fs-read` / `fs-write` / `clock`, then the Meta family without
  `read` / `explain`, then Evolution; `read` / `explain` need the
  Stage-1 surface and stay in Python.
- **D8 — `position_path` is an explicit path stack** in a native
  runtime: push on entering any non-literal node, pop on leaving; a
  tail call pops the frame it replaces, exactly as the Python stack
  does.
- **D9 — kept as contract**, quirks and all: Rule-2 extras do not
  charge the budget (quirk 21); `trace` adds its steps after the fact
  (23); `identity` does not coerce (26); `deviation` on texts is an
  equality test (18); `p` names `partition_number` (19); the `hot`
  list lands under `detail["calls"]` (20); zero-argument `apply`
  returns the head (32). A port reproduces them; a later milestone
  may change them in both runtimes at once.

## 1. The byte encoding

### 1.1 Stream shape

A program is **one** top-level expression. `decode(data)` decodes one
expression from offset 0 and raises if anything is left over:

```
trailing bytes after decode: <hex of the remainder>
```

Every node begins with **one opcode byte**. Valid opcodes are exactly
the 88 keys of `SIGNATURES` (`0x00`–`0x57` less the unused gap; see
the table in §5). An unknown byte:

```
unknown token 0x{op:02X} at position {pos}
```

An empty or exhausted stream: `unexpected end of stream`.

Only three shapes exist after the opcode:

| Shape | Determined by | Bytes that follow |
|---|---|---|
| `LIT_INT` (0x01) | opcode | 1 length byte, then that many payload bytes |
| `LIT_TEXT` (0x40) | opcode | 2 length bytes (big-endian), then that many UTF-8 bytes |
| fixed arity *n* | `SIGNATURES[op]["arity"]` is an int | exactly *n* child expressions, back to back |
| variadic | `SIGNATURES[op]["arity"] == "variadic"` | zero or more child expressions, then `END` (0x00) |

`END` (0x00) is **only** a variadic terminator. It is never an
operator: it has no runtime handler, and meeting it as the start of an
expression decodes a childless `Node(op=END)` whose evaluation raises
`NotImplementedError` (see §5.9). `decode` does not special-case it
outside the variadic loop.

The three variadic operators are `defpop` (0x20), `seq` (0x28) and
`apply` (0x2D). Nothing else is variadic.

### 1.2 `LIT_INT` payload

Encoding (`_encode_into`):

```
n_bytes = max(1, (val.bit_length() + 1 + 7) // 8)     # +1 for the sign bit
if n_bytes > 255: error "LIT_INT too large: {val}"
emit 0x01, n_bytes (one byte), val.to_bytes(n_bytes, "big", signed=True)
```

Decoding: read the length byte; read that many bytes; interpret as a
**big-endian two's-complement signed integer**.

- `0` encodes as one byte `0x00` (bit_length 0 → `max(1, …)` → 1).
- Negative values are two's complement over exactly `n_bytes`.
- The payload may be **0 bytes long** if a producer writes length 0;
  `decode` accepts it and `int.from_bytes(b"", …)` yields `0`.
  `encode` never produces it. *(quirk)*
- Maximum literal magnitude: 255 payload bytes → roughly ±2^2039.
- Errors: `LIT_INT: missing length byte`, `LIT_INT: truncated payload`.

A `LIT_INT` node's `args` is `[int]` — a scalar, **not** a child node.
This matters everywhere a tree is walked: `LIT_INT` has no children.

### 1.3 `LIT_TEXT` payload

```
data = str(args[0]).encode("utf-8")
if len(data) > 0xFFFF: error "LIT_TEXT too long: {len} bytes"
emit 0x40, len(data) as 2 bytes big-endian, data
```

Decoding: 2-byte big-endian **byte** length (not character count),
then `data.decode("utf-8")` — strict, so invalid UTF-8 raises. Errors:
`LIT_TEXT: missing length`, `LIT_TEXT: truncated payload`.

A `LIT_TEXT` node's `args` is `[str]` — again a scalar, no children.

### 1.4 Name ids

There are **no symbols in the byte stream**. A name is an integer, and
it travels as an ordinary `LIT_INT` in the slot the operator reserves
for it:

- `(let name value body)` — `args[0]` must be `LIT_INT`; the payload
  is the name id.
- `(lambda param body)` — `args[0]` must be `LIT_INT`; the payload is
  the parameter's name id.
- `(ref name)` — `args[0]` must be `LIT_INT`; the payload is the name
  id to look up.

The runtime uses the payload as a dictionary key; nothing constrains
its range or sign, and negative ids work. The *surface* parser interns
source identifiers to small non-negative integers, but that is a
Stage-1 concern and not part of this contract.

A `LET` / `LAMBDA` / `REF` whose name slot is not a `LIT_INT` falls to
the generic handler and traps `malformed` (§5.7).

### 1.5 Round-trip properties a port must preserve

- `decode(encode(t)) == t` structurally for every well-formed tree.
- `encode` validates arity for fixed-arity operators:
  `token {name} expects {n} args, got {m}`.
- `hash` (0x3C) is `int.from_bytes(encode(program), "big")`, so the
  encoding is *observable inside the language*. A port must produce
  byte-identical output from `encode`.

---

## 2. The value model

### 2.1 The value kinds

| Kind | Python type | Produced by |
|---|---|---|
| **Integer** | `int` (unbounded) | `lit`, all arithmetic, `text-len`, `text-find`, `text-cmp`, `text-int`, `nil?`, `text?`, `threshold`, `deviation`, `surprise`, `stdout`, `fs-write`, `net-send`, `clock`, `hash`, `uid`, `generation`, `ancestor-of`, `any`, `filter`'s predicate use… |
| **Text** | `str` | `text` literal, `text-cat`, `text-slice`, `text-join`, `text-of-chars`, `int-text`, `text-trim`, `explain`, `why`, `stdin`, `fs-read`, `net-recv`, `cons` of a codepoint onto a text |
| **Nil** | `_Nil` singleton `NIL_VALUE` | `nil` (0x15), `tail` of a one-element list, `stdin` at end of input, `net-recv` on timeout, `text-match` with no match, `lineage-query` of an unregistered program |
| **Cons cell** | `Cons(head, tail)` | `cons`, every list-returning operator |
| **Map** | `MapValue` | `map-put`, `_as_map` of a list of pairs |
| **Closure** | `Closure` | `lambda` |
| **LoopFn** | `LoopFn` | `loop-until` |
| **Population** | `Population` (runtime's own, not `core/populations.py`'s) | `defpop`, `evolve`, `retire` |
| **Program** | `Node` | `quote`, `read`, `clone`, `mutate`, `variant`, `select` |

There is no boolean. `bool` is defensively coerced wherever it could
appear (`isinstance(v, bool)` guards), but no operator produces one.

`NIL_VALUE` is a **singleton**; identity (`is`) is the test used
throughout. A port needs one distinguished empty-list value.

`Cons` is a linked cell with `head: Any` and `tail: Cons | NIL_VALUE`.
It is never mutated after construction. `head` may hold **any** value
(M17): an integer, a list, a text, a program, a function, a map.
`tail` is coerced to a list by `cons` itself (§5.1).

Critically, **a text is also a list** wherever a list is expected: a
`str` is read as its codepoint list by `_as_list`, `list_to_python`,
`_text_chars`, `_map_key`, and by every list-family walker. The
converse is not automatic: a list becomes a text only through
`_as_text`.

### 2.2 `format_value` (`core/cli.py`) — how values print

This is the CLI/MCP rendering, not a language operator, but it is the
observable surface of a run and a port's CLI should match it.

```
str          -> quote_text(v): '"' + v with \ -> \\ , " -> \" ,
                LF -> \n, TAB -> \t, CR -> \r + '"'
Population   -> #<population n={len(variants)} gen={generation}>
MapValue     -> #<map n={N} {k: v k: v ...}>      (first 8 entries,
                " ..." appended when N > 8; k and v formatted recursively)
Node         -> #<program uid={uid} {pretty(node)}>   (" uid=…" only when uid truthy)
list (Cons/NIL) -> "(" + elements + ")", each element formatted
                recursively except plain ints, which print bare.
                If the list is non-empty and EVERY element is an int
                in [32, 0x10FFFF], the text rendering is appended:
                   (65 66)  "AB"
                (a ValueError from chr() falls back to the bare list)
int          -> str(v)
anything else (Closure, LoopFn) -> repr(v)
                Closure: <closure param=N> or <closure param=N name=M>
                LoopFn:  <loop-until>
```

### 2.3 Truthiness

There is exactly one rule: **an integer is true iff it is non-zero.**
Every site coerces to `Int` first.

| Site | Rule |
|---|---|
| `if-surprise` test | `_as_int(test) != 0` → then-branch, else else-branch |
| `loop-until` predicate | `_as_int(verdict) != 0` → stop and return the value |
| `filter` predicate | `_as_int(f x) != 0` → keep |
| `any` predicate | `_as_int(f x) != 0` → return 1 |
| `sort-by` comparator | `_as_int(less a b) != 0` |
| `nil?` | *returns* 1/0; it is not a truthiness site |

`nil?` is the only list predicate: `NIL` → 1, `Cons` → 0, `""` → 1,
non-empty `str` → 0, anything else → `_as_list` raises (§5.1).

### 2.4 Coercions

All coercion helpers take a context string `ctx` that appears verbatim
in the fault message.

#### `_as_int(v, ctx)`

```
bool           -> int(v)                       (defensive)
int            -> v
Population     -> DomainTrap "type-violation"
                  "{ctx}: expected an Int, got a population; `fitness` gives its scores, `select` gives a variant"
                  detail {"operator": ctx, "expected": "Int", "got": "Population"}
                  hint "use `fitness` for the scores or `select` for a variant"
Node (Program) -> DomainTrap "type-violation"
                  "{ctx}: expected an Int, got a program; `hash` gives its integer, `eval` gives its result"
                  detail {"operator": ctx, "expected": "Int", "got": "Program"}
                  hint "use `hash` for the program's integer or `eval` for its value"
list (NIL/Cons)-> DomainTrap "type-violation"
                  "{ctx}: expected an Int, got a list ({v!r}); use `head` to take an element out of it"
                  detail {"operator": ctx, "expected": "Int", "got": "List"}
                  hint "use `head` to take an element out of the list"
anything else  -> DomainTrap "type-violation"
                  "{ctx}: expected an Int, got a function value ({v!r}); a function can only appear in the head slot of `apply` or in a slot typed Fn"
                  detail {"operator": ctx, "expected": "Int", "got": "Fn"}
                  hint "apply the function to get an integer, or use it in an Fn slot"
```

Note the last branch catches a **text** as well — a `str` in an Int
slot is reported as "a function value". *(quirk)*

#### `_as_text(v, ctx)`

```
str          -> v
int (non-bool) -> str(v)                       decimal, "-" for negatives
Population   -> "type-violation"
                "{ctx}: cannot write a population; `explain` a selected variant"
                detail {"operator": ctx, "got": "Population"}; hint "write `(explain (select pop 0))`"
Node         -> "type-violation"
                "{ctx}: cannot write a program directly; `explain` renders it"
                detail {"operator": ctx, "got": "Program"}; hint "write `(explain p)` instead of `p`"
MapValue     -> "type-violation"
                "{ctx}: cannot write a map; write its `map-pairs`"
                detail {"operator": ctx, "got": "Map"}; hint "iterate `(map-pairs m)` and write each entry"
list         -> every element must be an int in [0, 0x10FFFF]; the
                text is "".join(chr(e)).  A bad element:
                "domain-error"
                "{ctx}: {code!r} is not a codepoint; a list is written as text, so every element must be one"
                detail {"operator": ctx, "element": code}
                hint "write a list whose elements are all valid codepoints"
otherwise    -> "type-violation"
                "{ctx}: cannot write a function value ({v!r}); write an integer or a list of codepoints"
                detail {"operator": ctx, "got": "Fn"}; hint "write an integer or a list of codepoints"
```

Order matters: the list branch is tried after Population / Program /
Map, so the `bool` case reaches the *int* branch (`isinstance(v, bool)`
is excluded explicitly there, so a `bool` falls all the way to the
final "function value" branch). No operator produces a `bool`.

#### `_as_list(v, ctx)`

```
NIL or Cons -> v
str         -> _text_chars(v, ctx)   == list_from([ord(c) for c in v])
otherwise   -> DomainTrap "type-violation"
   message: "{ctx}: expected a List, got {v!r}; only `nil`, `cons` and `tail` produce list values"
   detail:  {"operator": ctx, "expected": "List",
             "got": _kind_of(v), "got_value": format_repr(v)}
   hint:    "`{ctx}` wants a list or a text and got {kind} {repr}"
            + ", if this came from an input, the argument arrived as an integer -- quote it on the command line to pass a text"
              (exactly: "; if this came from an input, the argument arrived as an "
                        "integer -- quote it on the command line to pass a text")
              — appended when v is a non-bool int
            + "; a record and a map are the same kind of value and it is not a "
              "list, so `(nil)` cannot stand for `absent` beside one -- give the "
              "record a field that says so, `(rec v 0 ...)`, and test `(get r v)`"
              — appended when v is a MapValue AND ctx is one of "nil?", "head", "tail"
```

`_kind_of(v)`: `"an integer"` for `bool`/`int`, `"a text"` for `str`,
`"a list"` for NIL/Cons, `"a function"` for anything `callable(...)`,
else `"a value"`. (`Closure` and `LoopFn` are dataclasses and are
**not** callable in Python, so they report `"a value"`. *(quirk)*)

`format_repr(v)`: `repr(v)`, truncated to `repr[:37] + "..."` when
longer than 40 characters.

#### `list_to_python(v)`

`str` → list of codepoints. Otherwise walk `Cons` cells collecting
heads; the walk must end at `NIL`, else:

```
DomainTrap "type-violation", "not a list: {value!r}",
  detail {"expected": "List"},
  hint "only `nil`, `cons` and `tail` produce list values"
```

(Unreachable from `cons`, which coerces its tail; reachable from a
hand-built value.)

#### `_as_fn(v, ctx)`

Accepts `Closure` and `LoopFn` only (by exact class). Otherwise:

```
DomainTrap "type-violation"
  "{ctx}: the function slot holds {kind} {repr}, not a function"
  detail {"operator": ctx, "expected": "Fn", "got": _kind_of(v)}
  hint "pass a `lambda` or the name of a `def`; an operator is not a value -- wrap it, `(lambda x (op x))`"
```

#### `_as_map(v, ctx)`

```
MapValue -> v
list     -> a fresh MapValue; every element must itself be a list of
            exactly two elements (key, value), inserted in order.
            non-list element:
              "type-violation", "{ctx}: a map from a list needs `(list key value)` pairs",
              detail {"operator": ctx, "got": type(entry).__name__},
              hint "build the list with `(list (list k v) ...)`"
            wrong length:
              "domain-error", "{ctx}: a map entry is a two-element list, got {n}",
              detail {"operator": ctx, "length": n},
              hint "give each entry as `(list key value)`"
otherwise -> "type-violation",
             "{ctx}: expected a Map or a list of pairs, got {v!r}",
             detail {"operator": ctx, "expected": "Map"},
             hint "start from `(nil)` and `map-put` into it"
```

`NIL` therefore **is** the empty map, and a text is read as a
codepoint list and then rejected entry by entry.

#### `_sep(v, ctx)` — separator slots

```
non-bool int -> chr(v)        (a codepoint is a one-character separator)
otherwise    -> _as_text(v, ctx)
```

Used by `text-find`, `text-split`, `text-join`.

#### `_as_program`, `_as_population`

```
_as_program:   Node -> v; else "type-violation",
  "{ctx}: expected a Program, got {v!r}; `quote` produces one",
  detail {"operator": ctx, "expected": "Program"},
  hint "wrap the expression in `quote`, or pass a program produced by `clone` or `mutate`"

_as_population: Population -> v; else "type-violation",
  "{ctx}: expected a Population, got {v!r}; `defpop` builds one",
  detail {"operator": ctx, "expected": "Population"},
  hint "build a pool with `(defpop scorer program ...)`"
```

### 2.5 Integers

Arbitrary precision. A port must use bignums.

- `merge` → `a + b`; `deviation` → `a - b`; `violate` → `a + 1`.
- `mul` → `a * b`, **guarded on the output**: if
  `a.bit_length() + b.bit_length() > 4096` (`MAX_INT_BITS`), trap
  before multiplying (§5.2). `bit_length()` is the number of bits of
  the absolute value; `0` has bit_length 0.
- `div` → `a // b`: **Python floor division.** The quotient is
  rounded toward negative infinity, not toward zero.
  `(-7) // 2 == -4`, `7 // (-2) == -4`, `(-7) // (-2) == 3`.
- `mod` → `a % b`: **Python modulo.** The result takes the sign of
  the *divisor*, and `a == (a // b) * b + (a % b)` holds.
  `(-7) % 2 == 1`, `7 % (-2) == -1`, `(-7) % (-2) == -1`.
  This is *not* C / Rust `%`. A Rust port must implement
  `rem_euclid`-style adjustment: `let r = a % b; if (r != 0) && ((r < 0) != (b < 0)) { r + b } else { r }`,
  and the matching `div_floor`.
- `b == 0` traps for both `div` and `mod` (§5.2).
- `gcd` → Python's `math.gcd`: **always non-negative**,
  `gcd(0, 0) == 0`, `gcd(-12, 18) == 6`.
- `partition` → `n // 2` (floor; `(-7) // 2 == -4`).

### 2.6 Comparison

`text-cmp` (0x49) is the only ordering operator on non-integers:

```
both str  -> (a > b) - (a < b)         # Python str comparison:
                                       # lexicographic by CODE POINT
otherwise -> xs = codepoints(a) if a is str else list_to_python(a)
             ys = codepoints(b) if b is str else list_to_python(b)
             return (xs > ys) - (xs < ys)
```

The second branch is Python **list** comparison: element by element,
first difference decides; if one list is a prefix of the other, the
shorter is smaller. Elements are compared with Python `<` / `>`, so:

- a list of ints compares element-wise as expected;
- a list containing a non-int element (a nested list, a text, a
  closure) is compared with Python's own rules and may raise a bare
  `TypeError` that escapes the LOVA error model. *(quirk)*

Integer ordering in LOVA is built from `deviation` + `threshold`:
`(a < b) == (threshold (deviation b a))`, `(a > b) == (threshold (deviation a b))`.
`threshold x` is `1 if x > 0 else 0`.

`deviation` has a **text special case**: if either operand is a `str`,
the result is `0` when `_as_text(a) == _as_text(b)` and `1` otherwise
— an equality test, not a difference, and note the polarity is
inverted relative to the integer case (equal → 0, as `a - b` would
give). *(quirk, but load-bearing: it is how `dev` compares texts.)*

`surprise a b` → `abs(a - b)` and emits a surprise event.

### 2.7 Map keys — `_map_key(v, ctx)`

```
non-bool int -> ("i", v)
str          -> ("l", tuple(("i", ord(ch)) for ch in v))
NIL / Cons   -> ("l", tuple(_map_key(item, ctx) for item in list_to_python(v)))
otherwise    -> DomainTrap "type-violation"
   "{ctx}: a map key is an integer or a list, not {type(v).__name__}"
   detail {"operator": ctx, "got": type(v).__name__}
   hint "key the map by an integer or by text"
```

Consequences a port must reproduce:

- **A text and its codepoint list are the same key.** `"ab"` and
  `(cons 97 (cons 98 (nil)))` collide deliberately.
- Keys are structural, recursive and arbitrarily nested.
- A `bool`, a `Map`, a `Closure`, a `LoopFn` and a `Program` cannot be
  keys. The message names the **Python type name**
  (`MapValue`, `Closure`, `LoopFn`, `Node`, `bool`) — a port must
  emit the same strings.
- The stored entry keeps the **original** key value, so `map-pairs`
  gives back the text, not the codepoint list.

### 2.8 The map — `MapValue`

A persistent map with Baker rerooting. One Python `dict` is shared by
a family of versions:

- the *owner* holds `_entries` (the dict) and `_diff = None`;
- every other version holds `_entries = None` and
  `_diff = (hashed_key, entry_or_MISSING, next_version_toward_owner)`.

`entries` (the accessor) reroots first:

```
_reroot(self):
    path = []; v = self
    while v._diff is not None: path.append(v); v = v._diff[2]
    entries = v._entries; owner = v
    for v in reversed(path):
        hashed, wanted, _ = v._diff
        current = entries.get(hashed, MISSING)
        if wanted is MISSING: del entries[hashed]
        else: entries[hashed] = wanted
        owner._entries, owner._diff = None, (hashed, current, v)
        v._entries, v._diff = entries, None
        owner = v
```

`put(hashed, key, value)`:

```
entries = self.entries                 # reroots if needed
previous = entries.get(hashed, MISSING)
entries[hashed] = (key, value)
successor = MapValue(entries)
self._entries, self._diff = None, (hashed, previous, successor)
return successor
```

Observable properties:

- **Order is dict insertion order.** `map-pairs` returns
  `entries.values()`, i.e. `(key, value)` pairs in the order keys were
  first inserted. Re-putting an existing key keeps its position.
- Rerooting undoes a put of a *new* key with `del`, and redoes it with
  a plain assignment, which re-appends. Because a diff chain is
  replayed in chain order, the original insertion order is restored.
  A port must use an **insertion-ordered map** and restore in the same
  order; a hash map with arbitrary iteration order will not reproduce
  `map-pairs`.
- Equality: `MapValue.__eq__` compares `entries` dicts (order
  insensitive); `__hash__` is `None`, so a map is unhashable and
  cannot be a map key (§2.7 rejects it earlier anyway).
- A port is free to use any persistent map; only the *observable*
  behaviour (`map-get`, `map-pairs` order, aliasing-free persistence)
  is contractual. The rerooting is a performance choice: a fold
  threading one map pays O(1) per put/get; alternating reads of two
  versions pay the chain length each time.

---

## 3. Step accounting

This is the part a port must get bit-exact.

### 3.1 Where steps are charged

**Rule 1 — one step per evaluated node.** Every compiled node closure
(`_n_*`) does, as its *first* act, before evaluating any operand:

```
if rt.budget_stack: rt.budget_stack[-1].charge(1)
rt.steps += 1
if rt.steps > rt.max_steps: raise StepTrap(steps=rt.steps, limit=rt.max_steps)
```

This holds for **every** operator without exception, **including
literals** (`_compile_LIT_INT`, `_compile_LIT_TEXT` both charge and
tick), including `nil` and `stdin` (arity 0), and including the
generic wrapper `_n_generic` and the "not implemented" wrapper.

Consequences:

- Steps are charged **pre-order** (parent before children) and
  **before** the operator's own work.
- A node that is never evaluated (the untaken branch of `if`, the
  default of `map-get` on a hit, the operand of `quote`) costs
  nothing.
- A node evaluated *k* times (a lambda body, a loop step) costs *k*.

**Rule 2 — the extra charges.** Beyond one-per-node, `rt.steps` is
incremented in exactly these places. **None of them charges the
budget** — the budget only ever sees Rule 1. *(quirk, and a real
one: a `(budget k …)` scope does not see list-walker or loop
iteration cost.)*

| Site | Charge | Checked against `max_steps`? |
|---|---|---|
| `_call`, `LoopFn` branch | `+1` per iteration, **before** calling the predicate | yes, inline |
| `map` (0x50) | `+1` per element, before the call | yes (`_tick`) |
| `filter` (0x51) | `+1` per element, before the call | yes |
| `fold` (0x52) | `+1` per element, before the two calls | yes |
| `reverse` (0x53) | `+len(xs)` once, before reversing | yes |
| `range` (0x54) | `+max(0, b - a)` once, **before** allocating | yes |
| `any` (0x55) | `+1` per element examined (stops at the first hit) | yes |
| `sort-by` (0x56) | `+1` per **comparator invocation** (see §3.4) | yes |
| `zip` (0x57) | `+min(len(xs), len(ys))` once | yes |
| `text-match-all` (0x4F) | `+1` per match found | yes, inline |
| `trace` (0x3A) | `+inner.steps` once, in a `finally` after the sandboxed run | **no** — added after the fact, so it can push `rt.steps` past `max_steps` without trapping there |

`_tick(rt, n=1)` is `rt.steps += n; if rt.steps > rt.max_steps: raise StepTrap(...)`.

**Nothing else charges steps.** In particular:

- A **function call costs no step of its own.** `_call` charges
  nothing for a Closure application; only the body's nodes tick. The
  frame bookkeeping, the depth check and the tail-call loop are free.
- `apply` charges one step for the `apply` node, one for the head, one
  for each argument node — and then the callee's body.
- Number-theory primitives (`p`, `tau`, `sigma`, `mobius`, `gcd`) cost
  **one step** regardless of input size. Their cost is bounded by
  `MAX_NT_INPUT` instead.
- `text-len`, `text-cat`, `text-slice`, `text-find`, `text-split`,
  `text-join`, `text-chars`, `text-of-chars`, `text-cmp`, `text-int`,
  `int-text`, `text?`, `text-trim`, `text-match` cost **one step**
  each, whatever the length of the text. They are the escape hatch the
  list family's per-element cost creates.
- `map-put`, `map-get`, `map-pairs` cost **one step** each, whatever
  the size of the map.
- `hash`, `explain`, `read`, `uid`, `generation`, `ancestor-of`,
  `lineage-query`, `why`, `quote`, `clone`, `mutate` cost one step
  each — `hash` encodes the whole tree for one step, `explain` pretty
  prints it for one step.
- `eval` costs one step for the `eval` node, and then the evaluated
  program's nodes tick normally **in the same runtime** (so its steps
  and budget are the caller's).
- `defpop` / `fitness` / `select` / `retire` / `evolve` cost one step
  for their own node, plus whatever the scorer calls consume (each
  scorer application evaluates the scorer's body, which ticks
  normally). The evolution machinery itself is free.
- The prelude (`lib/prelude.lova`, 40 top-level `def`s) is a chain of
  40 `LET`s. Loading it costs **80 steps** before the program body
  runs: 1 for each `LET` node and 1 for each `LAMBDA` value node.
  Every measured count below that uses the prelude includes it.

`Runtime.charge()` and `Runtime.tick()` exist as methods but are
**dead code** — nothing calls them. *(quirk)*

### 3.2 Order relative to evaluation, and where `StepTrap` is raised

```
_n_<op>(rt):
    try:
        charge budget                 # 1. may raise BudgetTrap
        steps += 1                    # 2.
        if steps > max_steps: raise StepTrap
        <evaluate operands, run the operator>    # 3.
    except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
        _trapped(trap, rt, node)      # enrich once, at the innermost node
        raise
```

`StepTrap` and `DepthTrap` are subclasses of `BudgetTrap`, so the same
`except` catches them.

The trap is raised **inside the node that crossed the ceiling** and
enriched by the **innermost enclosing node that has a `node` local** —
which is every node except a literal (§6.1). That is why
`(merge 1 1)` with `max_steps=2` reports `position_path == (3,)`.

### 3.3 The budget stack

`(budget k body)` (0x10):

1. the `budget` node itself charges the **enclosing** budget (Rule 1);
2. `k` is evaluated (charged to the enclosing budget);
3. `Budget(limit=k)` is pushed on `rt.budget_stack`;
4. `body` is evaluated — every node in it charges the new budget *and*
   every enclosing budget? **No**: only `budget_stack[-1]` is charged.
   An inner budget scope therefore *shields* the outer one. *(quirk)*
5. the budget is popped in a `finally`, so a trap unwinds it.

`Budget.charge(cost=1)`:

```
self.spent += cost
if self.spent > self.limit: raise BudgetTrap(...)
```

`BudgetTrap`'s anomaly:

```
kind: "budget-exceeded"
detail: {"limit": L, "spent": S, "overrun": S - L}
position_path: (), offending_op: None, offending_op_name: "",
valid_alternatives: (),
repair_hint: "reduce body size (fewer operators) or raise budget to >= {spent}"
message (Exception str): "BUDGET trap: spent {spent} > limit {limit} (overrun {overrun})"
```

`(conserve expected body)` (0x11) is not a counter but an equality
contract: `expected` and `body` are both evaluated and coerced to
`Int`; if they differ, a `DeltaTrap` is raised carrying a
`body_offender` computed by probing (§5.3). See §6 for the anomaly.

### 3.4 `sort-by` and the host sort *(quirk — the worst one)*

```
def compare(a, b):
    _tick(rt)                                 # one step per invocation
    ab = _as_int(_call(_call(less, a, rt), b, rt), "sort-by") != 0
    ba = _as_int(_call(_call(less, b, rt), a, rt), "sort-by") != 0
    return -1 if ab and not ba else (1 if ba and not ab else 0)
return list_from(sorted(xs, key=functools.cmp_to_key(compare)))
```

- Each `compare` call charges **1 step** and makes **4** `_call`s
  (two curried applications of a two-argument comparator), so it costs
  `1 + 2 * (cost of one (less a b) application)` steps.
- Both directions are probed so that a `le` comparator sorts as `lt`
  does, and the sort is stable either way.
- **The number of `compare` calls is CPython's Timsort's.** Measured:
  an already-sorted or reverse-sorted list of *n* takes exactly *n−1*
  comparisons; `[3, 1, 2]` takes **4**; `[3, 1, 2, 5, 4]` takes **8**.
  A port that uses a different sort will produce different step
  counts. To be exact it must reimplement CPython's `list.sort`
  (Timsort with binary insertion for short runs, galloping merge,
  minrun computation) and drive it through the same
  `cmp_to_key`-style single-`__lt__` protocol — `cmp_to_key` maps each
  `<` the sort performs to exactly one `compare` call.

### 3.5 Worked examples

All three were run with
`Runtime()` + `evaluate(parse(...))` / `evaluate(parse_with_prelude(...))`
and `rt.steps` read afterwards.

#### (a) `(merge 1 (mul 2 3))` → value `7`, **steps = 5**

No prelude. The tree is `merge(lit 1, mul(lit 2, lit 3))`, 5 nodes:

| # | node | step |
|---|---|---|
| 1 | `merge` | 1 |
| 2 | `lit 1` | 2 |
| 3 | `mul` | 3 |
| 4 | `lit 2` | 4 |
| 5 | `lit 3` | 5 |

`5 nodes × 1 = 5`. Nothing else charges: `merge` and `mul` add no
per-operand cost, and `mul`'s bit-length guard is free.

#### (b) `(map inc (list 1 2 3))` with the prelude → value `(2 3 4)`, **steps = 101**

```
101 = 80  (prelude: 40 LET nodes + 40 LAMBDA value nodes)
    +  9  (the program's own nodes, evaluated once)
    +  3  (map's per-element tick, 1 x 3 elements)
    +  9  (three applications of `inc`, 3 body nodes each)
```

The program desugars to
`(map (ref inc) (cons 1 (cons 2 (cons 3 (nil)))))` and sits in the
prelude's `LET` body, so the prelude's final body literal is replaced
by it (hence 80, not 81).

The 9 own nodes: `map` 1, `ref inc` 1, `cons` ×3 = 3, `lit` ×3 = 3,
`nil` 1.

`inc` is `(def inc [n] (merge n 1))` →
`(lambda n (merge (ref n) (lit 1)))`. Its body is 3 nodes: `merge`,
`ref n`, `lit 1`. The `lambda` node itself was already counted among
the prelude's 40 value nodes. A call costs no step of its own, so
`3 calls × 3 nodes = 9`.

Check: `80 + 9 + 3 + 9 = 101`. ✓
(The same program written without the prelude —
`(map (lambda x (merge (ref x) 1)) (cons 1 (cons 2 (cons 3 (nil)))))` —
costs `21`: 9 own nodes + 1 for the `lambda` node + 3 ticks + 9 body,
i.e. `10 + 3 + 9`.)

#### (c) `(def f [n] (if (gt n 0) (f (sub n 1)) 0))` then `(f 10)` with the prelude → value `0`, **steps = 191**

```
191 = 80   (prelude)
    +  1   (the LET that binds f)
    +  1   (the LAMBDA value)
    +  3   (the call site: `apply` 1, `ref f` 1, `lit 10` 1)
    + 100  (10 recursive calls with n = 10..1, 10 nodes each)
    +  6   (the last call, n = 0, taking the else branch)
```

`gt` and `sub` are surface macros, not operators:
`(gt a b)` → `(threshold (deviation a b))`, `(sub a b)` → `(deviation a b)`.
So the body is

```
(if-surprise (threshold (deviation (ref n) (lit 0)))
             (apply (ref f) (deviation (ref n) (lit 1)))
             (lit 0))
```

Per call, the test costs 5 nodes: `if-surprise` 1, `threshold` 1,
`deviation` 1, `ref n` 1, `lit 0` 1.

- **then-branch** (n > 0): `apply` 1, `ref f` 1, `deviation` 1,
  `ref n` 1, `lit 1` 1 = 5. Total **10** per call. Ten such calls
  (n = 10, 9, …, 1): **100**.
- **else-branch** (n == 0): `lit 0` = 1. Total **6**. One such call:
  **6**.

Check: `80 + 1 + 1 + 3 + 100 + 6 = 191`. ✓

Note that the recursive `apply` is in **tail position** (lambda body →
`if` branch), so `call_depth` never exceeds 1 — the step count is
unaffected by that, but the depth ceiling is.

---

## 4. Call semantics

### 4.1 `_call(fn, argument, rt)` in full

```
while True:
    if fn is a LoopFn:
        value = argument
        pred, step = fn.pred, fn.step
        loop forever:
            rt.steps += 1
            if rt.steps > rt.max_steps: raise StepTrap(rt.steps, rt.max_steps)
            verdict = _call(pred, value, rt)
            if not an int: verdict = _as_int(verdict, "loop-until predicate")
            if verdict != 0: return value
            value = _call(step, value, rt)

    if fn is not a Closure: raise _not_callable(fn)

    # --- hot attribution (Exp 20) ---
    if fn.name is not None: fn.calls += 1; me = fn
    else:                   me = fn.owner
    outer = rt.current
    if me is not outer:
        s = rt.steps
        if outer is not None: outer.own += s - rt.mark
        rt.mark = s
        rt.current = me

    # --- depth ---
    rt.call_depth += 1
    if rt.call_depth > rt.max_call_depth:
        d = rt.call_depth; rt.call_depth -= 1
        raise DepthTrap(depth=d, limit=rt.max_call_depth)

    # --- frame ---
    scope = new Scope; scope.parent = fn.env; scope[fn.param] = argument
    save rt.env, rt.caps, rt.enclosed
    rt.env = scope; rt.caps = fn.caps; rt.enclosed = fn.enclosed
    try:
        result = (fn.code or (fn.code = _code_tail(fn.body, rt)))(rt)
    finally:
        restore rt.env, rt.caps, rt.enclosed
        rt.call_depth -= 1
        if me is not outer:
            s = rt.steps
            if me is not None: me.own += s - rt.mark
            rt.mark = s
            rt.current = outer

    if result is not a TailCall: return result
    fn, argument = result.fn, result.arg          # loop: the tail call
```

Points a port must reproduce:

- **One parameter per call.** Multi-argument functions are curried;
  `(apply f a b)` is `_call(_call(f, a), b)`.
- A call charges **no step**.
- The frame is a new `Scope` whose `parent` is the closure's captured
  environment — *not* the caller's. Lexical scoping.
- `rt.caps` and `rt.enclosed` are taken from the closure, so a
  boundary is **lexical**: a lambda written inside
  `(boundary "fs-read" …)` may read files wherever it is applied.
- `rt.env` / `rt.caps` / `rt.enclosed` / `call_depth` are restored in
  a `finally`, so a trap leaves the runtime consistent.
- `DepthTrap` is raised **after** decrementing back, so
  `rt.call_depth` at trap time is the pre-call value while the
  anomaly's `spent` is the attempted depth.

### 4.2 Scope

```
class Scope(dict):
    parent: Scope | dict | None
    __missing__(key): walk parent chain (iteratively); a plain dict at
        the root answers with its own lookup or KeyError; None -> KeyError
    bound(key): True iff key is in this frame or any ancestor
    `in` tests THIS frame only
```

`flatten_env(env)` collapses the chain into one dict, **inner frames
winning** (it walks out to the root, then updates from root inwards).
Used by: `unbound-ref`'s `bound_names`, `conserve`'s body probe, and
`trace`'s sandbox.

The root environment is a plain `dict` (`Runtime.env`), not a `Scope`.

### 4.3 The `let` chain rule (letrec and binding groups)

`_compile_LET` produces `_n_let`, which behaves as:

```
chained = (rt.let_chain is _n_let)       # read FIRST, before anything
charge + tick
saved_env = rt.env
extend = chained and saved_env.__class__ is Scope and not saved_env.bound(name_id)
if extend: scope = saved_env
else:      scope = new Scope with parent = saved_env; rt.env = scope
try:
    value = value_code(rt)                      # evaluated with the scope ALREADY installed
    if value is a Closure and value.name is None:
        value.name = name_id
        rt.named.append(value)
    scope[name_id] = value                      # bound AFTER the value exists
    rt.let_chain = body_code                    # the body may continue the group
    return body_code(rt)
finally:
    rt.let_chain = None
    if not extend: rt.env = saved_env
```

What this buys:

- **letrec.** The scope is installed before the value is evaluated, so
  a `lambda` in the value slot captures it by reference; the binding is
  written into that same frame after the closure exists. A
  self-recursive function therefore resolves at apply time.
- **Binding groups / mutual recursion.** `rt.let_chain` is set to the
  body's compiled closure just before the body runs. If the body *is*
  a `LET`, that `LET` sees `rt.let_chain is <itself>` and `chained` is
  true, so it writes into the **same frame**. A chain of `def`s
  therefore shares one frame and every function in the group sees
  every other, in any order.
- **A `LET` anywhere else opens its own frame.** In an argument
  position, inside a lambda body, inside a loop step — `rt.let_chain`
  holds another node's closure or `None`.
- **Shadowing breaks the chain.** `extend` requires
  `not saved_env.bound(name_id)`: re-binding a name the enclosing
  chain already holds opens a fresh frame, so an earlier closure in
  the group does not see the rebinding.
- The first `LET` under the root `dict` environment always opens a
  frame (`saved_env.__class__ is Scope` is false for a plain dict).
- `rt.let_chain` is cleared to `None` in the `finally`, unconditionally.
- **A closure gets its `name`** the first time a `LET` binds it and
  only if it does not already have one, and is appended to `rt.named`
  at that moment. This is what `hot` reports on.

### 4.4 Tail calls (M32)

`_code_tail(node, rt)` compiles a node **in tail position**. Only four
operators have a tail compiler; anything else falls back to `_code`:

| Form | What it passes tail position to |
|---|---|
| `lambda` (0x2C) | its **body** — the root of every tail chain |
| `if-surprise` (0x2A) | **both** branches (not the test) |
| `seq` (0x28) | its **last** child only (and only if non-empty) |
| `let` (0x2E) | its **body** (not its value) |
| `apply` (0x2D) | — it is the *consumer*: in tail position it returns a `TailCall` |

`_n_apply_tail` (only when the node has at least one argument):

```
charge + tick
fn = head(rt)
for code in all-but-last arguments: fn = _call(fn, code(rt), rt)
if fn is not a Closure and not a LoopFn: raise _not_callable(fn)
return TailCall(fn, last(rt))         # the LAST argument is evaluated here
```

So `(apply f a b)` in tail position makes the `a` application eagerly
and hands back only the final one. `(apply f)` (no arguments) is not a
tail call — it compiles as an ordinary apply and yields `f`.

**What is NOT tail position** (a call there keeps its frame):

- an operand of any other operator — `(merge 1 (apply f x))`;
- the value slot of a `let`;
- the test of an `if-surprise`;
- any child of `seq` but the last;
- the body of `conserve`, `budget`, `when-anomaly`, `external-boundary`
  (these use the generic compiler, which never asks for tail
  position);
- anything inside `map` / `filter` / `fold` / `any` / `sort-by` — those
  call through `_call` themselves;
- a `loop-until` predicate or step.

Caches: a node compiled for tail position lives in `rt.tail_cache`; a
node compiled normally lives in `rt.code_cache`. A node has one
parent, so in a given run it is normally one or the other; both caches
exist so that a probe or a `trace` sandbox that evaluates a sub-tree
on its own can meet a tail-compiled body outside a call frame. Both
caches are keyed by `id(node)` with the node itself stored alongside
so an id cannot be reused, and both are **cleared at the start of
every `evaluate`** — a tree edited in place between runs is
recompiled.

`Closure.code` is cached **on the closure**, not in the runtime, so a
function value survives across runtimes (`tests/test_compiled.py`
pins this).

Depth consequence: `test_depth_trap_path_is_one_apply_per_frame` uses
`(merge 1 (apply (ref 0) (ref 1)))` precisely because the `merge`
keeps the frame; if the call were in tail position the recursion would
be a loop and never reach the ceiling.

### 4.5 `hot` attribution

Per-`Closure` counters: `owner` (the named closure whose body created
this anonymous lambda — `rt.current` at `lambda`-evaluation time),
`calls`, `own`.

- A **named** closure (one a `LET` bound) is its own attribution
  target and increments `calls` on every application.
- An **anonymous** lambda attributes to its `owner`, and increments no
  call count.
- `rt.current` is the function whose body is running; `rt.mark` is
  `rt.steps` at the moment `current` last changed. Changing `current`
  settles the open interval into the outgoing function's `own`.
  A self-recursive call costs one identity comparison and no
  bookkeeping.

`_cost_by_function(rt)` (called only when a `StepTrap` or `DepthTrap`
is enriched):

```
open_steps = rt.steps - rt.mark
for fn in rt.named:
    own = fn.own + (open_steps if fn is rt.current else 0)
    steps[fn.name] += own ; calls[fn.name] += fn.calls
hot = the 8 largest by steps (sorted descending, ties by dict order)
return [[name_id, steps, calls] for each with steps > 0]
```

The result is written to `anomaly["detail"]["calls"]` — note the key
is `"calls"` although the `StepTrap` repair hint calls it `hot`.
*(quirk)*

Two closures bound to the same name id (a `def` evaluated twice)
collapse into one row.

### 4.6 `LoopFn`

`(loop-until pred step)` evaluates both slots, checks both are
callable, and returns `LoopFn(pred, step)` — it does **not** iterate.
The seed arrives through `apply`. Iteration happens in `_call`
(§4.1): a Python `while`, so a loop of a million rounds costs **one**
call frame and never touches `max_call_depth`. `max_steps` is what
stops a non-terminating loop.

Per round: **1 step** for the round itself, plus the predicate
application's body, plus (if not stopping) the step application's body.

---

## 5. Operators

Legend for the tables: **args** is the arity; **order** is left to
right unless stated. Every operator charges one step and one budget
unit before doing anything (§3.1); that is not repeated per row.
All fault `kind` strings, messages and hints are verbatim.

### 5.0 Universal faults

Any operator whose operand coercion fails raises the `DomainTrap` of
§2.4 with `ctx` equal to the operator's **name as spelled below**
(`"merge"`, `"text-slice"`, `"loop-until predicate"`, `"fitness"`, …).

An operator with no handler (`END`, 0x00) raises a plain Python
`NotImplementedError`:

```
operator {name} (family {family}) not implemented in Milestone 1 runtime
```

This is **not** a LOVA anomaly — it is not caught by `when-anomaly`
and carries no anomaly dict. 87 of the 88 tokens are implemented;
`END` is the one that is not.

### 5.1 Structural (0x00–0x07)

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x00 | `end` | 0 | variadic terminator only; evaluating it raises `NotImplementedError` (§5.0) |
| 0x01 | `lit` | payload | returns the payload integer. Charges/ticks but takes **no position-path entry** (§6.1) |
| 0x02 | `partition` | 1 | `_as_int(x, "partition") // 2` (floor) |
| 0x03 | `merge` | 2 | `_as_int(a, "merge") + _as_int(b, "merge")`; left evaluated and coerced, then right |
| 0x04 | `cons` | 2 | see below |
| 0x05 | `head` | 1 | see below |
| 0x06 | `tail` | 1 | see below |
| 0x07 | `identity` | 1 | returns the operand unchanged — **no coercion**, so it passes lists, texts, closures, maps through |

**`cons x xs`** — `x` evaluated first, then `xs`:

```
if xs is a str:
    if x is a non-bool int in [0, 0x10FFFF]: return chr(x) + xs        # stays a text
    else: xs = codepoints(xs)                                          # becomes a list
elif xs is not NIL and not a Cons: xs = _as_list(xs, "cons")           # raises
return Cons(x, xs)
```

So consing a codepoint onto a text keeps it a text (O(1) in LOVA
terms, O(n) in the reference); consing anything else onto a text
explodes the text into a codepoint list first.

**`head xs`**:

```
Cons            -> .head
non-empty str   -> ord(xs[0])
otherwise       -> xs = _as_list(xs, "head")   # a text becomes its codepoints (empty -> NIL)
                   if xs is NIL: DomainTrap "domain-error"
                     "head: the list is empty; guard with `nil?` before taking a head"
                     detail {"operator": "head"}
                     hint "guard with `(if (nil? xs) fallback (head xs))`; reached through `nth` or `last`, the index is past the end"
                   return xs.head
```

(The generic `_op_HEAD`, reachable only from a mis-aried hand-built
tree, has the same message but the shorter hint
`"guard with `(if (nil? xs) fallback (head xs))`"`.)

**`tail xs`**:

```
Cons           -> .tail
non-empty str  -> xs[1:]                       # stays a text
otherwise      -> _as_list, and if NIL:
                  "domain-error", "tail: the list is empty; guard with `nil?` before taking a tail"
                  detail {"operator": "tail"}
                  hint "guard with `(if (nil? xs) fallback (tail xs))`"
```

### 5.2 Number theory (0x08–0x0F)

All five number-theoretic functions guard their **input** at
`MAX_NT_INPUT = 2000` and cost one step.

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x08 | `p` | 1 | partitions of *n*, Euler's pentagonal recurrence. `n < 0` → `0`; `n == 0` → `1` |
| 0x09 | `tau` | 1 | divisor count. `n <= 0` → `0` |
| 0x0A | `sigma` | 1 | divisor sum. `n <= 0` → `0` |
| 0x0B | `mul` | 2 | `a * b`, output-guarded |
| 0x0C | `mod` | 2 | `a % b` (Python floor semantics, §2.5) |
| 0x0D | `div` | 2 | `a // b` (Python floor semantics) |
| 0x0E | `gcd` | 2 | `math.gcd(a, b)` — non-negative, `gcd(0,0)==0` |
| 0x0F | `mobius` | 1 | μ(n). `n <= 0` → `0`; `n == 1` → `1`; `0` if a squared prime divides |

Faults:

```
p / tau / sigma / mobius, n > 2000:
  "domain-error", "{fn} input {n} exceeds MAX_NT_INPUT=2000"
  detail {"operator": "<partition_number|tau|sigma|mobius>", "input": n, "limit": 2000}
  hint "reduce the argument below 2000"
```

Note `p`'s detail operator name is `"partition_number"`, not `"p"`,
and its message begins `partition_number input …`. *(quirk)*

```
mul, a.bit_length() + b.bit_length() > 4096:
  "domain-error",
  "mul result would exceed MAX_INT_BITS=4096 ({abits} + {bbits} bits)"
  detail {"operator": "mul", "limit": 4096}
  hint "multiply smaller numbers"

div, b == 0:
  "domain-error", "div: division by zero", detail {"operator": "div"}
  hint "guard the divisor with `(if d (div a d) fallback)`"

mod, b == 0:
  "domain-error", "mod: division by zero", detail {"operator": "mod"}
  hint "guard the divisor with `(if d (mod a d) fallback)`"
```

Evaluation order for the binary ones: left operand evaluated **and
coerced**, then right operand evaluated and coerced, then the guard,
then the arithmetic.

### 5.3 Conservation (0x10–0x17)

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x10 | `budget` | 2 | §3.3. Result is the body's value (uncoerced) |
| 0x11 | `conserve` | 2 | equality contract; see below |
| 0x12 | `signal` | 1 | raises a program-defined anomaly |
| 0x13 | `map-put` | 3 | `(map-put m k v)` |
| 0x14 | `map-get` | 3 | `(map-get m k default)` |
| 0x15 | `nil` | 0 | `NIL_VALUE` |
| 0x16 | `map-pairs` | 1 | `(list k v)` per entry, insertion order |
| 0x17 | `violate` | 1 | `_as_int(x, "violate") + 1` — a test operator that always breaks a `conserve` |

**`conserve expected body`.** `expected` and `body` are both evaluated
and `_as_int`-coerced (`ctx == "conserve"`). If equal, the result is
`actual`. If not:

1. `_scan_body_offender(node.args[1], expected, actual, flatten_env(rt.env))`
   probes for a single-node edit that closes the deviation (below);
2. a `DeltaTrap` is raised with

```
kind: "conservation-violated"
detail: {"invariant": "conserve/equality", "entry": expected,
         "exit": actual, "deviation": actual - expected}
position_path: (), offending_op: None, offending_op_name: "",
valid_alternatives: (), body_offender: <dict or None>,
repair_hint:
  if no offender: "body produced a value different from the expected conserve target; replace the divergent op with one that preserves the value"
  if an offender: "body-offender `{op_name}` at path {path} returns {observed}; needs {needed} (correction {correction:+d}) to restore the conserve invariant"
message: "Delta trap: conserve/equality violated -- entry {entry} vs exit {exit}"
```

`_scan_body_offender` (Q20, M6 Day 2) — deterministic, O(n²) in body
size, runs **only** on a Δ-trap:

- give up unless both `expected` and `actual` are ints and
  `deviation = actual - expected` is non-zero;
- collect `(path, node, depth)` for every `Node` subtree, path being
  the tuple of argument indices from the body root;
- probe every subtree's value with a **fresh `Runtime`** seeded with
  `dict(env)` (so no steps, budget or output of the probe reach the
  real run); a probe that raises anything, or yields a non-int, is
  recorded as unknown;
- order candidates deepest-first, ties by path lexicographically;
- **Pass A (operator swap):** for each non-`LIT_INT` subtree, for each
  `alt` in `suggest_alternatives(sub.op)` in order, rebuild the body
  with the op replaced and probe; the first that makes the body equal
  `expected` wins. Returns
  `{op, op_name, path, depth, observed, needed, correction, fix: "operator-swap", alternative_op, alternative_op_name}`
  where `needed` is the swapped subtree's own value and `correction`
  is `needed - observed` (0 if either is unknown);
- **Pass B (literal replacement):** for each subtree with a known
  value (skipping non-root `LIT_INT`s), replace it with
  `LIT_INT(observed - deviation)` and probe. First hit wins, with
  `fix: "literal-replacement"` and `correction = needed - observed`;
- **Fallback:** the deepest non-root subtree whose own value *equals*
  the deviation, with `fix: "heuristic-value-equals-deviation"`,
  `observed = deviation`, `needed = 0`, `correction = -deviation`;
- else `None`.

`suggest_alternatives(op)` (from `core/observability.py`):

```
VIOLATE            -> (IDENTITY,)
{P, TAU, SIGMA, MOBIUS}, {MERGE, GCD}, {IDENTITY, PARTITION},
{MUL, MOD, DIV}, {HEAD, TAIL}, {DEVIATION, THRESHOLD}
                   -> tuple(sorted(group - {op}))
anything else      -> ()
```

**`signal code`**:

```
code = _as_int(x, "signal")
if code < 16 (FIRST_PROGRAM_SIGNAL):
    "domain-error", "signal: codes below 16 are the substrate's own kinds"
    detail {"operator": "signal", "code": code, "first_allowed": 16}
    hint "signal with a code of 16 or more"
else:
    "signalled", "signal {code}", detail {"operator": "signal", "code": code}
    hint "catch it with `when-anomaly` and branch on the code"
```

`signal` never returns.

**`map-put m k v`** — `m` evaluated and `_as_map`'d, then `k`, then
`v`. Returns a new `MapValue`; `m` keeps its meaning.

**`map-get m k default`** — `m` evaluated and `_as_map`'d, then `k`.
`entries.get(_map_key(k))`; **the default expression is evaluated only
on a miss**, and its steps are charged only then. The stored value is
returned as-is, whatever its kind.

*(quirk)* A stored value that is Python-`None` is indistinguishable
from a miss (`hit is None`). No LOVA operator produces `None`, so this
is unreachable from a program.

**`map-pairs m`** — `list_from([list_from([k, v]) for k, v in m.entries.values()])`,
insertion order.

### 5.4 Surprise (0x18–0x1F)

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x18 | `surprise` | 2 | `dev = abs(p - a)`; appends `{"predicted": p, "actual": a, "deviation": dev, "ctx": "surprise"}` to the trace; returns `dev` |
| 0x19 | `nil?` | 1 | §2.3 |
| 0x1A | `when-anomaly` | 2 | see below |
| 0x1B | `threshold` | 1 | `1 if _as_int(x, "threshold") > 0 else 0` |
| 0x1C | `eval` | 1 | `_as_program(x, "eval")` then evaluate **in the caller's runtime and environment** |
| 0x1D | `trace-surprise` | 1 | `v = _as_int(x, "trace-surprise")`; emits `{predicted: 0, actual: v, deviation: abs(v), ctx: "trace-surprise"}`; returns `v` |
| 0x1E | `read` | 1 | `_as_text(x, "read")` then `core.surface.parse` → a Program |
| 0x1F | `deviation` | 2 | §2.6 |

**`when-anomaly body handler`**:

```
try: return eval(body)
except StepTrap: raise                       # DELIBERATELY NOT CAUGHT
except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
    anomaly = trap.anomaly                   # if absent, re-raise
    code = anomaly_code(anomaly)
    rt.caught.append(anomaly)
    rt.surprise.emit(0, code, ctx="when-anomaly")     # a handled fault is still observed
    handler = eval(node.args[1])             # the handler expression is evaluated HERE, after the fault
    return _call(handler, code, rt)
```

- It catches `BudgetTrap` (and therefore **`DepthTrap`**), `DeltaTrap`
  and `DomainTrap` — i.e. every kind except `step-limit-exceeded`.
  The step ceiling is the substrate's termination guarantee and a
  guarantee a program can mask is not one.
- It does **not** catch `NotImplementedError` or any bare Python
  exception (`ValueError` from `int()`, `TypeError` from a mixed
  `text-cmp`).
- The handler receives **one integer**: `anomaly_code(anomaly)` —
  the kind's code from `ANOMALY_CODES`, except for a `"signalled"`
  anomaly, where it is the program's own `detail["code"]`.
- The handler expression's own evaluation is charged after the body
  failed; a handler that itself traps propagates.
- The surprise event and `rt.caught` entry are the audit trail: a
  handled fault is not an invisible one.

**`read`** wraps a surface parse failure:

```
"malformed", "read: {exc}"
detail {"operator": "read", "source": source[:80]}
hint "give `read` text that `explain` could have produced"
```

(Only `ValueError` from the parser is converted.)

### 5.5 Evolution (0x20–0x27)

The runtime's own `Population` is
`{scorer: Fn, variants: list[Node], generation: int}` and is
**immutable** — `evolve` and `retire` return new pools.

Scoring (`_score_population`): for each variant, in pool order,
`_as_int(_call(scorer, variant, rt), "fitness")`. **Lower is
fitter.** A `StepTrap` propagates (the ceiling is not a fitness
signal); a `BudgetTrap` / `DeltaTrap` / `DomainTrap` is appended to
`rt.caught` and the variant scores `UNFIT = 1 << 62`.

Ranking (`_rank_population`): `sorted(range(n), key=lambda i: (scores[i], i))`
— fittest first, **ties keep pool order**.

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x20 | `defpop` | variadic | see below |
| 0x21 | `variant` | 2 | `(variant pop k)` — the *k*-th variant in **pool** order |
| 0x22 | `evolve` | 1 | one generation; see below |
| 0x23 | `select` | 2 | `(select pop k)` — the *k*-th **fittest** (0 = best) |
| 0x24 | `mutate` | 2 | `(mutate program percent)` |
| 0x25 | `clone` | 1 | registers the program if needed, then `lineage.clone` |
| 0x26 | `fitness` | 1 | every variant's score as a list, in pool order |
| 0x27 | `retire` | 1 | the pool without its least-fit member, same generation |

**`defpop scorer p1 p2 …`**:

```
no args            -> "malformed", "defpop: missing scorer",
                      detail {"operator": "defpop"},
                      hint "give `defpop` a scorer function and at least one program"
scorer not callable-> "type-violation", "defpop: the scorer must be a function, got {scorer!r}",
                      detail {"operator": "defpop", "expected": "Fn"},
                      hint "pass a lambda from Program to Int as the first argument"
each remaining arg: a list value is SPLICED (each element must be a Program),
                    otherwise the value itself must be a Program
no variants        -> "domain-error", "defpop: a population needs at least one variant",
                      detail {"operator": "defpop"}, hint "quote at least one program"
every variant is registered as a lineage root if it has no uid
```

**`variant` / `select` range faults**:

```
variant: "domain-error", "variant: index {k} out of range for a pool of {n}"
         detail {"operator": "variant", "index": k, "size": n}
         hint "index from 0 to one less than the pool size"
select:  "domain-error", "select: rank {k} out of range for a pool of {n}"
         detail {"operator": "select", "rank": k, "size": n}
         hint "rank 0 is the fittest; the last rank is the pool size less one"
```

`select` scores the whole pool first (so its cost is *n* scorer runs).

**`retire`**:

```
len(variants) < 2 -> "domain-error", "retire: cannot retire the last variant"
                     detail {"operator": "retire", "size": n}
                     hint "a population keeps at least one variant"
else: rank, drop order[-1] (the least fit), keep the rest IN POOL ORDER,
      generation unchanged
```

**`mutate program percent`**:

```
percent = _as_int(...); if not 0 <= percent <= 100:
  "domain-error", "mutate: strength {percent} is not a percentage"
  detail {"operator": "mutate", "strength": percent}
  hint "give a strength between 0 and 100"
register the program if needed; return lineage.mutate(program, strength=percent/100)
```

**`evolve pop`** — one generation, the rule matching
`core/populations.py`'s defaults:

```
size < 2 -> "domain-error", "evolve: a population of one cannot evolve"
            detail {"operator": "evolve", "size": size}
            hint "start with at least two variants"

scores, order = rank(pop)
n_retire  = max(1, int(size * 0.2))                 # RETIRE_FRACTION
survivors = order[:size - n_retire]                 # fittest first
clamp     = [min(scores[i], 10**9) for i in survivors]
worst_kept= max(clamp)
weights   = [(worst_kept - c + 1) ** 3 for c in clamp]     # SELECTION_SHARPNESS
# A port may hold a weight in a fixed width: the clamp bounds it above,
# and the native runtime uses i128 with saturation, which only differs
# from Python's bignum for a variant scoring below about -10^12.
rng       = rt.lineage._rng                         # random.Random(seed), seed 0 by default
for _ in range(n_retire):
    pick = rng.random() * sum(weights)
    acc = 0.0; chosen = survivors[-1]
    for idx, weight in zip(survivors, weights):
        acc += weight
        if pick <= acc: chosen = idx; break
    parent = pop.variants[chosen]
    if rng.random() < 0.3:  child = lineage.clone(parent)       # CLONE_PROBABILITY
    else:                   child = lineage.mutate(parent, strength=0.3)  # EVOLVE_STRENGTH
kept = [v for i, v in enumerate(pop.variants) if i in set(survivors)]   # POOL order
return Population(scorer, kept + children, generation + 1)
```

**Randomness.** The only source is `LineageStore._rng`, a
`random.Random(seed)` with `seed = 0` by default, created once per
`LineageStore` (one per `Runtime` unless shared). It is consumed by
`evolve` (two `random()` draws per child, in the order shown) and by
`_mutate_inplace`. A run is therefore reproducible, and **a port must
reproduce the Mersenne Twister stream of CPython's `random.Random`**
to match a recorded run exactly: `random()` is
`(a*2^26 + b) * 2^-53` from two 32-bit outputs (`a = genrand()>>5`,
`b = genrand()>>6`), `randint(-5, 5)` goes through `_randbelow(11)`
(rejection sampling on `getrandbits(4)`), and `choice(seq)` is
`seq[_randbelow(len(seq))]`. If exactness is not required, a port may
substitute any PRNG — but then evolution results diverge.

**`LineageStore`** (`core/lineage.py`):

- uids from `itertools.count(1)`; the uid is stored on the `Node` as
  an attribute, never in the bytes.
- `register_root(node, notes)` → record `{uid, parent_uid: None,
  root_uid: uid, generation: 0, mutation_kind: "root",
  created_at: time.time(), notes}`.  `created_at` is host-side: nothing
  in the language reads it (`why` prints `mutation_kind` and `notes`),
  and a port need not keep it (the native runtime does not).
- `clone(parent)` → `_deep_copy_node` + child record with
  `mutation_kind "clone"`, `generation = parent.generation + 1`.
  Raises a bare `ValueError("parent must be registered before clone()")`
  if the parent has no uid (the runtime always registers first).
- `mutate(parent, strength, kind="auto")` → deep copy, then
  `_mutate_inplace`, then a child record with `mutation_kind "mutate"`
  and `notes = f"strength={strength} [{applied}]"` where `applied` is
  the comma-joined mutation log or `"no-op"`.
- `_deep_copy_node`: `LIT_INT` copies its scalar payload; every other
  node copies children recursively and passes non-`Node` args
  (a `LIT_TEXT`'s `str`) through by reference. The copy's `uid` is
  `None`.
- `_mutate_inplace(node, rng, strength, kind, log)`:

```
if rng.random() < strength:
    effective = kind; if kind == "auto": effective = rng.choice(["literal", "operator"])
    if effective == "literal" and node.op == LIT_INT:
        delta = rng.randint(-5, 5); while delta == 0: delta = rng.randint(-5, 5)
        node.args[0] = old + delta ; log "lit:{old}->{new}"
    elif effective == "operator":
        g = swap group of node.op            # {P,TAU,SIGMA,MOBIUS} or {MERGE,GCD}
        if g and len(g) > 1:
            new_op = rng.choice(sorted(g - {node.op}))
            log "op:{old_name}->{new_name}"
if node.op != LIT_INT: recurse into every Node child, in order
```

Note the mutation swap groups are **narrower** than the repair
suggestion groups: only `{P, TAU, SIGMA, MOBIUS}` and `{MERGE, GCD}`.

`core/populations.py` is a **host-side** driver, not reachable from
LOVA: its own `Population` class dispatches variants by rolling mean
fitness (**higher is better** there — the opposite convention), with
`window_size=10`, `alpha=3.0`, warmup that dispatches every unseen
variant once, `rng = random.Random(0)`, and
`evolve(retire_frac=0.2, clone_prob=0.3, mutation_strength=0.3)`
retiring the bottom fraction of *dispatched* variants and refilling by
`weights = max(1e-6, mean - min + 1.0) ** alpha`. A failed evaluation
scores `-1e9`. A port needs this only if it reimplements the Python
experiment harness.

### 5.6 Composition (0x28–0x2F)

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x28 | `seq` | variadic | evaluates every child left to right; returns the **last** value, or `0` when empty. No coercion |
| 0x29 | `quote` | 1 | **does not evaluate** its operand; returns `_deep_copy_node(operand)` — a fresh tree with `uid = None`, so registering or mutating it never reaches back into the containing program |
| 0x2A | `if-surprise` | 3 | `_as_int(test, "if-surprise") != 0` → branch 1 else branch 2. Only one branch is evaluated |
| 0x2B | `loop-until` | 2 | §4.6 |
| 0x2C | `lambda` | 2 | builds a `Closure(param, body, env=rt.env, caps=rt.caps, enclosed=rt.enclosed, code=<body compiled for tail position>, owner=rt.current)` |
| 0x2D | `apply` | variadic | §4.4; ordinary form: evaluate head, then for each argument evaluate it and `_call`. Zero arguments yields the head value unchanged |
| 0x2E | `let` | 3 | §4.3 |
| 0x2F | `ref` | 1 | `rt.env[name_id]`; a `KeyError` becomes `unbound-ref` |

`loop-until` type fault:

```
"type-violation",
"LOOP_UNTIL: both slots must be functions (type Fn); got pred={pred!r}, step={step!r}"
detail {"operator": "loop-until", "expected": "Fn"}
hint "pass two lambdas: a predicate and a step"
```

`apply` on a non-function (`_not_callable`):

```
"type-violation",
"apply: head slot is not a function (got {fn!r}); only `lambda` and `loop-until` produce callable values"
detail {"operator": "apply", "expected": "Fn"}
hint "apply a `lambda` or a `loop-until`, or a name bound to one"
```

`ref` on an unbound name (`_unbound`):

```
"unbound-ref", "unbound ref: {name_id}"
detail {"name_id": name_id, "bound_names": sorted(flatten_env(rt.env))}
hint "bind the name with a `let`, or reference one that is bound"
```

`bound_names` is the sorted list of **every** name id visible from the
current environment — the CLI prunes and renders it; the runtime emits
the raw ids.

Malformed shapes (generic handlers, reachable only from hand-built
trees):

```
LET name slot not LIT_INT:
  "malformed", "LET: name slot must be a literal integer id",
  detail {"operator": "let", "slot": 0}, hint "put a literal integer in LET's first slot"
LAMBDA param slot not LIT_INT:
  "malformed", "LAMBDA: param slot must be a literal integer id",
  detail {"operator": "lambda", "slot": 0}, hint "put a literal integer in LAMBDA's first slot"
REF name slot not LIT_INT:
  "malformed", "REF: name slot must be a literal integer id",
  detail {"operator": "ref", "slot": 0}, hint "put a literal integer in REF's slot"
APPLY with no args:
  "malformed", "APPLY: missing function in head slot",
  detail {"operator": "apply"}, hint "give `apply` a function to call"
```

### 5.7 Effects / IO (0x30–0x37)

Capability bits (`CAPABILITY_BITS`):

```
fs-read  = 1
fs-write = 2
clock    = 4
net      = 8
ALL_CAPABILITIES = 1 | 2 | 4 = 7      # `net` is NOT in `all`
```

`CAPABILITY_OF`: `fs-read`→1, `fs-write`→2, `clock`→4,
`net-send`→8, `net-recv`→8.

Two independent masks on the runtime:

- `rt.granted` — what the **host** allows this run. Default `0`:
  nothing. The CLI's `--allow` builds it (`fs-read`, `fs-write`,
  `clock`, `all`, `net=host:port`, `net=:port`; bare `net` is refused
  with `--allow: the network is granted by place: net=host:port to
  send there, net=:port to listen`).
- `rt.caps` — what the **innermost `external-boundary`** declared.
  Default `0`. `rt.enclosed` says whether any boundary is open.

**`external-boundary caps body`** (0x30):

```
args[0] must be a LIT_INT, else:
  "malformed", "external-boundary: capability slot must be a literal"
  detail {"operator": "external-boundary", "slot": 0}
  hint "put a literal capability mask in the first slot"

declared = args[0] payload
excess = declared & ~rt.caps
if rt.enclosed and excess:                      # a nested boundary may only narrow
  "capability-denied",
  "external-boundary: nested boundary declares {names(excess)} beyond the enclosing {names(rt.caps)}"
  detail {"operator": "external-boundary", "declared": names(declared),
          "enclosing": names(rt.caps), "excess": names(excess)}
  hint "a nested boundary may only narrow; declare it in the enclosing one"

missing = declared & ~rt.granted
if missing:
  "capability-denied",
  "external-boundary: declares {names(declared)} but the host granted {names(rt.granted) or 'nothing'}"
  detail {"operator": "external-boundary", "declared": names(declared),
          "granted": names(rt.granted), "missing": names(missing)}
  hint "run with `--allow " + ",".join(names(missing)) + "`, or declare less"

save caps/enclosed; rt.caps, rt.enclosed = declared, True
try: return eval(body)  finally: restore
```

`capability_names(mask)` returns the names whose bit is set, **in the
declaration order of `CAPABILITY_BITS`**: `fs-read, fs-write, clock, net`.
The `{names(...)}` above are Python lists formatted with `str()`, e.g.
`['fs-read', 'clock']`. The boundary traps **before** the body runs.

`_require_capability(rt, op, name)`, used by `fs-read`, `fs-write`,
`net-send`, `net-recv`, `clock`:

```
bit = CAPABILITY_OF[op]
if not rt.caps & bit:
  needed = capability_names(bit)[0]
  "capability-denied", "{name}: used outside a boundary that declares {needed}"
  detail {"operator": name, "needs": needed, "declared": capability_names(rt.caps)}
  hint 'wrap the use in (boundary "{needed}" ...)'
```

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x30 | `external-boundary` | 2 | above; result is the body's value |
| 0x31 | `net-send` | 2 | see below |
| 0x32 | `net-recv` | 0 | see below |
| 0x33 | `fs-read` | 1 | capability check; `_as_text(path, "fs-read")`; `open(path, encoding="utf-8").read()` → a **text** |
| 0x34 | `fs-write` | 2 | capability check; `_as_text(path)`, `_as_text(value)`; `open(path, "w", encoding="utf-8", newline="")` → returns `len(text)` in **characters** |
| 0x35 | `stdout` | 1 | `text = _as_text(value, "stdout")`; appends to `rt.output` and forwards to `rt.out_stream` if set; returns `len(text)`. **No capability required** — the terminal is ambient |
| 0x36 | `stdin` | 0 | next line, **terminator included**, or `NIL` at end of input. **No capability required** |
| 0x37 | `clock` | 0 | capability check; `rt.clock()` coerced with `_as_int(..., "clock")` if set, else `time.time_ns() // 1_000_000` (milliseconds since the epoch) |

`fs-read` fault (`OSError` or `UnicodeDecodeError`):

```
"domain-error", "fs-read: {path}: {exc}"
detail {"operator": "fs-read", "path": path, "reason": type(exc).__name__}
(`reason` is the Python exception class name; a port maps its own error
kinds onto those names -- `FileNotFoundError`, `PermissionError`,
`IsADirectoryError` -- and the message text is not contractual.)
hint "give `fs-read` the path of a readable UTF-8 file"
```

`fs-write` fault (`OSError`):

```
"domain-error", "fs-write: {path}: {exc}"
detail {"operator": "fs-write", "path": path, "reason": type(exc).__name__}
hint "give `fs-write` a path in a directory that exists"
```

`stdin`: `rt.read_line()` pops `rt.input_lines` first; if empty and
`rt.input_source` is set, calls it and uses the result if truthy;
otherwise `None` → `NIL`. A queued line without a terminator is
passed as it is; a blank line read from a terminal is `"\n"`, which is
the one-element list `(10)` and is **not** end of input (Q78).

**`net-send address value`**:

```
capability check (net)
address = _as_text(...); payload = _as_text(...)
host, port = _net_address(address, "net-send")
if "*" not in rt.net_send_to and f"{host}:{port}" not in rt.net_send_to:
  "capability-denied", "net-send: {host}:{port} is not a granted address"
  detail {"operator": "net-send", "address": "{host}:{port}", "granted": sorted(allowed)}
  hint "run with `--allow net={host}:{port}`"
data = payload.encode("utf-8")
send from the listening socket when one is granted (so a reply lands),
else from a throwaway UDP socket
OSError -> "domain-error", "net-send: {host}:{port}: {exc}"
           detail {"operator": "net-send", "address": ..., "reason": type(exc).__name__}
           hint "give `net-send` a reachable host:port"
return len(data)                       # BYTES, not characters
```

`_net_address(text, ctx)` splits on the **last** `:`; host and port
must both be non-empty, the port all digits and `0 < port < 65536`:

```
"domain-error", "{ctx}: not an address: {text!r}"
detail {"operator": ctx, "address": text}
hint 'give {ctx} an address of the form "host:port"'
```

**`net-recv`**:

```
capability check (net)
if not rt.net_listen_on:
  "capability-denied", "net-recv: no listening port was granted"
  detail {"operator": "net-recv", "granted": []}
  hint "run with `--allow net=:PORT`"
port = min(rt.net_listen_on)
bind (once, cached in rt.net_sockets) the LOWEST granted port;
settimeout(rt.net_timeout)   # 5.0 s default
recvfrom(65535)
socket.timeout -> return NIL          # nothing arrived; not an error
OSError -> "domain-error", "net-recv: port {port}: {exc}"
           detail {"operator": "net-recv", "port": port, "reason": type(exc).__name__}
           hint "grant a port that is free to bind"
return data.decode("utf-8", errors="replace")
```

The listening socket is bound by the **first** network operation of
either kind, so a fast reply is not lost.

### 5.8 Meta / lineage (0x38–0x3F)

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x38 | `lineage-query` | 1 | `uid` absent/0 → `NIL`; else the list of uids self → parent → … → root |
| 0x39 | `why` | 1 | `uid` absent/0 → the text `"unregistered"`; else `f"{rec.mutation_kind} {rec.notes}".strip()` |
| 0x3A | `trace` | 1 | see below |
| 0x3B | `explain` | 1 | `core.surface.pretty(program)` → a **text** (Stage-1 s-expression) |
| 0x3C | `hash` | 1 | `int.from_bytes(encode(program), "big")` — Axiom 1 taken literally |
| 0x3D | `uid` | 1 | `program.uid or 0` |
| 0x3E | `ancestor-of` | 2 | both uids must be truthy, else `0`; `1` if a is an ancestor of b **or equal**, else `0` |
| 0x3F | `generation` | 1 | `uid` absent/0 → `0`; else the record's `generation` |

**`trace program`** — a sandboxed run whose deviations are the result:

```
inner = Runtime(env=flatten_env(rt.env), lineage=rt.lineage,
                max_steps=max(1, rt.max_steps - rt.steps),
                max_call_depth=max(1, rt.max_call_depth - rt.call_depth))
try: _eval(program, inner)
finally: rt.steps += inner.steps
return list_from([event["deviation"] for event in inner.surprise.events])
```

- The sandbox inherits the *remaining* ceilings, so a loop of traces
  cannot slip past `max_steps`.
- It has its own empty `budget_stack`, so a traced program's nodes
  charge **no budget**. *(quirk)*
- It has its own `output`, `caught` and `surprise` — writes inside a
  trace do not reach `rt.output`.
- `rt.steps += inner.steps` is in a `finally`, **after** the run, and
  is not checked against `max_steps`, so a trace can leave `rt.steps`
  above the ceiling without trapping at that point; the next node to
  tick will trap.
- A trap inside the sandbox propagates out of `trace` (after the
  steps are added).

### 5.9 Text (0x40–0x4F)

All cost one step. `_sep` (§2.4) applies to separator slots.

| Byte | Name | Args | Behaviour |
|---|---|---|---|
| 0x40 | `text` | payload | returns the payload `str`. No position-path entry (§6.1) |
| 0x41 | `text-len` | 1 | `str` → `len(v)` in **characters**; else `len(list_to_python(_as_list(v, "text-len")))` |
| 0x42 | `text-cat` | 2 | both `str` → `a + b`; otherwise both coerced to lists and concatenated into a **list** |
| 0x43 | `text-slice` | 3 | `str` → `v[max(0,start):max(0,end)]`; else the same slice of the list. Negative bounds are clamped to 0 (so a negative index does **not** mean "from the end"); `end <= start` yields empty |
| 0x44 | `text-find` | 2 | `_as_text(t).find(_sep(needle))` — first index, or `-1`. An empty needle gives `0` |
| 0x45 | `text-split` | 2 | `sep == ""` → `t.split()` (**whitespace runs**, leading/trailing stripped, no empty pieces); else `t.split(sep)` (every occurrence, empty pieces kept) |
| 0x46 | `text-join` | 2 | `sep.join(_as_text(p, "text-join") for p in parts)`; a `str` `parts` is exploded to its codepoints first, so each part is then an int and joins as its **digits** *(quirk)* |
| 0x47 | `text-chars` | 1 | `str` → its codepoint list; else `_as_list(v, "text-chars")` |
| 0x48 | `text-of-chars` | 1 | `_as_text(v, "text-of-chars")` |
| 0x49 | `text-cmp` | 2 | §2.6 |
| 0x4A | `text-int` | 1 | see below |
| 0x4B | `int-text` | 1 | `str(_as_int(v, "int-text"))` |
| 0x4C | `text?` | 1 | `1` if the value is a `str`, else `0` |
| 0x4D | `text-trim` | 1 | `_as_text(v, "text-trim").strip()` — **Unicode** whitespace |
| 0x4E | `text-match` | 2 | first match, or `NIL` |
| 0x4F | `text-match-all` | 2 | every match; **+1 step per match** |

**`text-int`**:

```
t = _as_text(v, "text-int").strip()
body = t[1:] if t.startswith("-") else t
if not body or not body.isdigit():
  "signalled", "text-int: not a number: {t[:40]!r}"
  detail {"operator": "text-int", "code": 16, "text": t[:40]}
  hint "give `text-int` decimal digits, with an optional leading -"
return int(t)
```

The kind is `"signalled"` with `code 16`, deliberately, so handlers
written against the prelude's old `parse-int` keep working. Note
`str.isdigit()` is Unicode-aware: `"²".isdigit()` is `True` but
`int("²")` raises a bare `ValueError` that **escapes the LOVA error
model**; `"١٢"` (Arabic-Indic) passes and parses as `12`. *(quirk)*
A leading `+` is rejected. No whitespace survives the `strip`.

**Patterns** (`text-match`, `text-match-all`). A pattern is a text in
a fixed subset. `_pattern(v, ctx)`:

1. Scan with `\\\\|\(\?|\\[0-9A-Za-z]`. For each hit:
   `"\\\\"` is skipped; `"(?"` or a backslash-escape whose letter is
   not in `dDwWsSnt` is refused:

```
"domain-error",
"{ctx}: `{tok}` is outside the pattern subset (literals, `.`, `[...]`, `\d \w \s`, `* + ? {m,n}`, `( )`, `|`, `^ $`)"
detail {"operator": ctx, "pattern": text, "at": m.start()}
hint "rewrite the pattern in the subset; match twice rather than refer back"
```

2. `re.compile(text)`; a `re.error` becomes:

```
"domain-error", "{ctx}: the pattern does not parse: {exc}"
detail {"operator": ctx, "pattern": text, "at": exc.pos}
hint "fix the pattern; a literal `(`, `[`, `.` or `*` needs a backslash"
```

3. Compiled patterns are cached in a module-level dict, cleared
   wholesale when it exceeds 256 entries.

The admitted subset: literal characters; `.`; a class `[a-z]` /
`[^0-9]`; the escapes `\d \D \w \W \s \S \n \t` and a backslash before
any punctuation; the repeats `* + ? {m,n}` with a trailing `?` for
lazy; a group `( )`; alternation `|`; anchors `^ $`. Refused by name:
back-references (`\1`), look-around and named/extension groups
(`(?…)`). A port implements the subset itself; the reference hands it
to Python's `re`, so its exact matching (leftmost, greedy/lazy,
`finditer`'s non-overlapping left-to-right scan with the empty-match
advance rule) is the contract.

Match values: `_match_value(m)` is
`list_from([m.group(0)] + [g if g is not None else "" for g in m.groups()])`
— the whole match followed by each group, an unmatched group becoming
the empty text. `text-match` returns `NIL` when there is no match;
`text-match-all` returns a list of those lists (possibly empty), one
step per match.

### 5.10 List (0x50–0x57)

Each walker: evaluates its slots left to right, coerces the function
slot with `_as_fn` and the sequence slot with `_as_list` then
`list_to_python` (so a text is its codepoints), then walks. All
per-element ticks are **before** the call. The called function's own
steps are counted normally and attributed to the def that wrote it.

| Byte | Name | Args | Steps beyond the node | Result |
|---|---|---|---|---|
| 0x50 | `map` | `(map f xs)` | 1 per element | list of `(f x)` |
| 0x51 | `filter` | `(filter f xs)` | 1 per element | the `x` where `_as_int((f x), "filter") != 0` |
| 0x52 | `fold` | `(fold f acc xs)` | 1 per element | `acc` after `acc = ((f acc) x)` per element, left to right. Slots evaluated in order: `f`, `acc`, `xs` |
| 0x53 | `reverse` | `(reverse xs)` | `len(xs)`, once | the reversed list |
| 0x54 | `range` | `(range a b)` | `max(0, b - a)`, once, **before** allocating | `a, a+1, …, b-1`; empty when `b <= a` |
| 0x55 | `any` | `(any f xs)` | 1 per element **examined** | `1` at the first non-zero `(f x)`, else `0` |
| 0x56 | `sort-by` | `(sort-by less xs)` | 1 per comparator invocation (§3.4) | stable ascending |
| 0x57 | `zip` | `(zip xs ys)` | `min(len(xs), len(ys))`, once | list of two-element lists, truncated to the shorter |

`sort-by`'s comparator is called as `((less a b))` — curried — twice
per comparison, in the order `(less a b)` then `(less b a)`.
`a` sorts before `b` iff `(less a b)` is non-zero and `(less b a)` is
zero; if both or neither, they compare equal (which is what makes a
`le` comparator sort like `lt`, stably).

`range` charges before building the list, so
`(range 0 100000000)` traps on the step ceiling rather than
allocating.

---

## 6. The anomaly schema

### 6.1 Trap classes

| Class | Python base | `kind` | Catchable by `when-anomaly`? |
|---|---|---|---|
| `BudgetTrap` | `Exception` | `"budget-exceeded"` | yes |
| `DepthTrap` | `BudgetTrap` | `"recursion-depth-exceeded"` | yes |
| `StepTrap` | `BudgetTrap` | `"step-limit-exceeded"` | **no** |
| `DeltaTrap` | `Exception` | `"conservation-violated"` | yes |
| `DomainTrap` | `ValueError` | `"domain-error"`, `"type-violation"`, `"unbound-ref"`, `"malformed"`, `"capability-denied"`, `"signalled"` | yes |

`ANOMALY_CODES` (the integer a LOVA handler receives):

```
budget-exceeded            1
recursion-depth-exceeded   2
conservation-violated      3
domain-error               4
type-violation             5
unbound-ref                6
malformed                  7
step-limit-exceeded        8      (not catchable)
capability-denied          9
signalled                 10
FIRST_PROGRAM_SIGNAL      16      (the first code a program may `signal`)
ANOMALY_KINDS = the inverse map
```

`anomaly_code(anomaly)`: for `kind == "signalled"`, the program's own
`detail["code"]` (defaulting to 10); otherwise
`ANOMALY_CODES.get(kind, 0)`.

Every anomaly dict has the same shape from birth:

```
{ "kind": str,
  "detail": {...},                # kind-specific
  "position_path": (),            # filled by enrichment
  "offending_op": None,
  "offending_op_name": "",
  "valid_alternatives": (),
  "repair_hint": str }
```

`DepthTrap` additionally carries `detail["call_chain"]` (always the
empty tuple — the runtime never passes one). *(quirk)*

Exception `str()` forms (used by the Python `except` path):

```
BudgetTrap: "BUDGET trap: spent {spent} > limit {limit} (overrun {overrun})"
DepthTrap:  "Depth trap: call depth {depth} > limit {limit}"
StepTrap:   "Step trap: {steps} evaluation steps > limit {limit}"
DeltaTrap:  "Delta trap: {invariant} violated -- entry {entry} vs exit {exit}"
DomainTrap: the message passed in
```

Standing repair hints:

```
budget-exceeded:
  "reduce body size (fewer operators) or raise budget to >= {spent}"

recursion-depth-exceeded:
  "the recursion has no reachable base case, or keeps more than {limit} frames; add or fix the `if` that terminates it.  A call in tail position costs no frame (M32), so a recursion whose last act is the call runs in constant depth; this one does something with the result after the call returns, so every level keeps a frame -- carry the result in an accumulator argument, or use `fold` / `map` / `range` or `loop-until`"

step-limit-exceeded:
  "the budget of {limit} steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program"
```

(The walker costs quoted in the step hint are the pre-M27 prelude's and
are stale; the list family costs one step an element. The text is part
of the contract as written.)

### 6.2 Enrichment — `_trapped` / `_enrich_trap`

`_trapped(trap, rt, node)` runs in the `except` of every compiled node
closure. It enriches **once**: `trap.anomaly["_enriched"]` is set the
first time and checked thereafter, so the innermost node wins and the
outer frames only re-raise.

`_enrich_trap(trap, rt)`:

1. `path = _node_path(rt)`;
2. `top = path[-1] if path else None`; `op = top.op if top else None`;
3. `alternatives = suggest_alternatives(op)` (§5.3) if `op` is not
   `None`, else `()`;
4. **span**: walk `reversed(path)` (innermost first) and take the
   first node with a non-`None` `span` attribute into
   `anomaly["span"]`. `span` is attached to nodes by the *surface
   parser*, not by `decode`; **a native runtime consuming bytes has no
   spans and should omit the field.**
5. `enrich_anomaly(...)` writes
   `position_path = tuple(n.op for n in path)`,
   `offending_op = op`,
   `offending_op_name = SIGNATURES[op]["name"]` (or `""`),
   `valid_alternatives = tuple(alternatives)`;
6. if `kind` is `"step-limit-exceeded"` or
   `"recursion-depth-exceeded"`, `detail["calls"] = _cost_by_function(rt)`
   when non-empty (§4.5);
7. if `kind == "conservation-violated"`:
   - when `body_offender` is `None` and `op` is not `None`, the
     generic hint is **overwritten** with
     ``"replace operator `{op_name}` with one of {[alt names]} to keep the body in the conserve invariant"``;
   - when `body_offender` *is* set, the `conserve` handler's own more
     specific hint is kept, and `valid_alternatives` is replaced by
     `suggest_alternatives(body_offender["op"])`.

**`_node_path(rt)` — the exact definition.** Walk the Python call
stack outward from `_node_path`'s caller. A frame counts iff:

- its code object's name starts with `"_n_"` (every compiled node
  closure is named `_n_<something>`), **and**
- `frame.f_locals["rt"] is rt` (frames belonging to another runtime —
  a `conserve` body probe, a `trace` sandbox — are skipped), **and**
- `"node"` is in `frame.f_locals`.

The collected nodes are then **reversed**, so the path is
**outermost first, innermost last**.

Consequences, all of them contractual:

- **A literal takes no entry.** `_compile_LIT_INT` and
  `_compile_LIT_TEXT` build closures that never mention `node`, so
  `node` is not among their locals. A `StepTrap` or `BudgetTrap`
  raised by a literal is reported at its parent.
  `tests/test_compiled.py::test_a_literal_takes_no_position` pins
  `(merge 1 1)` at `max_steps=2` → `("step-limit-exceeded", (3,), 3, None)`.
- **A call adds no entry of its own** — `_call` is not `_n_*`. A
  recursion shows one entry per *node* on the live evaluation path,
  which for `(let 0 (lambda 1 (merge 1 (apply (ref 0) (ref 1)))) (apply (ref 0) 0))`
  at `max_call_depth=5` is `(46, 45) + (3, 45) * 5` — LET, APPLY, then
  MERGE/APPLY per kept frame.
- **A tail call removes its frame from the path.** The `_call` that
  made the tail call has already returned from the body's closures;
  the new body's closures are entered from the same `_call`'s loop, so
  the path carries only the *current* body's nodes plus whatever
  frames are genuinely still live below. A tail-recursive loop
  therefore shows a short path, not one entry per iteration.
- The path is the *live Python stack*, so it reflects only nodes whose
  evaluation has not returned.

**What a native runtime must produce:**

| Field | Who | Note |
|---|---|---|
| `kind` | native | verbatim from §6.1 |
| `detail` | native | verbatim keys and values |
| `repair_hint` | native | verbatim strings above and in §5 |
| `position_path` | native | the ops of the live evaluation path, outermost first, literals excluded |
| `offending_op` / `offending_op_name` | native | the innermost path entry |
| `valid_alternatives` | native | `suggest_alternatives`, §5.3 |
| `body_offender` (conserve only) | native | §5.3; deterministic |
| `detail["calls"]` (step/depth only) | native | §4.5 |
| `span` | **Python side** | a surface-parser annotation; out of scope for a byte-consuming runtime |
| `excerpt`, `line`, `col` | **Python side** | `core/mcp_server.py` derives them from `span` and the source it was sent |
| `bound_names` rendering | **Python side** | the runtime emits raw ids; `core/cli.py` maps them to names and prunes |
| `position_path` elision | **Python side** | the CLI and MCP shorten a path longer than 12 to `path[:6] + ["... N more ..."] + path[-3:]` |

---

## 7. Limits and guards

| Constant | Value | Where |
|---|---|---|
| `MAX_NT_INPUT` | `2_000` | input guard on `p` / `tau` / `sigma` / `mobius` |
| `MAX_INT_BITS` | `4_096` | output guard on `mul` (sum of operand bit lengths) |
| `MAX_CALL_DEPTH` | `10_000` | library default `Runtime.max_call_depth` |
| `MAX_STEPS` | `1_000_000` | library default `Runtime.max_steps` |
| `CLI_MAX_STEPS` | `20_000_000` | `core/cli.py`, `--max-steps` default |
| `CLI_MAX_DEPTH` | `10_000` | `core/cli.py`, `--max-depth` default |
| MCP `max_steps` / `max_depth` | `20_000_000` / `10_000` | `core/mcp_server.py`, same defaults |
| `Runtime.net_timeout` | `5.0` seconds | `net-recv` |
| `Runtime.granted` | `0` | nothing is granted unless the host asks |
| `_PATTERN_CACHE` cap | `256` entries, cleared wholesale | `_pattern` |
| `_PY_FRAMES_PER_CALL` | `14` | Python recursion-limit sizing |
| `_PY_RECURSION_HEADROOM` | `1_000` | Python recursion-limit sizing |
| `_STACK_BYTES_PER_FRAME` | `4_096` | PyPy thread stack sizing |
| `_STACK_FLOOR` | `64 * 1024 * 1024` | PyPy thread stack sizing |
| `UNFIT` | `1 << 62` | the score of a variant whose scorer trapped |
| `RETIRE_FRACTION` / `CLONE_PROBABILITY` / `EVOLVE_STRENGTH` / `SELECTION_SHARPNESS` | `0.2` / `0.3` / `0.3` / `3` | `evolve` |
| `LineageStore` seed | `0` | `random.Random(0)` |

Host-interpreter plumbing a native runtime does **not** need:

- `evaluate` raises `sys.setrecursionlimit` to
  `max_call_depth * 14 + 1000` for the duration of a run and restores
  it afterwards; a `RecursionError` that escapes anyway is converted
  to `DepthTrap(depth=rt.call_depth, limit=rt.max_call_depth)`.
- On PyPy (`platform.python_implementation() == "PyPy"`), `evaluate`
  runs on a daemon thread with a stack of
  `max(64 MiB, max_call_depth * 4096)` bytes, joined by polling every
  50 ms so Ctrl-C still works; a nested `evaluate` (the `conserve`
  probe, `trace`, `evolve`) stays on that thread via a thread-local
  flag.
- `rt.code_cache` and `rt.tail_cache` are cleared at the start of
  every `evaluate`.

---

## 8. Python-specific quirks a port must reproduce deliberately

1. **Unbounded integers.** Every integer is a bignum. `bit_length()`
   drives `mul`'s guard and `encode`'s length byte.
2. **Floor division and floor modulo.** `div` is `//` and `mod` is
   `%`: the quotient rounds toward −∞ and the remainder takes the
   **divisor's** sign. Rust's `/` and `%` truncate toward zero and
   take the dividend's sign — both must be adjusted.
3. **`math.gcd` is non-negative**, and `gcd(0, 0) == 0`.
4. **Dict insertion order is the map's order.** `map-pairs` and
   `format_value`'s first-8 preview depend on it. Rerooting removes
   and re-adds keys; the replay order restores the original sequence.
5. **`str.split()` with no separator** splits on **runs** of Unicode
   whitespace and drops leading/trailing empties —
   `" a b ".split() == ["a", "b"]`. `t.split(sep)` with a
   non-empty separator keeps empty pieces. `text-split` chooses
   between them on `sep == ""`.
6. **`str.strip()` with no argument** strips Unicode whitespace
   (including NBSP, U+00A0). `text-trim` and `text-int` both use it.
7. **`str.isdigit()` is Unicode-aware and wider than `int()`.**
   `"²".isdigit()` is `True` but `int("²")` raises a bare
   `ValueError` that escapes the LOVA error model; `"١٢"` parses to
   `12`. A port that uses ASCII-digit checks will accept a different
   set.
8. **`str.find`** returns `-1` on absence and `0` for an empty needle.
9. **Python string comparison is by code point**, not by locale or
   normalisation. `text-cmp` on two texts inherits it.
10. **Python list comparison** drives `text-cmp` on lists: element-wise,
    prefix is smaller. A heterogeneous list can raise a bare
    `TypeError`.
11. **Slicing clamps, it does not wrap.** `text-slice` applies
    `max(0, …)` to both bounds, so a negative index is `0`, not
    "from the end", and an out-of-range end simply truncates.
12. **`sorted` is CPython's Timsort**, and `sort-by`'s step count is
    the number of comparisons it performs (§3.4). Measured anchors:
    *n−1* for sorted and reverse-sorted input; 4 for `[3,1,2]`; 8 for
    `[3,1,2,5,4]`. `functools.cmp_to_key` maps each `<` to exactly one
    comparator invocation.
13. **`re` is the pattern engine.** Leftmost-first alternation
    (not leftmost-longest), greedy-by-default quantifiers, and
    `finditer`'s non-overlapping scan with its empty-match advance
    rule are all observable through `text-match-all`.
14. **`random.Random` is the Mersenne Twister**, seeded 0, and drives
    `evolve` and `mutate`. Reproducing recorded evolution runs
    requires reproducing MT19937 and CPython's `random()`,
    `randint`, `_randbelow` and `choice` exactly.
15. **`_node_path` reads the Python call stack.** A port maintains an
    explicit evaluation-path stack instead, and must exclude literals
    from it to match `position_path`.
16. **`Closure` and `LoopFn` are not Python-callable**, so `_kind_of`
    reports them as `"a value"`, never `"a function"`.
17. **A text in an Int slot** is reported by `_as_int` as
    `"got a function value"` — the `str` case falls through to the
    catch-all branch.
18. **`deviation` on a text is an equality test**, returning `0` for
    equal and `1` for different — the opposite polarity to the
    integer subtraction it otherwise is.
19. **`p`'s domain fault names `partition_number`**, not `p`, in both
    the message and `detail["operator"]`.
20. **The `hot` list lands under `detail["calls"]`** although the step
    hint calls it `hot`.
21. **Only Rule-1 node steps charge the budget.** List-walker ticks,
    `loop-until` iterations, `text-match-all` matches and `trace`'s
    imported steps do not, so `(budget k …)` and `max_steps` measure
    different things.
22. **An inner `budget` shields the outer one** — only
    `budget_stack[-1]` is charged.
23. **`trace` has its own budget stack and output**, and its steps are
    added after the fact without a ceiling check.
24. **`DepthTrap.detail["call_chain"]` is always `()`.**
25. **`Runtime.charge()` and `Runtime.tick()` are dead code.**
26. **`identity` does not coerce**, so it passes non-integers through
    despite declaring `Int → Int`.
27. **`text-join` on a text explodes it to codepoints**, and each
    codepoint then joins as its decimal digits.
28. **`decode` accepts a zero-length `LIT_INT` payload** (yielding 0),
    which `encode` never produces.
29. **`quote` deep-copies** its operand, clearing `uid` on the copy, so
    a quoted program is never the same object as the one in the tree.
30. **`_deep_copy_node` shares a `LIT_TEXT`'s `str`** by reference;
    harmless because Python strings are immutable, but a port using
    mutable strings must copy.
31. **`NotImplementedError` (only `END`) is not a LOVA anomaly** and is
    not catchable by `when-anomaly`.
32. **Zero-argument `apply` returns the head value**, without checking
    that it is callable.
33. **`stdout` and `stdin` need no capability**; every other effect
    does.
34. **`fs-write` returns characters, `net-send` returns bytes.**
35. **`net-recv` decodes with `errors="replace"`**, so malformed UTF-8
    becomes U+FFFD rather than a fault.
