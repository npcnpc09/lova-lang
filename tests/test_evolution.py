"""Tests for M15 — populations in the language; Axiom 6 completed.

Axiom 6: a function is a population of variants, not a single
definition; dispatch selects per workload; losers retire, winners are
cloned and mutated. From M4 to M14 that lived in ``core/populations.py``.
These tests cover the six Evolution operators that put it in LOVA:
``defpop`` ``variant`` ``select`` ``fitness`` ``retire`` ``evolve``.

A scorer is an ``Fn`` from Program to Int and **lower is fitter**, so a
surprise magnitude is a score without translation.
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.conservation import DomainTrap, StepTrap
from core.lineage import LineageStore
from core.runtime import (
    Population, Runtime, UNFIT, evaluate, is_population_value, list_to_python,
)
from core.surface import parse, pretty
from core.tokens import DEFPOP, EVOLVE, SIGNATURES, TYPED_TOKENS
from core.types import POPULATION, VALUE, is_subtype

SCORER = "(lambda 9 (surprise 42 (eval (ref 9))))"
SEEDS = ("(quote (p 5))", "(quote (sigma 12))", "(quote (merge 10 20))",
         "(quote (tau 100))", "(quote (gcd 24 36))")
POOL = f"(defpop {SCORER} {' '.join(SEEDS)})"


def run(src: str, rt: Runtime = None):
    node, _ = compile(parse(src))
    return evaluate(node, rt or Runtime())


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


class TestDefpop(unittest.TestCase):

    def test_builds_a_population(self):
        pop = run(POOL)
        self.assertTrue(is_population_value(pop))
        self.assertEqual(len(pop.variants), 5)
        self.assertEqual(pop.generation, 0)

    def test_variants_are_registered_in_lineage(self):
        rt = Runtime()
        pop = run(POOL, rt)
        self.assertEqual([v.uid for v in pop.variants], [1, 2, 3, 4, 5])

    def test_needs_a_function_scorer(self):
        with self.assertRaises(CompileError):
            compile(parse("(defpop 5 (quote 1))"))

    def test_needs_at_least_one_variant(self):
        with self.assertRaises(DomainTrap) as ctx:
            run(f"(defpop {SCORER})")
        self.assertEqual(ctx.exception.anomaly["kind"], "domain-error")

    def test_a_scorer_defined_with_def_works(self):
        src = ("(def score [p] (surprise 42 (eval p)))"
               f"(fitness (defpop score {' '.join(SEEDS)}))")
        self.assertEqual(list_to_python(run(src)), [35, 14, 12, 33, 30])


class TestScoring(unittest.TestCase):

    def test_fitness_is_in_pool_order_and_lower_is_fitter(self):
        # Exp 05's initial distances, reproduced from inside the language.
        self.assertEqual(list_to_python(run(f"(fitness {POOL})")),
                         [35, 14, 12, 33, 30])

    def test_variant_is_pool_order(self):
        self.assertEqual(text(run(f"(explain (variant {POOL} 0))")), "(p 5)")
        self.assertEqual(text(run(f"(explain (variant {POOL} 2))")),
                         "(merge 10 20)")

    def test_select_is_fitness_order(self):
        self.assertEqual(text(run(f"(explain (select {POOL} 0))")),
                         "(merge 10 20)")                     # distance 12
        self.assertEqual(text(run(f"(explain (select {POOL} 4))")), "(p 5)")

    def test_select_ties_keep_pool_order(self):
        src = f"(explain (select (defpop {SCORER} (quote 40) (quote 44)) 0))"
        self.assertEqual(text(run(src)), "40")

    def test_out_of_range_is_loud(self):
        for op in ("variant", "select"):
            with self.subTest(op=op):
                with self.assertRaises(DomainTrap):
                    run(f"({op} {POOL} 9)")

    def test_an_unfit_variant_is_scored_unfit_and_recorded(self):
        # A variant that traps under the scorer loses; it does not crash
        # the pool, and it is not silent.
        rt = Runtime()
        scores = list_to_python(
            run(f"(fitness (defpop {SCORER} (quote (div 1 0)) (quote 42)))", rt))
        self.assertEqual(scores, [UNFIT, 0])
        self.assertEqual(rt.caught[0]["kind"], "domain-error")

    def test_the_step_ceiling_is_not_a_fitness_signal(self):
        spin = "(quote (apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1))"
        with self.assertRaises(StepTrap):
            evaluate(parse(f"(fitness (defpop {SCORER} {spin}))"),
                     Runtime(max_steps=3000))


class TestRetire(unittest.TestCase):

    def test_retire_drops_the_least_fit(self):
        pop = run(f"(retire {POOL})")
        self.assertEqual([pretty(v) for v in pop.variants],
                         ["(sigma 12)", "(merge 10 20)", "(tau 100)", "(gcd 24 36)"])

    def test_retire_keeps_the_generation(self):
        self.assertEqual(run(f"(retire {POOL})").generation, 0)

    def test_cannot_retire_the_last_variant(self):
        with self.assertRaises(DomainTrap):
            run(f"(retire (defpop {SCORER} (quote 1)))")


class TestEvolve(unittest.TestCase):

    def _trail(self, seed: int, generations: int):
        rt = Runtime(lineage=LineageStore(seed=seed))
        pop = run(POOL, rt)
        best = []
        for _ in range(generations):
            pop = evaluate(parse("(evolve (ref 0))").__class__(
                op=EVOLVE, args=[parse("(ref 0)")]), Runtime(env={0: pop}, lineage=rt.lineage))
            scores = list_to_python(evaluate(
                parse("(fitness (ref 0))"), Runtime(env={0: pop}, lineage=rt.lineage)))
            best.append(min(scores))
        return pop, best

    def test_one_generation_keeps_the_size(self):
        pop = run(f"(evolve {POOL})")
        self.assertEqual(len(pop.variants), 5)
        self.assertEqual(pop.generation, 1)

    def test_survivors_keep_their_identity_and_children_are_derived(self):
        rt = Runtime()
        pop = run(f"(evolve {POOL})", rt)
        parents = {1, 2, 3, 4, 5}
        kept = [v.uid for v in pop.variants[:-1]]
        child = pop.variants[-1]
        self.assertTrue(set(kept) <= parents)
        self.assertNotIn(child.uid, parents)
        self.assertEqual(rt.lineage.record(child.uid).generation, 1)
        self.assertIn(rt.lineage.record(child.uid).mutation_kind, ("clone", "mutate"))

    def test_the_least_fit_is_the_one_retired(self):
        pop = run(f"(evolve {POOL})")
        self.assertNotIn("(p 5)", [pretty(v) for v in pop.variants[:-1]])

    def test_best_fitness_never_worsens(self):
        # Elitism: the fittest survivor is always kept.
        for seed in (0, 1, 2):
            with self.subTest(seed=seed):
                _pop, best = self._trail(seed, 20)
                for earlier, later in zip(best, best[1:]):
                    self.assertLessEqual(later, earlier)

    def test_fitness_improves_within_thirty_generations(self):
        # The self-healing claim of Exp 05, in the language.  Deterministic
        # for the store seed, so this is a fixed trajectory, not a hope.
        _pop, best = self._trail(1, 30)
        self.assertLess(best[-1], 12)

    def test_evolve_is_reproducible(self):
        a = self._trail(2, 10)[1]
        b = self._trail(2, 10)[1]
        self.assertEqual(a, b)

    def test_a_population_of_one_cannot_evolve(self):
        with self.assertRaises(DomainTrap):
            run(f"(evolve (defpop {SCORER} (quote 1)))")

    def test_axiom_5_and_6_compose(self):
        # The winner of a run can say where it came from.
        src = ("(def score [p] (surprise 42 (eval p)))"
               "(def gen [pop k] (if k (gen (evolve pop) (sub k 1)) pop))"
               f"(let 0 (gen (defpop score {' '.join(SEEDS)}) 30)"
               "  (generation (select (ref 0) 0)))")
        rt = Runtime(lineage=LineageStore(seed=1))
        self.assertGreaterEqual(run(src, rt), 1)


class TestTypes(unittest.TestCase):

    def test_population_is_disjoint_and_a_value(self):
        self.assertTrue(is_subtype(POPULATION, VALUE))
        from core.types import INT, LIST, PROGRAM
        for other in (INT, LIST, PROGRAM):
            self.assertFalse(is_subtype(POPULATION, other))

    def test_a_population_in_an_int_slot_is_a_compile_error(self):
        with self.assertRaises(CompileError):
            compile(parse(f"(merge {POOL} 1)"))

    def test_a_population_cannot_be_written(self):
        with self.assertRaises(DomainTrap) as ctx:
            run(f"(stdout {POOL})")
        self.assertIn("select", ctx.exception.anomaly["repair_hint"])

    def test_the_family_is_complete(self):
        for byte in range(0x20, 0x28):
            with self.subTest(byte=hex(byte)):
                self.assertIn(byte, TYPED_TOKENS)
        self.assertEqual(SIGNATURES[DEFPOP]["name"], "defpop")


if __name__ == "__main__":
    unittest.main()
