"""Tests for M20 — function shapes, as far as the checker can see.

``Fn`` said "callable" and nothing more, so a partial application in an
integer slot, a call with too many arguments, or a call result in the
wrong slot all failed at run time (Q35, Q51).  The compiler now infers a
*shape* -- curried arity and return type -- from any syntactically
visible lambda, lets it flow through ``let`` and ``apply``, and refuses
what the shape rules out.  Where the tree does not say -- a parameter
(Q43), a ``head``, an ``eval``, a recursive call still being typed --
the answer is still unknown, and unknown is still accepted anywhere.
The generator is untouched: it sees operator bytes, not shapes.
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.conservation import DomainTrap
from core.generator import validates
from core.runtime import Closure, Runtime, evaluate
from core.surface import parse, parse_with_prelude
from core.tokens import encode
from core.types import FN, FnType, INT, LIST, LITERAL_INT, VALUE, fn_type, is_subtype


def run(src: str, prelude: bool = False):
    tree = parse_with_prelude(src) if prelude else parse(src)
    return evaluate(compile(tree)[0], Runtime())


def refused(test, src: str, prelude: bool = False):
    tree = parse_with_prelude(src) if prelude else parse(src)
    with test.assertRaises(CompileError) as ctx:
        compile(tree)
    test.assertEqual(ctx.exception.anomaly["kind"], "type-mismatch")
    return ctx.exception.anomaly["detail"]


class TestShapeType(unittest.TestCase):

    def test_a_shape_prints_its_arity_and_return(self):
        self.assertEqual(repr(fn_type(2, INT)), "Fn<2,Int>")
        self.assertEqual(repr(fn_type(1)), "Fn<1,?>")

    def test_a_shape_is_an_fn_and_a_value(self):
        self.assertTrue(is_subtype(fn_type(2, INT), FN))
        self.assertTrue(is_subtype(fn_type(2, INT), VALUE))
        self.assertFalse(is_subtype(fn_type(2, INT), INT))
        self.assertFalse(is_subtype(fn_type(2, INT), LIST))

    def test_a_plain_fn_promises_no_shape(self):
        self.assertFalse(is_subtype(FN, fn_type(1, INT)))

    def test_shapes_compare_by_arity_and_return(self):
        self.assertTrue(is_subtype(fn_type(1, LITERAL_INT), fn_type(1, INT)))
        self.assertFalse(is_subtype(fn_type(1, INT), fn_type(1, LITERAL_INT)))
        self.assertTrue(is_subtype(fn_type(1, INT), fn_type(1, None)))
        self.assertFalse(is_subtype(fn_type(1, INT), fn_type(2, INT)))
        self.assertIsInstance(fn_type(1), FnType)


class TestArity(unittest.TestCase):

    def test_too_many_arguments_is_a_compile_error(self):
        detail = refused(self, "(apply (lambda 0 (mul (ref 0) 2)) 1 2)")
        self.assertEqual(detail["takes"], 1)
        self.assertEqual(detail["given"], 2)

    def test_the_curried_chain_is_counted(self):
        compile(parse("(apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 1 2)"))
        detail = refused(self, "(apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 1 2 3)")
        self.assertEqual(detail["takes"], 2)

    def test_an_unknown_return_may_still_be_a_function(self):
        # The body returns a parameter: it could be a function, so three
        # arguments are not provably too many.  The runtime decides.
        compile(parse("(apply (lambda 0 (lambda 1 (ref 0))) 1 2 3)"))

    def test_a_function_returned_through_an_if_is_counted(self):
        src = "(apply (lambda 0 (if (ref 0) (lambda 1 1) (lambda 1 2))) 1 2)"
        self.assertEqual(run(src), 1)
        refused(self, "(apply (lambda 0 (if (ref 0) (lambda 1 1) (lambda 1 2))) 1 2 3)")

    def test_a_loop_function_has_no_shape(self):
        # `loop-until` yields a plain Fn; nothing is said about its arity.
        compile(parse("(apply (loop-until (lambda 0 1) (lambda 0 (ref 0))) 1)"))

    def test_via_def_sugar(self):
        refused(self, "(def pair [a b] (merge a b)) (pair 1 2 3)")
        self.assertEqual(run("(def pair [a b] (merge a b)) (pair 1 2)"), 3)


class TestResultType(unittest.TestCase):

    def test_a_partial_application_in_an_int_slot_is_refused(self):
        detail = refused(self, "(merge (apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 3) 1)")
        self.assertEqual(detail["produces"], "Fn")
        self.assertEqual(detail["shape"], "Fn<1,Int>")

    def test_a_partial_application_is_still_a_value(self):
        self.assertIsInstance(
            run("(apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 3)"), Closure)

    def test_a_list_result_in_an_int_slot_is_refused(self):
        detail = refused(self, "(merge (apply (lambda 0 (nil)) 1) 1)")
        self.assertEqual(detail["produces"], "List")

    def test_an_int_result_in_a_list_slot_is_refused(self):
        refused(self, "(head (apply (lambda 0 (mul (ref 0) 2)) 1))")

    def test_the_shape_flows_through_let(self):
        refused(self, "(def twice [x] (mul x 2)) (head (twice 3))")
        self.assertEqual(run("(def twice [x] (mul x 2)) (merge (twice 3) 1)"), 7)

    def test_a_reference_to_a_shaped_binding_reports_the_family(self):
        detail = refused(self, "(let 0 (lambda 1 (mul (ref 1) 2)) (merge (ref 0) 1))")
        self.assertEqual(detail["produces"], "Fn")
        self.assertEqual(detail["shape"], "Fn<1,Int>")

    def test_a_recursive_function_gets_its_return_from_the_base_case(self):
        src = "(def len2 [xs] (if (nil? xs) 0 (merge 1 (len2 (tail xs)))))"
        self.assertEqual(run(src + " (merge (len2 (list 1 2)) 0)"), 2)
        refused(self, src + " (head (len2 (list 1 2)))")

    def test_disagreeing_branches_are_unknown(self):
        # One branch an Int, the other a List: nothing is claimed, so
        # the misuse is the runtime's, as before.
        src = "(def pick [c] (if c 1 (nil)))"
        compile(parse(src + " (merge (pick 1) 1)"))
        compile(parse(src + " (head (pick 0))"))
        self.assertEqual(run(src + " (merge (pick 1) 1)"), 2)

    def test_agreeing_branches_are_known(self):
        refused(self, "(def pick [c] (if c (nil) (list 1))) (merge (pick 1) 1)")

    def test_a_handler_that_returns_the_wrong_type_is_refused(self):
        refused(self, "(merge (try (div 1 0) (nil)) 1)")
        self.assertEqual(run("(merge (try (div 1 0) 7) 1)"), 8)


class TestHonestUnknowns(unittest.TestCase):

    def test_a_parameter_is_still_untyped(self):
        # Q43 stays open by design: no annotations, so the misuse of a
        # parameter is caught where its value is used, at run time.
        compile(parse("(apply (lambda 0 (merge (ref 0) 1)) (nil))"))
        with self.assertRaises(DomainTrap):
            run("(apply (lambda 0 (merge (ref 0) 1)) (nil))")

    def test_head_and_eval_are_still_unknown(self):
        compile(parse("(merge (head (list 1)) 1)"))
        compile(parse("(merge (eval (quote 1)) 1)"))

    def test_the_prelude_gets_shapes(self):
        refused(self, "(head (len (list 1)))", prelude=True)
        refused(self, "(merge (map (lambda 9 (ref 9)) (list 1)) 1)", prelude=True)
        self.assertEqual(run("(sum (map (lambda 9 (mul (ref 9) 2)) (list 1 2)))", prelude=True), 6)

    def test_generation_is_unchanged(self):
        # Shapes are the compiler's; the state machine still sees `Fn`.
        self.assertTrue(validates(encode(parse("(apply (lambda 0 (ref 0)) 1 2)"))))


if __name__ == "__main__":
    unittest.main()
