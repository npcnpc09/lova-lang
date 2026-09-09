"""Tests for M18 — ``read``, ``use``, and a library of evolution rules.

``explain`` (M14) turns a program into text; ``read`` is its inverse, so
a LOVA program can build a program from text and run it.  ``(use
"name")`` includes ``lib/name.lova`` textually, once, the way the prelude
has been included since M11 — a module system with no new operator.
``defpop`` splices list arguments so a pool can be rebuilt from its
variants by library code; ``lib/evolution.lova`` is that library.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.compiler import compile
from core.conservation import DomainTrap
from core.generator import GenState
from core.observability import _EFFECTS
from core.runtime import Cons, Node, Population, Runtime, evaluate, list_to_python
from core.surface import expand_uses, parse, parse_with_prelude, resolve_library
from core.tokens import (
    HASH, READ, SIGNATURES, _TYPE_INFO, decode, encode,
)
from core.types import LIST, PROGRAM


def run(src: str, prelude: bool = False):
    tree = parse_with_prelude(src) if prelude else parse(src)
    return evaluate(compile(tree)[0], Runtime())


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


class TestRead(unittest.TestCase):

    def test_read_is_on_the_reused_normal_range_slot(self):
        self.assertEqual(READ, 0x1E)
        self.assertEqual(SIGNATURES[READ]["name"], "read")
        self.assertEqual(_TYPE_INFO[READ]["in_types"], [LIST])
        self.assertEqual(_TYPE_INFO[READ]["out_type"], PROGRAM)

    def test_read_of_a_string_is_a_program(self):
        value = run('(read "(merge 1 2)")')
        self.assertIsInstance(value, Node)
        self.assertEqual(value, parse("(merge 1 2)"))

    def test_read_inverts_explain(self):
        for src in ("(merge 1 2)", "(mul (merge 1 2) (sub 5 3))",
                    "(let 0 5 (merge (ref 0) 1))",
                    "(if-surprise 1 2 3)", "(lambda 1 (mul (ref 0) 2))",
                    "(cons 1 (cons 2 (nil)))", "(quote (merge 1 2))"):
            with self.subTest(src=src):
                self.assertEqual(
                    run(f'(read (explain (quote {src})))'), parse(src))

    def test_read_then_eval(self):
        self.assertEqual(run('(eval (read "(mul 12 12)"))'), 144)

    def test_read_accepts_the_surface_sugar(self):
        # `def` and macros are the surface, so a program authored in the
        # sugar reads back to the same core.
        self.assertEqual(run('(eval (read "(sub 10 (abs -3))"))'), 7)
        self.assertEqual(
            run('(eval (read "(def twice [x] (mul x 2)) (twice 21)"))'), 42)

    def test_read_of_malformed_text_is_a_structured_fault(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(read "(merge 1")')
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "malformed")
        self.assertEqual(anomaly["detail"]["operator"], "read")

    def test_read_of_a_non_text_is_a_fault(self):
        # A list is typed, but a list of programs is not text.
        with self.assertRaises(DomainTrap):
            run("(read (list (quote 1)))")

    def test_a_malformed_read_can_be_caught(self):
        self.assertEqual(run('(when-anomaly (read "(") (lambda 9 7))'), 7)

    def test_read_is_effect_free(self):
        self.assertEqual(_EFFECTS[READ], frozenset())

    def test_read_survives_the_bytes(self):
        tree = parse('(hash (read "(merge 1 2)"))')
        self.assertEqual(decode(encode(tree)), tree)

    def test_read_fits_a_program_slot(self):
        self.assertIn(READ, GenState.fresh().step(HASH).valid_next())

    def test_read_of_explain_preserves_the_hash(self):
        self.assertEqual(
            run("(hash (read (explain (quote (mul (merge 1 2) 3)))))"),
            run("(hash (quote (mul (merge 1 2) 3)))"))


class TestUse(unittest.TestCase):

    def test_libraries_resolve_from_lib(self):
        self.assertTrue(resolve_library("prelude").endswith("prelude.lova"))
        self.assertTrue(resolve_library("evolution").endswith("evolution.lova"))

    def test_an_unknown_library_is_an_error(self):
        with self.assertRaises(ValueError):
            parse('(use "no-such-library") 1')

    def test_use_includes_the_definitions(self):
        self.assertEqual(run('(use "prelude") (sum (list 1 2 3))'), 6)

    def test_use_is_included_once(self):
        src = '(use "prelude") (use "prelude") (len (list 1 2))'
        expanded = expand_uses(src)
        self.assertEqual(expanded.count("(def len"), 1)
        self.assertEqual(run(src), 2)

    def test_use_of_a_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "triple.lova")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("(def triple [x] (mul x 3))\n")
            self.assertEqual(run(f'(use "{path}") (triple 5)'), 15)

    def test_use_is_transitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = os.path.join(tmp, "inner.lova")
            outer = os.path.join(tmp, "outer.lova")
            with open(inner, "w", encoding="utf-8") as handle:
                handle.write("(def one [x] 1)\n")
            with open(outer, "w", encoding="utf-8") as handle:
                handle.write(f'(use "{inner}") (def two [x] (merge (one x) (one x)))\n')
            self.assertEqual(run(f'(use "{outer}") (two 0)'), 2)

    def test_a_cycle_terminates(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.lova")
            b = os.path.join(tmp, "b.lova")
            with open(a, "w", encoding="utf-8") as handle:
                handle.write(f'(use "{b}") (def fa [x] 1)\n')
            with open(b, "w", encoding="utf-8") as handle:
                handle.write(f'(use "{a}") (def fb [x] 2)\n')
            self.assertEqual(run(f'(use "{a}") (merge (fa 0) (fb 0))'), 3)

    def test_unused_definitions_are_dropped(self):
        # A library costs nothing a program does not call.
        with_lib = compile(parse('(use "prelude") 1'))[0]
        self.assertEqual(with_lib, compile(parse("1"))[0])

    def test_use_inside_read(self):
        # `read` takes the full surface, `use` included.
        self.assertEqual(
            run('(eval (read "(use \\"prelude\\") (product (list 2 3 4))"))'),
            24)


class TestDefpopSplice(unittest.TestCase):

    SCORER = "(lambda 9 (eval (ref 9)))"

    def test_defpop_takes_a_list_of_programs(self):
        pop = run(f"(defpop {self.SCORER} (list (quote 1) (quote 2) (quote 3)))")
        self.assertIsInstance(pop, Population)
        self.assertEqual(len(pop.variants), 3)

    def test_programs_and_lists_mix(self):
        pop = run(f"(defpop {self.SCORER} (quote 0) (list (quote 1) (quote 2)) (quote 3))")
        self.assertEqual(len(pop.variants), 4)

    def test_a_non_program_element_is_a_fault(self):
        with self.assertRaises(DomainTrap):
            run(f"(defpop {self.SCORER} (list 1 2))")

    def test_an_empty_list_alone_is_a_fault(self):
        with self.assertRaises(DomainTrap):
            run(f"(defpop {self.SCORER} (nil))")


class TestEvolutionLibrary(unittest.TestCase):

    SCORER = "(lambda 9 (eval (ref 9)))"
    POOL = f"(defpop {SCORER} (quote (merge 1 1)) (quote (merge 2 3)) (quote (mul 3 4)))"

    def test_pool_size(self):
        self.assertEqual(run(f'(use "evolution") (pool-size {self.POOL})'), 3)

    def test_best_and_best_score(self):
        # Lower is fitter, as for every scorer.
        self.assertEqual(
            text(run(f'(use "evolution") (explain (best {self.POOL}))')),
            "(merge 1 1)")
        self.assertEqual(run(f'(use "evolution") (best-score {self.POOL})'), 2)

    def test_variants_of_lists_every_program(self):
        value = run(f'(use "evolution") (variants-of {self.POOL})')
        self.assertIsInstance(value, Cons)
        self.assertEqual(len(list_to_python(value)), 3)
        self.assertTrue(all(isinstance(v, Node) for v in list_to_python(value)))

    def test_evolve_n_keeps_the_pool_size(self):
        pop = run(f'(use "evolution") (evolve-n {self.POOL} 3)')
        self.assertIsInstance(pop, Population)
        self.assertEqual(len(pop.variants), 3)

    def test_evolve_with_is_a_custom_rule(self):
        # Retire the least fit, add a mutation of the best: size is kept
        # and the best score never worsens (lower is fitter).
        pop = run(f'(use "evolution") (evolve-with-n {self.POOL} {self.SCORER} 40 4)')
        self.assertIsInstance(pop, Population)
        self.assertEqual(len(pop.variants), 3)
        self.assertLessEqual(
            run(f'(use "evolution") (best-score (evolve-with-n {self.POOL} {self.SCORER} 40 4))'),
            2)


if __name__ == "__main__":
    unittest.main()
