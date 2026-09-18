"""Questions about a program, answered from its tree (2026-09-18).

Exp 28's sessions read the whole program on six of eight tasks, once
only to find a string that occurs once.  `core/query.py` answers what
they kept in their heads: the defs and their spans, one def's text,
what is bound at a point, who calls whom -- and a patch can be
addressed by def and text.
"""

from __future__ import annotations

import unittest

from core.query import callees, callers, def_text, defs, find_in_def, scope_at

NL = chr(10)
SRC = ("(def clamp [lo hi x] (if (lt x lo) lo (if (gt x hi) hi x)))" + NL +
       "(def score [xs] (fold (lambda a (lambda x (merge a (clamp 0 10 a)))) 0 xs))" + NL +
       "(def mean [xs] (let n (len xs) (div (score xs) n)))" + NL +
       "(example (score (list 3 20 -5)) 13)" + NL +
       "(mean (list 1 2 3))")


class Query(unittest.TestCase):

    def test_defs_with_spans_and_parameters(self):
        d = defs(SRC)
        self.assertEqual([x["name"] for x in d], ["clamp", "score", "mean"])
        self.assertEqual(d[0]["params"], ["lo", "hi", "x"])
        self.assertEqual(SRC[slice(*d[1]["span"])][:11], "(def score ")
        self.assertEqual((d[2]["line"], d[2]["col"]), (3, 1))

    def test_one_def_by_name(self):
        d = def_text(SRC, "mean")
        self.assertTrue(d["text"].startswith("(def mean [xs]"))
        self.assertIsNone(def_text(SRC, "nope"))

    def test_callers_and_callees(self):
        self.assertEqual(callers(SRC, "clamp"), ["score"])
        self.assertEqual(callers(SRC, "score"), ["mean"])
        self.assertEqual(callees(SRC, "mean"), ["score"])
        self.assertEqual(callees(SRC, "clamp"), [])

    def test_scope_at_a_point(self):
        at = SRC.index("(merge a (clamp") + 8
        s = scope_at(SRC, at)
        self.assertEqual(s["defs"], ["clamp", "score", "mean"])
        self.assertEqual([b["name"] for b in s["local"]], ["xs", "a", "x"])
        self.assertEqual(s["at"]["excerpt"], "(merge a (clamp 0 10 a))")
        inner = scope_at(SRC, SRC.index("(div (score") + 1)["local"]
        self.assertEqual([(b["name"], b["by"]) for b in inner], [("xs", "parameter"), ("n", "let")])

    def test_find_in_def_needs_one_occurrence_in_that_def(self):
        f = find_in_def(SRC, "score", "(clamp 0 10 a)")
        self.assertTrue(f["ok"])
        self.assertEqual(SRC[slice(*f["span"])], "(clamp 0 10 a)")
        self.assertFalse(find_in_def(SRC, "clamp", "x")["ok"])
        self.assertIn("occurs 4 times", find_in_def(SRC, "clamp", "x")["message"])
        self.assertIn("no def named", find_in_def(SRC, "nope", "x")["message"])

    def test_patch_by_def_and_text(self):
        from core.mcp_server import tool_patch
        r = tool_patch({"source": SRC, "def": "score", "find": "(clamp 0 10 a)", "replacement": "(clamp 0 10 x)"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["replaced"], "(clamp 0 10 a)")
        self.assertIn("(clamp 0 10 x)", r["source"])
        r = tool_patch({"source": SRC, "def": "clamp", "find": "x", "replacement": "y"})
        self.assertFalse(r["ok"])

    def test_the_fault_line_says_how_many_examples_reach_the_def(self):
        from core.examples import check, summary
        results = check(SRC + NL + "(example (clamp 0 10 15) 10)")
        text = summary(results)
        self.assertIn("def score is reached by 1 of 2 examples", text)
        self.assertEqual(results[0]["reaches"], ["clamp", "score"])
        self.assertEqual(results[1]["reaches"], ["clamp"])


if __name__ == "__main__":
    unittest.main()
