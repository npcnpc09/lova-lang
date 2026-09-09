"""Regenerate ``spec/tokens.md`` from ``core.tokens.SIGNATURES``.

``spec/tokens.md`` calls itself authoritative and auto-generated, but
until M9 there was no generator, so the table drifted: 0x0B / 0x0C were
still listed as the mock-theta placeholders they had stopped being, and
the implemented-operator count was three milestones stale.  This script
is the generator the header always claimed existed.

Run it after any change to the token table:

    PYTHONPATH=. python spec/generate_tokens_md.py

The prose sections live here rather than in the Markdown, because
anything kept only in the output would be lost on the next run.
"""

from __future__ import annotations

import os
import sys
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.observability import _EFFECTS
from core.tokens import ALIASES, SIGNATURES, TYPED_TOKENS

OUT_PATH = os.path.join(_HERE, "tokens.md")

FAMILIES = [
    ("Structural", 0x00, 0x07),
    ("Numerical primitives", 0x08, 0x0F),
    ("Conservation", 0x10, 0x17),
    ("Surprise / watch", 0x18, 0x1F),
    ("Evolution", 0x20, 0x27),
    ("Composition", 0x28, 0x2F),
    ("Effects / IO", 0x30, 0x37),
    ("Meta / lineage", 0x38, 0x3F),
]


def _implemented() -> set:
    """Operators the runtime actually evaluates.

    ``TYPED_TOKENS`` is the authority: an operator gets type info in
    ``_TYPE_INFO`` exactly when the runtime learned to evaluate it, and
    that same set is what type-directed generation may emit.
    """
    return set(TYPED_TOKENS)


def _in_types(sig: dict) -> str:
    if "variadic_type" in sig:
        head = [str(t) for t in sig.get("head_types", ())]
        return ", ".join(head + [f"{sig['variadic_type']}*"])
    in_types = sig.get("in_types")
    if not in_types:
        return "-"
    return ", ".join(str(t) for t in in_types)


def _effects(token: int) -> str:
    effects = _EFFECTS.get(token, frozenset())
    if not effects:
        return "-"
    return "{" + ", ".join(sorted(effects)) + "}"


