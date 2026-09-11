"""M27 (Q94): the list family at 0x50-0x57.

`map` / `filter` / `fold` / `reverse` / `range` / `any` / `sort-by` /
`zip` were prelude functions written over `loop-until` and cost 20-40
steps an element; Exp 20 found the walkers to be the budget of every
search that read a list once `nth` was native.  They are operators
now: one step an element, plus the function they call.  Programs are
unchanged textually; what these tests pin is that the semantics are
the prelude's, the cost is not, and the family is wired through the
table, the two surfaces, the validator and the card.
"""

from __future__ import annotations

import unittest

from core.mcp_server import tool_execute
from core.tokens import (
    LIST_ANY, LIST_FAMILY, LIST_FILTER, LIST_FOLD, LIST_MAP, LIST_RANGE,
    LIST_REVERSE, LIST_SORT_BY, LIST_ZIP, SIGNATURES, RESULT_FOLLOWS_OPERANDS,
)


def run(src: str, **kw):
    return tool_execute({"source": src, **kw})


def value(src: str, **kw) -> str:
    r = run(src, **kw)
    assert r["ok"], r.get("anomaly")
    return r["value"]


class Semantics(unittest.TestCase):
    """The prelude's meanings, kept."""

    def test_map_filter_fold(self):
        self.assertEqual(value("(map inc (list 1 2 3))"), "(2 3 4)")
        self.assertEqual(value("(filter odd (list 1 2 3 4))"), "(1 3)")
        # fold calls (f acc x), left to right
        self.assertEqual(value("(fold (lambda a (lambda x (cons x a))) (nil) (list 1 2 3))"), "(3 2 1)")
        self.assertEqual(value("(fold (lambda a (lambda x (merge a x))) 0 (nil))"), "0")

    def test_reverse_range_zip(self):
        self.assertEqual(value("(reverse (list 1 2 3))"), "(3 2 1)")
        self.assertEqual(value("(range 2 6)"), "(2 3 4 5)")
        self.assertEqual(value("(range 5 2)"), "()")
        self.assertEqual(value("(zip (list 1 2 3) (list 4 5))"), "((1 4) (2 5))")

    def test_any_stops_at_the_first_hit(self):
        self.assertEqual(value("(any (lambda x (eq x 2)) (list 1 2 3))"), "1")
        self.assertEqual(value("(any (lambda x (eq x 9)) (list 1 2 3))"), "0")
        r = run("(any (lambda x (eq x 3)) (range 0 100000))")
        self.assertEqual(r["value"], "1")
        self.assertLess(r["steps"], 100000 + 1000)      # the range, then four elements

    def test_sort_by_is_stable_and_takes_a_curried_def(self):
        src = ("(sort-by (lambda a (lambda b (lt (head a) (head b)))) "
               "(list (list 1 9) (list 0 8) (list 1 7)))")
        self.assertEqual(value(src), "((0 8) (1 9) (1 7))")
        self.assertEqual(value("(def desc [a b] (gt a b))\n(sort-by desc (list 2 9 4))"), "(9 4 2)")
        self.assertEqual(value("(sort (list 3 1 2))"), "(1 2 3)")
        self.assertEqual(value('(sort-by text-lt (list "pear" "apple" "fig"))'), '("apple" "fig" "pear")')

    def test_a_text_is_read_as_its_codepoints(self):
        # a codepoint list prints with its text beside it
        self.assertTrue(value('(reverse "abc")').startswith("(99 98 97)"))
        self.assertTrue(value('(map (lambda c (merge c 1)) "ab")').startswith("(98 99)"))
        self.assertEqual(value('(any (lambda c (eq c 98)) "abc")'), "1")

    def test_the_prelude_idioms_over_them(self):
        self.assertEqual(value("(sum (list 1 2 3))"), "6")
        self.assertEqual(value("(product (list 2 3 4))"), "24")
        self.assertEqual(value("(contains (list 1 2) 2)"), "1")
        self.assertEqual(value("(contains (list 1 2) 5)"), "0")
        self.assertEqual(value("(all odd (list 1 3))"), "1")
        self.assertEqual(value("(all odd (list 1 2))"), "0")
        self.assertEqual(value("(all odd (nil))"), "1")
        self.assertEqual(value("(map-keys (map-put (map-put (nil) 5 1) 6 2))"), "(5 6)")
        self.assertEqual(value('(join (map text-of (list 1 2)) " ")'), '"1 2"')


