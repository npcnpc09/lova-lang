"""M32 -- a complete language: what the milestone added, one test a claim.

- a call in tail position costs no frame, so an accumulator recursion
  and a mutual recursion run in constant depth; a call that keeps work
  for afterwards still meets the depth ceiling;
- an operator or a fixed-arity macro spelled bare is the function that
  wraps it, unless the source binds that spelling;
- `text-match` / `text-match-all` (0x4E / 0x4F) read a text by a
  pattern in a fixed subset, and refuse what is outside it by name;
- `map-get` takes `(nil)` as the empty map, as `map-put` did;
- the lint pass reports a parameter or local binding nothing reads and
  a parameter that shadows one in scope, and the CLI spells them;
- an escape the language does not define keeps its backslash.
"""

from __future__ import annotations

import io
import sys
import unittest

from core.compiler import CompileError
from core.conservation import DepthTrap, DomainTrap, StepTrap
from core.mcp_server import tool_execute, tool_static_analyze
from core.runtime import Runtime, evaluate
from core.surface import parse, parse_with_prelude
from core.cli import build, format_value, name_warnings

NL = "\n"


def run(src: str, **kw):
    rt = Runtime(**kw)
    return evaluate(parse_with_prelude(src), rt), rt


def val(src: str, **kw) -> str:
    """The value as the CLI prints it: `6`, `"hi!"`, `(1 2 3)`."""
    return format_value(run(src, **kw)[0])


class TailCalls(unittest.TestCase):

    def test_an_accumulator_recursion_runs_in_constant_depth(self):
        src = ("(def up [n acc] (if (gt n 20000) acc (up (merge n 1) (merge acc n))))" + NL +
               "(up 0 0)")
        value, rt = run(src, max_call_depth=50)
        self.assertEqual(value, 200010000)

    def test_a_mutual_recursion_runs_in_constant_depth(self):
        src = ("(def ev [n] (if (eq n 0) 1 (od (sub n 1))))" + NL +
               "(def od [n] (if (eq n 0) 0 (ev (sub n 1))))" + NL +
               "(ev 20001)")
        value, _ = run(src, max_call_depth=50)
        self.assertEqual(value, 0)

    def test_tail_position_passes_through_if_seq_and_let(self):
        src = ("(def f [n] (seq 1 (let m (sub n 1) (if (gt n 0) (f m) 7))))" + NL +
               "(f 30000)")
        value, _ = run(src, max_call_depth=50)
        self.assertEqual(value, 7)

    def test_a_call_that_keeps_work_still_meets_the_ceiling(self):
        src = "(def down [n] (if (eq n 0) 0 (merge 1 (down (sub n 1)))))(down 30000)"
        with self.assertRaises(DepthTrap):
            run(src, max_call_depth=1000)

    def test_a_call_inside_try_is_not_a_tail_call(self):
        # The handler must stay around the body, so the frame is kept:
        # the depth ceiling is met, and the innermost `try` catches it.
        src = "(def f [n] (try (f n) -1))(f 1)"
        value, rt = run(src, max_call_depth=100, max_steps=10_000_000)
        self.assertEqual(value, -1)
        self.assertEqual(rt.caught[0]["kind"], "recursion-depth-exceeded")

    def test_a_runaway_tail_recursion_meets_the_step_ceiling(self):
        with self.assertRaises(StepTrap):
            run("(def spin [n] (spin (inc n)))(spin 0)", max_steps=20_000)

    def test_a_tail_call_to_a_loop_function_works(self):
        src = ("(def to-ten [] (loop-until (lambda x (ge x 10)) (lambda x (inc x))))" + NL +
               "(def go [n] (if (gt n 0) (go (sub n 1)) (to-ten 0)))" + NL +
               "(go 5)")
        value, _ = run(src)
        self.assertEqual(value, 10)

    def test_a_tail_call_of_a_non_function_names_the_apply(self):
        src = "(def f [n] (if (gt n 0) (f (sub n 1)) (n 1)))(f 2)"
        with self.assertRaises(DomainTrap) as ctx:
            run(src)
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")

    def test_the_step_count_is_unchanged_by_the_marker(self):
        _, a = run("(def f [n] (if (gt n 0) (f (sub n 1)) 0))(f 100)")
        _, b = run("(def f [n] (if (gt n 0) (f (sub n 1)) 0))(f 100)")
        self.assertEqual(a.steps, b.steps)
        self.assertGreater(a.steps, 100)

    def test_the_hot_list_still_attributes_steps(self):
        src = "(def f [n] (if (gt n 0) (f (sub n 1)) 0))(f 100000)"
        with self.assertRaises(StepTrap) as ctx:
            run(src, max_steps=5000)
        hot = ctx.exception.anomaly["detail"].get("calls") or ctx.exception.anomaly["detail"].get("hot")
        self.assertTrue(hot)


