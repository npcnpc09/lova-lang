"""Exp 18 / 19 -- the agent-loop harness.

The harness is the instrument that measures the goal, so its two
comparisons (an integer answer, a text answer) and the feedback it
prints are pinned here.  The oracles are checked against the Python
references, which is what `dry-run` does.
"""

from __future__ import annotations

import unittest

from experiments import experiment_18_agent_loop as e18
from experiments import experiment_19_agent_loop_apps as e19


class Harness(unittest.TestCase):

    def test_python_references_pass_their_own_oracles(self):
        for task in e18.TASKS:
            self.assertTrue(e18.run_python(e18.REFERENCE_PY[task.id], task)["passed"], task.id)
        for task in e19.TASKS:
            self.assertTrue(e18.run_python(e19.REFERENCE_PY[task.id], task)["passed"], task.id)

    def test_a_lova_answer_is_compared_as_integer_or_text(self):
        t01 = e18.BY_ID["t01"]
        src = ("(def walk [cs d] (cond (lt d 0) 0 (nil? cs) (eq d 0) "
               "(walk (tail cs) (if (eq (head cs) 40) (inc d) (sub d 1)))))\n(walk {s} 0)")
        self.assertTrue(e18.run_lova(src, t01)["passed"])
        h08 = e19.BY_ID["h08"]
        wrong = '(text-cat "0 " (text-of (len (lines {text}))))'
        r = e18.run_lova(wrong, h08)
        self.assertFalse(r["passed"])
        self.assertEqual(r["failures"][0]["expected"], "0 3")
        self.assertIn("FAIL", e18.feedback_text("lova", r))

    def test_a_compile_fault_is_the_feedback(self):
        r = e18.run_lova("(map text-int (words {s}))", e18.BY_ID["t03"])
        a = r["failures"][0]["anomaly"]
        self.assertEqual((a["kind"], a["stage"], a["excerpt"]), ("unbound-ref", "compile", "text-int"))
        self.assertIn("(lambda x0 (text-int x0))", a["repair_hint"])

    def test_a_python_traceback_is_the_feedback(self):
        r = e18.run_python("def solve(s):\n    return 1 // 0", e18.BY_ID["t01"])
        self.assertIn("ZeroDivisionError", e18.feedback_text("python", r))


if __name__ == "__main__":
    unittest.main()


class QuotedArgument(unittest.TestCase):
    """Exp 19's first finding: a text that looks like a number."""

    def test_a_quoted_argument_is_a_text_whatever_it_holds(self):
        from core.cli import substitute
        self.assertEqual(substitute("(text-len {s})", ['s="7"']), '(text-len "7")')
        self.assertEqual(substitute("(merge {n} 1)", ["n=7"]), "(merge 7 1)")
        self.assertEqual(substitute("{s}", ['s=""']), '""')
        self.assertEqual(substitute("{s}", ["racecar"]), '"racecar"')

    def test_the_harness_passes_texts_quoted(self):
        h01 = e19.BY_ID["h01"]
        r = e18.run_lova("(text-len {s})", h01)          # wrong answer, but a text arrived
        self.assertNotIn("anomaly", r["failures"][0])

    def test_a_list_operator_given_an_integer_says_what_it_got(self):
        from core.mcp_server import tool_execute
        a = tool_execute({"source": "(text-len {s})", "args": ["s=7"]})["anomaly"]
        self.assertEqual(a["kind"], "type-violation")
        self.assertEqual(a["detail"]["got"], "an integer")
        self.assertIn("quote it", a["repair_hint"])


class Exp19Feedback(unittest.TestCase):
    """Exp 19, run 1: what three sessions read and could not use."""

    def test_a_parse_error_says_where(self):
        from core.mcp_server import tool_execute
        for src, line, col, excerpt in (
            ("(merge 1 2))", 1, 12, ")"),
            ("(def won [b] (merge 1 2)\n(won 3)", 2, 1, "("),
            ("(loop-until 1 2 3 4 5 6 7)", 1, 1, "(loop-until 1 2 3 4 5 6 7)"),
            ("(lt 1)", 1, 1, "(lt 1)"),
        ):
            a = tool_execute({"source": src})["anomaly"]
            self.assertEqual(a["kind"], "parse-error", src)
            self.assertEqual((a["line"], a["col"], a["excerpt"]), (line, col, excerpt), src)

    def test_a_parse_error_is_still_a_value_error(self):
        from core.surface import ParseError, parse
        with self.assertRaises(ValueError) as ctx:
            parse("(lt 1)")
        self.assertIsInstance(ctx.exception, ParseError)
        self.assertEqual(ctx.exception.anomaly["span"], (0, 6))

    def test_the_step_trap_does_not_claim_non_termination(self):
        from core.mcp_server import tool_execute
        a = tool_execute({"source": "(def f [n] (if n (merge 1 (f (sub n 1))) 0))\n(f 5000)",
                          "max_steps": 1000})["anomaly"]
        self.assertEqual(a["kind"], "step-limit-exceeded")
        self.assertIn("or the work is larger than the budget", a["repair_hint"])
        self.assertNotIn("does not terminate within", a["repair_hint"])

    def test_the_budget_is_at_parity_with_the_wall_clock(self):
        self.assertEqual(e18.BUDGET, 7_000_000)
        self.assertEqual(e18.PY_TIMEOUT, 10.0)
