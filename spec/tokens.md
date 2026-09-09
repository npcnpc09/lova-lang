# LOVA - Token Specification

> **Status: authoritative.** Auto-generated from `core/tokens.py`
> SIGNATURES. Regenerate after any M2+ extension of the table.

## Overview

LOVA's core is exactly **64 operators**, one byte each.
Tokens are grouped into 8 families of 8 operators.  Arguments
follow each operator as typed-slot tokens; types are positional,
not annotated.  See `spec/paradigm-inheritance.md` for the
paradigm lineage and `spec/axioms.md` for the ten design
invariants.

Legend:
- **M1-impl**: operator is implemented in the Milestone 1 runtime
  (`core.runtime`).  19 of the 64 tokens are currently M1-impl.
- **Reserved**: operator has a declared slot but is not yet
  runtime-supported.  Attempting to evaluate raises
  `NotImplementedError`.  Reserved tokens are also excluded
  from type-directed generation (`TYPED_TOKENS`).

## Structural (0x00 - 0x07)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x00 | `end` | 0 | - | - | - | Reserved |
| 0x01 | `lit` | 0 | - | LiteralInt | - | M1-impl |
| 0x02 | `partition` | 1 | Int | Int | - | M1-impl |
| 0x03 | `merge` | 2 | Int, Int | Int | - | M1-impl |
| 0x04 | `heat-inc` | 1 | - | - | - | Reserved |
| 0x05 | `heat-get` | 1 | - | - | - | Reserved |
| 0x06 | `inherit` | 2 | - | - | - | Reserved |
| 0x07 | `identity` | 1 | Int | Int | - | M1-impl |

## Numerical primitives (0x08 - 0x0F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x08 | `p` | 1 | Int | Int | - | M1-impl |
| 0x09 | `tau` | 1 | Int | Int | - | M1-impl |
| 0x0A | `sigma` | 1 | Int | Int | - | M1-impl |
| 0x0B | `phi3` | 2 | - | - | - | Reserved |
| 0x0C | `psi7` | 2 | - | - | - | Reserved |
| 0x0D | `eta` | 1 | - | - | - | Reserved |
| 0x0E | `gcd` | 2 | Int, Int | Int | - | M1-impl |
| 0x0F | `mobius` | 1 | Int | Int | - | M1-impl |

## Conservation (0x10 - 0x17)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x10 | `budget` | 2 | LiteralInt, Int | Int | {budget-scope} | M1-impl |
| 0x11 | `conserve` | 2 | Int, Int | Int | {conservation-check} | M1-impl |
| 0x12 | `delta-check` | 1 | - | - | - | Reserved |
| 0x13 | `respawn` | 1 | - | - | - | Reserved |
| 0x14 | `budget-remaining` | 0 | - | - | - | Reserved |
| 0x15 | `sum-invariant` | 0 | - | - | - | Reserved |
| 0x16 | `preserve` | 2 | - | - | - | Reserved |
| 0x17 | `violate` | 1 | Int | Int | {synthetic-violation} | M1-impl |

## Surprise / watch (0x18 - 0x1F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x18 | `surprise` | 2 | Int, Int | Int | {write-surprise-trace} | M1-impl |
| 0x19 | `watch` | 1 | - | - | - | Reserved |
| 0x1A | `when-anomaly` | 2 | - | - | - | Reserved |
| 0x1B | `threshold` | 1 | - | - | - | Reserved |
| 0x1C | `predict` | 1 | - | - | - | Reserved |
| 0x1D | `trace-surprise` | 1 | Int | Int | {write-surprise-trace} | M1-impl |
| 0x1E | `normal-range` | 2 | - | - | - | Reserved |
| 0x1F | `deviation` | 2 | - | - | - | Reserved |

