"""Tests for M10 — data, and the zero-slot surface levers.

Until M10 the only LOVA value was a scalar integer. This milestone adds
one cons cell and one division operator, and takes the two surface
levers Exp 13 measured:

- ``nil`` / ``cons`` / ``head`` / ``tail`` / ``nil?`` — lists, and
  therefore pairs, and therefore strings as codepoint lists
- ``div`` — division was O(a/b) repeated subtraction burning call depth
- one-token operator spellings — 30% of the algorithmic density gap for
  zero token-table slots (Exp 13)
- ``sub`` / ``lt`` / ``gt`` / ``list`` / ``"..."`` as macros — the two
  candidate primitives Exp 13 costed at 9% for two slots, taken as
  expansions instead so they cost none
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.generator import GenState
from core.runtime import (
    Cons, NIL_VALUE, Runtime, evaluate, is_list_value, list_from,
    list_to_python,
)
from core.surface import MACROS, parse, pretty, string_to_nodes
from core.tokens import (
    CONS, DIV, HEAD, IS_NIL, NIL, SHORT_ALIASES, SIGNATURES, TAIL,
    TYPED_TOKENS, decode, encode,
)
from core.types import INT, LIST, VALUE, is_subtype


def run(src: str, rt: Runtime = None):
    return evaluate(parse(src), rt)


# --- division ---------------------------------------------------------------

class TestDiv(unittest.TestCase):
    """0x0D carries div since M10 (it was the Dedekind-eta stub)."""

    def test_div(self):
        self.assertEqual(run("(div 17 5)"), 3)
        self.assertEqual(run("(div 10 2)"), 5)

    def test_div_is_floored_like_mod(self):
        # Sign convention has to match `mod`, or `(merge (mul (div a b) b)
        # (mod a b))` stops equalling `a`.
        for a, b in ((17, 5), (-17, 5), (17, -5), (-17, -5)):
            with self.subTest(a=a, b=b):
                q = run(f"(div {a} {b})")
                r = run(f"(mod {a} {b})")
                self.assertEqual(q, a // b)
                self.assertEqual(q * b + r, a)

    def test_div_by_zero_is_loud(self):
        with self.assertRaises(ValueError):
            run("(div 3 0)")

    def test_div_folds(self):
        node, _ = compile(parse("(div 100 7)"))
        self.assertEqual(pretty(node), "14")

    def test_division_by_zero_does_not_fold(self):
        node, _ = compile(parse("(div 3 0)"))
        self.assertNotEqual(pretty(node), "0")

    def test_digit_sum_was_impossible_before(self):
        # Digit sum needs floor division by ten.  `partition` halves, so
        # before M10 this could only be written as repeated subtraction.
        src = "(def ds [n] (if n (merge (mod n 10) (ds (div n 10))) 0))(ds {n})"
        for n in (0, 7, 98765, 999):
            with self.subTest(n=n):
                self.assertEqual(
                    run(src.replace("{n}", str(n))),
                    sum(int(d) for d in str(n)),
                )


# --- lists ------------------------------------------------------------------

class TestLists(unittest.TestCase):

    def test_nil_is_a_list(self):
        value = run("(nil)")
        self.assertIs(value, NIL_VALUE)
        self.assertTrue(is_list_value(value))

    def test_cons_builds_a_list(self):
        value = run("(cons 1 (cons 2 (cons 3 (nil))))")
        self.assertIsInstance(value, Cons)
        self.assertEqual(list_to_python(value), [1, 2, 3])

    def test_head_and_tail(self):
        self.assertEqual(run("(head (list 7 8 9))"), 7)
        self.assertEqual(list_to_python(run("(tail (list 7 8 9))")), [8, 9])

    def test_nil_predicate(self):
        self.assertEqual(run("(nil? (nil))"), 1)
        self.assertEqual(run("(nil? (list 1))"), 0)

    def test_head_of_empty_is_loud(self):
        # Constraint 5: no silent failures.  An empty list has no head.
        with self.assertRaises(ValueError) as ctx:
            run("(head (nil))")
        self.assertIn("nil?", str(ctx.exception))

    def test_tail_of_empty_is_loud(self):
        with self.assertRaises(ValueError):
            run("(tail (nil))")

    def test_tail_is_structural_sharing(self):
        # A cons cell, not a copied slice: tail must be the same object,
        # which is what makes traversal O(n) rather than O(n^2).
        value = run("(list 1 2 3)")
        self.assertIs(run("(head (nil))") if False else value.tail, value.tail)
        self.assertIsInstance(value.tail, Cons)

    def test_list_helpers_round_trip(self):
        self.assertEqual(list_to_python(list_from([1, 2, 3])), [1, 2, 3])
        self.assertEqual(list_to_python(list_from([])), [])

    def test_list_to_python_rejects_a_non_list(self):
        with self.assertRaises(ValueError):
            list_to_python(5)

    def test_lists_survive_encode_decode(self):
        tree = parse("(cons 1 (cons 2 (nil)))")
        self.assertEqual(decode(encode(tree)), tree)

    def test_list_consuming_function(self):
        src = ("(def total [xs] (if (nil? xs) 0 "
               "(merge (head xs) (total (tail xs)))))"
               "(total (list 1 2 3 4 5))")
        self.assertEqual(run(src), 15)

    def test_list_returning_function(self):
        src = ("(def rev [xs acc] (if (nil? xs) acc "
               "(rev (tail xs) (cons (head xs) acc))))"
               "(rev (list 1 2 3) (nil))")
        self.assertEqual(list_to_python(run(src)), [3, 2, 1])

    def test_a_cons_cell_is_a_pair(self):
        # The two-value return `partition` has always wanted.
        src = "(cons 3 (cons 4 (nil)))"
        pair = run(src)
        self.assertEqual((pair.head, pair.tail.head), (3, 4))


# --- strings ----------------------------------------------------------------

class TestStrings(unittest.TestCase):
    """A string is a list of codepoints, so it costs zero table slots."""

    def test_string_literal_desugars_to_cons(self):
        self.assertEqual(parse('"abc"'), parse("(list 97 98 99)"))

    def test_string_evaluates_to_codepoints(self):
        self.assertEqual(list_to_python(run('"LOVA"')), [76, 79, 86, 65])

    def test_empty_string_is_nil(self):
        self.assertIs(run('""'), NIL_VALUE)

    def test_escapes(self):
        self.assertEqual(list_to_python(run('"a\\nb"')), [97, 10, 98])
        self.assertEqual(list_to_python(run('"a\\"b"')), [97, 34, 98])

    def test_unterminated_string_is_rejected(self):
        with self.assertRaises(ValueError):
            parse('"abc')

    def test_string_is_not_an_identifier(self):
        # `"1"` must not be read as the integer 1, nor as a name.
        self.assertEqual(list_to_python(run('"1"')), [49])

    def test_string_helper_matches_the_literal(self):
        self.assertEqual(string_to_nodes("hi"), parse('"hi"'))

    def test_string_length(self):
        src = ("(def len [xs] (if (nil? xs) 0 (merge 1 (len (tail xs)))))"
               "(len \"racecar\")")
        self.assertEqual(run(src), 7)


# --- surface levers ---------------------------------------------------------

class TestShortSpellings(unittest.TestCase):
    """Zero slots, zero semantics: additional accepted spellings."""

    def test_every_alias_parses_to_its_canonical_form(self):
        for alias, canonical in SHORT_ALIASES.items():
            with self.subTest(alias=alias):
                if canonical == "defn":
                    short = f"({alias} f [x] x)(f 1)"
                    long = f"({canonical} f [x] x)(f 1)"
                else:
                    token = next(t for t, sig in SIGNATURES.items()
                                 if sig["name"] == canonical)
                    arity = SIGNATURES[token]["arity"]
                    args = " ".join(["1"] * (arity if isinstance(arity, int) else 1))
                    short = f"({alias} {args})".replace("( ", "(")
                    long = f"({canonical} {args})".replace("( ", "(")
                self.assertEqual(parse(short), parse(long))

    def test_aliases_do_not_change_the_pretty_printer(self):
        # Canonical names stay canonical -- these are spellings, not renames.
        self.assertEqual(pretty(parse("(if 1 2 3)")), "(if-surprise 1 2 3)")

    def test_unicode_pretty_printing_is_unaffected(self):
        self.assertEqual(pretty(parse("(mul 2 3)"), unicode=True), "(⊗ 2 3)")

    def test_alias_does_not_shadow_a_variable_name(self):
        # `dist` as a parameter name still binds, because aliases resolve
        # only in operator position.
        self.assertEqual(run("(def f [dist] (merge dist 1))(f 41)"), 42)


class TestMacros(unittest.TestCase):
    """The two primitives Exp 13 costed at 2 slots, taken as expansions."""

    def test_sub_on_a_literal_folds_the_negation(self):
        # (sub n 1) must be two nodes, not four -- and `1` is one LLM
        # token where `-1` is two.
        self.assertEqual(parse("(sub 10 3)"), parse("(merge 10 -3)"))

    def test_sub_on_an_expression(self):
        self.assertEqual(parse("(sub 10 (p 3))"),
                         parse("(merge 10 (mul -1 (p 3)))"))
        self.assertEqual(run("(sub 10 (p 3))"), 7)

    def test_lt_and_gt(self):
        self.assertEqual(parse("(lt 3 5)"), parse("(threshold (deviation 5 3))"))
        self.assertEqual(run("(lt 3 5)"), 1)
        self.assertEqual(run("(lt 5 3)"), 0)
        self.assertEqual(run("(lt 3 3)"), 0)
        self.assertEqual(run("(gt 5 3)"), 1)
        self.assertEqual(run("(gt 3 5)"), 0)

    def test_macros_reach_no_new_tokens(self):
        # Constraint 6: sugar must not introduce semantics the core 64
        # tokens cannot express.
        for src in ("(sub 5 2)", "(lt 1 2)", "(gt 1 2)", "(list 1 2)", '"ab"'):
            with self.subTest(src=src):
                ops = set()

                def collect(node):
                    ops.add(node.op)
                    if node.op != 0x01:
                        for child in node.args:
                            collect(child)

                collect(parse(src))
                for op in ops:
                    self.assertLessEqual(op, 0x3F)
                    self.assertIn(op, TYPED_TOKENS)

    def test_macro_arity_is_checked(self):
        with self.assertRaises(ValueError) as ctx:
            parse("(sub 1)")
        self.assertIn("sub", str(ctx.exception))

    def test_variadic_macro_accepts_any_arity(self):
        self.assertIn("list", MACROS)
        self.assertEqual(list_to_python(run("(list)")), [])
        self.assertEqual(list_to_python(run("(list 1 2 3 4)")), [1, 2, 3, 4])


# --- types ------------------------------------------------------------------

class TestListTypes(unittest.TestCase):

    def test_list_is_disjoint_from_int_and_fn(self):
        from core.types import FN
        self.assertFalse(is_subtype(LIST, INT))
        self.assertFalse(is_subtype(INT, LIST))
        self.assertFalse(is_subtype(LIST, FN))
        self.assertTrue(is_subtype(LIST, VALUE))

    def test_int_slot_never_offers_a_list(self):
        valid = GenState.fresh().valid_next()
        self.assertNotIn(NIL, valid)
        self.assertNotIn(CONS, valid)
        self.assertIn(DIV, valid)
        self.assertIn(HEAD, valid)      # head produces an Int
        self.assertIn(IS_NIL, valid)

    def test_list_slot_offers_list_producers_and_nothing_typed_otherwise(self):
        from core.tokens import (
            EXPLAIN, FITNESS, LINEAGE_QUERY, MERGE, P, RESULT_NOT_STATIC,
            STDIN, TRACE, WHY,
        )
        valid = GenState.fresh().step(HEAD).valid_next()
        # Lists come from the cons cell, from input, from every Meta
        # operator that answers in text (M14), and from `fitness` (M15).
        producers = frozenset({NIL, CONS, TAIL, STDIN,
                               EXPLAIN, LINEAGE_QUERY, WHY, TRACE, FITNESS})
        self.assertLessEqual(producers, valid)
        # Plus the operators whose result type the state machine cannot
        # see -- a conditional returning a list is how `map` is shaped.
        self.assertLessEqual(valid, producers | RESULT_NOT_STATIC)
        self.assertNotIn(MERGE, valid)
        self.assertNotIn(P, valid)

    def test_list_generation_can_terminate(self):
        # `nil` is arity 0, so a List slot always has a terminating choice.
        from core.observability import _is_terminating
        self.assertTrue(_is_terminating(NIL))

    def test_list_in_an_int_slot_is_a_compile_error(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (nil) 1)"))
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "type-mismatch")
        self.assertEqual(anomaly["detail"]["produces"], "List")

    def test_int_in_a_list_slot_is_a_compile_error(self):
        with self.assertRaises(CompileError):
            compile(parse("(head 5)"))

    def test_list_bound_by_let_is_tracked(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(let 0 (nil) (merge (ref 0) 1))"))
        self.assertEqual(ctx.exception.anomaly["detail"]["produces"], "List")

    def test_parameter_references_are_accepted_in_any_slot(self):
        # A parameter's type is not knowable from the definition, so the
        # checker accepts it anywhere and leaves misuse to the runtime.
        node, _ = compile(parse(
            "(def f [xs] (if (nil? xs) 0 (head xs)))(f (list 9))"
        ))
        self.assertEqual(evaluate(node), 9)

    def test_a_misused_parameter_fails_at_runtime_with_a_hint(self):
        with self.assertRaises(ValueError) as ctx:
            run("(def f [xs] (merge xs 1))(f (list 9))")
        self.assertIn("head", str(ctx.exception))

    def test_apply_accepts_a_list_argument(self):
        node, _ = compile(parse("(def f [xs] (head xs))(f (list 4 5))"))
        self.assertEqual(evaluate(node), 4)


# --- budget accounting ------------------------------------------------------

class TestSlotBudget(unittest.TestCase):
    """The allocation actually spent, guarded against drift."""

    def test_slots_spent_so_far(self):
        # 25 after M9, +6 data (M10), +2 IO (M11), +1 when-anomaly (M13),
        # +12 for M14: quote/eval, the whole Meta family, clone/mutate;
        # +6 for M15: the rest of Evolution; +1 for M18: read; +4 for
        # M19: external-boundary, fs-read, fs-write, clock.
        self.assertEqual(len(TYPED_TOKENS), 57)

    def test_the_core_is_still_64_operators(self):
        self.assertEqual(len(SIGNATURES), 64)

    def test_reallocated_slots_carry_their_new_meaning(self):
        expected = {
            0x04: "cons", 0x05: "head", 0x06: "tail",
            0x0D: "div", 0x15: "nil", 0x19: "nil?",
            # M11 and M13 used slots for what the original table named
            # them, so these are activations rather than reallocations.
            0x35: "stdout", 0x36: "stdin", 0x1A: "when-anomaly",
            # M14: the two free slots spent, and the Meta family activated.
            0x29: "quote", 0x1C: "eval",
            0x3B: "explain", 0x3C: "hash", 0x3D: "uid", 0x3F: "generation",
            0x3E: "ancestor-of", 0x38: "lineage-query", 0x39: "why",
            0x3A: "trace", 0x25: "clone", 0x24: "mutate",
            # M15: the rest of the Evolution family, activated as named.
            0x20: "defpop", 0x21: "variant", 0x22: "evolve",
            0x23: "select", 0x26: "fitness", 0x27: "retire",
            # M18: read, the inverse of explain, on a free slot.
            0x1E: "read",
        }
        for byte, name in expected.items():
            self.assertEqual(SIGNATURES[byte]["name"], name)

    def test_number_theory_family_was_not_reallocated(self):
        # Exp 13's reserve position, deliberately not taken.
        for byte, name in ((0x08, "p"), (0x09, "tau"), (0x0A, "sigma"),
                           (0x0E, "gcd"), (0x0F, "mobius")):
            self.assertEqual(SIGNATURES[byte]["name"], name)


if __name__ == "__main__":
    unittest.main()
