"""Tests for the Stage-2 surface (`core/surface2.py`).

Stage 2 is the text projection of the byte encoding: one printable
character per byte, no delimiters, because arity already determines the
structure. The property that matters is losslessness — a projection
that changes the program is not a projection — so most of this file is
round-trips, including over generated programs, which reach shapes
nobody writes by hand.
"""

from __future__ import annotations

import unittest

from core import surface2
from core.generator import constrained_random
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import LIT_INT, Node, REF, SIGNATURES, decode, encode
from corpus.tasks import TASKS_V3 as BENCH_TASKS


def s2(src: str) -> str:
    return surface2.render(parse(src))


class TestSymbolTable(unittest.TestCase):

    def test_every_byte_has_a_symbol(self):
        self.assertEqual(len(surface2.SYMBOLS), 86)
        for byte in range(0x40):
            self.assertIn(byte, surface2.SYMBOLS)

    def test_symbols_are_distinct(self):
        self.assertEqual(len(set(surface2.SYMBOLS.values())), 86)

    def test_digits_and_minus_are_reserved_for_literals(self):
        # The lexer decides literal-vs-operator on the first character,
        # so an operator symbol may never be a digit or a minus sign.
        reserved = set("0123456789-")
        self.assertFalse(set(surface2.SYMBOLS.values()) & reserved)
        self.assertFalse(set(surface2.REF_SYMBOLS) & reserved)

    def test_reference_symbols_do_not_collide(self):
        self.assertFalse(
            set(surface2.REF_SYMBOLS) & set(surface2.SYMBOLS.values())
        )
        self.assertEqual(len(surface2.REF_SYMBOLS), 10)

    def test_reserved_operators_still_project(self):
        # A program using a future operator must still render, or the
        # projection is not total over the table.
        for byte, symbol in surface2.SYMBOLS.items():
            self.assertIn(symbol, surface2.TOKEN_FOR_SYMBOL)
            self.assertEqual(surface2.TOKEN_FOR_SYMBOL[symbol], byte)


class TestRoundTrip(unittest.TestCase):

    def _check(self, tree, label=""):
        for pack in (False, True):
            text = surface2.render(tree, pack_refs=pack)
            back = surface2.parse(text)
            self.assertEqual(back, tree, f"{label} pack={pack}: {text!r}")
            # Bytes, not merely an equal tree.
            self.assertEqual(encode(back), encode(tree), label)

    def test_hand_written_shapes(self):
        for src in (
            "(p 12)",
            "(merge (p 3) (tau 12))",
            "(seq (p 3) (p 4) (p 5))",
            "(let 1 12 (p (ref 1)))",
            "(budget 100 (p 12))",
            "(conserve 77 (violate 77))",
            "(if-surprise 1 2 3)",
            "(defn square [n] (mul n n))(square 7)",
            '"abc"',
            "(list 1 2 3)",
            "(nil)",
            "(head (cons 7 (nil)))",
        ):
            with self.subTest(src=src):
                self._check(parse(src), src)

    def test_adjacent_literals_keep_their_separator(self):
        # (merge 3 12) must not pack to "+312" and read back as one number.
        tree = parse("(merge 3 12)")
        self._check(tree)
        self.assertIn(" ", surface2.render(tree))
        self.assertEqual(surface2.parse(surface2.render(tree)), tree)

    def test_negative_literal_needs_no_separator(self):
        # `-` starts a literal unambiguously.
        text = surface2.render(parse("(merge 3 -12)"))
        self.assertNotIn(" ", text)
        self.assertEqual(surface2.parse(text), parse("(merge 3 -12)"))

    def test_multi_digit_literals(self):
        for value in (0, 7, 10, 99, 1000, -1, -1000):
            with self.subTest(value=value):
                self._check(parse(f"(identity {value})"))

    def test_benchmark_corpus(self):
        import re
        for task in BENCH_TASKS:
            src = re.sub(r"\{(\w+)\}", "7", task.template)
            with self.subTest(task=task.id):
                self._check(parse(src), task.id)

    def test_generated_programs(self):
        # Generated programs reach shapes nobody writes by hand.
        for seed in range(200):
            tree = decode(constrained_random(seed=seed, max_depth=6))
            with self.subTest(seed=seed):
                self._check(tree, f"seed{seed}")

    def test_evaluation_is_unchanged(self):
        for src in (
            "(merge (p 3) (tau 12))",
            "(defn fact [n] (if n (mul n (fact (sub n 1))) 1))(fact 6)",
            "(def sum [xs] (if (nil? xs) 0 (merge (head xs) (sum (tail xs)))))"
            "(sum (list 1 2 3 4))",
        ):
            with self.subTest(src=src):
                tree = parse(src)
                expected = evaluate(tree, Runtime())
                projected = surface2.parse(surface2.render(tree))
                self.assertEqual(evaluate(projected, Runtime()), expected)


