"""Tests for M11 — what a language needs to be usable.

Four gaps, and what closed each:

- **no output** — `stdout` / `stdin` on the IO family's own reserved
  slots (0x35 / 0x36), the first operators that touch the world
- **no logic** — `not` / `and` / `or` / `eq` / `min` / `cond` and the
  rest as macros, zero token slots
- **no standard library** — `lib/prelude.lova`, written in LOVA, made
  free by the compiler's `drop-unused` pass
- **no way to run a file** — `core/cli.py`: run, repl, emit, analyze
"""

from __future__ import annotations

import io
import sys
import unittest

from core.cli import format_value, main as cli_main
from core.compiler import CompileError, compile
from core.observability import static_analyze
from core.runtime import NIL_VALUE, Runtime, evaluate, list_to_python
from core.surface import MACROS, parse, parse_with_prelude, load_prelude
from core.tokens import SIGNATURES, STDIN, STDOUT, TYPED_TOKENS


def run(src: str, rt: Runtime = None):
    return evaluate(parse(src), rt)


def run_with_prelude(src: str, rt: Runtime = None):
    node, report = compile(parse_with_prelude(src))
    return evaluate(node, rt or Runtime()), report


# --- IO ---------------------------------------------------------------------

class TestOutput(unittest.TestCase):

    def test_writes_an_integer_as_digits(self):
        rt = Runtime()
        self.assertEqual(run("(stdout 42)", rt), 2)   # two codepoints
        self.assertEqual(rt.written(), "42")

    def test_writes_a_list_as_text(self):
        rt = Runtime()
        run('(stdout "hello")', rt)
        self.assertEqual(rt.written(), "hello")

    def test_writes_nothing_for_the_empty_list(self):
        rt = Runtime()
        self.assertEqual(run('(stdout "")', rt), 0)
        self.assertEqual(rt.written(), "")

    def test_returns_the_number_of_codepoints(self):
        # An Int, so a write can sit anywhere an Int can.
        self.assertEqual(run('(merge (stdout "abc") 1)', Runtime()), 4)

    def test_a_function_cannot_be_written(self):
        with self.assertRaises(ValueError) as ctx:
            run("(stdout (lambda 0 (ref 0)))", Runtime())
        self.assertIn("function", str(ctx.exception))

    def test_a_non_codepoint_list_is_loud(self):
        with self.assertRaises(ValueError):
            run("(stdout (cons -5 (nil)))", Runtime())

    def test_output_is_captured_by_default(self):
        # Nothing reaches a terminal unless a caller asks, which is what
        # keeps generated programs and tests from spraying stdout.
        rt = Runtime()
        run("(stdout 1)", rt)
        self.assertEqual(rt.output, ["1"])
        self.assertIsNone(rt.out_stream)

    def test_output_is_forwarded_when_a_stream_is_set(self):
        sink = io.StringIO()
        rt = Runtime(out_stream=sink)
        run('(stdout "x")', rt)
        self.assertEqual(sink.getvalue(), "x")

    def test_sequencing_writes(self):
        rt = Runtime()
        run('(seq (stdout "a") (stdout "b") (stdout 3))', rt)
        self.assertEqual(rt.written(), "ab3")


class TestInput(unittest.TestCase):

    def test_reads_a_line_as_codepoints(self):
        rt = Runtime(input_lines=["abc"])
        self.assertEqual(list_to_python(run("(stdin)", rt)), [97, 98, 99])

    def test_end_of_input_is_the_empty_list_not_an_error(self):
        self.assertIs(run("(stdin)", Runtime()), NIL_VALUE)

    def test_never_blocks_without_a_source(self):
        # A generated program containing `stdin` must not hang a test run.
        rt = Runtime()
        for _ in range(3):
            self.assertIs(run("(stdin)", rt), NIL_VALUE)

    def test_a_live_source_is_used_after_the_queue(self):
        lines = iter(["from-queue-later\n", ""])
        rt = Runtime(input_lines=["queued"], input_source=lambda: next(lines))
        self.assertEqual(list_to_python(run("(stdin)", rt)),
                         [ord(c) for c in "queued"])
        self.assertEqual(list_to_python(run("(stdin)", rt)),
                         [ord(c) for c in "from-queue-later"])
        self.assertIs(run("(stdin)", rt), NIL_VALUE)


