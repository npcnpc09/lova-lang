"""The surface sugar and tooling of 2026-09-27 (journal, "The danmaku's
pain points").

Each sugar form compiles to exactly the bytes of the form it abbreviates
(Constraint 6: layout, not semantics); an expression may stand at the
head of a call; `quot` truncates where `div` floors; a native anomaly
names its hot functions; and a failed native check re-runs only its
failures in Python.
"""

from __future__ import annotations

import unittest

from core.cli import build
from core.examples import check
from core.native import enrich
from core.runtime import evaluate
from core.surface import parse, parse_with_prelude
from core.tokens import encode


def same_bytes(a: str, b: str) -> bool:
    return encode(parse(a)) == encode(parse(b))


def value(src: str):
    return evaluate(parse_with_prelude(src))


class Sugar(unittest.TestCase):

    def test_multi_binding_let_is_nested_lets(self):
        self.assertTrue(same_bytes("(let [a 1 b (merge a 2)] (mul a b))",
                                   "(let a 1 (let b (merge a 2) (mul a b)))"))
        self.assertEqual(value("(let [a 1 b (merge a 2)] (mul a b))"), 3)

    def test_fn_is_curried_lambdas(self):
        self.assertTrue(same_bytes("(fn [a b c] (merge a (mul b c)))",
                                   "(lambda a (lambda b (lambda c (merge a (mul b c)))))"))
        self.assertEqual(value("(fold (fn [acc x] (merge acc (mul x x))) 0 (list 1 2 3))"), 14)

    def test_put_takes_several_fields(self):
        self.assertTrue(same_bytes("(put (rec x 1 y 2) x 5 y 6)",
                                   "(put (put (rec x 1 y 2) x 5) y 6)"))
        self.assertEqual(value("(let r (put (rec x 1 y 2) x 5 y 6) (merge (get r x) (get r y)))"), 11)

    def test_an_expression_may_head_a_call(self):
        src = "(let r (rec f (fn [a b] (sub a b))) ((get r f) 10 3))"
        self.assertEqual(value(src), 7)
        self.assertEqual(value("((nth (list inc neg) 1) 4)"), -4)

    def test_let_bracket_names_are_bound_not_its_values(self):
        # `b` in a value refers to an outer b, not to a later binding
        self.assertEqual(value("(let b 10 (let [a b b 2] (merge a b)))"), 12)

    def test_quot_truncates_where_div_floors(self):
        self.assertEqual(value("(list (quot -7 2) (div -7 2) (quot 7 -2) (quot 7 2))"),
                         value("(list -3 -4 -3 3)"))


class Tooling(unittest.TestCase):

    def test_native_calls_are_named(self):
        tree, _ = build("(def spin [n] (if (eq n 0) 0 (spin (sub n 1))))\n(spin 5)")
        sid = tree.symbols.intern("spin")
        anomaly = {"kind": "step-limit-exceeded", "detail": {"calls": [[sid, 900, 30]]}}
        enrich(anomaly, tree)
        self.assertEqual(anomaly["detail"]["hot"], [["spin", 900, 30]])
        self.assertNotIn("calls", anomaly["detail"])

    def test_check_only_runs_the_named_examples(self):
        src = ("(def sq [x] (mul x x))\n"
               "(example (sq 3) 9)\n(example (sq 4) 15)\n(example (sq 5) 25)\n(sq 2)")
        every = check(src, runtime="python")
        self.assertEqual([r["passed"] for r in every], [True, False, True])
        one = check(src, runtime="python", only={1})
        self.assertEqual(len(one), 1)
        self.assertFalse(one[0]["passed"])


if __name__ == "__main__":
    unittest.main()
