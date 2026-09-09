"""LOVA type system (Milestone 2 minimum).

A deliberately tiny type system — two types: ``Int`` and ``LiteralInt``
— with a single subtype relation (``LiteralInt`` <: ``Int``).  Every
operator declares ``in_types`` (typed slots) and ``out_type`` (what it
produces).  This is enough to exhibit type-directed generation
(Axiom 3): from any prefix of a token sequence, the set of well-typed
next tokens is computable.

**Paradigm lineage** (see ``../spec/paradigm-inheritance.md``):
- Dependent types (Agda/Idris/Lean): types constrain the space of
  valid programs.
- Grammar-constrained decoding (Outlines/llguidance/LMQL): runtime
  enforcement of structural grammars during LLM generation.
- Positional typing (stack languages, Forth, APL): type is a function
  of position in the token stream, not explicit annotation.

LOVA's synthesis: full-language grammar-constraint enforced at each
token position, so that an AI generating tokens from the valid set
cannot produce ill-typed programs.

Future milestones will add ``Population<F>``, ``Stream<T>``,
``Conserved<sum>``, ``Lineage<T>`` and richer subtyping relations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Type:
    """A type descriptor — MVP uses a flat name-based identity."""
    name: str

    def __repr__(self) -> str:
        return self.name


# --- the two types we use in Milestone 2 -------------------------------

INT = Type("Int")
"""Any integer-valued expression (literals or computed)."""

LITERAL_INT = Type("LiteralInt")
"""Literal integer only (for name-binding slots in LET / REF).

``LiteralInt`` is a subtype of ``Int`` — a literal can satisfy any slot
that expects ``Int``, but a slot that requires ``LiteralInt`` (e.g. the
name slot in ``(LET name value body)``) will reject a computed ``Int``
expression.  This is how we enforce "name must be a literal" at the
type-system level rather than with ad-hoc parser checks.
"""


# --- subtype relation (table-driven; keep it simple in MVP) -------------

# Set of (child, parent) pairs that are in the subtype relation.  Any
# pair not in this set is NOT a subtype relation.  Reflexivity is
# handled separately.
_SUBTYPE_PAIRS = frozenset({
    (LITERAL_INT, INT),
})


def is_subtype(child: Type, parent: Type) -> bool:
    """Is ``child`` a subtype of ``parent``?

    Reflexive (T <: T) and includes the explicit pairs in
    ``_SUBTYPE_PAIRS``.  MVP does not support structural subtyping or
    parameterised types.
    """
    if child == parent:
        return True
    return (child, parent) in _SUBTYPE_PAIRS


# --- self-test ----------------------------------------------------------

def _self_test() -> None:
    assert is_subtype(INT, INT)
    assert is_subtype(LITERAL_INT, LITERAL_INT)
    assert is_subtype(LITERAL_INT, INT)
    assert not is_subtype(INT, LITERAL_INT)
    print("core.types self-test OK")
    print(f"  INT          = {INT}")
    print(f"  LITERAL_INT  = {LITERAL_INT}")
    print(f"  LITERAL_INT <: INT  :  {is_subtype(LITERAL_INT, INT)}")
    print(f"  INT         <: LITERAL_INT  :  {is_subtype(INT, LITERAL_INT)}")


if __name__ == "__main__":
    _self_test()
