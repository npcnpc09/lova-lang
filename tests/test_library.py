"""Tests for M22 — a standard library a real program can stand on.

Three things.  The list functions iterate rather than recurse, so a
list is bounded by memory and the step ceiling, not by call depth; the
default depth and step ceilings are wide enough for real programs; and
the library grew the functions a text-processing program needs (take /
drop / zip / any / all / sort / split / lines / words / join /
parse-int / text-of / text-lt) plus an association-list map in
``lib/assoc.lova``.  ``signal`` (0x12) lets a library raise the
structured anomaly its callers can already catch.
"""

from __future__ import annotations

import unittest

from core.cli import CLI_MAX_DEPTH, CLI_MAX_STEPS
from core.compiler import CompileError, compile
from core.conservation import ANOMALY_CODES, DomainTrap, anomaly_code
from core.generator import GenState, cheapest_to_finish, is_certain
from core.runtime import MAX_CALL_DEPTH, Runtime, evaluate, list_to_python
from core.surface import parse, parse_with_prelude
from core.tokens import RESULT_FOLLOWS_OPERANDS, SIGNAL, SIGNATURES, TYPED_TOKENS
from core.types import INT, LIST


def run(src: str, **kw):
    return evaluate(compile(parse_with_prelude(src))[0], Runtime(**kw))


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


def texts(value):
    return [text(v) for v in list_to_python(value)]


def ints(value):
    return list_to_python(value)


