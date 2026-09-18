"""A failed example locates its fault (the audit, 2026-09-18).

Before: an example that missed said `offender: apply at depth 0` -- the
example's own call -- because the body scanner could not see past a
closure.  Now `check` probes every single-node edit of every def the
example ran through, and of the example's own expression, and reports
the one that makes the example pass, scored against the other examples.
The shapes here are Exp 21's planted faults: a comparison off by one,
a minus dropped, a reference to the wrong name, a fault in the
expression rather than a def, and a fault no single edit closes.
"""

from __future__ import annotations

import unittest

from core.examples import check, summary

NL = chr(10)


def _fault(src: str):
    results = check(src)
    failed = [r for r in results if not r["passed"]]
    assert failed, "the example was expected to fail"
    return failed[0].get("fault"), results


class Located(unittest.TestCase):

    def test_a_reference_to_the_wrong_name_inside_a_def(self):
        fault, results = _fault(
            "(def clamp [lo hi x] (if (lt x lo) lo (if (gt x hi) hi x)))" + NL +
            "(def score [xs] (fold (lambda a (lambda x (merge a (clamp 0 10 a)))) 0 xs))" + NL +
            "(example (clamp 0 10 15) 10)" + NL +
            "(example (score (list 3 20 -5)) 13)" + NL +
            "(example (score (list 4 6)) 10)" + NL +
            "(score (list 1))")
        self.assertEqual(fault["kind"], "ref")
        self.assertEqual(fault["excerpt"], "a")
        self.assertEqual(fault["replacement"], "x")
        self.assertEqual(fault["def"], "score")
        self.assertEqual((fault["line"], fault["col"]), (2, 64))
        self.assertEqual((fault["others_passing"], fault["others"]), (2, 2))
        self.assertIn("`a` here should be `x`  -> x  [fixes all 3 examples]", summary(results))
        self.assertIn("[123, 124)", summary(results))

    def test_a_comparison_off_by_one(self):
        fault, _ = _fault(
            "(def withdraw [bal n] (if (gt bal n) (sub bal n) bal))" + NL +
            "(example (withdraw 100 50) 50)" + NL +
            "(example (withdraw 50 50) 0)" + NL +
            "(example (withdraw 10 50) 10)" + NL +
            "(withdraw 1 1)")
        self.assertEqual(fault["kind"], "compare")
        self.assertEqual(fault["excerpt"], "(gt bal n)")
        self.assertEqual(fault["replacement"], "(ge bal n)")
        self.assertEqual(fault["others_passing"], 2)

    def test_a_minus_dropped(self):
        fault, _ = _fault(
            "(def signed [neg? n] (if neg? n n))" + NL +
            "(example (signed 1 5) -5)" + NL +
            "(example (signed 0 5) 5)" + NL +
            "(signed 0 1)")
        self.assertEqual(fault["kind"], "add-minus")
        self.assertEqual(fault["replacement"], "(neg n)")
        self.assertEqual(fault["others_passing"], 1)

    def test_a_fault_in_the_expression_is_not_probed(self):
        # Exp 28: an edit inside an example's own expression repairs the
        # statement, not the program, so the defs alone are probed and a
        # miss says so.
        fault, results = _fault(
            "(def sq [n] (mul n n))" + NL +
            "(example (sub (sq 3) 2) 11)" + NL +
            "(example (sub (sq 2) 2) 6)" + NL +
            "(sq 1)")
        self.assertEqual(fault["kind"], "none")
        self.assertIn("no single edit of a def makes this example pass", summary(results))

    def test_an_exchanged_reference_that_compares_a_thing_with_itself_is_not_offered(self):
        fault, results = _fault(
            "(def bigger [a b] (if (lt a b) a b))" + NL +        # `lt` should be `gt`
            "(example (bigger 3 5) 5)" + NL +
            "(example (bigger 9 2) 9)" + NL +
            "(bigger 1 2)")
        self.assertEqual(fault["kind"], "compare")
        self.assertEqual(fault["replacement"], "(gt a b)")

    def test_a_fault_no_single_edit_closes_says_so(self):
        fault, results = _fault(
            "(def total [xs] (fold (lambda a (lambda x (merge a 1))) 0 xs))" + NL +
            "(example (total (list 5 6 7)) 18)" + NL +
            "(example (total (list 1 1)) 2)" + NL +
            "(total (list 1))")
        # `1` should be `x`: a literal for a reference is not an edit tried,
        # so either nothing is found or a partial fix is marked as such.
        text = summary(results)
        if fault and fault.get("span"):
            self.assertIn("the fault may be elsewhere", text)
        else:
            self.assertIn("no single edit of a def makes this example pass", text)

    def test_examples_may_state_lists_and_texts(self):
        results = check(
            "(def rev [xs] (reverse xs))" + NL +
            "(example (rev (list 1 2 3)) (list 3 2 1))" + NL +
            '(example (text-cat "a" "b") "ab")' + NL +
            "(example (rev (list 1 2)) (list 1 2))" + NL +
            "(rev (list 1))")
        self.assertEqual([r["passed"] for r in results], [True, True, False])
        self.assertEqual(results[2]["expected"], "(1 2)")
        self.assertEqual(results[2]["got"], "(2 1)")
        self.assertEqual(results[2]["anomaly"]["kind"], "conservation-violated")


if __name__ == "__main__":
    unittest.main()


class SecondOracle(unittest.TestCase):
    """Q115: candidate literals come from the examples' data, and every
    full fix is scored by how many nearby inputs it changes the answer
    on, so an edit that fits the examples by widening a test ranks below
    the constant the examples mention."""

    SRC = ('(def punct? [c] (or (eq c 39) (eq c 58)))' + NL +          # 39 should be 46
           '(def strip [t] (if (nil? t) t (if (punct? (last t)) (take (sub (len t) 1) t) t)))' + NL +
           '(example (text-of-chars (strip (text-chars "cat."))) "cat")' + NL +
           '(example (text-of-chars (strip (text-chars "dog:"))) "dog")' + NL +
           '(example (text-of-chars (strip (text-chars "ox1"))) "ox1")' + NL +
           '(strip (text-chars "a"))')

    def test_a_constant_from_the_examples_beats_a_widened_test(self):
        results = check(self.SRC)
        fault = [r for r in results if not r["passed"]][0]["fault"]
        self.assertEqual(fault["kind"], "literal")
        self.assertEqual(fault["replacement"], "46")
        self.assertIn("impact", fault)
        self.assertLess(fault["impact"], fault["nearby"])
        text = summary(results)
        self.assertIn("should be 46 (`.`)", text)
        self.assertIn("changes the answer on", text)

    def test_data_literals_are_the_examples_numbers_and_characters(self):
        from core.cli import build
        from core.locate import data_literals, example_expression
        tree, _ = build('(list (text-len "ab.") 7)')
        lits = data_literals([example_expression(tree)])
        for v in (7, ord("a"), ord("b"), ord(".")):
            self.assertIn(v, lits)
