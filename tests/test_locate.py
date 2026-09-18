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


class AtSize(unittest.TestCase):
    """What Exp 29's programs found in the locator before any session ran
    (2026-09-18): a def taking a name the prelude binds opens a child
    frame, and the example must be evaluated there; a trapped example
    locates its fault as a miss does; a probe the step cap cut off is
    retried with room."""

    def test_a_def_that_shadows_a_prelude_name_does_not_hide_the_later_defs(self):
        fault, results = _fault(
            "(def lines [n] (mul n 2))" + NL +                 # `lines` is a prelude name
            "(def big? [n] (gt (lines n) 10))" + NL +          # `gt` should be `ge`
            "(example (big? 5) 1)" + NL +
            "(example (big? 4) 0)" + NL +
            "(example (big? 6) 1)" + NL +
            "(big? 1)")
        self.assertEqual(fault["kind"], "compare")
        self.assertEqual(fault["replacement"], "(ge (lines n) 10)")
        self.assertEqual(fault["def"], "big?")
        self.assertEqual((fault["others_passing"], fault["others"]), (2, 2))

    def test_a_trapped_example_locates_its_fault_upstream_of_the_trap(self):
        fault, results = _fault(
            "(def idx [n] (merge n 1))" + NL +                 # should be n
            "(def pick [xs n] (nth xs (idx n)))" + NL +
            "(example (pick (list 5 6 7) 2) 7)" + NL +         # nth 3: a trap, not a miss
            "(example (pick (list 5 6 7) 0) 5)" + NL +
            "(example (pick (list 1) 0) 1)" + NL +
            "(pick (list 1) 0)")
        self.assertEqual(fault["kind"], "literal")
        self.assertEqual(fault["def"], "idx")
        self.assertEqual(fault["replacement"], "0")
        self.assertEqual((fault["others_passing"], fault["others"]), (2, 2))
        text = summary(results)
        self.assertIn("trapped at", text)
        self.assertIn("the literal 1 should be 0", text)
        self.assertNotIn("guard with", text)

    def test_a_probe_the_step_cap_cut_off_is_retried_with_room(self):
        # The trap comes at once; the fixed run is thirty thousand steps,
        # past the cap set from the examples' own runs.
        fault, results = _fault(
            "(def total [n] (if (gt n 5) (head (nil)) (fold (lambda a (lambda k (merge a k))) 0 (range 0 n))))" + NL +
            "(example (total 5000) 12497500)" + NL +
            "(example (total 3) 3)" + NL +
            "(total 1)")
        self.assertEqual(fault["def"], "total")
        self.assertEqual((fault["others_passing"], fault["others"]), (1, 1))
        self.assertFalse(fault.get("budget"))
        offered = [fault.get("replacement")] + [a.get("replacement") for a in fault.get("also", [])]
        self.assertIn("5000", offered)

    def test_one_search_serves_every_failing_example(self):
        # Two failures of one fault: the fix found on the first is the
        # second's, and its search is not run again.
        results = check(
            "(def lines [n] (mul n 2))" + NL +
            "(def big? [n] (gt (lines n) 10))" + NL +
            "(example (big? 5) 1)" + NL +
            "(example (big? 4) 0)" + NL +
            "(example (big? 6) 1)" + NL +
            "(example (lt (big? 5) 2) 1)" + NL +
            "(big? 1)")
        failed = [r for r in results if not r["passed"]]
        self.assertEqual(len(failed), 1)
        results = check(
            "(def lines [n] (mul n 2))" + NL +
            "(def big? [n] (gt (lines n) 10))" + NL +
            "(example (big? 5) 1)" + NL +
            "(example (merge (big? 5) 1) 2)" + NL +
            "(example (big? 4) 0)" + NL +
            "(big? 1)")
        failed = [r for r in results if not r["passed"]]
        self.assertEqual(len(failed), 2)
        self.assertEqual(failed[0]["fault"]["replacement"], "(ge (lines n) 10)")
        self.assertEqual(failed[1]["fault"]["replacement"], "(ge (lines n) 10)")
        self.assertEqual(failed[0]["fault"]["probes"], failed[1]["fault"]["probes"])
        self.assertIn("the same as at", summary(results))

    def test_a_constant_computed_from_the_probed_def_is_recomputed(self):
        # `keys` is a value built with `key` before any probe; a probe that
        # fixes `key` must see `keys` rebuilt, or every probe fails (g2048's
        # `all-cells`, Exp 29 Q120).
        fault, results = _fault(
            "(def key [x y] (merge (mul x 3) y))" + NL +          # 3 should be 4
            "(def keys [] (map (lambda x (key x 3)) (range 0 4)))" + NL +
            "(def look [x y] (nth keys x))" + NL +
            "(example (look 1 0) 7)" + NL +
            "(example (look 3 0) 15)" + NL +
            "(example (key 2 1) 9)" + NL +
            "(look 0 0)")
        self.assertEqual(fault["def"], "key")
        self.assertEqual(fault["replacement"], "4")
        self.assertEqual((fault["others_passing"], fault["others"]), (2, 2))

    def test_a_fault_in_a_constant_is_located(self):
        fault, results = _fault(
            "(def powers [] (list 1 3 9 28 81))" + NL +            # 28 should be 27
            "(def digit [n k] (mod (div n (nth powers k)) 3))" + NL +
            "(example (digit 54 3) 2)" + NL +
            "(example (digit 54 2) 0)" + NL +
            "(example (digit 5 1) 1)" + NL +
            "(digit 1 0)")
        self.assertEqual(fault["def"], "powers")
        self.assertTrue(fault["constant"])
        self.assertEqual(fault["replacement"], "27")
        self.assertEqual((fault["others_passing"], fault["others"]), (2, 2))
        self.assertNotIn("is reached by", summary(results))