class TestIteration(unittest.TestCase):

    def test_long_lists_cost_no_depth(self):
        # 5000 elements under a call-depth ceiling of 50: only iteration
        # gets through.
        self.assertEqual(run("(len (range 0 5000))", max_call_depth=50), 5000)
        self.assertEqual(run("(sum (range 0 5000))", max_call_depth=50), 12497500)
        self.assertEqual(run("(len (map inc (range 0 5000)))", max_call_depth=50), 5000)
        self.assertEqual(run("(len (filter even (range 0 5000)))", max_call_depth=50), 2500)
        self.assertEqual(run("(fold (lambda a (lambda b (merge a b))) 0 (range 0 5000))",
                             max_call_depth=50), 12497500)
        self.assertEqual(run("(last (range 0 5000))", max_call_depth=50), 4999)
        self.assertEqual(run("(len (reverse (range 0 5000)))", max_call_depth=50), 5000)

    def test_the_old_cases_still_hold(self):
        cases = {
            "(len (list 1 2 3))": 3, "(sum (range 1 5))": 10,
            "(product (list 2 3 4))": 24, "(nth (list 7 8 9) 1)": 8,
            "(last (list 7 8 9))": 9, "(contains (list 1 2 3) 2)": 1,
            "(contains (list 1 2 3) 9)": 0, "(len (append (list 1 2) (list 3 4 5)))": 5,
            "(head (reverse (list 1 2 3)))": 3, '(same "abc" "abc")': 1,
            '(same "abc" "abd")': 0, '(same "ab" "abc")': 0, "(pow 2 10)": 1024,
            "(pow 3 0)": 1, "(len (repeat 7 4))": 4, "(len (range 5 5))": 0,
            "(len (repeat 7 0))": 0,
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                self.assertEqual(run(src), want)

    def test_nth_and_last_are_loud(self):
        with self.assertRaises(DomainTrap):
            run("(nth (list 1 2) 5)")
        with self.assertRaises(DomainTrap):
            run("(last (nil))")

    def test_shapes_survive_iteration(self):
        # `(merge 0 (head s))` keeps `len` an Int for the checker.
        with self.assertRaises(CompileError):
            compile(parse_with_prelude("(head (len (list 1)))"))
        with self.assertRaises(CompileError):
            compile(parse_with_prelude("(merge (reverse (list 1)) 1)"))


class TestNewListFunctions(unittest.TestCase):

    def test_take_and_drop(self):
        self.assertEqual(ints(run("(take 2 (list 1 2 3))")), [1, 2])
        self.assertEqual(ints(run("(take 9 (list 1 2 3))")), [1, 2, 3])
        self.assertEqual(ints(run("(take 0 (list 1 2 3))")), [])
        self.assertEqual(ints(run("(drop 2 (list 1 2 3))")), [3])
        self.assertEqual(ints(run("(drop 9 (list 1 2 3))")), [])

    def test_zip(self):
        pairs = list_to_python(run("(zip (list 1 2 3) (list 4 5))"))
        self.assertEqual([ints(p) for p in pairs], [[1, 4], [2, 5]])

    def test_any_and_all(self):
        self.assertEqual(run("(any even (list 1 3 4))"), 1)
        self.assertEqual(run("(any even (list 1 3 5))"), 0)
        self.assertEqual(run("(all even (list 2 4 6))"), 1)
        self.assertEqual(run("(all even (list 2 5 6))"), 0)
        self.assertEqual(run("(all even (nil))"), 1)
        self.assertEqual(run("(any even (nil))"), 0)

    def test_sort(self):
        self.assertEqual(ints(run("(sort (list 5 3 9 1 3))")), [1, 3, 3, 5, 9])
        self.assertEqual(ints(run("(sort-by ge2 (list 5 3 9 1))")), [9, 5, 3, 1])
        self.assertEqual(ints(run("(sort (nil))")), [])
        self.assertEqual(ints(run("(sort (list 1))")), [1])

    def test_sort_is_stable_enough_for_keys(self):
        # Sorting pairs by their first element keeps equal keys in order.
        src = ("(def by-key [a b] (le (head a) (head b)))"
               "(sort-by by-key (list (list 2 1) (list 1 1) (list 2 2) (list 1 2)))")
        self.assertEqual([ints(p) for p in list_to_python(run(src))],
                         [[1, 1], [1, 2], [2, 1], [2, 2]])

    def test_sort_scales(self):
        # 1000 elements: log-depth recursion, and the merge iterates.
        # Costs more than the library's step default; the CLI's suffices.
        rt = Runtime(max_steps=CLI_MAX_STEPS, max_call_depth=64)
        value = evaluate(compile(parse_with_prelude("(take 3 (sort (reverse (range 0 1000))))"))[0], rt)
        self.assertEqual(ints(value), [0, 1, 2])


class TestText(unittest.TestCase):

    def test_split_lines_words(self):
        self.assertEqual(texts(run('(split "a,b,,c" 44)')), ["a", "b", "", "c"])
        self.assertEqual(texts(run('(split "" 44)')), [""])
        self.assertEqual(texts(run('(lines "one\\ntwo\\n")')), ["one", "two", ""])
        self.assertEqual(texts(run('(words "  the quick\\n brown  fox ")')),
                         ["the", "quick", "brown", "fox"])
        self.assertEqual(texts(run('(words "")')), [])

    def test_join(self):
        self.assertEqual(text(run('(join (list "a" "b" "c") 44)')), "a,b,c")
        self.assertEqual(text(run('(join (list "" "b") 44)')), ",b")
        self.assertEqual(text(run("(join (nil) 44)")), "")

    def test_parse_int_and_text_of(self):
        self.assertEqual(run('(parse-int "1234")'), 1234)
        self.assertEqual(run('(parse-int "-56")'), -56)
        self.assertEqual(run('(parse-int "0")'), 0)
        self.assertEqual(text(run("(text-of 1234)")), "1234")
        self.assertEqual(text(run("(text-of -56)")), "-56")
        self.assertEqual(text(run("(text-of 0)")), "0")
        self.assertEqual(run('(parse-int (text-of 987654321))'), 987654321)

    def test_parse_int_of_garbage_is_a_signal(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(parse-int "12a")')
        self.assertEqual(ctx.exception.anomaly["kind"], "signalled")
        self.assertEqual(anomaly_code(ctx.exception.anomaly), 16)
        self.assertEqual(run('(when-anomaly (parse-int "12a") (lambda 9 (ref 9)))'), 16)
        self.assertEqual(run('(try (parse-int "") -1)'), -1)

    def test_text_lt(self):
        self.assertEqual(run('(text-lt "apple" "banana")'), 1)
        self.assertEqual(run('(text-lt "banana" "apple")'), 0)
        self.assertEqual(run('(text-lt "app" "apple")'), 1)
        self.assertEqual(run('(text-lt "apple" "app")'), 0)
        self.assertEqual(run('(text-lt "same" "same")'), 0)
        self.assertEqual(texts(run('(sort-by text-lt (list "pear" "fig" "apple"))')),
                         ["apple", "fig", "pear"])


class TestAssoc(unittest.TestCase):

    def test_get_put_has(self):
        src = '(use "assoc") (let m (assoc-put (assoc-put (nil) "a" 1) "b" 2) {body})'
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "a" 0)')), 1)
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "b" 0)')), 2)
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "c" 7)')), 7)
        self.assertEqual(run(src.replace("{body}", '(assoc-has m "a")')), 1)
        self.assertEqual(run(src.replace("{body}", '(assoc-has m "c")')), 0)

    def test_put_replaces(self):
        src = ('(use "assoc") (let m (assoc-put (assoc-put (nil) "a" 1) "a" 5) '
               '(list (assoc-get m "a" 0) (len m)))')
        self.assertEqual(ints(run(src)), [5, 1])

    def test_count_and_keys(self):
        src = ('(use "assoc") (let m (fold assoc-count (nil) (words "b a b c b a")) {body})')
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "b" 0)')), 3)
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "a" 0)')), 2)
        self.assertEqual(run(src.replace("{body}", '(assoc-get m "c" 0)')), 1)
        self.assertEqual(sorted(texts(run(src.replace("{body}", "(assoc-keys m)")))),
                         ["a", "b", "c"])
        self.assertEqual(sorted(ints(run(src.replace("{body}", "(assoc-vals m)")))),
                         [1, 2, 3])

    def test_del(self):
        src = '(use "assoc") (len (assoc-del (assoc-put (assoc-put (nil) "a" 1) "b" 2) "a"))'
        self.assertEqual(run(src), 1)


