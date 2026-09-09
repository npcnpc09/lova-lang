"""Tests for M17 — lists hold any value; the termination bias stays certain.

From M10 to M16 a cons cell held an ``Int``, which kept ``head : List
-> Int`` sound and ruled out trees, lists of programs and nested
structure (Q42). M17 widens the element to ``Value`` and makes ``head``'s
result follow its operand — unknown to the checker, checked at run time
— the trade ``apply`` and ``ref`` already made.

That change had a side effect on the generator: ``(head (nil))`` became
the cheapest way to close an ``Fn`` slot, so the depth bias would reach
for a guaranteed trap. The bias now chooses among *certain* closers
only; the free phase may still gamble.
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.conservation import DomainTrap
from core.generator import (
    GenState, cheapest_to_finish, completion_cost, constrained_random,
    is_certain, validates,
)
from core.runtime import Cons, Runtime, evaluate, list_to_python
from core.surface import parse, parse_with_prelude
from core.tokens import (
    APPLY, HEAD, LAMBDA, LET, LIT_INT, REF, RESULT_NOT_STATIC, decode, encode,
)
from core.types import FN, INT, LIST, PROGRAM


def run(src: str, rt: Runtime = None):
    return evaluate(compile(parse(src))[0], rt or Runtime())


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


class TestNestedLists(unittest.TestCase):

    def test_a_list_of_lists(self):
        value = run("(list (list 1 2) (list 3) (nil))")
        self.assertIsInstance(value.head, Cons)
        self.assertEqual(value.depth(), 2)
        self.assertEqual([list_to_python(x) if isinstance(x, Cons) else x
                          for x in list_to_python(value)][:2], [[1, 2], [3]])

    def test_head_of_a_nested_list(self):
        self.assertEqual(run("(head (head (list (list 7 8) (list 9))))"), 7)

    def test_a_tree_can_be_summed(self):
        src = ("(def tsum [t] (if (nil? t) 0 (merge (sum (head t)) (tsum (tail t)))))"
               "(tsum (list (list 1 2) (list 3 4) (list 5)))")
        self.assertEqual(evaluate(compile(parse_with_prelude(src))[0]), 15)

    def test_a_list_of_programs(self):
        self.assertEqual(
            text(run("(explain (head (list (quote (merge 1 2)) (quote 5))))")),
            "(merge 1 2)")

    def test_a_list_of_functions(self):
        self.assertEqual(
            run("(apply (head (list (lambda 0 (mul (ref 0) 2)))) 21)"), 42)

    def test_strings_are_unchanged(self):
        self.assertEqual(text(run('"abc"')), "abc")
        self.assertEqual(run('(head "abc")'), 97)

    def test_nested_lists_survive_the_bytes(self):
        tree = parse("(list (list 1 2) (list 3))")
        self.assertEqual(decode(encode(tree)), tree)
        self.assertTrue(validates(encode(tree)))


class TestHeadIsTransparent(unittest.TestCase):

    def test_head_in_an_int_slot_compiles(self):
        compile(parse("(merge (head (list 1)) 1)"))

    def test_a_nested_head_in_an_int_slot_fails_at_run_time(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(merge (head (list (list 1))) 1)")
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")

    def test_head_of_a_non_list_is_still_a_compile_error(self):
        with self.assertRaises(CompileError):
            compile(parse("(head 5)"))

    def test_a_list_binding_is_still_tracked(self):
        with self.assertRaises(CompileError):
            compile(parse("(let 0 (nil) (merge (ref 0) 1))"))

    def test_head_is_in_the_transparent_set(self):
        self.assertIn(HEAD, RESULT_NOT_STATIC)

    def test_a_program_cannot_be_written_via_a_list(self):
        # A list is written as codepoints; a program inside one is not a
        # codepoint, and says so.
        with self.assertRaises(DomainTrap):
            run("(stdout (list (quote 1)))")


class TestCertainBias(unittest.TestCase):

    def test_fn_slot_costs_a_lambda(self):
        self.assertEqual(completion_cost(FN), 3)

    def test_program_slot_costs_a_quote(self):
        self.assertEqual(completion_cost(PROGRAM), 2)

    def test_the_bias_never_picks_a_gamble(self):
        for slot_type in (INT, LIST, FN, PROGRAM):
            with self.subTest(slot=slot_type):
                fresh = GenState.fresh(slot_type)
                for token in cheapest_to_finish(fresh, fresh.valid_next()):
                    self.assertNotIn(token, RESULT_NOT_STATIC)

    def test_head_is_not_certain(self):
        self.assertFalse(is_certain(GenState.fresh(FN), HEAD))

    def test_a_ref_to_a_typed_function_is_certain(self):
        state = (GenState.fresh(INT).step(LET).step(LIT_INT, 0)
                 .step(LAMBDA).step(LIT_INT, 1).step(LIT_INT, 5).step(APPLY))
        self.assertTrue(is_certain(state, REF))
        self.assertEqual(cheapest_to_finish(state, state.valid_next()), [REF])

    def test_a_ref_to_an_untyped_binding_is_not_certain(self):
        # Bound by a call: type unknown, so the bias will not lean on it.
        state = (GenState.fresh(INT).step(LET).step(LIT_INT, 0)
                 .step(APPLY).step(LAMBDA).step(LIT_INT, 1).step(LIT_INT, 5)
                 .step(0x00)                                  # END the apply
                 .step(APPLY))
        self.assertFalse(is_certain(state, REF))

    def test_generation_still_terminates_and_validates(self):
        self.assertTrue(all(validates(constrained_random(seed=s, max_depth=6))
                            for s in range(300)))


if __name__ == "__main__":
    unittest.main()
