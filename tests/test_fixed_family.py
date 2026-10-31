"""The fixed-point family (6b): sin, cos, sin-fine, cos-fine, quot, nth,
isqrt as operators, checked against the LOVA definitions they replace.

The old definitions are kept here, renamed, as the oracle: the operators
must give their values to the bit -- the table, the floored reflections,
the step between entries rounded toward zero, twelve Newton rounds --
and the faults where the definitions faulted.  The native runtime's
agreement is the golden set's business (`corpus/golden/lib.jsonl`,
`traps.jsonl`, the `fixed-*` records).
"""

from __future__ import annotations

import unittest

from core.cli import build, format_value
from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import DomainTrap, Runtime, evaluate
from core.tokens import (FIX_COS, FIX_COS_FINE, FIX_ISQRT, FIX_NTH, FIX_QUOT,
                         FIX_SIN, FIX_SIN_FINE, FIXED_FAMILY, SIGNATURES)

OLD = r"""
(def o-sin-table []
  (list 0 25 50 75 100 125 150 175 200 224 249 273 297
        321 345 369 392 415 438 460 483 505 526 548 569 590
        610 630 650 669 688 706 724 742 759 775 792 807 822
        837 851 865 878 891 903 915 926 936 946 955 964 972
        980 987 993 999 1004 1009 1013 1016 1019 1021 1023 1024 1024))
(def o-sin-q []
  (fold (lambda m (lambda pr (map-put m (head (tail pr)) (head pr))))
        (nil) (zip o-sin-table (range 0 (len o-sin-table)))))
(def o-sin [ang]
  (let k (mod ang 256)
    (cond (le k 64) (map-get o-sin-q k (head (nil)))
          (le k 128) (map-get o-sin-q (sub 128 k) (head (nil)))
          (le k 192) (neg (map-get o-sin-q (sub k 128) (head (nil))))
          (neg (map-get o-sin-q (sub 256 k) (head (nil)))))))
(def o-quot [a b]
  (let [q (div (abs a) (abs b))] (if (eq (lt a 0) (lt b 0)) q (neg q))))
(def o-isqrt [n]
  (if (lt n 4) (if (gt n 0) 1 0)
    (fold (lambda x (lambda i (div (merge x (div n x)) 2)))
          (max 1024 (div n 1024)) (range 0 12))))
(def o-sin-fine [ang]
  (let [a (mod ang 4096) k (div a 16) f (mod a 16) s0 (o-sin k) s1 (o-sin (inc k))]
    (merge s0 (o-quot (mul (sub s1 s0) f) 16))))
(def o-nth [xs k] (head (text-slice xs k (merge k 1))))
(def bad [f g xs] (filter (lambda x (ne (f x) (g x))) xs))
(def big [] (list 1000000000000000000000000000000 -1000000000000000000000000000000
                  31415926535897932384626433832795 98765432109876 -7))
"""


def run(src: str, old: bool = True):
    tree, _ = build((OLD if old else "") + src)
    rt = Runtime(max_steps=200_000_000)
    return evaluate(tree, rt), rt.steps


def value(src: str) -> str:
    return format_value(run(src)[0])


class TheTable(unittest.TestCase):

    def test_the_family_is_seven_operators_at_0x58(self):
        self.assertEqual(sorted(FIXED_FAMILY), list(range(0x58, 0x5F)))
        self.assertEqual([SIGNATURES[t]["name"] for t in sorted(FIXED_FAMILY)],
                         ["sin", "cos", "sin-fine", "cos-fine", "quot", "nth", "isqrt"])
        self.assertEqual((FIX_SIN, FIX_COS, FIX_SIN_FINE, FIX_COS_FINE, FIX_QUOT, FIX_NTH, FIX_ISQRT),
                         tuple(range(0x58, 0x5F)))


