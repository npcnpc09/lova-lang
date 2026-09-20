"""M40 -- would the examples notice if a def were wrong?

`core.strength.strength` tries the locator's single-node edits on a
passing program and counts, def by def, the ones no example catches.
A def whose edits survive is unguarded; a def no example reaches is
reported apart.  `lova check FILE --strength` prints it.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from core.cli import main
from core.strength import strength, summary


# `gap` is symmetric, and the value example at (0, 0) cannot tell
# `x` from `y` or `merge` from `sub` -- most wrong programs give the
# right answer at the origin.  The relation examples can.
VALUES_ONLY = """(def gap [a b] (abs (sub a b)))
(def clamp [lo hi x] (max lo (min hi x)))
(def unused [n] (mul n 3))
(example (gap 0 0) 0)
(example (clamp 0 10 5) 5)
(gap {a} {b})"""

WITH_RELATIONS = """(def gap [a b] (abs (sub a b)))
(def clamp [lo hi x] (max lo (min hi x)))
(def unused [n] (mul n 3))
(example (gap 3 7) 4)
(example (gap 3 7) (gap 7 3))
(example (gap 2 9) (gap 9 2))
(example (clamp 2 8 5) 5)
(example (clamp 2 8 11) 8)
(example (clamp 2 8 -3) 2)
(gap {a} {b})"""


def _by_name(report):
    return {d["name"]: d for d in report["defs"]}


class Strength(unittest.TestCase):

    def test_values_at_the_origin_leave_a_def_unguarded(self):
        report = strength(VALUES_ONLY.replace("{a}", "1").replace("{b}", "2"), budget_s=10)
        defs = _by_name(report)
        self.assertIn("gap", defs)
        self.assertGreater(defs["gap"]["survived"], 0)
        self.assertEqual(report["examples"], 2)
        # `unused` is reached by no example, and is said so apart
        self.assertEqual([u["name"] for u in report["unreached"]], ["unused"])
        # a survivor names the edit and where it is
        s = defs["gap"]["survivors"][0]
        self.assertTrue(s["edit"])
        self.assertEqual(s["line"], 1)

    def test_relations_guard_what_values_did_not(self):
        report = strength(WITH_RELATIONS.replace("{a}", "1").replace("{b}", "2"), budget_s=10)
        defs = _by_name(report)
        weak = strength(VALUES_ONLY.replace("{a}", "1").replace("{b}", "2"), budget_s=10)
        self.assertLess(defs["gap"]["survived"], _by_name(weak)["gap"]["survived"])
        self.assertLess(defs["clamp"]["survived"], _by_name(weak)["clamp"]["survived"])
        # every edit of `gap` is caught: swapped operands change the
        # sign the `abs` hides only when the example compares both ways
        self.assertEqual(defs["gap"]["survived"], 0, defs["gap"]["survivors"])

    def test_only_and_the_budget(self):
        src = WITH_RELATIONS.replace("{a}", "1").replace("{b}", "2")
        report = strength(src, budget_s=10, only=["clamp"])
        self.assertEqual([d["name"] for d in report["defs"]], ["clamp"])
        report = strength(src, budget_s=0.0)
        self.assertEqual(report["tried"], 0)
        self.assertIn("not tried (budget)", summary(report))

    def test_a_failing_example_is_refused(self):
        src = VALUES_ONLY.replace("(example (gap 0 0) 0)", "(example (gap 0 0) 5)")
        with self.assertRaises(ValueError):
            strength(src.replace("{a}", "1").replace("{b}", "2"), budget_s=5)

    def test_the_summary_and_the_cli(self):
        report = strength(VALUES_ONLY.replace("{a}", "1").replace("{b}", "2"), budget_s=10)
        text = summary(report)
        self.assertIn("edits unseen", text)
        self.assertIn("no example reaches: unused", text)
        with tempfile.NamedTemporaryFile("w", suffix=".lova", delete=False, encoding="utf-8") as f:
            f.write(WITH_RELATIONS)
            path = f.name
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = main(["check", path, "1", "2", "--strength", "--strength-budget", "10"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("6/6 examples pass", out.getvalue())
            self.assertIn("strength: what the examples would not see", out.getvalue())
            self.assertIn("gap", out.getvalue())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
