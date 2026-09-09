# LOVA - Token Specification

> **Status: authoritative.** Generated from `core/tokens.py`
> SIGNATURES by `spec/generate_tokens_md.py`. Rerun that script
> after any change to the table; do not hand-edit this file.

## Overview

LOVA's core is exactly **64 operators**, one byte each.
Tokens are grouped into 8 families of 8 operators.  Arguments
follow each operator as typed-slot tokens; types are positional,
not annotated.  See `spec/paradigm-inheritance.md` for the
paradigm lineage and `spec/axioms.md` for the ten design
invariants.

Legend:
- **impl**: the runtime (`core.runtime`) evaluates this operator.
  52 of the 64 tokens are implemented.
- **Reserved**: the operator has a declared slot but no runtime
  support.  Evaluating one raises `NotImplementedError`, and it is
  excluded from type-directed generation (`TYPED_TOKENS`).

## Structural (0x00 - 0x07)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x00 | `end` | 0 | - | - | - | Reserved |
| 0x01 | `lit` | 0 | - | LiteralInt | - | **impl** |
| 0x02 | `partition` | 1 | Int | Int | - | **impl** |
| 0x03 | `merge` | 2 | Int, Int | Int | - | **impl** |
| 0x04 | `cons` | 2 | Int, List | List | - | **impl** |
| 0x05 | `head` | 1 | List | Int | - | **impl** |
| 0x06 | `tail` | 1 | List | List | - | **impl** |
| 0x07 | `identity` | 1 | Int | Int | - | **impl** |

## Numerical primitives (0x08 - 0x0F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x08 | `p` | 1 | Int | Int | - | **impl** |
| 0x09 | `tau` | 1 | Int | Int | - | **impl** |
| 0x0A | `sigma` | 1 | Int | Int | - | **impl** |
| 0x0B | `mul` | 2 | Int, Int | Int | - | **impl** |
| 0x0C | `mod` | 2 | Int, Int | Int | - | **impl** |
| 0x0D | `div` | 2 | Int, Int | Int | - | **impl** |
| 0x0E | `gcd` | 2 | Int, Int | Int | - | **impl** |
| 0x0F | `mobius` | 1 | Int | Int | - | **impl** |

## Conservation (0x10 - 0x17)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x10 | `budget` | 2 | LiteralInt, Int | Int | {budget-scope} | **impl** |
| 0x11 | `conserve` | 2 | Int, Int | Int | {conservation-check} | **impl** |
| 0x12 | `delta-check` | 1 | - | - | - | Reserved |
| 0x13 | `respawn` | 1 | - | - | - | Reserved |
| 0x14 | `budget-remaining` | 0 | - | - | - | Reserved |
| 0x15 | `nil` | 0 | - | List | - | **impl** |
| 0x16 | `preserve` | 2 | - | - | - | Reserved |
| 0x17 | `violate` | 1 | Int | Int | {synthetic-violation} | **impl** |

## Surprise / watch (0x18 - 0x1F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x18 | `surprise` | 2 | Int, Int | Int | {write-surprise-trace} | **impl** |
| 0x19 | `nil?` | 1 | List | Int | - | **impl** |
| 0x1A | `when-anomaly` | 2 | Value, Fn | Int | {handle-anomaly} | **impl** |
| 0x1B | `threshold` | 1 | Int | Int | - | **impl** |
| 0x1C | `eval` | 1 | Program | Int | {eval, unbounded-cost} | **impl** |
| 0x1D | `trace-surprise` | 1 | Int | Int | {write-surprise-trace} | **impl** |
| 0x1E | `normal-range` | 2 | - | - | - | Reserved |
| 0x1F | `deviation` | 2 | Int, Int | Int | - | **impl** |

