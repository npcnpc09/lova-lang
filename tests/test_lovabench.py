"""LOVABench v3: every reference solution validates, in LOVA and in
Python, and the algorithmic category is what Q33 asked for."""

from __future__ import annotations

import unittest

from corpus.evaluator import run_task
from corpus.python_solutions import PYTHON_ALGORITHMIC
from corpus.tasks import ALGORITHMIC, TASKS, TASKS_V3


class References(unittest.TestCase):

    def test_v3_is_v2_plus_twenty_algorithmic_tasks(self):
        self.assertEqual(len(TASKS), 60)
        self.assertEqual(len(ALGORITHMIC), 20)
        self.assertEqual(len(TASKS_V3), 80)
        for task in ALGORITHMIC:
            self.assertIn("algorithmic", task.tags)

    def test_every_lova_reference_passes_its_tests(self):
        for task in TASKS_V3:
            with self.subTest(task=task.id):
                result = run_task(task.template, task)
                self.assertTrue(result.all_passed,
                                [(r.inputs, r.expected, r.got) for r in result.results])

    def test_every_python_reference_passes_its_tests(self):
        for task in ALGORITHMIC:
            with self.subTest(task=task.id):
                scope: dict = {}
                exec(PYTHON_ALGORITHMIC[task.id], scope)
                for inputs, expected in task.tests:
                    self.assertEqual(scope["solve"](**inputs), expected, inputs)

    def test_the_algorithmic_prompts_do_not_name_an_operator(self):
        # The prompts say what to compute, not which LOVA operator does it
        # (Exp 13 F3: the v1/v2 prompts state the formula).
        for task in ALGORITHMIC:
            with self.subTest(task=task.id):
                for word in ("sigma", "tau", "mobius", "(p ", "merge", "if-surprise"):
                    self.assertNotIn(word, task.prompt)


if __name__ == "__main__":
    unittest.main()