class BitForBit(unittest.TestCase):

    def test_sin_and_cos(self):
        self.assertEqual(value("(bad (lambda a (sin a)) o-sin (text-cat (range -600 700) big))"), "()")
        self.assertEqual(value("(bad (lambda a (cos a)) (lambda a (o-sin (merge a 64)))"
                               " (text-cat (range -600 700) big))"), "()")

    def test_the_fine_pair(self):
        self.assertEqual(value("(bad (lambda a (sin-fine a)) o-sin-fine (text-cat (range -4200 4300) big))"), "()")
        self.assertEqual(value("(bad (lambda a (cos-fine a)) (lambda a (o-sin-fine (merge a 1024)))"
                               " (text-cat (range -4200 4300) big))"), "()")

    def test_quot_rounds_toward_zero_both_ways(self):
        self.assertEqual(value(
            "(fold text-cat (nil) (map (lambda b (bad (lambda a (quot a b)) (lambda a (o-quot a b))"
            " (text-cat (range -100 100) big))) (list -17 -8 -3 -1 1 3 8 17 100000000000000000000)))"), "()")
        self.assertEqual(value("(list (quot -9 8) (quot 9 8) (quot 9 -8) (quot -9 -8))"), "(-1 1 -1 1)")

    def test_isqrt_is_twelve_newton_rounds(self):
        self.assertEqual(value("(bad (lambda n (isqrt n)) o-isqrt"
                               " (text-cat (range -20 5000) (text-cat (map (lambda k (mul k (mul k k))) (range 0 900)) big)))"),
                         "()")
        self.assertEqual(value("(list (isqrt -5) (isqrt 0) (isqrt 1) (isqrt 3) (isqrt 4) (isqrt 1048576))"),
                         "(0 0 1 1 2 1024)")

    def test_nth_on_lists_and_texts(self):
        self.assertEqual(value("(let xs (range 50 90) (bad (lambda k (nth xs k)) (lambda k (o-nth xs k)) (range 0 40)))"), "()")
        self.assertEqual(value('(bad (lambda k (nth "東方 ab" k)) (lambda k (o-nth "東方 ab" k)) (range 0 5))'), "()")


class Faults(unittest.TestCase):

    def anomaly(self, src: str) -> dict:
        with self.assertRaises((BudgetTrap, DeltaTrap, DomainTrap)) as ctx:
            run(src)
        return ctx.exception.anomaly

    def test_nth_outside_is_a_domain_error(self):
        for k in ("3", "-1", "100000000000000000000"):
            a = self.anomaly(f"(apply (lambda k (nth (list 5 6 7) k)) {k})")
            self.assertEqual((a["kind"], a["detail"]["operator"]), ("domain-error", "nth"))
        a = self.anomaly('(apply (lambda k (nth "ab" k)) 2)')
        self.assertEqual(a["kind"], "domain-error")

    def test_nth_of_an_integer_is_a_type_violation(self):
        a = self.anomaly("(apply (lambda k (nth k 0)) 7)")
        self.assertEqual((a["kind"], a["detail"]["operator"]), ("type-violation", "nth"))

    def test_quot_by_zero(self):
        a = self.anomaly("(apply (lambda b (quot 7 b)) 0)")
        self.assertEqual((a["kind"], a["detail"]["operator"]), ("domain-error", "quot"))


class OneStepANode(unittest.TestCase):

    def test_an_operator_costs_its_node(self):
        # apply + lambda + the operator node + one reference per operand
        # + the literal argument: no call, no body.
        self.assertEqual(run("(apply (lambda a (sin a)) 70)", old=False)[1], 5)
        self.assertEqual(run("(apply (lambda a (quot a 3)) -70)", old=False)[1], 6)

    def test_literal_operands_fold(self):
        self.assertEqual(run("(sin-fine 700)", old=False), (run("(o-sin-fine 700)")[0], 1))
        self.assertEqual(run("(nth (list 1 2) 1)", old=False)[1], 7)


if __name__ == "__main__":
    unittest.main()