class TestReferenceDigram(unittest.TestCase):

    def test_single_digit_refs_pack(self):
        for index in range(10):
            tree = Node(op=REF, args=[Node(op=LIT_INT, args=[index])])
            self.assertEqual(surface2.render(tree),
                             surface2.REF_SYMBOLS[index])

    def test_larger_refs_fall_back(self):
        tree = Node(op=REF, args=[Node(op=LIT_INT, args=[12])])
        self.assertEqual(surface2.render(tree),
                         surface2.SYMBOLS[REF] + "12")
        self.assertEqual(surface2.parse(surface2.render(tree)), tree)

    def test_packing_is_optional_and_both_round_trip(self):
        tree = parse("(let 1 12 (p (ref 1)))")
        packed = surface2.render(tree, pack_refs=True)
        plain = surface2.render(tree, pack_refs=False)
        self.assertNotEqual(packed, plain)
        self.assertEqual(surface2.parse(packed), tree)
        self.assertEqual(surface2.parse(plain), tree)

    def test_packing_shortens(self):
        tree = parse("(defn square [n] (mul n n))(square 7)")
        self.assertLess(len(surface2.render(tree)),
                        len(surface2.render(tree, pack_refs=False)))


class TestParserErrors(unittest.TestCase):
    """No silent failures (Constraint 5) at the surface either."""

    def test_unknown_symbol(self):
        with self.assertRaises(ValueError):
            surface2.parse("§")

    def test_truncated_program(self):
        with self.assertRaises(ValueError):
            surface2.parse("+3")           # merge wants two arguments

    def test_trailing_input(self):
        with self.assertRaises(ValueError):
            surface2.parse("p3p4")         # two top-level expressions

    def test_unterminated_variadic(self):
        with self.assertRaises(ValueError):
            surface2.parse(",p3")          # seq with no end marker

    def test_bare_minus(self):
        with self.assertRaises(ValueError):
            surface2.parse("+3-")

    def test_literal_symbol_is_never_written(self):
        # `#` stands for LIT_INT in the table but digits are what get
        # emitted; writing it should say so rather than misparse.
        with self.assertRaises(ValueError) as ctx:
            surface2.parse("#")
        self.assertIn("digits", str(ctx.exception))

    def test_stray_end_marker(self):
        with self.assertRaises(ValueError):
            surface2.parse(";")


class TestDensity(unittest.TestCase):
    """The point of the exercise, guarded against regression."""

    ALGORITHMIC = (
        "(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))"
        "(fact 20)"
    )

    def test_stage2_is_shorter_than_stage1(self):
        self.assertLess(len(s2(self.ALGORITHMIC)), len(self.ALGORITHMIC))

    def test_no_parentheses_survive(self):
        text = s2(self.ALGORITHMIC)
        self.assertNotIn("(", text)
        self.assertNotIn(")", text)

    def test_one_character_per_node(self):
        # The structural claim: without the digram, every non-literal node
        # is exactly one character, every literal is its digits, and a
        # variadic adds its end marker.  Nothing else is spent -- which is
        # what "the parentheses were never necessary" means concretely.
        for src in ("(merge (p 3) (tau 12))",
                    "(seq (p 3) (p 4) (p 5))",
                    "(let 1 12 (p (ref 1)))",
                    "(merge 3 -12)"):
            with self.subTest(src=src):
                tree = parse(src)
                text = surface2.render(tree, pack_refs=False)
                self.assertEqual(len(text.replace(" ", "")),
                                 _expected_length(tree), text)


def _expected_length(node) -> int:
    """One char per operator, its digits per literal, plus variadic ends."""
    if node.op == LIT_INT:
        return len(str(int(node.args[0])))
    total = 1 + sum(_expected_length(c) for c in node.args)
    if SIGNATURES[node.op]["arity"] == "variadic":
        total += 1                      # the end marker
    return total


if __name__ == "__main__":
    unittest.main()
