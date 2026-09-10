"""M24 -- a fault says where, and the fix is a patch of that span.

Every node parsed from text carries (start, end) offsets; a compile
error or a run-time trap reports the innermost such span -- a fault
inside a library function reports the call that reached it -- and
`lova_patch` replaces exactly that text.  The loop an AI runs is
execute, patch, execute; a fix costs the size of the fix.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from core.cli import main
from core.compiler import CompileError, compile as lova_compile
from core.conservation import BudgetTrap, DomainTrap
from core.mcp_server import tool_execute, tool_patch
from core.runtime import Runtime, evaluate
from core.surface import line_col, parse, parse_with_prelude, span_of


def _text(src, span):
    return src[span[0]:span[1]]


class Spans(unittest.TestCase):

    SRC = "(def f [n] (merge n 1))\n(merge (f 2) (div 10 (sub 3 3)))"

    def test_every_node_from_text_knows_its_text(self):
        tree = parse(self.SRC)
        self.assertEqual(_text(self.SRC, span_of(tree)), "(def f [n] (merge n 1))")
        body = tree.args[2]
        self.assertEqual(_text(self.SRC, span_of(body)), "(merge (f 2) (div 10 (sub 3 3)))")
        self.assertEqual(_text(self.SRC, span_of(body.args[1])), "(div 10 (sub 3 3))")
        self.assertEqual(_text(self.SRC, span_of(body.args[0])), "(f 2)")
        self.assertEqual(_text(self.SRC, span_of(body.args[1].args[0])), "10")

    def test_prelude_nodes_have_no_span_of_the_program(self):
        tree = parse_with_prelude("(merge 1 2)")
        # The outermost lets are the prelude's copies: no span.
        self.assertIsNone(span_of(tree))
        node = tree
        while node.op != 3:                       # walk to the merge
            node = node.args[2]
        self.assertEqual(span_of(node), (0, 11))

    def test_line_and_column(self):
        self.assertEqual(line_col(self.SRC, 0), (1, 1))
        self.assertEqual(line_col(self.SRC, 24), (2, 1))
        self.assertEqual(line_col(self.SRC, 37), (2, 14))


class FaultsSayWhere(unittest.TestCase):

    def test_a_compile_error_points_at_the_name(self):
        src = "(merge 1 (undefined-thing 2))"
        with self.assertRaises(CompileError) as ctx:
            lova_compile(parse_with_prelude(src))
        self.assertEqual(_text(src, ctx.exception.anomaly["span"]), "undefined-thing")

    def test_a_run_time_trap_points_at_the_expression(self):
        src = Spans.SRC
        tree, _ = lova_compile(parse_with_prelude(src))
        with self.assertRaises(DomainTrap) as ctx:
            evaluate(tree, Runtime())
        self.assertEqual(_text(src, ctx.exception.anomaly["span"]), "(div 10 (sub 3 3))")

    def test_a_fault_inside_the_library_reports_the_call(self):
        src = "(merge 1 (nth (list 1 2) 9))"
        tree, _ = lova_compile(parse_with_prelude(src))
        with self.assertRaises(DomainTrap) as ctx:
            evaluate(tree, Runtime())
        self.assertEqual(_text(src, ctx.exception.anomaly["span"]), "(nth (list 1 2) 9)")

    def test_a_budget_trap_points_inside_the_users_function(self):
        src = "(def spin [n] (spin (inc n)))\n(merge 1 (budget 50 (spin 0)))"
        tree, _ = lova_compile(parse_with_prelude(src))
        with self.assertRaises(BudgetTrap) as ctx:
            evaluate(tree, Runtime())
        self.assertIn(_text(src, ctx.exception.anomaly["span"]), ("(inc n)", "(spin (inc n))", "n"))

    def test_the_cli_prints_where(self):
        fd, path = tempfile.mkstemp(suffix=".lova")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(Spans.SRC)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["run", path])
        finally:
            os.remove(path)
        self.assertNotEqual(code, 0)
        self.assertIn("at: 2:14  (div 10 (sub 3 3))", err.getvalue())


class Patch(unittest.TestCase):

    def test_execute_patch_execute(self):
        src = Spans.SRC
        first = tool_execute({"source": src})
        self.assertFalse(first["ok"])
        a = first["anomaly"]
        self.assertEqual(a["excerpt"], "(div 10 (sub 3 3))")
        self.assertEqual((a["line"], a["col"]), (2, 14))
        patched = tool_patch({"source": src, "span": a["span"], "replacement": "(div 10 2)"})
        self.assertTrue(patched["ok"])
        self.assertEqual(patched["replaced"], "(div 10 (sub 3 3))")
        second = tool_execute({"source": patched["source"]})
        self.assertTrue(second["ok"])
        self.assertEqual(second["value_int"], 8)

    def test_a_patch_that_does_not_compile_says_so_and_keeps_the_text(self):
        src = "(merge 1 2)"
        r = tool_patch({"source": src, "span": [0, 11], "replacement": "(merge 1"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["source"], "(merge 1")
        self.assertEqual(r["stage"], "compile")

    def test_a_span_outside_the_source_is_refused(self):
        r = tool_patch({"source": "(merge 1 2)", "span": [5, 99], "replacement": "x"})
        self.assertFalse(r["ok"])
        self.assertIn("outside", r["anomaly"]["message"])

    def test_placeholders_keep_spans_honest(self):
        # Spans are offsets into the source after placeholders are filled.
        src = "(div {n} (sub 1 1))"
        r = tool_execute({"source": src, "args": ["12345"]})
        self.assertEqual(r["anomaly"]["excerpt"], "(div 12345 (sub 1 1))")


if __name__ == "__main__":
    unittest.main()
