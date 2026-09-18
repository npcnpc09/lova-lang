"""The porting decisions of spec/runtime-semantics.md §0.1, pinned.

A native runtime is checked against the golden set; these tests pin
the Python runtime to the decided behaviour so the golden set records
it.  D1: `sort-by` is a specified merge sort, so its comparator count
is the language's.  D2: `text-int` takes ASCII digits only.  D3:
`text-cmp` on elements that do not compare is a fault, not a bare
TypeError.
"""

from __future__ import annotations

import unittest

from core.conservation import DomainTrap
from core.runtime import Runtime, evaluate
from core.surface import parse_with_prelude


def run(src: str):
    rt = Runtime()
    return evaluate(parse_with_prelude(src), rt), rt


class D1MergeSort(unittest.TestCase):

    def _steps(self, src: str) -> int:
        return run(src)[1].steps

    def test_the_comparison_count_is_the_merge_sorts(self):
        # [3 1 2]: sort [1 2] (1 comparison), merge [3] with [1 2] (2).
        # [1 2 3]: sort [2 3] (1), merge [1] with [2 3] (1).  One more
        # comparison, at one step plus two applications of `lt` -- the
        # inner lambda node (1) and `(threshold (deviation b a))` (4)
        # each -- is 11 steps.
        a = self._steps("(sort-by lt (list 3 1 2))")
        b = self._steps("(sort-by lt (list 1 2 3))")
        self.assertEqual(a - b, 11)

    def test_reverse_sorted_five_costs_what_the_spec_says(self):
        # [5 4 3 2 1]: [5 4] -> 1; [3 2 1] -> [2 1] 1, merge [3]|[1 2] 2;
        # merge [4 5]|[1 2 3]: 1<4, 2<4, 3<4, then left runs out: 3.
        # Total 7 comparisons against 5 for the sorted input ([1 2] 1,
        # [3 4 5] 2, merge [1 2]|[3 4 5] 2).
        a = self._steps("(sort-by lt (list 5 4 3 2 1))")
        b = self._steps("(sort-by lt (list 1 2 3 4 5))")
        self.assertEqual(a - b, 2 * 11)

    def test_ties_keep_their_order_under_lt_and_le_alike(self):
        src = ("(map (lambda r (get r n)) (sort-by (lambda a (lambda b ({cmp} (get a k) (get b k))))"
               " (list (rec k 1 n 1) (rec k 0 n 2) (rec k 1 n 3) (rec k 0 n 4))))")
        from core.cli import format_value
        for cmp in ("lt", "le"):
            with self.subTest(cmp=cmp):
                self.assertEqual(format_value(run(src.replace("{cmp}", cmp))[0]), "(2 4 1 3)")


class D2TextInt(unittest.TestCase):

    def test_ascii_digits_parse_with_a_sign_and_surrounding_space(self):
        self.assertEqual(run('(text-int " -42 ")')[0], -42)

    def test_other_scripts_digits_and_superscripts_are_the_signal(self):
        for text in ("١٢", "²", "1e3", ""):
            with self.subTest(text=text):
                with self.assertRaises(DomainTrap) as ctx:
                    run(f'(text-int "{text}")')
                self.assertEqual(ctx.exception.anomaly["kind"], "signalled")
                self.assertEqual(ctx.exception.anomaly["detail"]["code"], 16)


class D3TextCmp(unittest.TestCase):

    def test_two_lists_of_integers_compare_element_wise(self):
        self.assertEqual(run("(text-cmp (list 1 2) (list 1 3))")[0], -1)

    def test_an_integer_against_a_text_inside_is_a_type_violation(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(text-cmp (list 1 "a") (list 1 2))')
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")
        self.assertEqual(ctx.exception.anomaly["detail"]["operator"], "text-cmp")


if __name__ == "__main__":
    unittest.main()
