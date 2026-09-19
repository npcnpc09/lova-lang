"""What a fault says, and whether it says it where the edit goes.

Every test here comes from a mistake actually made while writing
`lib/` on 2026-09-15 (journal Exp 25).  The language was not wrong in
any of them; the message was, and a message that points three hundred
characters away from the fault is a round trip an author pays for.

  F7  a missing closing paren on a nested curried lambda, reported as
      `lambda: expects 2 args, got 4` at the *next* definition.  Four
      times in one afternoon.
  --  an example that states a list, reported as `cons produces List,
      slot expects Int` with nothing about examples in it.  Twice.
  --  `(nil? r)` where `r` is a record, reported as "only `nil`, `cons`
      and `tail` produce list values", which is true and does not say
      that a record is a map.
  --  `(def dist ...)`, silently dead, because `dist` is the short
      spelling of `surprise`.  Two libraries had one.
"""

from __future__ import annotations

import unittest

from core.compiler import compile
from core.runtime import Runtime, evaluate
from core.surface import ParseError, parse, parse_with_prelude

NL = chr(10)

# The shape that cost four round trips: the inner `fold`'s lambda is one
# paren short, so `(def ring ...)` swallows the definition after it.
UNCLOSED = (
    "(def ring [w p seen frontier]" + NL +
    "  (fold (lambda acc (lambda k" + NL +
    "          (fold (lambda a (lambda i" + NL +
    "                  (let tx (merge 1 i)" + NL +
    "                    (if tx (cons tx a) a))))" + NL +    # one short: lambda acc
    "                acc (range 0 4))))" + NL +
    "        (nil) frontier)" + NL +
    NL +
    "(def other [x] (merge x 1))" + NL +
    "(other 7)" + NL
)


class Parens(unittest.TestCase):

    def test_an_unclosed_form_is_named_by_its_first_line(self):
        with self.assertRaises(ParseError) as caught:
            parse(UNCLOSED)
        exc = caught.exception
        detail = exc.anomaly["detail"]
        self.assertIn("unclosed", detail)
        self.assertEqual(detail["unclosed"]["line"], 1)
        self.assertEqual(detail["unclosed"]["missing"], 1)
        self.assertIn("(def ring", detail["unclosed"]["excerpt"])
        # and the span, which is what the CLI prints and what a patch
        # would be applied to, covers that line rather than one bracket
        start, end = exc.anomaly["span"]
        self.assertEqual(UNCLOSED[start:end], "(def ring [w p seen frontier]")

    def test_the_original_message_is_kept(self):
        """It is true; it is only in the wrong place.  Which message the
        parser reaches first depends on where the missing paren lands --
        an arity, a closing paren, the end of the source -- so the test
        asks only that whatever it said survives, with the hint after
        it."""
        with self.assertRaises(ParseError) as caught:
            parse(UNCLOSED)
        message = str(caught.exception)
        self.assertIn("ring", message)
        self.assertIn(";", message)
        self.assertIn("never close", message)

    def test_it_works_with_the_prelude_in_scope(self):
        with self.assertRaises(ParseError) as caught:
            parse_with_prelude(UNCLOSED)
        self.assertIn("never close", str(caught.exception))
        self.assertEqual(caught.exception.anomaly["detail"]["unclosed"]["line"], 1)

    def test_a_stray_closing_paren_is_named_from_the_other_side(self):
        with self.assertRaises(ParseError) as caught:
            parse("(def f [x] (merge x 1)))" + NL + "(f 3)" + NL)
        detail = caught.exception.anomaly["detail"]
        self.assertEqual(detail["unclosed"]["kind"], "extra-paren")
        self.assertIn("nothing open to close", str(caught.exception))

    def test_a_balanced_program_is_left_alone(self):
        """The hint must not appear where it does not belong: an ordinary
        arity mistake in a balanced program stays an ordinary arity
        mistake."""
        with self.assertRaises(ParseError) as caught:
            parse("(merge 1 2 3 4)" + NL)
        self.assertNotIn("never close", str(caught.exception))
        self.assertNotIn("unclosed", caught.exception.anomaly["detail"])


