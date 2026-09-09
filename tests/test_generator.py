"""Unit tests for ``core.generator`` — type-directed generation."""

from __future__ import annotations

import unittest

from core.generator import (
    GenState, constrained_random, unconstrained_random, validates,
)
from core.tokens import (
    END, GCD, LET, LIT_INT, MERGE, P, SEQ, SIGMA, TAU, TYPED_TOKENS,
    decode,
)


class ValidNextInvariants(unittest.TestCase):

    def test_fresh_state_not_empty(self):
        self.assertGreater(len(GenState.fresh().valid_next()), 0)

    def test_fresh_state_is_incomplete(self):
        self.assertFalse(GenState.fresh().is_complete())

    def test_after_lit_fresh_state_is_complete(self):
        state = GenState.fresh().step(LIT_INT)
        self.assertTrue(state.is_complete())

    def test_let_name_slot_allows_only_lit(self):
        state = GenState.fresh().step(LET)
        self.assertEqual(state.valid_next(), frozenset({LIT_INT}))

    def test_variadic_slot_allows_end(self):
        state = GenState.fresh().step(SEQ)
        self.assertIn(END, state.valid_next())

    def test_valid_next_subset_of_typed_tokens(self):
        state = GenState.fresh()
        v = state.valid_next()
        # Every token in valid_next (except END) must be typed.
        self.assertTrue((v - {END}).issubset(TYPED_TOKENS))

    def test_step_rejects_invalid_token(self):
        state = GenState.fresh()
        # END is only valid inside variadic; should reject at fresh.
        with self.assertRaises(ValueError):
            state.step(END)


class ConstrainedGeneration(unittest.TestCase):
    """Constrained generation is 100% well-formed by construction."""

    def test_constrained_random_always_validates(self):
        for seed in range(50):
            with self.subTest(seed=seed):
                data = constrained_random(seed=seed, max_depth=6)
                self.assertTrue(validates(data),
                                f"constrained seed={seed} did not validate: "
                                f"{data.hex()}")

    def test_constrained_random_produces_parseable(self):
        for seed in range(20):
            data = constrained_random(seed=seed, max_depth=6)
            # decode should never raise on a constrained sample.
            decode(data)  # no assertion needed: raising fails the test


class UnconstrainedGeneration(unittest.TestCase):
    """Unconstrained generation rarely (ideally never) validates."""

    def test_unconstrained_mostly_fails(self):
        passes = 0
        N = 200
        for seed in range(N):
            data = unconstrained_random(seed=seed, max_tokens=10)
            if validates(data):
                passes += 1
        # We allow a small number of accidental hits but bound them.
        self.assertLess(passes, N // 20,
                        f"unconstrained validates {passes}/{N}; "
                        f"expected << 5%")


class StateTransitions(unittest.TestCase):

    def test_after_merge_expects_two_ints(self):
        # MERGE has arity 2; state stack should grow after step(MERGE).
        s0 = GenState.fresh()
        s1 = s0.step(MERGE)
        self.assertGreater(len(s1.stack), len(s0.stack))

    def test_filling_all_slots_completes(self):
        # (merge 3 5): MERGE -> LIT 3 -> LIT 5 completes
        s = GenState.fresh().step(MERGE).step(LIT_INT).step(LIT_INT)
        self.assertTrue(s.is_complete())

    def test_seq_closed_with_end(self):
        # SEQ then two literals then END closes the variadic.
        s = (GenState.fresh().step(SEQ)
                              .step(LIT_INT).step(LIT_INT).step(END))
        self.assertTrue(s.is_complete())


if __name__ == "__main__":
    unittest.main()