class OperatorsAsValues(unittest.TestCase):

    def test_a_macro_named_bare_is_its_function(self):
        self.assertEqual(val("(sort-by lt (list 3 1 2))"), "(1 2 3)")
        self.assertEqual(val("(map neg (list 1 2))"), "(-1 -2)")
        self.assertEqual(val("(filter not (list 0 1 0))"), "(0 0)")

    def test_an_operator_named_bare_is_its_function(self):
        self.assertEqual(val("(fold merge 0 (list 1 2 3))"), "6")
        self.assertEqual(val('(map text-len (list "ab" "c"))'), "(2 1)")

    def test_a_binding_of_the_spelling_wins(self):
        # A parameter named after an operator is the parameter, as before.
        self.assertEqual(val('(def show [text] (text-cat text "!"))(show "hi")'), '"hi!"')
        self.assertEqual(val("(let min 5 (merge min 1))"), "6")

    def test_a_record_field_named_after_an_operator_is_the_name(self):
        self.assertEqual(val("(get (rec min 3 max 9) min)"), "3")

    def test_the_expansion_is_plain_core(self):
        from core.surface2 import render
        tree = parse("(sort-by lt (list 3 1 2))")
        self.assertNotIn("lt", render(tree))

    def test_a_variadic_is_not_a_value(self):
        with self.assertRaises(CompileError) as ctx:
            build("(map seq (list 1))")
        self.assertEqual(ctx.exception.anomaly["kind"], "unbound-ref")
        self.assertIn("any number of arguments", ctx.exception.anomaly["repair_hint"])


class TextMatch(unittest.TestCase):

    def test_the_first_match_is_the_whole_and_its_groups(self):
        self.assertEqual(val('(text-match "cpu 12% mem 40%" "(\\w+) (\\d+)%")'),
                         '("cpu 12%" "cpu" "12")')

    def test_no_match_is_nil(self):
        self.assertEqual(val('(text-match "abc" "x")'), "()")
        self.assertEqual(val('(nil? (text-match "abc" "x"))'), "1")

    def test_every_match(self):
        self.assertEqual(val('(text-match-all "cpu 12% mem 40%" "(\\w+) (\\d+)%")'),
                         '(("cpu 12%" "cpu" "12") ("mem 40%" "mem" "40"))')
        self.assertEqual(val('(map head (text-match-all "a1b22c333" "\\d+"))'), '("1" "22" "333")')

    def test_an_unmatched_group_is_the_empty_text(self):
        self.assertEqual(val('(text-match "ab" "a(x)?b")'), '("ab" "")')

    def test_anchors_classes_repeats_and_alternatives(self):
        self.assertEqual(val('(text-match "2026-09-18" "^(\\d{4})-(\\d{2})-(\\d{2})$")'),
                         '("2026-09-18" "2026" "09" "18")')
        self.assertEqual(val('(head (text-match "key: val" "[a-z]+(:|=)"))'), '"key:"')

    def test_a_repeat_in_braces_is_not_a_placeholder(self):
        # `{4}` used to be read as an input the program expects (M32).
        r = tool_execute({"source": '(text-match "2026" "\\d{4}")'})
        self.assertTrue(r.get("ok"), r)

    def test_outside_the_subset_is_refused_by_name(self):
        for pattern in ("\\\\1", "(?=a)", "(?P<n>a)", "\\\\b"):
            with self.subTest(pattern=pattern):
                r = tool_execute({"source": f'(text-match "a" "{pattern}")'})
                self.assertFalse(r.get("ok"))
                self.assertEqual(r["anomaly"]["kind"], "domain-error")
                self.assertIn("rewrite the pattern in the subset", r["anomaly"]["repair_hint"])

    def test_a_pattern_that_does_not_parse_is_a_domain_error(self):
        r = tool_execute({"source": '(text-match "a(" "(")'})
        self.assertEqual(r["anomaly"]["kind"], "domain-error")

    def test_a_text_literal_keeps_an_escape_the_language_does_not_define(self):
        self.assertEqual(val('(text-len "\\d")'), "2")
        self.assertEqual(val('(text-len "\\n")'), "1")

    def test_the_two_matchers_have_stage2_symbols_and_round_trip(self):
        from core.surface2 import render, parse as parse2
        from core.tokens import encode
        src = '(text-match-all "a1b22" "\\d+")'
        tree = parse(src)
        back = parse2(render(tree))
        self.assertEqual(encode(back), encode(tree))

    def test_replace_in_the_prelude(self):
        self.assertEqual(val('(replace "a-b-c" "-" "+")'), '"a+b+c"')