class Faults(unittest.TestCase):
    def test_an_operator_is_not_a_function_value(self):
        a = run("(map merge (list 1 2))")["anomaly"]
        self.assertEqual(a["kind"], "unbound-ref")
        self.assertIn("operator", a["repair_hint"])

    def test_an_integer_in_the_function_slot_is_a_compile_error(self):
        a = run("(map 5 (list 1 2))")["anomaly"]
        self.assertEqual(a["kind"], "type-mismatch")
        self.assertEqual(a["detail"]["expected"], "Fn")

    def test_a_non_list_is_a_domain_error(self):
        a = run("(reverse 7)")["anomaly"]
        self.assertEqual(a["kind"], "type-violation")

    def test_a_fault_inside_the_function_reports_the_call(self):
        r = run("(map (lambda x (div 1 x)) (list 1 0))")
        self.assertEqual(r["anomaly"]["kind"], "domain-error")
        self.assertEqual(r["stage"], "run")


class Cost(unittest.TestCase):
    """One step an element, plus the function called; the ceiling holds."""

    def _per_element(self, body: str) -> float:
        src = ("(def nine [] (list 9 8 7 6 5 4 3 2 1))"
               "(def lp [i acc] (if (eq i 0) acc (lp (sub i 1) %s)))(lp 200 0)")
        bare = run(src % "acc")["steps"]
        return (run(src % body)["steps"] - bare) / 200 / 9

    def test_the_walkers_cost_a_few_steps_an_element(self):
        # Exp 20 measured the prelude forms at 17 to 39 an element.
        self.assertLess(self._per_element("(len (map inc nine))"), 8)
        self.assertLess(self._per_element("(len (filter odd nine))"), 8)
        self.assertLess(self._per_element("(fold (lambda a (lambda x (merge a x))) 0 nine)"), 8)
        self.assertLess(self._per_element("(len (reverse nine))"), 2)
        self.assertLess(self._per_element("(len (range 0 9))"), 2)
        self.assertLess(self._per_element("(len (sort nine))"), 30)      # n log n comparisons

    def test_a_huge_range_is_a_step_trap_not_a_hang(self):
        a = run("(len (range 0 100000000))", max_steps=1000)["anomaly"]
        self.assertEqual(a["kind"], "step-limit-exceeded")

    def test_a_lambda_in_a_walker_is_charged_to_the_def_that_wrote_it(self):
        src = ("(def big [] (range 0 300))\n"
               "(def walk [i acc] (if (eq i 0) acc (walk (sub i 1) "
               "(merge acc (fold (lambda a (lambda x (merge a x))) 0 big)))))\n"
               "(walk 1000 0)")
        a = run(src, max_steps=200000)["anomaly"]
        hot = {name: steps for name, steps, calls in a["detail"]["hot"]}
        self.assertIn("walk", hot)
        self.assertGreater(hot["walk"], 150000)
        self.assertNotIn("fold", hot)
        self.assertNotIn("iterate", hot)


class Wiring(unittest.TestCase):
    def test_the_family_is_eight_bytes_at_0x50(self):
        self.assertEqual(sorted(LIST_FAMILY), list(range(0x50, 0x58)))
        self.assertEqual([SIGNATURES[t]["name"] for t in sorted(LIST_FAMILY)],
                         ["map", "filter", "fold", "reverse", "range", "any", "sort-by", "zip"])
        self.assertTrue(all(SIGNATURES[t]["family"] == "list" for t in LIST_FAMILY))
        self.assertIn(LIST_FOLD, RESULT_FOLLOWS_OPERANDS)

    def test_the_prelude_no_longer_defines_them(self):
        from pathlib import Path
        prelude = (Path(__file__).resolve().parent.parent / "lib" / "prelude.lova").read_text(encoding="utf-8")
        for name in ("map", "filter", "fold", "reverse", "range", "any", "sort-by", "zip", "rev-onto", "merge-by"):
            self.assertNotIn("(def " + name + " ", prelude)

    def test_both_surfaces_round_trip(self):
        from core.surface import parse
        from core import surface2
        from core.tokens import encode, decode
        src = ("(merge (fold (lambda a (lambda x (merge a x))) 0 (sort-by (lambda a (lambda b (lt a b))) (reverse (range 0 4)))) "
               "(len (zip (range 0 3) (list 1 2))))")
        tree = parse(src)
        self.assertEqual(decode(encode(tree)), tree)
        self.assertEqual(surface2.parse(surface2.render(tree)), tree)
        self.assertEqual(run(src)["value"], "8")

    def test_the_validator_admits_the_family_and_the_sampler_does_not(self):
        from core.generator import GenState
        from core.types import LIST
        state = GenState.fresh(LIST)
        self.assertIn(LIST_MAP, state.valid_next(generate=False))
        self.assertNotIn(LIST_MAP, state.valid_next(generate=True))

    def test_the_card_names_every_list_operator(self):
        from pathlib import Path
        card = (Path(__file__).resolve().parent.parent / "corpus" / "language_card.md").read_text(encoding="utf-8")
        for t in LIST_FAMILY:
            self.assertIn("`" + SIGNATURES[t]["name"] + "`", card)
        self.assertIn("List operators:", card)


if __name__ == "__main__":
    unittest.main()