def _rows(low: int, high: int, impl: set) -> str:
    lines = [
        "| Byte | Name | Arity | In types | Out type | Effects | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for token in range(low, high + 1):
        sig = SIGNATURES[token]
        out_type = sig.get("out_type")
        status = "**impl**" if token in impl else "Reserved"
        lines.append(
            f"| 0x{token:02X} | `{sig['name']}` | {sig['arity']} | "
            f"{_in_types(sig)} | {out_type if out_type is not None else '-'} | "
            f"{_effects(token)} | {status} |"
        )
    return "\n".join(lines)


def render() -> str:
    impl = _implemented()
    n_impl = len(impl)

    parts = [
        "# LOVA - Token Specification",
        "",
        "> **Status: authoritative.** Generated from `core/tokens.py`",
        "> SIGNATURES by `spec/generate_tokens_md.py`. Rerun that script",
        "> after any change to the table; do not hand-edit this file.",
        "",
        "## Overview",
        "",
        "LOVA's core is exactly **64 operators**, one byte each.",
        "Tokens are grouped into 8 families of 8 operators.  Arguments",
        "follow each operator as typed-slot tokens; types are positional,",
        "not annotated.  See `spec/paradigm-inheritance.md` for the",
        "paradigm lineage and `spec/axioms.md` for the ten design",
        "invariants.",
        "",
        "Legend:",
        f"- **impl**: the runtime (`core.runtime`) evaluates this operator.",
        f"  {n_impl} of the 64 tokens are implemented.",
        "- **Reserved**: the operator has a declared slot but no runtime",
        "  support.  Evaluating one raises `NotImplementedError`, and it is",
        "  excluded from type-directed generation (`TYPED_TOKENS`).",
        "",
    ]

    for name, low, high in FAMILIES:
        parts += [f"## {name} (0x{low:02X} - 0x{high:02X})", "",
                  _rows(low, high, impl), ""]

    parts += [
        "## Slot conventions",
        "",
        "- Every fixed-arity operator is followed immediately by its",
        "  `in_types` children in order.",
        "- Variadic operators are followed by zero or more children of",
        "  type `variadic_type`, terminated by a single `END` token",
        "  (byte `0x00`).",
        "- A variadic operator may also declare `head_types`: leading",
        "  slots with their own types, filled before the tail opens.",
        "  `APPLY` is the only one — its head is the function being",
        "  called, and the tail is the arguments.",
        "- `LIT_INT` (0x01) is the only operator with a non-AST payload:",
        "  after the byte, a 1-byte length prefix L, then L bytes of",
        "  big-endian signed two's-complement integer.",
        "",
        "## Type system",
        "",
        "Four types:",
        "",
        "- **Int** - any integer-valued expression.  Produced by most",
        "  operators.",
        "- **LiteralInt** - subtype of Int; produced *only* by `LIT_INT`.",
        "  Used where a bound-variable identifier is required (slot 0 of",
        "  `LET`, `LAMBDA` and `REF`).",
        "- **Fn** - a unary function `Int -> Value`, produced by `LAMBDA`",
        "  and `LOOP_UNTIL`.  Multi-argument functions are curried, so a",
        "  two-argument function is an `Fn` returning an `Fn`.  `Fn` and",
        "  `Int` are incomparable: neither is a subtype of the other, so",
        "  an `Int` slot never offers a function and `APPLY`'s head slot",
        "  offers nothing else.",
        "- **Value** - the top type.  Exactly one slot has it: the value",
        "  slot of `LET`, because a binding may hold either an integer or",
        "  a function.  Nothing *produces* a `Value`.",
        "",
        "Subtype relation: `LiteralInt <: Int <: Value` and `Fn <: Value`.",
        "",
        "**Where the guarantee stops.** `valid_next` enforces types at the",
        "*operator* level: it cannot consult scope, because name ids live",
        "in `LIT_INT` payloads that the generation state machine never",
        "sees.  So `REF` declares `Int`, and a reference to a",
        "function-valued binding used in an integer slot is caught by the",
        "compiler's scope-aware type pass rather than being unrepresentable",
        "at generation time.  Same division of labour as `unbound-ref`",
        "(Exp 08).  Curried arity is likewise untracked, so a partial",
        "application in an `Int` slot fails at run time, not at compile",
        "time (see journal Q35).",
        "",
        "## Ordering, without an ordering operator",
        "",
        "The core has no `<`.  Ordering is built from the surprise family:",
        "`DEVIATION` (0x1F) is the signed sibling of `SURPRISE` (which",
        "returns `|a - b|`), and `THRESHOLD` (0x1B) is the sign test.",
        "",
        "```lova",
        "(threshold (deviation b a))    ; a < b",
        "(threshold (deviation a b))    ; a > b",
        "(surprise a b)                 ; |a - b| — zero iff equal",
        "```",
        "",
        "## Substrate ceilings",
        "",
        "Since abstraction landed, non-termination is reachable, so two",
        "always-on ceilings apply to every run regardless of whether the",
        "program declares a `BUDGET`:",
        "",
        "| Ceiling | Default | Trap | Anomaly kind |",
        "|---|---|---|---|",
        "| `MAX_CALL_DEPTH` | 200 | `DepthTrap` | `recursion-depth-exceeded` |",
        "| `MAX_STEPS` | 1,000,000 | `StepTrap` | `step-limit-exceeded` |",
        "",
        "Both subclass `BudgetTrap` and carry the standard L2 anomaly",
        "schema, so one handler covers every ceiling.  Both are settable",
        "per-`Runtime`.",
        "",
        "## Effect catalogue",
        "",
        "Effects are declared per-operator and aggregated by",
        "`static_analyze`.  Current effects:",
        "",
        "| Effect | Emitted by | Meaning |",
        "|---|---|---|",
        "| `budget-scope` | `BUDGET` (0x10) | Opens a budget-tracked scope |",
        "| `conservation-check` | `CONSERVE` (0x11) | Verifies value invariant at exit |",
        "| `synthetic-violation` | `VIOLATE` (0x17) | Synthetic test-only op that breaks conservation |",
        "| `write-surprise-trace` | `SURPRISE` (0x18), `TRACE_SURPRISE` (0x1D) | Appends to runtime surprise log |",
        "| `read-surprise` | `IF_SURPRISE` (0x2A) | Branches on surprise value |",
        "| `unbounded-cost` | `APPLY` (0x2D), `LOOP_UNTIL` (0x2B) | Node count stops being a cost bound |",
        "",
        "## Stage-1 surface syntax",
        "",
        "Each token has a surface representation (Lisp-like s-expression)",
        "mapped to the byte via `core.tokens.NAME_TO_TOKEN`.  Unicode",
        "aliases recognised by the surface parser:",
        "",
        "| Alias | Maps to |",
        "|---|---|",
    ]
    for alias, name in ALIASES.items():
        parts.append(f"| `{alias}` | `{name}` |")

    parts += [
        "",
        "Three sugars desugar into the tokens above and introduce no",
        "semantics of their own (Constraint 6):",
        "",
        "| Written | Desugars to |",
        "|---|---|",
        "| `(defn f [a b] body)` | `(let f (lambda a (lambda b body)) ...)` |",
        "| `(f x y)` for a bound `f` | `(apply (ref f) x y)` |",
        "| bare `x` in an argument | `(ref x)` |",
        "",
        "Identifiers are interned to integer name ids by the parser and",
        "printed back as integers: the integer is the program (Axiom 1),",
        "the identifier was a convenience for whoever typed it.",
        "",
        "## Revision history",
        "",
        "- 2026-04-23 - initial draft (stub).",
        "- 2026-04-24 - complete, hand-transcribed from SIGNATURES at M5.",
        "  Recorded as 19/64 implemented; `TYPED_TOKENS` in fact held 18.",
        f"- {date.today().isoformat()} - M9.  0x0B / 0x0C reallocated from the",
        "  never-implemented mock-theta placeholders `phi3` / `psi7` to `mul`",
        "  and `mod`; `threshold` (0x1B), `deviation` (0x1F), `loop-until`",
        "  (0x2B), `lambda` (0x2C) and `apply` (0x2D) implemented; `Fn` and",
        "  `Value` types added; this file made genuinely generated.",
        f"  {n_impl}/64 operators implemented.",
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    text = render()
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {OUT_PATH}  ({len(text.splitlines())} lines, "
          f"{len(_implemented())}/64 operators implemented)")


if __name__ == "__main__":
    main()
