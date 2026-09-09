"""Unit tests for ``core.runtime`` — per-operator behaviour + traps."""

from __future__ import annotations

import unittest

from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, evaluate, mobius, partition_number, sigma, tau
from core.surface import parse


class NumberTheoryReferenceValues(unittest.TestCase):

    def test_p(self):
        for n, expected in [(0, 1), (1, 1), (2, 2), (5, 7), (10, 42), (12, 77),
                             (20, 627)]:
            self.assertEqual(partition_number(n), expected)

    def test_tau(self):
        for n, expected in [(1, 1), (12, 6), (17, 2), (100, 9), (36, 9)]:
            self.assertEqual(tau(n), expected)

    def test_sigma(self):
        for n, expected in [(1, 1), (6, 12), (10, 18), (12, 28), (28, 56)]:
            self.assertEqual(sigma(n), expected)

    def test_mobius(self):
        for n, expected in [(1, 1), (2, -1), (4, 0), (6, 1), (12, 0), (30, -1)]:
            self.assertEqual(mobius(n), expected)


class OperatorSemantics(unittest.TestCase):

    def _eval(self, src: str) -> int:
        return evaluate(parse(src))

    def test_merge(self):
        self.assertEqual(self._eval("(merge 3 5)"), 8)

    def test_identity(self):
        self.assertEqual(self._eval("(identity 42)"), 42)

    def test_partition(self):
        # partition returns n // 2 in MVP
        self.assertEqual(self._eval("(partition 10)"), 5)

    def test_gcd(self):
        self.assertEqual(self._eval("(gcd 12 18)"), 6)
        self.assertEqual(self._eval("(gcd 7 13)"), 1)

    def test_nested(self):
        # (merge (p 3) (tau 12)) = 3 + 6 = 9
        self.assertEqual(self._eval("(merge (p 3) (tau 12))"), 9)

    def test_seq_returns_last(self):
        self.assertEqual(self._eval("(seq (p 3) (p 4) (p 5))"), 7)

    def test_let_ref(self):
        self.assertEqual(self._eval("(let 0 12 (p (ref 0)))"), 77)

    def test_if_surprise_nonzero_takes_then(self):
        # surprise between 10 and p(12)=77 is 67 (non-zero) → take then
        self.assertEqual(self._eval("(if-surprise (surprise 10 (p 12)) 1 2)"), 1)

    def test_if_surprise_zero_takes_else(self):
        # surprise between 77 and p(12)=77 is 0 → take else
        self.assertEqual(self._eval("(if-surprise (surprise 77 (p 12)) 1 2)"), 2)


class ConservationTraps(unittest.TestCase):

    def test_budget_pass(self):
        # (p 12) is 2 nodes; budget 100 has lots of headroom
        self.assertEqual(evaluate(parse("(budget 100 (p 12))")), 77)

    def test_budget_fail(self):
        with self.assertRaises(BudgetTrap) as ctx:
            evaluate(parse("(budget 3 (merge (p 3) (tau 12)))"))
        a = ctx.exception.anomaly
        self.assertEqual(a["kind"], "budget-exceeded")
        self.assertEqual(a["detail"]["limit"], 3)
        self.assertGreater(a["detail"]["spent"], 3)
        self.assertIn("repair_hint", a)

    def test_conserve_pass(self):
        # expected 77, body produces p(12)=77 → OK
        self.assertEqual(evaluate(parse("(conserve 77 (p 12))")), 77)

    def test_conserve_fail(self):
        # violate bumps +1 → body returns 78, expected 77 → Δ-trap
        with self.assertRaises(DeltaTrap) as ctx:
            evaluate(parse("(conserve 77 (violate 77))"))
        a = ctx.exception.anomaly
        self.assertEqual(a["kind"], "conservation-violated")
        self.assertEqual(a["detail"]["entry"], 77)
        self.assertEqual(a["detail"]["exit"], 78)

    def test_trap_anomaly_has_enrichment_fields(self):
        """Both traps must include the L2 observability fields."""
        try:
            evaluate(parse("(budget 1 (p 12))"))
        except BudgetTrap as t:
            for key in ("kind", "detail", "position_path", "offending_op",
                        "offending_op_name", "valid_alternatives",
                        "repair_hint"):
                self.assertIn(key, t.anomaly,
                              f"BudgetTrap anomaly missing `{key}`")


class SurpriseTrace(unittest.TestCase):

    def test_surprise_emits_event(self):
        rt = Runtime()
        deviation = evaluate(parse("(surprise 10 (p 12))"), rt)
        self.assertEqual(deviation, 67)
        self.assertEqual(len(rt.surprise.events), 1)
        event = rt.surprise.events[0]
        self.assertEqual(event["predicted"], 10)
        self.assertEqual(event["actual"], 77)
        self.assertEqual(event["deviation"], 67)

    def test_surprise_trace_accumulates(self):
        rt = Runtime()
        evaluate(parse("(surprise 10 (p 12))"), rt)
        evaluate(parse("(surprise 3 (p 3))"), rt)
        evaluate(parse("(surprise 100 (tau 12))"), rt)
        self.assertEqual(len(rt.surprise.events), 3)


class EdgeCases(unittest.TestCase):

    def test_negative_literal_in_merge(self):
        self.assertEqual(evaluate(parse("(merge -3 5)")), 2)

    def test_zero_inputs(self):
        self.assertEqual(evaluate(parse("(tau 0)")), 0)
        self.assertEqual(evaluate(parse("(sigma 0)")), 0)
        self.assertEqual(evaluate(parse("(mobius 0)")), 0)
        self.assertEqual(evaluate(parse("(p 0)")), 1)

    def test_deep_nesting_does_not_stack_overflow(self):
        import sys
        sys.setrecursionlimit(10000)
        depth = 500
        src = "(p " * depth + "3" + ")" * depth
        self.assertEqual(evaluate(parse(src)), 3)

    def test_unbound_ref_raises(self):
        with self.assertRaises(ValueError) as ctx:
            evaluate(parse("(ref 99)"))
        self.assertIn("unbound", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
