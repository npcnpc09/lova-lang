"""LOVA type system (Milestone 2 minimum, extended in M9 and M10).

A deliberately tiny type system — five types: ``Int``, ``LiteralInt``,
``Fn``, ``List`` and the top type ``Value``.
``Fn`` is disjoint from ``Int``: a function is not an integer and an
integer is not callable, so the slot-type filter alone keeps
``(apply 5 3)`` and ``(merge (lambda ...) 1)`` unrepresentable.  Every
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

FN = Type("Fn")
"""A one-argument function ``Int -> Int`` (M9).

LOVA lambdas are unary; multi-argument functions are curried, so a
two-argument function has type ``Fn`` and *returns* an ``Fn``.  The
type system does not track the arity of the curried chain — it only
distinguishes "callable" from "integer", which is exactly what
``valid_next`` needs to keep the APPLY head slot and the LAMBDA body
slot from being filled with the wrong kind of thing.

``Fn`` and ``Int`` are incomparable: ``Fn`` is not an ``Int`` and
``Int`` is not an ``Fn``.  A slot expecting ``Int`` therefore never
offers LAMBDA / LOOP_UNTIL, and the APPLY head slot offers only the
``Fn``-producing operators.
"""

LIST = Type("List")
"""A list of integers, built from ``cons`` and terminated by ``nil``.

One cons cell is the cheapest purchase in the token table: it buys
pairs (a cell is a pair), lists (nested cells), and strings (a list of
codepoints, so ``"abc"`` is surface sugar and costs no slots at all).
Before it there was no way to return two values -- ``partition``
returns ``n // 2`` rather than the pair it means, because a pair was
not representable.

**Elements are any value (M17).**  From M10 to M16 a cons cell held an
``Int`` only, which kept ``head : List -> Int`` sound at the cost of
ruling out trees, lists of programs and nested structure.  M17 widened
the element to ``Value`` and made ``head``'s result follow its operand
-- unknown to the checker, checked at run time -- the same trade
``apply`` and ``ref`` made.  A parameterised ``List<T>`` would recover
the static answer (journal Q42) and now has something to be measured
against.
"""

PROGRAM = Type("Program")
"""A program as a value (M14).

Axiom 1 says a program *is* an integer.  Until M14 the language could
not touch that integer: nothing produced a program as a value, so
``(explain program)`` -- Stage 3's only human interface -- and every
lineage query were unreachable from inside LOVA.  ``quote`` produces
one, ``eval`` runs one, and the Meta and Evolution families operate on
them.

Disjoint from ``Int``, ``List`` and ``Fn``: a program is not a number
(``hash`` gives you its number), not text (``explain`` gives you its
text), and not callable (``eval`` runs it).
"""

POPULATION = Type("Population")
"""A pool of program variants under a fitness function (M15).

Axiom 6 says a function is a population of variants, not a single
definition.  Until M15 that was true only in ``core/populations.py``:
the Evolution family's remaining six slots each needed a population as
a *value*, and the language had no collection but a list of integers.
This is that value.  ``defpop`` builds one from a scorer and any number
of programs; ``evolve`` returns the next generation; ``select`` ranks.
"""

VALUE = Type("Value")
"""The top type — anything a name can be bound to (M9).

Exactly one slot in the language has this type: the value slot of
``LET``.  A binding may hold an integer or a function, and the slot
must admit both without ``Int`` and ``Fn`` collapsing into each other
everywhere else.  ``Value`` appears in no operator's ``out_type``, so
nothing ever *produces* a ``Value`` — it only ever *accepts* one.
"""


# --- subtype relation (table-driven; keep it simple in MVP) -------------

# Set of (child, parent) pairs that are in the subtype relation.  Any
# pair not in this set is NOT a subtype relation.  Reflexivity is
# handled separately.
# The relation is stored as its explicit transitive closure rather than
# computed — with four types that is three extra pairs, and it keeps
# ``is_subtype`` a single set membership test.
_SUBTYPE_PAIRS = frozenset({
    (LITERAL_INT, INT),
    (LITERAL_INT, VALUE),
    (INT, VALUE),
    (FN, VALUE),
    (LIST, VALUE),
    (PROGRAM, VALUE),
    (POPULATION, VALUE),
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
    # Fn is disjoint from the integer types (M9).
    assert is_subtype(FN, FN)
    assert not is_subtype(FN, INT)
    assert not is_subtype(INT, FN)
    assert not is_subtype(LITERAL_INT, FN)
    # Value is the top type: everything flows into it, nothing out of it.
    for t in (INT, LITERAL_INT, FN, VALUE, LIST, PROGRAM):
        assert is_subtype(t, VALUE), t
    for other in (INT, LIST, FN):
        assert not is_subtype(PROGRAM, other) and not is_subtype(other, PROGRAM)
    # List is incomparable with Int and Fn.
    assert not is_subtype(LIST, INT) and not is_subtype(INT, LIST)
    assert not is_subtype(LIST, FN) and not is_subtype(FN, LIST)
    assert not is_subtype(VALUE, INT)
    assert not is_subtype(VALUE, FN)
    print("core.types self-test OK")
    print(f"  INT          = {INT}")
    print(f"  LITERAL_INT  = {LITERAL_INT}")
    print(f"  LITERAL_INT <: INT  :  {is_subtype(LITERAL_INT, INT)}")
    print(f"  INT         <: LITERAL_INT  :  {is_subtype(INT, LITERAL_INT)}")
    print(f"  FN           = {FN}")
    print(f"  FN          <: INT          :  {is_subtype(FN, INT)}")
    print(f"  VALUE        = {VALUE}  (top; only LET's value slot uses it)")
    print(f"  FN          <: VALUE        :  {is_subtype(FN, VALUE)}")
    print(f"  LIST         = {LIST}")
    print(f"  LIST        <: INT          :  {is_subtype(LIST, INT)}")


if __name__ == "__main__":
    _self_test()
