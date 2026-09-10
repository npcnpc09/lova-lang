"""Q86 -- a boundary is a region: `def` forms may live inside it.

A boundary is lexical, which is what lets the compiler refuse an
undeclared effect before the program runs.  Until M26 that meant an
effectful helper had to be a `let`-bound lambda, because `def` was a
top-level form; three of the twelve programs were rewritten around it.
Now `(boundary "kind" (def ...) ... body)` binds the helpers inside the
boundary, so they carry the declared effect, and the region ends where
the boundary does.
"""

from __future__ import annotations

import unittest

from core import surface2
from core.compiler import CompileError, compile as lova_compile
from core.mcp_server import tool_execute
from core.surface import parse, parse_with_prelude
from core.tokens import EXTERNAL_BOUNDARY, LET, encode, decode


class Region(unittest.TestCase):

    SRC = ('(boundary "clock" (def now [] (clock)) '
           '(def later [n] (merge (clock) n)) (if (ge (later 1) now) 1 0))')

    def test_a_def_inside_the_boundary_carries_the_effect(self):
        r = tool_execute({"source": self.SRC, "allow": ["clock"]})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["value_int"], 1)

    def test_the_shape_is_a_boundary_around_a_let_chain(self):
        tree = parse(self.SRC)
        self.assertEqual(tree.op, EXTERNAL_BOUNDARY)
        self.assertEqual(tree.args[1].op, LET)            # now
        self.assertEqual(tree.args[1].args[2].op, LET)    # later
        self.assertEqual(decode(encode(tree)), tree)
        self.assertEqual(surface2.parse(surface2.render(tree)), tree)

    def test_a_def_outside_is_still_refused_with_the_new_hint(self):
        src = '(def secret [n] (inc (mod (clock) n)))(boundary "clock" (secret 10))'
        with self.assertRaises(CompileError) as ctx:
            lova_compile(parse_with_prelude(src))
        a = ctx.exception.anomaly
        self.assertEqual(a["kind"], "capability-denied")
        self.assertIn("(def ...)", a["repair_hint"])

    def test_the_host_must_still_grant_it(self):
        r = tool_execute({"source": self.SRC})
        self.assertFalse(r["ok"])
        self.assertEqual(r["anomaly"]["kind"], "capability-denied")

    def test_the_region_ends_with_the_boundary(self):
        # A helper defined inside is not visible after it.
        r = tool_execute({"source": '(merge (boundary "clock" (def now [] (clock)) 1) now)',
                          "allow": ["clock"]})
        self.assertFalse(r["ok"])
        self.assertEqual(r["anomaly"]["kind"], "unbound-ref")

    def test_a_boundary_without_defs_is_unchanged(self):
        r = tool_execute({"source": '(boundary "clock" (if (clock) 1 1))', "allow": ["clock"]})
        self.assertTrue(r["ok"])
        self.assertEqual(r["value_int"], 1)


if __name__ == "__main__":
    unittest.main()