## Evolution (0x20 - 0x27)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x20 | `defpop` | variadic | - | - | - | Reserved |
| 0x21 | `variant` | 2 | - | - | - | Reserved |
| 0x22 | `evolve` | 1 | - | - | - | Reserved |
| 0x23 | `select` | 2 | - | - | - | Reserved |
| 0x24 | `mutate` | 2 | - | - | - | Reserved |
| 0x25 | `clone` | 1 | - | - | - | Reserved |
| 0x26 | `fitness` | 1 | - | - | - | Reserved |
| 0x27 | `retire` | 1 | - | - | - | Reserved |

## Composition (0x28 - 0x2F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x28 | `seq` | variadic | Int* | Int | - | M1-impl |
| 0x29 | `par` | variadic | - | - | - | Reserved |
| 0x2A | `if-surprise` | 3 | Int, Int, Int | Int | {read-surprise} | M1-impl |
| 0x2B | `loop-until` | 2 | - | - | - | Reserved |
| 0x2C | `lambda` | 2 | - | - | - | Reserved |
| 0x2D | `apply` | variadic | - | - | - | Reserved |
| 0x2E | `let` | 3 | LiteralInt, Int, Int | Int | - | M1-impl |
| 0x2F | `ref` | 1 | LiteralInt | Int | - | M1-impl |

## Effects / IO (0x30 - 0x37)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x30 | `external-boundary` | 2 | - | - | - | Reserved |
| 0x31 | `net-send` | 1 | - | - | - | Reserved |
| 0x32 | `net-recv` | 0 | - | - | - | Reserved |
| 0x33 | `fs-read` | 1 | - | - | - | Reserved |
| 0x34 | `fs-write` | 2 | - | - | - | Reserved |
| 0x35 | `stdout` | 1 | - | - | - | Reserved |
| 0x36 | `stdin` | 0 | - | - | - | Reserved |
| 0x37 | `clock` | 0 | - | - | - | Reserved |

## Meta / lineage (0x38 - 0x3F)

| Byte | Name | Arity | In types | Out type | Effects | Status |
|---|---|---|---|---|---|---|
| 0x38 | `lineage-query` | 1 | - | - | - | Reserved |
| 0x39 | `why` | 1 | - | - | - | Reserved |
| 0x3A | `trace` | 1 | - | - | - | Reserved |
| 0x3B | `explain` | 1 | - | - | - | Reserved |
| 0x3C | `hash` | 1 | - | - | - | Reserved |
| 0x3D | `uid` | 0 | - | - | - | Reserved |
| 0x3E | `ancestor-of` | 2 | - | - | - | Reserved |
| 0x3F | `generation` | 1 | - | - | - | Reserved |

## Slot conventions

- Every fixed-arity operator is followed immediately by its
  `in_types` children in order.
- Variadic operators are followed by zero or more children of
  type `variadic_type`, terminated by a single `END` token
  (byte `0x00`).
- `LIT_INT` (0x01) is the only operator with a non-AST payload:
  after the byte, a 1-byte length prefix L, then L bytes of
  big-endian signed two's-complement integer.

## Type system

Two types in M2:

- **Int** - any integer-valued expression.  Produced by most
  operators.
- **LiteralInt** - subtype of Int; produced *only* by
  `LIT_INT`.  Used where a bound-variable identifier is
  required (slot 0 of `LET` and `REF`).

Subtype relation: `LiteralInt <: Int`.  An `Int`-expecting slot
accepts a literal, but a `LiteralInt`-expecting slot does NOT
accept a computed `Int`.

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

## Stage-1 surface syntax

Each token has a surface representation (Lisp-like s-expression)
mapped to the byte via `core.tokens.NAME_TO_TOKEN`.  Unicode
aliases are recognised by the surface parser:

| Alias | Maps to |
|---|---|
| `⊕` | `merge` |
| `⊖` | `partition` |
| `τ` | `tau` |
| `σ` | `sigma` |
| `η` | `eta` |
| `μ` | `mobius` |
| `λ` | `lambda` |
| `?` | `surprise` |

## Revision history

- 2026-04-23 - initial draft (stub).
- 2026-04-24 - complete auto-generated from SIGNATURES at M5.
  19/64 operators M1-implemented.