## Evolution (0x20 - 0x27)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x20 | `defpop` | variadic | Fn, Program* | Population | {write-lineage} | **impl** |
| 0x21 | `variant` | 2 | Population, Int | Program | - | **impl** |
| 0x22 | `evolve` | 1 | Population | Population | {unbounded-cost, write-lineage} | **impl** |
| 0x23 | `select` | 2 | Population, Int | Program | {unbounded-cost} | **impl** |
| 0x24 | `mutate` | 2 | Program, Int | Program | {write-lineage} | **impl** |
| 0x25 | `clone` | 1 | Program | Program | {write-lineage} | **impl** |
| 0x26 | `fitness` | 1 | Population | List | {unbounded-cost} | **impl** |
| 0x27 | `retire` | 1 | Population | Population | {unbounded-cost} | **impl** |

## Composition (0x28 - 0x2F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x28 | `seq` | variadic | Int* | Int | - | **impl** |
| 0x29 | `quote` | 1 | Value | Program | - | **impl** |
| 0x2A | `if-surprise` | 3 | Int, Int, Int | Int | {read-surprise} | **impl** |
| 0x2B | `loop-until` | 2 | Fn, Fn | Fn | {unbounded-cost} | **impl** |
| 0x2C | `lambda` | 2 | LiteralInt, Value | Fn | - | **impl** |
| 0x2D | `apply` | variadic | Fn, Value* | Int | {unbounded-cost} | **impl** |
| 0x2E | `let` | 3 | LiteralInt, Value, Int | Int | - | **impl** |
| 0x2F | `ref` | 1 | LiteralInt | Int | - | **impl** |

## Effects / IO (0x30 - 0x37)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x30 | `external-boundary` | 2 | - | - | - | Reserved |
| 0x31 | `net-send` | 1 | - | - | - | Reserved |
| 0x32 | `net-recv` | 0 | - | - | - | Reserved |
| 0x33 | `fs-read` | 1 | - | - | - | Reserved |
| 0x34 | `fs-write` | 2 | - | - | - | Reserved |
| 0x35 | `stdout` | 1 | Value | Int | {write-stdout} | **impl** |
| 0x36 | `stdin` | 0 | - | List | {read-stdin} | **impl** |
| 0x37 | `clock` | 0 | - | - | - | Reserved |

## Meta / lineage (0x38 - 0x3F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x38 | `lineage-query` | 1 | Program | List | {read-lineage} | **impl** |
| 0x39 | `why` | 1 | Program | List | {read-lineage} | **impl** |
| 0x3A | `trace` | 1 | Program | List | {unbounded-cost} | **impl** |
| 0x3B | `explain` | 1 | Program | List | - | **impl** |
| 0x3C | `hash` | 1 | Program | Int | - | **impl** |
| 0x3D | `uid` | 1 | Program | Int | {read-lineage} | **impl** |
| 0x3E | `ancestor-of` | 2 | Program, Program | Int | {read-lineage} | **impl** |
| 0x3F | `generation` | 1 | Program | Int | {read-lineage} | **impl** |

## Slot conventions

- Every fixed-arity operator is followed immediately by its
  `in_types` children in order.
- Variadic operators are followed by zero or more children of
  type `variadic_type`, terminated by a single `END` token
  (byte `0x00`).
- A variadic operator may also declare `head_types`: leading
  slots with their own types, filled before the tail opens.
  `APPLY` is the only one — its head is the function being
  called, and the tail is the arguments.
- `LIT_INT` (0x01) is the only operator with a non-AST payload:
  after the byte, a 1-byte length prefix L, then L bytes of
  big-endian signed two's-complement integer.

## Type system

Four types:

- **Int** - any integer-valued expression.  Produced by most
  operators.
- **LiteralInt** - subtype of Int; produced *only* by `LIT_INT`.
  Used where a bound-variable identifier is required (slot 0 of
  `LET`, `LAMBDA` and `REF`).
- **Fn** - a unary function `Int -> Value`, produced by `LAMBDA`
  and `LOOP_UNTIL`.  Multi-argument functions are curried, so a
  two-argument function is an `Fn` returning an `Fn`.  `Fn` and
  `Int` are incomparable: neither is a subtype of the other, so
  an `Int` slot never offers a function and `APPLY`'s head slot
  offers nothing else.
- **Value** - the top type.  Exactly one slot has it: the value
  slot of `LET`, because a binding may hold either an integer or
  a function.  Nothing *produces* a `Value`.

Subtype relation: `LiteralInt <: Int <: Value` and `Fn <: Value`.