class Examples(unittest.TestCase):

    def test_an_example_may_state_a_list_a_text_or_a_record(self):
        from core.examples import check
        results = check("(def rev [xs] (reverse xs))" + NL +
                        "(example (rev (list 0 1 2 3)) (list 3 2 1 0))" + NL +
                        '(example (text-cat "a" "bc") "abc")' + NL +
                        "(example (put (rec a 0) a 1) (rec a 1))" + NL +
                        "(example (rev (list 1 2)) (list 1 2))" + NL +
                        "(rev (list 1))")
        self.assertEqual([r["passed"] for r in results], [True, True, True, False])
        self.assertEqual((results[3]["expected"], results[3]["got"]), ("(1 2)", "(2 1)"))

    def _old_refusal(self):
        for stated in ("(list 3 2 1 0)", '"abc"', "(rec a 1)"):
            with self.assertRaises(ValueError) as caught:
                parse("(def f [] 1)" + NL + f"(example (f) {stated})" + NL + "(f)" + NL)
            self.assertIn("example", str(caught.exception))
            self.assertIn("has to be a number", str(caught.exception))

    def test_an_example_that_states_a_number_is_fine(self):
        for stated in ("120", "(merge 100 20)", "(len (list 1 2))"):
            tree = parse_with_prelude(
                "(def f [] 120)" + NL + f"(example f {stated})" + NL + "f" + NL)
            self.assertEqual(evaluate(compile(tree)[0], Runtime(max_steps=100_000)), 120)


class Records(unittest.TestCase):

    def test_nil_on_a_record_says_a_record_is_a_map(self):
        """The mistake `lib/ray.lova` made: a function that returns either a
        record or `(nil)`, and a caller that tests it with `nil?`."""
        tree = parse_with_prelude(
            "(def f [n] (if n (rec a 1) (nil)))" + NL + "(nil? (f 1))" + NL)
        with self.assertRaises(Exception) as caught:
            evaluate(compile(tree, type_check=False)[0], Runtime(max_steps=10_000))
        anomaly = caught.exception.anomaly
        repair = anomaly.get("repair") or anomaly.get("repair_hint") or ""
        self.assertIn("record", repair)
        self.assertIn("(get r v)", repair)


class OperatorNames(unittest.TestCase):

    def test_a_def_cannot_take_an_operator_name(self):
        """`(def dist [a b] 99)` parsed, and `(dist 1 2)` went to `surprise`:
        a definition nothing could call, and a wrong value with no
        diagnostic."""
        for name in ("dist", "if", "min", "select", "keep", "merge"):
            with self.assertRaises(ValueError) as caught:
                parse(f"(def {name} [a b] 99)" + NL + f"({name} 1 2)" + NL)
            self.assertIn(name, str(caught.exception))
            self.assertIn("operator", str(caught.exception))

    def test_a_parameter_still_may(self):
        """The prelude's `(def split [text sep] ...)` reads `text` as a value
        and never calls it; taking that away would cost more than the
        mistake it prevents."""
        tree = parse_with_prelude("(def f [text] (len text))" + NL + '(f "abcd")' + NL)
        self.assertEqual(evaluate(compile(tree)[0], Runtime(max_steps=10_000)), 4)


if __name__ == "__main__":
    unittest.main()


class Feedback(unittest.TestCase):
    """The audit of 2026-09-18, against the yardstick's second number
    (context spent per failure).  Measured on the first program written
    that morning: an unbound-ref anomaly was 660 characters, 400 of them
    the prelude's forty names, and the miss itself -- `add` for `merge`
    -- got `Nearest: all, odd`."""

    def _anomaly(self, src):
        from core.mcp_server import tool_execute
        r = tool_execute({"source": src})
        self.assertFalse(r["ok"])
        return r["anomaly"]

    def test_a_synonym_from_another_language_is_translated(self):
        a = self._anomaly("(add 1 2)")
        self.assertEqual(a["kind"], "unbound-ref")
        self.assertIn("in LOVA that is `(merge a b)`", a["repair_hint"])
        a = self._anomaly('(length (list 1 2))')
        self.assertIn("`(len xs)`", a["repair_hint"])

    def test_the_bound_list_is_the_programs_own_names(self):
        a = self._anomaly("(def total [xs] (fold (lambda a (lambda b (merge a b))) 0 xs))" + NL +
                          "(totl (list 1 2 3))")
        self.assertEqual(a["detail"]["bound"], ["total"])
        self.assertIn("Nearest: total", a["repair_hint"])

    def test_a_near_prelude_name_is_still_offered(self):
        a = self._anomaly('(map parse-in (list "1"))')
        self.assertIn("parse-int", a["detail"]["bound"])

    def test_raw_alternatives_are_not_printed(self):
        import io
        from contextlib import redirect_stderr
        from core.cli import build, report_error
        from core.runtime import Runtime, evaluate
        src = "(div 1 0)"
        tree, _ = build(src)
        err = io.StringIO()
        with redirect_stderr(err):
            try:
                evaluate(tree, Runtime())
            except Exception as exc:          # noqa: BLE001 -- the trap under test
                report_error(exc, src)
        text = err.getvalue()
        self.assertIn("domain-error", text)
        self.assertNotIn("valid_alternatives", text)

    def test_the_depth_hint_names_the_loop_forms(self):
        # M32: the accumulator form runs now; the one that keeps a frame is
        # the one that meets the ceiling, and the hint says why.
        a = self._anomaly("(def up [n] (if (gt n 20000) 0 (merge n (up (merge n 1)))))" + NL +
                          "(up 0)")
        self.assertEqual(a["kind"], "recursion-depth-exceeded")
        self.assertIn("tail position costs no frame", a["repair_hint"])
        self.assertIn("`fold`", a["repair_hint"])
        # and the path per frame is elided, as the CLI has done since M23
        self.assertLess(len(a["position_path"]), 12)