class TestEffects(unittest.TestCase):

    def test_effects_are_declared(self):
        self.assertIn("write-stdout", static_analyze(parse("(stdout 1)")).effects)
        self.assertIn("read-stdin", static_analyze(parse("(stdin)")).effects)

    def test_reading_makes_a_program_non_deterministic(self):
        self.assertFalse(static_analyze(parse("(stdin)")).is_deterministic)
        self.assertTrue(static_analyze(parse("(stdout 1)")).is_deterministic)

    def test_io_used_its_own_reserved_slots(self):
        # An activation, not a reallocation: 0x35 / 0x36 were named
        # `stdout` / `stdin` in the original table.
        self.assertEqual(SIGNATURES[0x35]["name"], "stdout")
        self.assertEqual(SIGNATURES[0x36]["name"], "stdin")
        self.assertIn(STDOUT, TYPED_TOKENS)
        self.assertIn(STDIN, TYPED_TOKENS)


# --- logic macros -----------------------------------------------------------

class TestLogicMacros(unittest.TestCase):

    def test_truth_table(self):
        cases = {
            "(not 0)": 1, "(not 5)": 0,
            "(and 1 7)": 7, "(and 0 7)": 0,
            "(or 0 9)": 9, "(or 4 9)": 4,
            "(eq 3 3)": 1, "(eq 3 4)": 0,
            "(ne 3 4)": 1, "(ne 3 3)": 0,
            "(le 3 3)": 1, "(le 4 3)": 0, "(le 2 3)": 1,
            "(ge 4 3)": 1, "(ge 2 3)": 0,
            "(neg 5)": -5, "(abs -7)": 7, "(abs 7)": 7,
            "(min 3 9)": 3, "(max 3 9)": 9,
            "(cond 0 10 1 20 30)": 20,
            "(cond 0 10 0 20 30)": 30,
            "(cond 1 10 1 20 30)": 10,
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                self.assertEqual(run(src), want)

    def test_and_short_circuits(self):
        rt = Runtime()
        run("(and 0 (stdout 99))", rt)
        self.assertEqual(rt.written(), "")

    def test_or_short_circuits(self):
        rt = Runtime()
        run("(or 1 (stdout 99))", rt)
        self.assertEqual(rt.written(), "")

    def test_or_evaluates_its_left_exactly_once(self):
        # `or` mentions its first argument twice in the expansion, so it
        # must bind it first -- an argument can write to stdout now.
        rt = Runtime()
        run("(or (stdout 5) 9)", rt)
        self.assertEqual(rt.written(), "5")

    def test_min_and_max_evaluate_each_argument_once(self):
        rt = Runtime()
        run("(min (stdout 1) (stdout 22))", rt)
        self.assertEqual(rt.written(), "122")

    def test_cond_requires_an_odd_argument_count(self):
        with self.assertRaises(ValueError) as ctx:
            parse("(cond 1 2 3 4)")
        self.assertIn("cond", str(ctx.exception))

    def test_macros_reach_no_new_tokens(self):
        for src in ("(not 1)", "(and 1 2)", "(or 1 2)", "(eq 1 2)",
                    "(min 1 2)", "(cond 1 2 3)", "(abs -1)", "(neg 1)"):
            with self.subTest(src=src):
                ops = set()

                def collect(node):
                    ops.add(node.op)
                    if node.op != 0x01:
                        for child in node.args:
                            collect(child)

                collect(parse(src))
                for op in ops:
                    self.assertIn(op, TYPED_TOKENS)

    def test_gensym_cannot_be_written_by_a_user(self):
        # The macros that bind a temporary use a name containing a space,
        # and the tokenizer splits on whitespace.
        from core.surface import SymbolTable
        table = SymbolTable()
        generated = table.gensym()
        self.assertEqual(table.intern(" g0"), generated)
        # A user writing `g0` gets a different id.
        self.assertNotEqual(table.intern("g0"), generated)


# --- the prelude ------------------------------------------------------------

class TestPrelude(unittest.TestCase):

    def test_prelude_parses(self):
        self.assertTrue(load_prelude().strip())
        parse_with_prelude("0")

    def test_list_functions(self):
        cases = {
            "(len (list 1 2 3))": 3,
            "(sum (range 1 5))": 10,
            "(product (list 2 3 4))": 24,
            "(nth (list 7 8 9) 1)": 8,
            "(last (list 7 8 9))": 9,
            "(contains (list 1 2 3) 2)": 1,
            "(contains (list 1 2 3) 9)": 0,
            "(len (append (list 1 2) (list 3 4 5)))": 5,
            "(head (reverse (list 1 2 3)))": 3,
            "(same \"abc\" \"abc\")": 1,
            "(same \"abc\" \"abd\")": 0,
            "(same \"ab\" \"abc\")": 0,
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                value, _ = run_with_prelude(src)
                self.assertEqual(value, want)

    def test_integer_functions(self):
        cases = {
            "(pow 2 10)": 1024, "(even 4)": 1, "(odd 4)": 0,
            "(gcd2 270 192)": 6, "(sum (digits 12345))": 15,
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                value, _ = run_with_prelude(src)
                self.assertEqual(value, want)

    def test_higher_order_functions(self):
        double = "(lambda 99 (mul (ref 99) 2))"
        value, _ = run_with_prelude(f"(sum (map {double} (list 1 2 3)))")
        self.assertEqual(value, 12)
        value, _ = run_with_prelude(
            "(sum (filter (lambda 99 (even (ref 99))) (range 0 10)))")
        self.assertEqual(value, 20)
        value, _ = run_with_prelude(
            "(fold (lambda 98 (lambda 99 (merge (ref 98) (ref 99)))) 0 "
            "(list 1 2 3 4))")
        self.assertEqual(value, 10)

    def test_map_returns_a_list(self):
        value, _ = run_with_prelude(
            "(map (lambda 99 (mul (ref 99) 3)) (list 1 2 3))")
        self.assertEqual(list_to_python(value), [3, 6, 9])

    def test_println_writes_a_newline(self):
        rt = Runtime()
        run_with_prelude('(println "hi")', rt)
        self.assertEqual(rt.written(), "hi\n")

    def test_a_user_definition_shadows_the_prelude(self):
        value, _ = run_with_prelude("(def len [xs] 99)(len (list 1 2 3))")
        self.assertEqual(value, 99)

    def test_the_prelude_is_free_when_unused(self):
        _value, report = run_with_prelude("(merge 1 2)")
        self.assertEqual(report.compiled_nodes, 1)
        self.assertGreater(report.dropped_bindings, 15)


# --- drop-unused ------------------------------------------------------------

class TestDropUnused(unittest.TestCase):

    def test_unused_binding_goes(self):
        _node, report = compile(parse("(let 0 (mul 6 7) 99)"))
        self.assertEqual(report.dropped_bindings, 1)

    def test_used_binding_stays(self):
        _node, report = compile(parse("(let 0 5 (merge (ref 0) 1))"))
        self.assertEqual(report.dropped_bindings, 0)

    def test_an_effectful_value_is_never_dropped(self):
        # Dropping this would silently lose the write.
        _node, report = compile(parse("(let 0 (stdout 5) 7)"))
        self.assertEqual(report.dropped_bindings, 0)
        rt = Runtime()
        evaluate(compile(parse("(let 0 (stdout 5) 7)"))[0], rt)
        self.assertEqual(rt.written(), "5")

    def test_a_lambda_body_does_not_count_as_an_effect(self):
        # Building a closure is pure; whatever the body would do happens
        # only if something applies it.  Without this, no recursive
        # prelude function could ever be dropped.
        _node, report = compile(parse("(def f [x] (stdout x))7"))
        self.assertEqual(report.dropped_bindings, 1)

    def test_a_chain_of_unused_definitions_collapses(self):
        node, report = compile(parse("(def f [x] (mul x 2))(def g [x] (f x))7"))
        self.assertEqual(report.dropped_bindings, 2)
        self.assertEqual(evaluate(node), 7)

    def test_the_pass_can_be_switched_off(self):
        _node, report = compile(parse("(let 0 5 7)"), drop_unused=False)
        self.assertEqual(report.dropped_bindings, 0)
        self.assertNotIn("drop-unused", report.passes)


# --- polymorphic result types -----------------------------------------------

class TestResultFollowsOperands(unittest.TestCase):
    """`if`, `let`, `seq` and `apply` take their type from their operands."""

    def test_a_conditional_can_return_a_list(self):
        # This is what made map/filter/reverse writable at all.
        node, _ = compile(parse("(if 1 (list 1 2) (nil))"))
        self.assertEqual(list_to_python(evaluate(node)), [1, 2])

    def test_a_let_can_return_a_list(self):
        node, _ = compile(parse("(let 0 5 (list 1 2))"))
        self.assertEqual(list_to_python(evaluate(node)), [1, 2])

    def test_a_seq_can_return_a_list(self):
        node, _ = compile(parse("(seq 1 (list 3 4))"))
        self.assertEqual(list_to_python(evaluate(node)), [3, 4])

    def test_a_top_level_program_may_be_any_type(self):
        # A program is an expression, not an integer expression.
        node, _ = compile(parse('"hi"'))
        self.assertEqual(list_to_python(evaluate(node)), [104, 105])

    def test_branches_are_still_checked_against_the_context(self):
        # Transparency is not permissiveness: an Int slot still rejects a
        # conditional whose branch is a list.
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (if 1 (nil) 2) 3)"))
        self.assertEqual(ctx.exception.anomaly["kind"], "type-mismatch")

    def test_the_condition_must_be_an_integer(self):
        with self.assertRaises(CompileError):
            compile(parse("(if (nil) 1 2)"))


# --- the CLI ----------------------------------------------------------------

class TestCLI(unittest.TestCase):

    def _capture(self, argv, stdin_text=""):
        """Run the CLI with every stream detached from the terminal.

        stdin in particular: `run -` reads it, and a test that touches
        the real one blocks forever the moment the suite is invoked with
        a terminal attached.
        """
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli_main(argv)
        finally:
            sys.stdin = saved_stdin
        return code, out.getvalue(), err.getvalue()

    def test_run_a_file(self):
        code, _out, err = self._capture(["run", "apps/is_prime.lova", "97"])
        self.assertEqual(code, 0)
        self.assertIn("=> 1", err)

    def test_run_substitutes_a_string_argument(self):
        code, _out, err = self._capture(
            ["run", "apps/palindrome.lova", "racecar"])
        self.assertEqual(code, 0)
        self.assertIn("=> 1", err)

    def test_program_output_goes_to_stdout_and_the_value_to_stderr(self):
        code, out, err = self._capture(
            ["run", "-", "--no-prelude"], stdin_text='(stdout "written")')
        self.assertEqual(code, 0)
        self.assertEqual(out, "written")       # only the program's own output
        self.assertIn("=>", err)               # the value never pollutes stdout

    def test_an_empty_program_is_an_error_not_a_silent_success(self):
        code, _out, err = self._capture(["run", "-", "--no-prelude"])
        self.assertNotEqual(code, 0)
        self.assertIn("empty source", err)

    def test_a_trap_reports_its_anomaly_and_exits_non_zero(self):
        code, _out, err = self._capture(["run", "apps/collatz.lova", "2463", "--max-depth", "200"])
        self.assertEqual(code, 2)
        self.assertIn("recursion-depth-exceeded", err)
        self.assertIn("repair:", err)

    def test_a_long_position_path_is_truncated(self):
        _code, _out, err = self._capture(["run", "apps/collatz.lova", "2463", "--max-depth", "200"])
        self.assertIn("more ...", err)

    def test_emit_stage2(self):
        code, out, _err = self._capture(
            ["emit", "apps/coprime.lova", "14", "15", "--form", "stage2"])
        self.assertEqual(code, 0)
        self.assertNotIn("(", out)

    def test_emit_bytes_and_int(self):
        code, out, _err = self._capture(
            ["emit", "apps/coprime.lova", "14", "15", "--form", "bytes"])
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())

    def test_analyze(self):
        code, out, _err = self._capture(["analyze", "apps/collatz.lova", "27"])
        self.assertEqual(code, 0)
        self.assertIn("effects:", out)
        self.assertIn("bytes:", out)

    def test_missing_argument_is_reported(self):
        with self.assertRaises(SystemExit):
            self._capture(["run", "apps/is_prime.lova"])

    def test_format_value_shows_a_list_as_text_too(self):
        rt = Runtime()
        value = run('"hi"', rt)
        self.assertIn('"hi"', format_value(value))
        self.assertIn("104", format_value(value))


if __name__ == "__main__":
    unittest.main()