**Where the guarantee stops.** `valid_next` enforces types at the
*operator* level: it cannot consult scope, because name ids live
in `LIT_INT` payloads that the generation state machine never
sees.  So `REF` declares `Int`, and a reference to a
function-valued binding used in an integer slot is caught by the
compiler's scope-aware type pass rather than being unrepresentable
at generation time.  Same division of labour as `unbound-ref`
(Exp 08).  Curried arity is likewise untracked, so a partial
application in an `Int` slot fails at run time, not at compile
time (see journal Q35).

## Ordering, without an ordering operator

The core has no `<`.  Ordering is built from the surprise family:
`DEVIATION` (0x1F) is the signed sibling of `SURPRISE` (which
returns `|a - b|`), and `THRESHOLD` (0x1B) is the sign test.

```lova
(threshold (deviation b a))    ; a < b
(threshold (deviation a b))    ; a > b
(surprise a b)                 ; |a - b| — zero iff equal
```

## Substrate ceilings

Since abstraction landed, non-termination is reachable, so two
always-on ceilings apply to every run regardless of whether the
program declares a `BUDGET`:

| Ceiling | Default | Trap | Anomaly kind |
|---|---|---|---|
| `MAX_CALL_DEPTH` | 200 | `DepthTrap` | `recursion-depth-exceeded` |
| `MAX_STEPS` | 1,000,000 | `StepTrap` | `step-limit-exceeded` |

Both subclass `BudgetTrap` and carry the standard L2 anomaly
schema, so one handler covers every ceiling.  Both are settable
per-`Runtime`.

## Effect catalogue

Effects are declared per-operator and aggregated by
`static_analyze`.  Current effects:

| Effect | Emitted by | Meaning |
|---|---|---|
| `budget-scope` | `BUDGET` (0x10) | Opens a budget-tracked scope |
| `conservation-check` | `CONSERVE` (0x11) | Verifies value invariant at exit |
| `synthetic-violation` | `VIOLATE` (0x17) | Synthetic test-only op that breaks conservation |
| `write-surprise-trace` | `SURPRISE` (0x18), `TRACE_SURPRISE` (0x1D) | Appends to runtime surprise log |
| `read-surprise` | `IF_SURPRISE` (0x2A) | Branches on surprise value |
| `unbounded-cost` | `APPLY` (0x2D), `LOOP_UNTIL` (0x2B) | Node count stops being a cost bound |

## Stage-1 surface syntax

Each token has a surface representation (Lisp-like s-expression)
mapped to the byte via `core.tokens.NAME_TO_TOKEN`.  Unicode
aliases recognised by the surface parser:

| Alias | Maps to |
|---|---|
| `⊕` | `merge` |
| `⊖` | `partition` |
| `τ` | `tau` |
| `σ` | `sigma` |
| `⊗` | `mul` |
| `μ` | `mobius` |
| `λ` | `lambda` |
| `?` | `surprise` |

Three sugars desugar into the tokens above and introduce no
semantics of their own (Constraint 6):

| Written | Desugars to |
|---|---|
| `(defn f [a b] body)` | `(let f (lambda a (lambda b body)) ...)` |
| `(f x y)` for a bound `f` | `(apply (ref f) x y)` |
| bare `x` in an argument | `(ref x)` |

Identifiers are interned to integer name ids by the parser and
printed back as integers: the integer is the program (Axiom 1),
the identifier was a convenience for whoever typed it.

## Revision history

- 2026-04-23 - initial draft (stub).
- 2026-04-24 - complete, hand-transcribed from SIGNATURES at M5.
  Recorded as 19/64 implemented; `TYPED_TOKENS` in fact held 18.
- 2026-09-09 - M9.  0x0B / 0x0C reallocated from the
  never-implemented mock-theta placeholders `phi3` / `psi7` to `mul`
  and `mod`; `threshold` (0x1B), `deviation` (0x1F), `loop-until`
  (0x2B), `lambda` (0x2C) and `apply` (0x2D) implemented; `Fn` and
  `Value` types added; this file made genuinely generated.
  52/64 operators implemented.
