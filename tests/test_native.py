"""The Python side of the native runtime, against the reference server.

`tools/mock_runtime.py` is the protocol made executable -- the Python
runtime behind the line protocol a native runtime speaks -- so the
client, the CLI flag and the MCP parameter can all be driven before any
binary exists.  It proves nothing about a port; it proves that this side
of the pipe is right.

What is checked: the process is started once and kept; a value printed
through the native path is character for character the value the Python
path prints; a trap is the same trap class, the same kind and the same
`position_path`, and reaches the same `span` / `line` / `col` through
`lova run` and `lova_execute`; `supports` keeps a program with `explain`
in Python; `--native on` with nothing to run on is an error and not a
traceback; and a runtime that dies says so instead of hanging.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "tools" / "mock_runtime.py"

from core import native as native_mod                          # noqa: E402
from core.cli import build, format_value, main as cli_main     # noqa: E402
from core.conservation import DomainTrap                       # noqa: E402
from core.native import (                                      # noqa: E402
    NativeResult, NativeRuntime, NativeUnavailable, NativeUnsupported,
    span_for_path, supports,
)
from core.runtime import Runtime, evaluate                     # noqa: E402

COMMAND = [sys.executable, str(MOCK)]

# Ten programs whose values cover the shapes `format_value` prints
# differently: an integer, a negative, a text, a list, a list that is
# also a text, a map, a closure, a fold over a range, a conditional and
# a program that writes as it goes.
PROGRAMS = [
    "(merge 1 2)",
    "(sub 3 10)",
    '(text-cat "ab" "cd")',
    "(list 1 2 3)",
    '(text-chars "hi")',
    "(rec x 1 y 2)",
    "(lambda n (mul n n))",
    "(fold (lambda a (lambda x (merge a x))) 0 (range 1 6))",
    "(if (lt 2 3) (list 1 (list 2 3)) 0)",
    '(seq (println "one") (println "two") 7)',
]


@unittest.skipUnless(MOCK.is_file(), f"no reference server at {MOCK}")
class NativeClient(unittest.TestCase):
    """`core/native.py` against the reference server."""

    def setUp(self) -> None:
        self.rt = NativeRuntime(COMMAND, timeout_s=60.0)
        self.addCleanup(self.rt.close)

    def test_ping_answers_with_a_version(self):
        version = self.rt.ping()
        self.assertTrue(version)
        self.assertIn("runtime", version)

    def test_a_value_is_what_the_python_runtime_prints(self):
        for source in PROGRAMS:
            with self.subTest(source=source):
                tree, _ = build(source)
                got = self.rt.run(tree, max_steps=1_000_000)
                want = evaluate(tree, Runtime(max_steps=1_000_000))
                self.assertIsInstance(got, NativeResult)
                self.assertEqual(got.value_text, format_value(want))

    def test_the_step_count_is_the_python_one(self):
        for source in PROGRAMS:
            with self.subTest(source=source):
                tree, _ = build(source)
                got = self.rt.run(tree, max_steps=1_000_000)
                py = Runtime(max_steps=1_000_000)
                evaluate(tree, py)
                self.assertEqual(got.steps, py.steps)

    def test_what_the_program_wrote_comes_back_and_not_on_stdout(self):
        tree, _ = build('(seq (println "hello") 1)')
        result = self.rt.run(tree, max_steps=1_000_000)
        self.assertEqual(result.stdout, "hello\n")
        self.assertEqual(result.value_text, "1")

    def test_stdin_reaches_the_program(self):
        tree, _ = build("(text-int (text-trim (stdin)))")
        result = self.rt.run(tree, stdin="41\n", max_steps=1_000_000)
        self.assertEqual(result.value_text, "41")

    def test_one_process_serves_every_run(self):
        first = self.rt.proc
        tree, _ = build("(merge 1 2)")
        for _ in range(5):
            self.rt.run(tree, max_steps=1000)
        self.assertIs(self.rt.proc, first)
        self.assertIsNone(first.poll(), "the process was restarted")

    def test_a_domain_trap_is_the_python_trap(self):
        source = "(def f [n] (div 10 n))\n(f 0)\n"
        tree, _ = build(source)
        with self.assertRaises(DomainTrap) as native_trap:
            self.rt.run(tree, max_steps=1_000_000)
        with self.assertRaises(DomainTrap) as python_trap:
            evaluate(tree, Runtime(max_steps=1_000_000))
        a, b = native_trap.exception.anomaly, python_trap.exception.anomaly
        self.assertEqual(a["kind"], b["kind"])
        self.assertEqual(tuple(a["position_path"]), tuple(b["position_path"]))
        self.assertEqual(a["offending_op"], b["offending_op"])
        self.assertEqual(tuple(a["span"]), tuple(b["span"]))
        self.assertEqual(a["valid_alternatives"], b["valid_alternatives"])

    def test_a_step_trap_is_a_step_trap(self):
        from core.conservation import StepTrap
        tree, _ = build("(def g [n] (g (merge n 1)))\n(g 0)\n")
        with self.assertRaises(StepTrap):
            self.rt.run(tree, max_steps=5_000)

    def test_supports_is_false_for_a_program_that_uses_explain(self):
        with_meta, _ = build("(explain (quote (merge 1 2)))")
        without, _ = build("(merge 1 2)")
        self.assertFalse(supports(with_meta))
        self.assertTrue(supports(without))
        self.assertEqual(native_mod.unsupported_in(with_meta), ["explain"])

    def test_a_killed_process_raises_and_a_fresh_client_recovers(self):
        tree, _ = build("(merge 1 2)")
        self.rt.run(tree, max_steps=1000)
        self.rt.proc.kill()
        self.rt.proc.wait(timeout=10)
        with self.assertRaises(NativeUnavailable):
            for _ in range(3):        # the first write may still buffer
                self.rt.run(tree, max_steps=1000)
        self.assertFalse(self.rt.alive)
        with NativeRuntime(COMMAND, timeout_s=60.0) as fresh:
            self.assertEqual(fresh.run(tree, max_steps=1000).value_text, "3")

    def test_a_command_that_is_not_there_is_unavailable_not_a_traceback(self):
        with self.assertRaises(NativeUnavailable):
            NativeRuntime([str(ROOT / "no" / "such" / "binary")])


class SpanRecovery(unittest.TestCase):
    """`span_for_path` mirrors what `_enrich_trap` reads off the stack."""

    def _python_trap(self, source):
        tree, _ = build(source)
        try:
            evaluate(tree, Runtime(max_steps=1_000_000))
        except Exception as exc:                        # noqa: BLE001
            return tree, exc.anomaly
        self.fail("the program did not trap")

    def test_the_span_is_the_one_the_python_runtime_reports(self):
        for source in ("(def f [n] (div 10 n))\n(f 0)\n",
                       "(def g [n] (head (list)))\n(g 1)\n",
                       "(nth (list 1 2) 9)\n"):
            with self.subTest(source=source):
                tree, anomaly = self._python_trap(source)
                self.assertEqual(
                    tuple(span_for_path(tree, anomaly["position_path"])),
                    tuple(anomaly["span"]))

    def test_an_empty_path_has_no_span(self):
        tree, _ = build("(merge 1 2)")
        self.assertIsNone(span_for_path(tree, ()))


@unittest.skipUnless(MOCK.is_file(), f"no reference server at {MOCK}")
class Wiring(unittest.TestCase):
    """The CLI flag and the MCP parameter, with the server as the runtime."""

    def setUp(self) -> None:
        native_mod.forget_default()
        self.addCleanup(native_mod.forget_default)
        self._env = os.environ.get("LOVA_NATIVE")
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._env is None:
            os.environ.pop("LOVA_NATIVE", None)
        else:
            os.environ["LOVA_NATIVE"] = self._env

    def _use_mock(self) -> None:
        os.environ["LOVA_NATIVE"] = f'"{sys.executable}" "{MOCK}"'
        native_mod.forget_default()

    def _write(self, name: str, text: str) -> str:
        import tempfile
        holder = tempfile.TemporaryDirectory(prefix="lova-native-")
        self.addCleanup(holder.cleanup)
        path = os.path.join(holder.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_run_prints_the_same_thing_on_both_runtimes(self):
        path = self._write("v.lova", '(seq (println "out") (list 1 2 3))\n')
        self._use_mock()
        native = self._cli(["run", path, "--native", "on"])
        python = self._cli(["run", path, "--native", "off"])
        self.assertEqual(native[0], 0)
        self.assertEqual(native[1], python[1])          # stdout
        self.assertEqual(native[2], python[2])          # the `=> value` line

    def test_a_trap_reports_the_same_place_on_both_runtimes(self):
        path = self._write("t.lova", "(def f [n] (div 10 n))\n(f 0)\n")
        self._use_mock()
        native = self._cli(["run", path, "--native", "on"])
        python = self._cli(["run", path, "--native", "off"])
        self.assertEqual(native[0], 2)
        self.assertEqual(native[2], python[2])
        self.assertIn("at: 1:12  (div 10 n)", native[2])

    def test_native_on_without_a_runtime_is_a_clean_error(self):
        path = self._write("v.lova", "(merge 1 2)\n")
        os.environ["LOVA_NATIVE"] = ""
        native_mod._DEFAULT[:] = [None]                 # nothing on this machine
        code, _out, err = self._cli(["run", path, "--native", "on"])
        self.assertEqual(code, 1)
        self.assertIn("no native runtime", err)
        self.assertNotIn("Traceback", err)

    def test_native_on_with_an_unsupported_program_is_a_clean_error(self):
        path = self._write("m.lova", "(explain (quote (merge 1 2)))\n")
        self._use_mock()
        code, _out, err = self._cli(["run", path, "--native", "on"])
        self.assertEqual(code, 1)
        self.assertIn("explain", err)
        self.assertNotIn("Traceback", err)

    def test_auto_falls_back_to_python_for_an_unsupported_program(self):
        path = self._write("m.lova", "(explain (quote (merge 1 2)))\n")
        self._use_mock()
        code, _out, err = self._cli(["run", path, "--native", "auto"])
        self.assertEqual(code, 0)
        self.assertIn('=> "(merge 1 2)"', err)

    def test_check_native_agrees_with_check(self):
        text = ("(def sq [n] (mul n n))\n(example (sq 5) 25)\n"
                "(example (sq 3) 9)\n(sq 2)\n")
        path = self._write("c.lova", text)
        self._use_mock()
        native = self._cli(["check", path, "--native"])
        python = self._cli(["check", path])
        self.assertEqual(native[0], 0)
        self.assertEqual(native[1], python[1])

    def test_a_failing_check_falls_back_to_the_python_report(self):
        text = ("(def sq [n] (mul n 2))\n(example (sq 5) 25)\n(sq 2)\n")
        path = self._write("c.lova", text)
        self._use_mock()
        native = self._cli(["check", path, "--native"])
        python = self._cli(["check", path])
        self.assertEqual(native[0], 2)
        self.assertEqual(native[1], python[1])
        self.assertIn("fault", native[1] + "lead")

    def test_check_native_uses_one_process_for_every_example(self):
        from core import examples as examples_mod
        text = "(def sq [n] (mul n n))\n" + "".join(
            f"(example (sq {i}) {i * i})\n" for i in range(1, 7)) + "(sq 2)\n"
        self._use_mock()
        started = []
        real = native_mod.default_runtime

        def counting(**kwargs):
            runtime = real(**kwargs)
            started.append(runtime)
            return runtime

        native_mod.default_runtime = counting
        try:
            results = examples_mod.check(text, runtime="native")
        finally:
            native_mod.default_runtime = real
        self.assertEqual(len(results), 6)
        self.assertTrue(all(r["passed"] for r in results))
        self.assertEqual(len(started), 1, "one process for the whole check")

    def test_mcp_execute_says_which_runtime_ran(self):
        from core.mcp_server import tool_execute
        self._use_mock()
        source = '(seq (println "hi") (merge 1 2))'
        native = tool_execute({"source": source, "native": "on"})
        python = tool_execute({"source": source, "native": "off"})
        self.assertEqual(native["runtime"], "native")
        self.assertEqual(python["runtime"], "python")
        self.assertEqual(native["value"], python["value"])
        self.assertEqual(native["output"], python["output"])
        self.assertEqual(native["steps"], python["steps"])

    def test_mcp_execute_reports_the_same_span_on_both_runtimes(self):
        from core.mcp_server import tool_execute
        self._use_mock()
        source = "(def f [n] (div 10 n))\n(f 0)\n"
        native = tool_execute({"source": source, "native": "on"})
        python = tool_execute({"source": source, "native": "off"})
        self.assertFalse(native["ok"])
        for key in ("kind", "span", "line", "col", "excerpt", "position_path"):
            self.assertEqual(native["anomaly"][key], python["anomaly"][key], key)

    def test_mcp_execute_defaults_to_auto(self):
        from core.mcp_server import tool_execute
        self._use_mock()
        self.assertEqual(tool_execute({"source": "(merge 1 2)"})["runtime"],
                         "native")

    def test_mcp_execute_on_without_a_runtime_says_so(self):
        from core.mcp_server import tool_execute
        os.environ["LOVA_NATIVE"] = ""
        native_mod._DEFAULT[:] = [None]
        answer = tool_execute({"source": "(merge 1 2)", "native": "on"})
        self.assertFalse(answer["ok"])
        self.assertIn("no native runtime", answer["anomaly"]["message"])


if __name__ == "__main__":
    unittest.main()
