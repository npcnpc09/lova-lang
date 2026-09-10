"""M26 -- a program carries its examples.

`(example expr expected)` forms stand beside the defs.  They are not
part of the program: the run, `hash` and `explain` ignore them.
`core.examples.check` runs each as a conservation contract in the
program's own scope and reports a miss with expected, got, the
example's span and the sub-expression at fault when the probe finds
one.  `lova check` and the MCP tool `lova_check` are the two doors.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from core.cli import main
from core.examples import check, examples_of, summary
from core.mcp_server import tool_check, tool_execute
from core.surface import parse
from core.tokens import LET

SRC = """(def fact [n] (if n (mul n (fact (sub n 1))) 1))
(example (fact 5) 120)
(example (fact 0) 1)
(example (fact 3) 7)
(fact 4)"""


class Examples(unittest.TestCase):

    def test_examples_are_read_and_kept_out_of_the_program(self):
        tree = parse(SRC)
        self.assertEqual(tree.op, LET)                       # the def, then the body
        self.assertEqual(len(tree.examples), 3)
        self.assertEqual(SRC[slice(*tree.examples[0]["span"])], "(example (fact 5) 120)")
        self.assertEqual(tool_execute({"source": SRC})["value_int"], 24)
        self.assertEqual(len(examples_of(SRC)), 3)

    def test_check_runs_each_as_a_contract(self):
        results = check(SRC)
        self.assertEqual([r["passed"] for r in results], [True, True, False])
        miss = results[2]
        self.assertEqual((miss["expected"], miss["got"]), (7, 6))
        self.assertEqual(miss["anomaly"]["kind"], "conservation-violated")
        self.assertEqual((miss["line"], miss["col"]), (4, 1))
        self.assertIn("2/3 examples pass", summary(results))

    def test_an_example_may_use_any_def_and_stand_anywhere(self):
        src = ("(example (twice 4) 8)\n"
               "(def twice [n] (mul 2 n))\n"
               "(example (twice (twice 1)) 4)\n"
               "(twice 21)")
        self.assertTrue(all(r["passed"] for r in check(src)))
        self.assertEqual(tool_execute({"source": src})["value_int"], 42)

    def test_a_faulting_example_reports_its_anomaly(self):
        src = "(def f [n] (div 1 n))\n(example (f 0) 1)\n(f 2)"
        r = check(src)[0]
        self.assertFalse(r["passed"])
        self.assertEqual(r["anomaly"]["kind"], "domain-error")

    def test_a_program_without_examples_has_none(self):
        self.assertEqual(check("(merge 1 2)"), [])

    def test_the_mcp_tool(self):
        r = tool_check({"source": SRC})
        self.assertFalse(r["ok"])
        self.assertEqual((r["passed"], r["total"]), (2, 3))
        self.assertEqual(r["examples"][2]["excerpt"], "(example (fact 3) 7)")

    def test_the_cli(self):
        fd, path = tempfile.mkstemp(suffix=".lova")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(SRC.replace("(fact 4)", "(fact {n})"))
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["check", path, "4"])
        finally:
            os.remove(path)
        self.assertEqual(code, 2)
        self.assertIn("FAIL  4:1  (example (fact 3) 7)  -- expected 7, got 6", out.getvalue())
        self.assertIn("2/3 examples pass", out.getvalue())


if __name__ == "__main__":
    unittest.main()
