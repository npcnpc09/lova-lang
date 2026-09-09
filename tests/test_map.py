"""Tests for the map (M22) — the sixth value kind, on the last three slots.

``map-put`` (0x13) yields a new map from a map or a list of pairs;
``map-get`` (0x14) reads with a default; ``map-pairs`` (0x16) gives the
entries back as ``(list k v)`` in insertion order.  Keys are integers or
lists; values are anything.  A map is a value: ``map-put`` leaves the
map it was given as it was.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from core.cli import format_value, main as cli_main
from core.compiler import CompileError, compile
from core.conservation import DomainTrap
from core.generator import GenState, cheapest_to_finish, completion_cost, validates
from core.observability import static_analyze
from core.runtime import MapValue, Runtime, evaluate, is_map_value, list_to_python
from core.surface import parse, parse_with_prelude
from core.tokens import (
    MAP_GET, MAP_PAIRS, MAP_PUT, RESULT_FOLLOWS_OPERANDS, SIGNATURES, TYPED_TOKENS,
    decode, encode,
)
from core.types import INT, LIST, MAP, VALUE, is_subtype


def run(src: str, prelude: bool = True, **kw):
    tree = parse_with_prelude(src) if prelude else parse(src)
    return evaluate(compile(tree)[0], Runtime(**kw))


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


def pairs(value):
    return [(list_to_python(e)[0], list_to_python(e)[1]) for e in list_to_python(value)]


class TestSlots(unittest.TestCase):

    def test_the_last_three_free_slots(self):
        self.assertEqual((MAP_PUT, MAP_GET, MAP_PAIRS), (0x13, 0x14, 0x16))
        for token, name in ((MAP_PUT, "map-put"), (MAP_GET, "map-get"), (MAP_PAIRS, "map-pairs")):
            self.assertEqual(SIGNATURES[token]["name"], name)
            self.assertIn(token, TYPED_TOKENS)
        self.assertEqual(len(TYPED_TOKENS), 63)          # the table is full but for END

    def test_map_is_a_value_type(self):
        self.assertTrue(is_subtype(MAP, VALUE))
        self.assertFalse(is_subtype(MAP, LIST))
        self.assertFalse(is_subtype(LIST, MAP))
        self.assertIn(MAP_GET, RESULT_FOLLOWS_OPERANDS)

    def test_maps_are_pure(self):
        self.assertEqual(static_analyze(parse('(map-pairs (map-put (nil) 1 2))')).effects, frozenset())

    def test_the_bytes_round_trip(self):
        tree = parse('(map-get (map-put (nil) "k" 1) "k" 0)')
        self.assertEqual(decode(encode(tree)), tree)
        self.assertTrue(validates(encode(tree)))


class TestOperations(unittest.TestCase):

    def test_put_get_default(self):
        self.assertEqual(run('(map-get (map-put (nil) "a" 1) "a" 0)'), 1)
        self.assertEqual(run('(map-get (map-put (nil) "a" 1) "b" 7)'), 7)
        self.assertEqual(run("(map-get (map-put (nil) 5 6) 5 0)"), 6)

    def test_the_default_is_evaluated_only_when_needed(self):
        self.assertEqual(run('(map-get (map-put (nil) "a" 1) "a" (signal 16))'), 1)
        with self.assertRaises(DomainTrap):
            run('(map-get (map-put (nil) 1 1) "a" (signal 16))')

    def test_values_may_be_anything(self):
        self.assertEqual(text(run('(map-get (map-put (nil) "k" "v") "k" (nil))')), "v")
        self.assertEqual(run('(apply (map-get (map-put (nil) 1 (lambda 9 (mul (ref 9) 2))) 1 0) 21)'), 42)
        self.assertEqual(run('(map-size (map-put (nil) "m" (map-put (nil) 1 2)))'), 1)

    def test_put_replaces_and_is_persistent(self):
        src = ('(let m (map-put (nil) "a" 1) '
               '  (let m2 (map-put m "a" 2) '
               '    (list (map-get m "a" 0) (map-get m2 "a" 0) (map-size m) (map-size m2))))')
        self.assertEqual(list_to_python(run(src)), [1, 2, 1, 1])

    def test_pairs_keep_insertion_order_and_keys(self):
        value = run('(map-pairs (map-put (map-put (map-put (nil) "b" 1) "a" 2) "b" 3))')
        got = pairs(value)
        self.assertEqual([text(k) for k, _ in got], ["b", "a"])
        self.assertEqual([v for _, v in got], [3, 2])

    def test_a_list_of_pairs_is_a_map(self):
        self.assertEqual(run('(map-get (map-put (list (list "x" 9)) "y" 1) "x" 0)'), 9)
        self.assertEqual(run('(map-size (map-of (list (list 1 2) (list 3 4) (list 1 5))))'), 2)
        self.assertEqual(run('(map-get (map-of (list (list 1 2) (list 1 5))) 1 0)'), 5)

    def test_bad_pairs_and_keys_are_structured_faults(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(map-put (list 1 2) "k" 1)')
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")
        with self.assertRaises(DomainTrap):
            run('(map-put (list (list 1)) "k" 1)')
        with self.assertRaises(DomainTrap) as ctx:
            run('(map-put (nil) (lambda 9 1) 1)')
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")
        with self.assertRaises(DomainTrap):
            run('(map-put (nil) (quote 1) 1)')

    def test_text_keys_compare_by_content(self):
        self.assertEqual(run('(map-get (map-put (nil) (list 104 105) 1) "hi" 0)'), 1)
        self.assertEqual(run('(map-get (map-put (nil) (list (list 1) 2) 7) (list (list 1) 2) 0)'), 7)

    def test_a_map_cannot_be_written(self):
        with self.assertRaises(DomainTrap):
            run('(stdout (map-put (nil) 1 2))')

    def test_format_value(self):
        shown = format_value(run('(map-put (map-put (nil) "a" 1) 2 (list 3))'))
        self.assertTrue(shown.startswith("#<map n=2"))
        self.assertIn("a", shown)


class TestChecker(unittest.TestCase):

    def test_map_get_fits_any_slot(self):
        compile(parse('(merge (map-get (map-put (nil) 1 2) 1 0) 1)'))
        compile(parse('(head (map-get (map-put (nil) 1 (nil)) 1 (nil)))'))

    def test_a_map_in_an_int_slot_is_refused(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (map-put (nil) 1 2) 1)"))
        self.assertEqual(ctx.exception.anomaly["detail"]["produces"], "Map")

    def test_map_pairs_wants_a_map(self):
        with self.assertRaises(CompileError):
            compile(parse("(map-pairs (list (list 1 2)))"))

    def test_the_generator_can_close_a_map_slot(self):
        state = GenState.fresh(MAP)
        self.assertIn(MAP_PUT, state.valid_next())
        self.assertEqual(completion_cost(MAP), 4)
        self.assertEqual(cheapest_to_finish(state, state.valid_next()), [MAP_PUT])


class TestPreludeIdioms(unittest.TestCase):

    def test_count_keys_vals(self):
        src = '(let m (fold map-count (nil) (words "b a b c b a")) {body})'
        self.assertEqual(run(src.replace("{body}", '(map-get m "b" 0)')), 3)
        self.assertEqual(run(src.replace("{body}", '(map-get m "a" 0)')), 2)
        self.assertEqual(run(src.replace("{body}", '(map-get m "z" 0)')), 0)
        self.assertEqual([text(k) for k in list_to_python(run(src.replace("{body}", "(map-keys m)")))],
                         ["b", "a", "c"])
        self.assertEqual(list_to_python(run(src.replace("{body}", "(map-vals m)"))), [3, 2, 1])
        self.assertEqual(run(src.replace("{body}", "(map-size m)")), 3)


class TestWordFrequency(unittest.TestCase):

    def test_the_acceptance_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("the cat the dog\nthe end\ndog\n")
            out, err = io.StringIO(), io.StringIO()
            saved = sys.stdin
            sys.stdin = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = cli_main(["run", "apps/wordfreq.lova", path.replace(os.sep, "/"), "2",
                                     "--allow", "fs-read"])
            finally:
                sys.stdin = saved
            self.assertEqual(code, 0, err.getvalue())
            self.assertEqual(out.getvalue(), "the 3\ndog 2\n")
            self.assertIn("=> 4", err.getvalue())


if __name__ == "__main__":
    unittest.main()
