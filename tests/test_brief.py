"""The fault in one line (core/brief.py, Exp 30)."""
import unittest

from core.brief import brief, compact
from core.mcp_server import tool_check, tool_execute


def run(src, **kw):
    return tool_execute({"source": src, "native": "off", "max_steps": 200000, **kw})


class Brief(unittest.TestCase):

    def test_every_line_says_where_and_what(self):
        cases = {
            "(def f [x] (div x 0))\n(f 3)": ("1:12 [11,20) `(div x 0)`", "division by zero"),
            "(def total [xs] (fold merge 0 xs))\n(totl (list 1 2))": ("2:2", "nearest: total"),
            "(merge (nil) 1)": ("1:8 [7,12) `(nil)`", "`nil` gives List; the slot wants Int"),
            "(def f [x] (merge x 1)))\n(f 2)": ("1:24", "unexpected closing paren"),
            "(signal 17)": ("1:1", "signal 17"),
        }
        for src, (where, what) in cases.items():
            c = compact(run(src))
            self.assertIn(where, c["fault"], src)
            self.assertIn(what, c["fault"], src)
            self.assertNotIn("anomaly", c)

    def test_the_step_trap_names_where_the_steps_went_once(self):
        c = compact(run("(def spin [n] (spin (merge n 1)))\n(spin 0)"))
        self.assertEqual(c["kind"], "step-limit-exceeded")
        self.assertIn("steps by function: spin", c["fault"])
        self.assertEqual(c["fault"].count("spin 199k"), 1)
        self.assertLess(len(c["fault"]), 300)

    def test_it_is_shorter_than_the_anomaly_and_keeps_the_patchable_span(self):
        import json
        r = run("(def f [x] (add x 1))\n(f 1)")
        self.assertLess(len(json.dumps(compact(r))), len(json.dumps(r)) / 3)
        start, end = r["anomaly"]["span"]
        self.assertIn(f"[{start},{end})", compact(r)["fault"])

    def test_a_failed_example_is_one_line_with_its_fix(self):
        r = tool_check({"source": "(def f [x] (merge x 2))\n(example (f 1) 4)\n(example (f 2) 4)\n(f 0)"})
        c = compact(r)
        self.assertEqual((c["passed"], c["total"]), (1, 2))
        self.assertEqual(len(c["faults"]), 1)
        self.assertIn("expected 4, got 3", c["faults"][0])
        self.assertIn("the literal 2 should be 3", c["faults"][0])

    def test_success_is_untouched(self):
        r = run("(merge 1 2)")
        self.assertIs(compact(r), r)

    def test_a_long_excerpt_is_clipped(self):
        a = {"kind": "x", "excerpt": "(" + "a " * 100 + ")", "line": 1, "col": 1, "repair_hint": "h"}
        self.assertLess(len(brief(a)), 100)


class Needed(unittest.TestCase):
    """Q141: a step trap says how many steps the run needs."""

    def test_a_program_over_budget_is_measured(self):
        r = run("(fold merge 0 (range 1 60000))")
        d = r["anomaly"]["detail"]
        self.assertGreater(d["needed"], 200000)
        self.assertLess(d["needed"], 800000)
        self.assertIn("x the budget)", compact(r)["fault"])

    def test_a_runaway_is_named_as_one(self):
        r = run("(def spin [n] (spin (merge n 1)))\n(spin 0)")
        self.assertIsNone(r["anomaly"]["detail"]["needed"])
        self.assertIn("non-terminating, or far too costly", compact(r)["fault"])

    def test_a_program_that_touches_the_world_is_not_run_twice(self):
        import os, tempfile
        path = os.path.join(tempfile.mkdtemp(), "count.txt")
        src = ('(boundary "fs-write fs-read" (seq (fs-write "%s" (text-cat (fs-read "%s") "x")) '
               '(fold merge 0 (range 1 60000))))' % (path, path))
        with open(path, "w") as fp:
            fp.write("")
        r = run(src, allow=["fs-write", "fs-read"])
        self.assertEqual(r["anomaly"]["kind"], "step-limit-exceeded")
        self.assertNotIn("needed", r["anomaly"]["detail"])
        with open(path) as fp:
            self.assertEqual(fp.read(), "x")          # written once, not twice

    def test_probe_zero_turns_it_off(self):
        r = run("(fold merge 0 (range 1 60000))", probe=0)
        self.assertNotIn("needed", r["anomaly"]["detail"])


if __name__ == "__main__":
    unittest.main()