class Uses(unittest.TestCase):
    """Q127: a program with `(use ...)` is parsed expanded, so its spans
    index a text the author never saw.  The map gives the author's own
    line and column, or the library's file and line."""

    SRC = '(use "assoc")' + NL + '(seq 1' + NL + '  (div 7 0))' + NL

    def test_the_expansion_maps_own_text_and_library_text(self):
        from core.surface import expansion
        exp = expansion(self.SRC)
        self.assertFalse(exp.plain)
        own = exp.text.index("(div 7 0)")
        self.assertEqual(exp.where(own), (None, 3, 3))
        self.assertEqual(exp.to_original(own), self.SRC.index("(div 7 0)"))
        origin, line, col = exp.where(0)
        self.assertEqual(origin, "lib/assoc.lova")
        self.assertEqual((line, col), (1, 1))
        self.assertIsNone(exp.to_original(0))
        self.assertTrue(expansion("(merge 1 2)").plain)

    def test_the_cli_reports_the_authors_line(self):
        import io as _io
        import sys as _sys
        from contextlib import redirect_stderr
        from core.cli import build, report_error
        tree, _ = build(self.SRC)
        err = _io.StringIO()
        try:
            evaluate(tree, Runtime(max_steps=10_000))
            self.fail("did not trap")
        except Exception as exc:                        # noqa: BLE001
            with redirect_stderr(err):
                report_error(exc, self.SRC)
        self.assertIn("at: 3:3  (div 7 0)", err.getvalue())

    def test_the_server_names_the_library_when_the_span_is_there(self):
        from core.mcp_server import _failure
        from core.surface import expansion
        exp = expansion(self.SRC)
        class Fake(Exception):
            pass
        exc = Fake("x")
        exc.anomaly = {"kind": "domain-error", "span": (0, 4)}
        out = _failure("run", exc, self.SRC)
        self.assertEqual(out["anomaly"]["file"], "lib/assoc.lova")
        self.assertEqual(out["anomaly"]["excerpt"], exp.text[0:4])
        own = exp.text.index("(div 7 0)")
        exc.anomaly = {"kind": "domain-error", "span": (own, own + 9)}
        out = _failure("run", exc, self.SRC)
        self.assertNotIn("file", out["anomaly"])
        self.assertEqual((out["anomaly"]["line"], out["anomaly"]["col"]), (3, 3))

    def test_a_patch_by_expanded_span_lands_in_the_source(self):
        from core.mcp_server import tool_patch
        from core.surface import expansion
        exp = expansion(self.SRC)
        own = exp.text.index("(div 7 0)")
        out = tool_patch({"source": self.SRC, "span": [own, own + 9], "replacement": "(div 7 1)"})
        self.assertTrue(out.get("ok"), out)
        self.assertIn("(div 7 1)", out["source"])
        self.assertTrue(out["source"].startswith('(use "assoc")'))
        out = tool_patch({"source": self.SRC, "span": [0, 4], "replacement": "x"})
        self.assertFalse(out.get("ok"))
        self.assertIn("lib/assoc.lova", out["anomaly"]["message"])