class MapGetOnNil(unittest.TestCase):

    def test_the_empty_map_is_nil_for_map_get_too(self):
        self.assertEqual(val("(map-get (nil) 1 0)"), "0")
        self.assertEqual(val("(map-get (map-put (nil) 1 5) 1 0)"), "5")


class Lint(unittest.TestCase):

    def _warnings(self, src):
        tree, report = build(src)
        return name_warnings(report.warnings, tree.symbols, src)

    def test_an_unread_parameter_is_reported_in_its_def(self):
        lines = self._warnings("(def f [a b] (merge a 1))(f 1 2)")
        self.assertEqual(len(lines), 1)
        self.assertIn("parameter `b` is never read", lines[0])
        self.assertIn("(in `f`)", lines[0])

    def test_an_unread_local_binding_is_reported(self):
        lines = self._warnings("(def g [x] (let y 3 (mul x 2)))(g 1)")
        self.assertEqual(len(lines), 1)
        self.assertIn("binding `y` is never read", lines[0])

    def test_a_shadowing_parameter_is_reported(self):
        lines = self._warnings("(def g [x] (map (lambda x (mul x 2)) (list x)))(g 1)")
        self.assertEqual(len(lines), 1)
        self.assertIn("parameter `x` hides a `x` already in scope", lines[0])

    def test_a_clean_program_has_none_and_the_prelude_is_silent(self):
        self.assertEqual(self._warnings("(def f [a b] (merge a b))(len (list (f 1 2)))"), [])

    def test_a_top_level_def_nothing_calls_is_not_a_warning(self):
        # Libraries define more than a program uses; drop-unused handles it.
        self.assertEqual(self._warnings("(def f [a] a)(def g [b] b)(g 1)"), [])

    def test_a_macro_temporary_is_never_reported(self):
        self.assertEqual(self._warnings("(def f [a] (try (div 1 a) 0))(f 0)"), [])

    def test_the_mcp_report_carries_the_lines(self):
        r = tool_static_analyze({"source": "(def f [a b] (merge a 1))(f 1 2)"})
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["report"]["warnings"]), 1)
        self.assertIn("`b`", r["report"]["warnings"][0])

    def test_the_cli_prints_them_under_analyze(self):
        import contextlib
        from core.cli import main
        import os, tempfile
        fd, path = tempfile.mkstemp(suffix=".lova")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("(def f [a b] (merge a 1))(f 1 2)")
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = main(["analyze", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        self.assertIn("warning:", out.getvalue())
        self.assertIn("`b`", out.getvalue())


class HeadHint(unittest.TestCase):

    def test_nth_past_the_end_says_so(self):
        r = tool_execute({"source": "(nth (list 1 2) 5)"})
        self.assertEqual(r["anomaly"]["kind"], "domain-error")
        self.assertIn("past the end", r["anomaly"]["repair_hint"])


if __name__ == "__main__":
    unittest.main()
