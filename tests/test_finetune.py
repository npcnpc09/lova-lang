"""M8 -- the corpus generator and the benchmark harness, offline.

The generator's promise is that every pair it emits is verified and
none of them solves a benchmark task; the harness's is that a
reference solution scores full marks through the same pipeline a
model's answer goes through.
"""

from __future__ import annotations

import json
import random
import re
import unittest

from corpus.finetune import (FAMILIES, _held_out, chat_record, generate,
                             SYSTEM_PROMPT)
from corpus.tasks import TASKS_V3, by_id


class Generator(unittest.TestCase):

    def test_pairs_are_verified_distinct_and_held_out(self):
        pairs, dropped = generate(40, seed=7)
        self.assertGreaterEqual(len(pairs), 30, dropped)
        self.assertEqual(len({(p["prompt"], p["program"]) for p in pairs}), len(pairs))
        bench = {re.sub(r"\s+", " ", t.template).strip() for t in TASKS_V3}
        for p in pairs:
            self.assertNotIn(re.sub(r"\s+", " ", p["program"]).strip(), bench, p["id"])
            self.assertGreaterEqual(len(p["tests"]), 2)
            for v in p["variables"]:
                self.assertIn("{" + v + "}", p["program"])

    def test_every_family_produces_and_names_its_benchmark_tasks(self):
        rng = random.Random(1)
        for family, _weight in FAMILIES:
            with self.subTest(family=family.__name__):
                seen_bench = set()
                for _ in range(60):
                    pair = family(rng)
                    self.assertTrue(pair.program.strip().startswith("("))
                    if pair.benchmark_id:
                        seen_bench.add(pair.benchmark_id)
                        self.assertTrue(_held_out(pair))
                for bid in seen_bench:
                    by_id(bid)                        # a real task id

    def test_chat_record_shape(self):
        pairs, _ = generate(3, seed=2)
        rec = chat_record("CARD", pairs[0])
        roles = [m["role"] for m in rec["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant"])
        self.assertTrue(rec["messages"][0]["content"].startswith(SYSTEM_PROMPT))
        self.assertEqual(rec["messages"][2]["content"], pairs[0]["program"])
        json.dumps(rec)


class Harness(unittest.TestCase):

    def test_reference_solutions_score_full_marks(self):
        from experiments.experiment_17_llm_benchmark import run, summarise
        tasks = [by_id("pb01"), by_id("pb61"), by_id("pb80")]
        result = run(None, tasks, ["lova", "python"], verbose=False)
        for row in result["rows"]:
            self.assertTrue(row["lova"]["passed"], row["id"])
            self.assertTrue(row["python"]["passed"], row["id"])
        self.assertIn("3/3", summarise(result, ["lova", "python"]))

    def test_a_wrong_or_hanging_answer_fails_cleanly(self):
        from experiments.experiment_17_llm_benchmark import run_lova, run_python
        task = by_id("pb61")
        self.assertFalse(run_lova("(merge {n} 1)", task)["passed"])
        self.assertFalse(run_lova("this is not a program", task)["passed"])
        self.assertFalse(run_python("def solve(n): return n + 1", task)["passed"])
        hang = run_python("def solve(n):\n    while True: pass", task, timeout=2)
        self.assertFalse(hang["passed"])


if __name__ == "__main__":
    unittest.main()