class TestSignal(unittest.TestCase):

    def test_signal_took_a_free_slot(self):
        self.assertEqual(SIGNAL, 0x12)
        self.assertEqual(SIGNATURES[SIGNAL]["name"], "signal")
        self.assertIn(SIGNAL, TYPED_TOKENS)
        self.assertIn(SIGNAL, RESULT_FOLLOWS_OPERANDS)
        self.assertEqual(ANOMALY_CODES["signalled"], 10)

    def test_a_signal_is_a_structured_fault_with_its_own_code(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(signal 42)")
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "signalled")
        self.assertEqual(anomaly["detail"]["code"], 42)
        self.assertEqual(anomaly_code(anomaly), 42)

    def test_the_handler_receives_the_programs_code(self):
        self.assertEqual(run("(when-anomaly (signal 42) (lambda 9 (ref 9)))"), 42)
        self.assertEqual(run("(when-anomaly (merge 1 (signal 99)) (lambda 9 (mul (ref 9) 2)))"), 198)

    def test_codes_below_16_are_reserved(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(signal 3)")
        self.assertEqual(ctx.exception.anomaly["kind"], "domain-error")

    def test_signal_fits_any_slot(self):
        for src in ("(merge 1 (signal 16))", "(head (signal 16))",
                    "(apply (signal 16) 1)", "(explain (signal 16))"):
            with self.subTest(src=src):
                compile(parse(src))

    def test_the_bias_never_reaches_for_a_signal(self):
        for slot in (INT, LIST):
            state = GenState.fresh(slot)
            self.assertIn(SIGNAL, state.valid_next())
            self.assertFalse(is_certain(state, SIGNAL))
            self.assertNotIn(SIGNAL, cheapest_to_finish(state, state.valid_next()))


class TestDefaults(unittest.TestCase):

    def test_the_library_ceilings(self):
        self.assertEqual(MAX_CALL_DEPTH, 10_000)
        self.assertEqual(CLI_MAX_DEPTH, 10_000)
        self.assertEqual(CLI_MAX_STEPS, 20_000_000)

    def test_a_deep_recursion_now_runs_by_default(self):
        self.assertEqual(run("(def count [n] (if n (merge 1 (count (sub n 1))) 0)) (count 3000)"), 3000)


if __name__ == "__main__":
    unittest.main()
