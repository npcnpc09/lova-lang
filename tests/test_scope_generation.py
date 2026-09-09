"""Tests for M16 — scope-aware generation; Axiom 3 at the name level.

Until M16 the generation state machine saw operator bytes only. A name
id lives in a LIT_INT payload it never inspected, so `ref` was offered
everywhere and an unbound reference was a compile error rather than an
unrepresentable program. Now `step` takes the payload, the machine keeps
scope, and `ref` is offered only where a bound, type-compatible name
exists. `track_scope=False` is the old machine, kept for measurement.
"""

from __future__ import annotations

import random
import unittest

from core.compiler import CompileError, compile
from core.generator import (
    Frame, GenState, constrained_random, validates,
)
from core.surface import parse
from core.tokens import (
    APPLY, LAMBDA, LET, LIT_INT, MERGE, REF, decode, encode,
)
from core.types import FN, INT, LIST, VALUE


def v(src: str, **kw) -> bool:
    return validates(encode(parse(src)), **kw)


class TestUnboundIsUnrepresentable(unittest.TestCase):

    def test_unbound_reference_does_not_validate(self):
        self.assertFalse(v("(merge (ref 99) 1)"))

    def test_bound_reference_validates(self):
        self.assertTrue(v("(let 0 5 (merge (ref 0) 1))"))

    def test_the_old_machine_accepted_it(self):
        self.assertTrue(v("(merge (ref 99) 1)", track_scope=False))

    def test_ref_is_not_offered_with_nothing_bound(self):
        self.assertNotIn(REF, GenState.fresh().valid_next())

    def test_ref_is_offered_once_something_is_bound(self):
        state = GenState.fresh().step(LET).step(LIT_INT, 0).step(LIT_INT, 7)
        self.assertIn(REF, state.valid_next())
        self.assertEqual(state.step(REF).valid_names(), [0])

    def test_a_ref_to_the_wrong_name_is_refused_by_step(self):
        state = GenState.fresh().step(LET).step(LIT_INT, 0).step(LIT_INT, 7)
        with self.assertRaises(ValueError):
            state.step(REF).step(LIT_INT, 42)

    def test_scope_closes_with_the_form(self):
        # (merge (let 0 1 (ref 0)) (ref 0)) -- the second ref is outside.
        self.assertFalse(v("(merge (let 0 1 (ref 0)) (ref 0))"))


class TestTypedNames(unittest.TestCase):

    def test_a_function_name_fits_an_fn_slot(self):
        self.assertTrue(v("(let 0 (lambda 1 (ref 1)) (apply (ref 0) 3))"))

    def test_an_integer_name_does_not_fit_an_fn_slot(self):
        self.assertFalse(v("(let 0 5 (apply (ref 0) 3))"))

    def test_a_list_name_does_not_fit_an_int_slot(self):
        self.assertFalse(v("(let 0 (nil) (merge (ref 0) 1))"))

    def test_a_lambda_parameter_is_unknown_and_fits_anywhere(self):
        # The checker's rule (Q43), mirrored: a parameter has no known type.
        self.assertTrue(v("(apply (lambda 0 (merge (ref 0) 1)) 3)"))
        self.assertTrue(v("(apply (lambda 0 (head (ref 0))) 3)"))

    def test_a_binding_from_a_call_is_unknown(self):
        # A call's result is not statically known (Q51); the name fits
        # anywhere, as in the compiler.
        self.assertTrue(v("(let 0 (apply (lambda 1 (ref 1)) 3) (head (ref 0)))"))

    def test_letrec_self_reference_is_in_scope_and_untyped_while_binding(self):
        self.assertTrue(v("(defn f [n] (if n (f (sub n 1)) 0))(f 3)"))

    def test_shadowing_uses_the_inner_binding(self):
        # Inner 0 is an Fn; using it as an Int must be refused, even
        # though an outer 0 is an Int.
        self.assertTrue(v("(let 0 1 (let 0 (lambda 1 (ref 1)) (apply (ref 0) 2)))"))
        self.assertFalse(v("(let 0 1 (let 0 (lambda 1 (ref 1)) (merge (ref 0) 2)))"))


class TestSampler(unittest.TestCase):

    def test_generated_programs_have_no_unbound_references(self):
        for seed in range(200):
            tree = decode(constrained_random(seed=seed, max_depth=6))
            try:
                compile(tree, type_check=False, fold=False, drop_unused=False)
            except CompileError as exc:
                self.assertNotEqual(exc.anomaly["kind"], "unbound-ref",
                                    f"seed {seed}")

    def test_generated_programs_still_all_validate(self):
        self.assertTrue(all(validates(constrained_random(seed=s, max_depth=6))
                            for s in range(200)))

    def test_generation_is_reproducible(self):
        self.assertEqual(constrained_random(seed=7), constrained_random(seed=7))

    def test_literal_for_gives_a_fresh_name_to_a_binder(self):
        state = GenState.fresh().step(LET)
        self.assertEqual(state.literal_for(random.Random(0)), 0)
        inner = state.step(LIT_INT, 0).step(LIT_INT, 1).step(LET)
        self.assertEqual(inner.literal_for(random.Random(0)), 1)

    def test_literal_for_gives_a_bound_name_to_a_ref(self):
        state = GenState.fresh().step(LET).step(LIT_INT, 3).step(LIT_INT, 1).step(REF)
        self.assertEqual(state.literal_for(random.Random(0)), 3)


class TestBoundary(unittest.TestCase):

    def test_mutual_recursion_compiles_but_does_not_validate(self):
        # A left-to-right machine cannot emit a reference to a name bound
        # later.  The generator is strictly more conservative than the
        # compiler, which is the safe direction (Q64).
        src = ("(def ev [n] (if n (od (sub n 1)) 1))"
               "(def od [n] (if n (ev (sub n 1)) 0))(ev 4)")
        compile(parse(src))
        self.assertFalse(v(src))

    def test_frames_are_immutable_across_states(self):
        base = GenState.fresh().step(LET).step(LIT_INT, 0)
        typed = base.step(LIT_INT, 7)
        self.assertIsNone(base.scopes[0].type)
        self.assertEqual(typed.scopes[0].type, INT)

    def test_frame_shape(self):
        frame = Frame(name=0, type=FN, base=1)
        self.assertEqual((frame.name, frame.type, frame.base), (0, FN, 1))


if __name__ == "__main__":
    unittest.main()
