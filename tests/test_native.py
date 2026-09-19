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
`lova run` and `lova_execute`; a runtime's **own** `unsupported` list is
what a program is screened against, and screens it before stdin is
handed over; `--native on` with nothing to run on is an error and not a
traceback; and a runtime that dies says so instead of hanging.

The reference server runs everything (it is the Python runtime), so its
`ping` declares `unsupported: []`.  A runtime that refuses something is
therefore a **fake** written for the test -- `write_fake_runtime` -- one
that answers `ping` with the list under test and refuses to run a
program at all, because every test that uses it is a test of the screen
and a program that reaches it has already got past the screen.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "tools" / "mock_runtime.py"

from core import native as native_mod                          # noqa: E402
from core.cli import build, format_value, main as cli_main     # noqa: E402
from core.conservation import DomainTrap                       # noqa: E402
from core.native import (                                      # noqa: E402
    UNSUPPORTED_OPS, NativeResult, NativeRuntime, NativeSession,
    NativeUnavailable, NativeUnsupported, Ref, ops_named, span_for_nodes,
    span_for_path, supports, unsupported_in,
)
from core.runtime import Runtime, evaluate                     # noqa: E402

COMMAND = [sys.executable, str(MOCK)]

FAKE_SOURCE = '''\
"""A runtime that answers `ping` and runs nothing (tests/test_native.py)."""
import json
import sys

UNSUPPORTED = {unsupported!r}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        request = json.loads(line)
    except ValueError:
        continue
    if request.get("op") == "ping":
        reply = {{"ok": True, "version": "fake runtime 0.0.0"}}
        if UNSUPPORTED is not None:
            reply["unsupported"] = UNSUPPORTED
    else:
        reply = {{"id": request.get("id"), "ok": False,
                  "error": "fake: this runtime never runs a program"}}
    sys.stdout.write(json.dumps(reply) + "\\n")
    sys.stdout.flush()
'''


# Two programs an operator screen can tell apart *after* the compiler:
# constant folding leaves `(merge 1 2)` a literal, so the operator under
# test has to reach the tree through a parameter.
MERGING = "(def f [n] (merge n 1))\n(f 2)\n"
MULTIPLYING = "(def g [n] (mul n 2))\n(g 5)\n"


def write_fake_runtime(directory: str, unsupported, name="fake_rt.py"):
    """A fake runtime's command, written into ``directory``.

    ``unsupported`` is the list its `ping` declares; ``None`` writes a
    runtime whose reply has no such key at all -- a phase-2 runtime,
    which is what `UNSUPPORTED_OP_NAMES` is the fallback for.
    """
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(FAKE_SOURCE.format(unsupported=unsupported))
    return [sys.executable, path]

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


class DeclaredScope(unittest.TestCase):
    """The runtime says what it refuses; this side believes it."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="lova-fake-rt-")
        self.addCleanup(holder.cleanup)
        self.dir = holder.name

    def _fake(self, unsupported, name="fake_rt.py") -> NativeRuntime:
        runtime = NativeRuntime(write_fake_runtime(self.dir, unsupported, name),
                                timeout_s=60.0)
        self.addCleanup(runtime.close)
        runtime.ping()
        return runtime

    # -- (a) the runtime's list is the screen --------------------------------

    def test_a_declared_list_overrides_the_static_one(self):
        # `merge` is in no phase's unsupported list; this runtime refuses
        # it anyway, and that is the answer that counts.  (Through a def:
        # `(merge 1 2)` on its own is folded to a literal before it gets
        # here, and a program with no `merge` left in it is not a test.)
        runtime = self._fake(["merge", "not-an-operator"])
        self.assertTrue(runtime.declares_unsupported)
        self.assertEqual(runtime.unsupported_ops, ops_named(["merge"]))
        self.assertIn("not-an-operator", runtime.unsupported_names)
        tree, _ = build(MERGING)
        self.assertFalse(supports(tree, runtime))
        self.assertEqual(unsupported_in(tree, runtime), ["merge"])
        # ... and the static list still says the opposite on its own.
        self.assertTrue(supports(tree))

    @unittest.skipUnless(MOCK.is_file(), f"no reference server at {MOCK}")
    def test_an_empty_declared_list_takes_the_whole_static_one_back(self):
        # The reference server is the Python runtime: it runs `explain`,
        # says so, and a program with `explain` is its to run.
        runtime = NativeRuntime(COMMAND, timeout_s=60.0)
        self.addCleanup(runtime.close)
        runtime.ping()
        self.assertTrue(runtime.declares_unsupported)
        self.assertEqual(runtime.unsupported_ops, frozenset())
        tree, _ = build("(explain (quote (merge 1 2)))")
        self.assertFalse(supports(tree))            # the static list
        self.assertTrue(supports(tree, runtime))    # the runtime's own
        self.assertEqual(runtime.run(tree, max_steps=100_000).value_text,
                         '"(merge 1 2)"')

    # -- (b) no list at all is a phase-2 runtime -----------------------------

    def test_a_ping_without_the_key_falls_back_to_the_static_list(self):
        runtime = self._fake(None)
        self.assertFalse(runtime.declares_unsupported)
        self.assertEqual(runtime.unsupported_ops, UNSUPPORTED_OPS)
        tree, _ = build("(explain (quote (merge 1 2)))")
        self.assertFalse(supports(tree, runtime))
        self.assertEqual(unsupported_in(tree, runtime), ["explain"])
        plain, _ = build("(merge 1 2)")
        self.assertTrue(supports(plain, runtime))

    def test_a_runtime_that_was_never_pinged_holds_the_static_list(self):
        runtime = NativeRuntime(write_fake_runtime(self.dir, [], "unpinged.py"),
                                timeout_s=60.0)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.unsupported_ops, UNSUPPORTED_OPS)

    # -- (2) the shared runtime, and a restart -------------------------------

    def _point_at(self, command) -> None:
        os.environ["LOVA_NATIVE"] = " ".join(f'"{word}"' for word in command)
        native_mod.forget_default()

    def test_the_shared_runtime_screens_every_program_against_its_list(self):
        self._env_guard()
        self._point_at(write_fake_runtime(self.dir, ["merge"], "shared_a.py"))
        refused, _ = build(MERGING)
        allowed, _ = build(MULTIPLYING)
        first = native_mod.choose(allowed, "auto", shared=True)
        self.assertIsNotNone(first)
        self.assertIsNone(native_mod.choose(refused, "auto", shared=True))
        # Screened, not closed: the server's one process serves the next
        # program, which is the whole point of sharing it.
        self.assertTrue(first.alive)
        self.assertIs(native_mod.choose(allowed, "auto", shared=True), first)
        with self.assertRaises(NativeUnsupported):
            native_mod.choose(refused, "on", shared=True)

    def test_a_restarted_shared_runtime_re_reads_the_list(self):
        self._env_guard()
        self._point_at(write_fake_runtime(self.dir, ["merge"], "shared_b.py"))
        refused, _ = build(MERGING)
        self.assertIsNone(native_mod.choose(refused, "auto", shared=True))
        # The process dies and the command behind it changes: the next
        # ask starts a new one and takes its list, not the dead one's.
        self._point_at(write_fake_runtime(self.dir, [], "shared_c.py"))
        after = native_mod.choose(refused, "auto", shared=True)
        self.assertIsNotNone(after)
        self.assertEqual(after.unsupported_ops, frozenset())

    def _env_guard(self) -> None:
        previous = os.environ.get("LOVA_NATIVE")

        def restore() -> None:
            if previous is None:
                os.environ.pop("LOVA_NATIVE", None)
            else:
                os.environ["LOVA_NATIVE"] = previous
            native_mod.forget_default()

        self.addCleanup(restore)


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
    def test_position_nodes_pick_the_call_the_ops_cannot(self):
        # Two println calls of the same shape; the second traps.  By ops
        # alone they tie and the first wins, so `span_for_path` cannot
        # answer these; the reference server names its frames' nodes,
        # and the client reports what the Python stack reports.
        for source in ("(def f [x] (merge x 1))\n"
                       "(seq (println (f 1))\n"
                       "     (println (quote (merge 1 2))))\n",
                       "(def show [p] (println p))\n"
                       "(let q (quote (mul 2 3)) (seq (println 1) (show q)))\n"):
            with self.subTest(source=source):
                tree, anomaly = self._python_trap(source)
                with NativeRuntime(COMMAND, timeout_s=60.0) as native:
                    with self.assertRaises(ValueError) as caught:
                        native.run(tree)
                got = caught.exception.anomaly
                self.assertIn("position_nodes", got)
                self.assertEqual(tuple(got["span"]), tuple(anomaly["span"]))
                self.assertEqual(
                    span_for_nodes(tree, got["position_nodes"]), anomaly["span"])


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

    def _use_fake(self, unsupported, name="fake_rt.py") -> None:
        """Point `LOVA_NATIVE` at a runtime that refuses what it names."""
        holder = tempfile.TemporaryDirectory(prefix="lova-fake-rt-")
        self.addCleanup(holder.cleanup)
        command = write_fake_runtime(holder.name, unsupported, name)
        os.environ["LOVA_NATIVE"] = " ".join(f'"{w}"' for w in command)
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
        self._use_fake(None)                     # a phase-2 runtime
        code, _out, err = self._cli(["run", path, "--native", "on"])
        self.assertEqual(code, 1)
        self.assertIn("explain", err)
        self.assertNotIn("Traceback", err)

    def test_auto_falls_back_to_python_for_an_unsupported_program(self):
        path = self._write("m.lova", "(explain (quote (merge 1 2)))\n")
        self._use_fake(None)
        code, _out, err = self._cli(["run", path, "--native", "auto"])
        self.assertEqual(code, 0)
        self.assertIn('=> "(merge 1 2)"', err)

    def test_an_operator_the_runtime_names_stays_in_python(self):
        # `text-cat` is in no phase's list: only this runtime's own reply
        # keeps the program out of it, which is what is being checked.
        path = self._write("t.lova", '(text-cat "ab" "cd")\n')
        self._use_fake(["text-cat"])
        auto = self._cli(["run", path, "--native", "auto"])
        self.assertEqual(auto[0], 0)
        self.assertIn('=> "abcd"', auto[2])
        code, _out, err = self._cli(["run", path, "--native", "on"])
        self.assertEqual(code, 1)
        self.assertIn("text-cat", err)
        self.assertNotIn("Traceback", err)

    def test_a_screened_program_never_has_its_stdin_handed_over(self):
        """The bug apps/guess.lova found: refused after the hand-over.

        The whole of stdin goes to the native side in the `run` request,
        so a program screened *after* that falls back to Python with its
        input already gone.  Here the screen is the runtime's own list,
        the fallback is Python, and the value proves Python still had
        the line to read.
        """
        path = self._write("i.lova", "(text-int (text-trim (stdin)))\n")
        self._use_fake(["text-int"])
        stdin = sys.stdin
        sys.stdin = io.StringIO("41\n")
        try:
            code, _out, err = self._cli(["run", path, "--native", "auto"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 0)
        self.assertIn("=> 41", err)

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


SESSION_SOURCE = """\
(def add2 [a b] (merge a b))
(def shout [t] (seq (println t) (text-len t)))
(def total [xs] (fold (lambda a (lambda x (merge a x))) 0 xs))
(def grow [n] (mul n 1000000000000))
(def xof [r] (get r x))
(def isnil [xs] (if (nil? xs) 1 0))
(def first [xs] (head xs))
(def boom [n] (div 10 n))
(rec add2 add2 shout shout total total grow grow xof xof isnil isnil
     first first boom boom empty (nil) point (rec x 5 y 6))
"""


@unittest.skipUnless(MOCK.is_file(), f"no reference server at {MOCK}")
class Sessions(unittest.TestCase):
    """`NativeSession` against the reference server (the protocol's 0.3.0).

    A session is what the three drivers need and `run` cannot give: the
    program evaluated once, its record of closures kept, and a call into
    it per tick with the world -- a value the runtime holds -- going
    back in as a handle.  Every claim below is checked against the same
    program run in this process with `core.runtime._call`, which is what
    the drivers do when there is no native runtime.
    """

    def setUp(self) -> None:
        self.runtime = NativeRuntime(COMMAND, timeout_s=60.0)
        self.addCleanup(self.runtime.close)
        self.runtime.ping()
        self.tree, _ = build(SESSION_SOURCE)
        self.session = NativeSession.open(self.runtime, self.tree,
                                          max_steps=1_000_000)
        self.addCleanup(self.session.close)
        # The same program in this process, for the comparison.
        self.rt = Runtime(max_steps=1_000_000)
        self.api = evaluate(self.tree, self.rt)

    @staticmethod
    def lova(value):
        """A Python argument as the Python runtime wants it."""
        from core.runtime import NIL_VALUE, list_from
        if value is None:
            return NIL_VALUE
        if isinstance(value, list):
            return list_from([Sessions.lova(item) for item in value])
        return value

    def python(self, name, *args):
        """`Rules.call` as the drivers spell it, in Python."""
        from core.runtime import _call, _map_key
        fn = self.api.entries[_map_key(name, "rec")][1]
        self.rt.steps = 0
        for arg in args:
            fn = _call(fn, self.lova(arg), self.rt)
        return fn

    def test_the_program_value_is_a_handle_and_its_fields_are_its_own(self):
        self.assertIsInstance(self.session.api, Ref)
        self.assertIsInstance(self.session.get("add2"), Ref)
        self.assertIsNone(self.session.get("no-such-field"))
        self.assertGreater(self.session.steps, 0, "the open cost steps")

    def test_a_call_with_integers_is_the_python_call(self):
        self.assertEqual(self.session.call(self.session.get("add2"), 3, 4), 7)
        self.assertEqual(self.python("add2", 3, 4), 7)

    def test_a_list_goes_in_as_a_list(self):
        self.assertEqual(self.session.call(self.session.get("total"),
                                           [1, 2, 3, 4]), 10)
        # nested, and back out again: a list of encoded elements,
        # recursively, and never a string
        self.assertEqual(self.session.call(self.session.get("first"),
                                           [[1, 2], 3]), [1, 2])
        self.assertEqual(self.session.call(self.session.get("first"),
                                           [[65, 66], 3]), [65, 66])

    def test_a_text_goes_in_as_a_text(self):
        self.assertEqual(self.session.call(self.session.get("shout"), "hello"),
                         5)

    def test_a_handle_goes_back_in(self):
        point = self.session.get("point")
        self.assertIsInstance(point, Ref)
        self.assertEqual(self.session.call(self.session.get("xof"), point), 5)
        self.assertEqual(self.session.get("x", point), 5)
        self.assertEqual(self.session.get("y", point), 6)

    def test_fewer_arguments_curry_and_more_apply_through(self):
        add2 = self.session.get("add2")
        half = self.session.call(add2, 3)
        self.assertIsInstance(half, Ref)
        self.assertEqual(self.session.call(half, 4), 7)
        self.assertEqual(self.session.call(add2, 3, 4), 7)

    def test_the_steps_of_a_call_start_at_zero_and_are_the_python_ones(self):
        for name, args in (("add2", (3, 4)), ("total", ([1, 2, 3],)),
                           ("shout", ("hi",)), ("grow", (7,))):
            with self.subTest(name=name):
                self.session.call(self.session.get(name), *args)
                first = self.session.steps
                self.session.call(self.session.get(name), *args)
                self.assertEqual(self.session.steps, first,
                                 "a call's steps are its own")
                self.python(name, *args)
                self.assertEqual(self.session.steps, self.rt.steps)

    def test_a_get_charges_nothing_and_leaves_the_last_call_standing(self):
        self.session.call(self.session.get("add2"), 3, 4)
        spent = self.session.steps
        self.session.get("point")
        self.assertEqual(self.session.steps, spent)

    def test_what_a_call_wrote_is_that_calls_own(self):
        shout = self.session.get("shout")
        self.session.call(shout, "one")
        self.assertEqual(self.session.stdout, "one\n")
        self.session.call(shout, "two")
        self.assertEqual(self.session.stdout, "two\n")
        self.session.call(self.session.get("add2"), 1, 2)
        self.assertEqual(self.session.stdout, "")

    def test_a_trap_is_the_python_trap_and_the_session_answers_after_it(self):
        with self.assertRaises(DomainTrap) as native:
            self.session.call(self.session.get("boom"), 0)
        with self.assertRaises(DomainTrap) as python:
            self.python("boom", 0)
        a, b = native.exception.anomaly, python.exception.anomaly
        self.assertEqual(a["kind"], b["kind"])
        self.assertEqual(a["offending_op"], b["offending_op"])
        self.assertEqual(tuple(a["position_path"]), tuple(b["position_path"]))
        self.assertEqual(tuple(a["span"]), tuple(b["span"]))
        self.assertEqual(self.session.call(self.session.get("add2"), 1, 2), 3)

    def test_a_big_integer_crosses_both_ways(self):
        big = self.session.call(self.session.get("grow"), 99_999_999)
        self.assertEqual(big, 99_999_999 * 1_000_000_000_000)
        self.assertGreater(big, 1 << 53)
        self.assertEqual(self.session.call(self.session.get("add2"), big, 1),
                         big + 1)

    def test_nil_crosses_both_ways(self):
        self.assertIsNone(self.session.get("empty"))
        isnil = self.session.get("isnil")
        self.assertEqual(self.session.call(isnil, None), 1)
        self.assertEqual(self.session.call(isnil, []), 1)
        self.assertEqual(self.session.call(isnil, [1]), 0)

    def test_a_released_handle_is_gone(self):
        add2 = self.session.get("add2")
        self.session.release(add2)
        with self.assertRaises(native_mod.NativeSessionError):
            self.session.call(add2, 1, 2)
        # the session itself is untouched
        self.assertEqual(self.session.call(self.session.get("add2"), 1, 2), 3)

    def test_close_ends_the_session_and_the_runtime_serves_another(self):
        self.session.close()
        with self.assertRaises(native_mod.NativeSessionError):
            self.session.get("add2")
        with NativeSession(self.runtime, self.tree, max_steps=1_000_000) as s:
            self.assertEqual(s.call(s.get("add2"), 20, 22), 42)

    def test_a_program_that_traps_opens_no_session(self):
        tree, _ = build("(def f [n] (div 10 n))\n(f 0)\n")
        with self.assertRaises(DomainTrap):
            NativeSession(self.runtime, tree, max_steps=1_000_000)
        # the runtime is still there, and the session that was open
        # before it is untouched
        self.assertEqual(self.session.call(self.session.get("add2"), 1, 2), 3)

    def test_open_session_off_never_opens_one(self):
        self.assertIsNone(native_mod.open_session(self.tree, "off"))

    def test_a_runtime_that_does_not_speak_sessions_stays_in_python(self):
        """A binary older than 0.3.0 answers `unknown op`, and that is a
        fall-back under `auto` and an error under `on` -- never a hang."""
        holder = tempfile.TemporaryDirectory(prefix="lova-fake-rt-")
        self.addCleanup(holder.cleanup)
        command = write_fake_runtime(holder.name, [], "no_sessions.py")
        previous = os.environ.get("LOVA_NATIVE")
        os.environ["LOVA_NATIVE"] = " ".join(f'"{w}"' for w in command)
        native_mod.forget_default()

        def restore():
            if previous is None:
                os.environ.pop("LOVA_NATIVE", None)
            else:
                os.environ["LOVA_NATIVE"] = previous
            native_mod.forget_default()

        self.addCleanup(restore)
        self.assertIsNone(native_mod.open_session(self.tree, "auto"))
        with self.assertRaises(NativeUnavailable):
            native_mod.open_session(self.tree, "on")


@unittest.skipUnless(MOCK.is_file(), f"no reference server at {MOCK}")
class Drivers(unittest.TestCase):
    """The three drivers' `Rules`, native and Python, side by side.

    `apps/war`, `apps/platformer` and `apps/citybuilder` evaluate their
    program once and call into it per tick.  `Rules(native=...)` chooses
    the runtime and nothing else in a driver knows which one it got, so
    the check is that the numbers are the same ones.
    """

    @classmethod
    def setUpClass(cls) -> None:
        for app in ("war", "platformer", "citybuilder"):
            path = str(ROOT / "apps" / app)
            if path not in sys.path:
                sys.path.insert(0, path)

    def setUp(self) -> None:
        self._env = os.environ.get("LOVA_NATIVE")
        os.environ["LOVA_NATIVE"] = f'"{sys.executable}" "{MOCK}"'
        native_mod.forget_default()
        self.addCleanup(native_mod.forget_default)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._env is None:
            os.environ.pop("LOVA_NATIVE", None)
        else:
            os.environ["LOVA_NATIVE"] = self._env

    def _rules(self, module, native):
        rules = module.Rules(native=native)
        self.addCleanup(lambda: rules.session and rules.session.close())
        if native == "on":
            self.assertIsNotNone(rules.session, "no session was opened")
        else:
            self.assertIsNone(rules.session)
        return rules

    def test_the_battlefield_is_the_same_battle(self):
        import war
        answers = []
        for native in ("off", "on"):
            rules = self._rules(war, native)
            world = rules.call("new", 1)
            run = []
            for _ in range(3):
                world = rules.call("tick", world)
                run.append(rules.rt.steps)
                run.append([rules.fields(s, "u", "v", "t", "hp", "s", "f")
                            for s in war.list_to_python(rules.call("spr", world))])
                run.append(rules.field(world, "turn"))
                run.append((rules.call("left", world, 0),
                            rules.call("left", world, 1)))
            answers.append(run)
        self.assertEqual(answers[0], answers[1])

    def test_the_platformer_plays_the_same_frame(self):
        import platformer
        answers = []
        for native in ("off", "on"):
            rules = self._rules(platformer, native)
            world = rules.new_game()
            for keys in ({"d"}, {"d"}, set(), {"jump"}, set()):
                world = rules.tick(world, keys)
            # `Rules.frame` unpacks the list of faces; each face is
            # unpacked by the caller, as `Game.paint` and `shot` do.
            answers.append([[platformer.list_to_python(f)
                             for f in rules.frame(world)], rules.rt.steps,
                            rules.call("coins", world),
                            rules.call("resets", world),
                            platformer.list_to_python(rules.call("where", world))])
        self.assertEqual(answers[0], answers[1])
        self.assertTrue(answers[0][0], "the frame has faces")

    def test_the_city_is_the_same_city(self):
        import citybuilder
        answers = []
        for native in ("off", "on"):
            rules = self._rules(citybuilder, native)
            world = rules.fn["new"]
            ev = {"keys": set(), "mu": 480, "mv": 300}
            for extra in ({"next": 1}, {}, {"build": 1}):
                world = rules.tick(world, dict(ev, **extra))
            answers.append([rules.frame(world), rules.rt.steps,
                            rules.call("cash", world), rules.text(world),
                            rules.cells(world), rules.view_key(world),
                            rules.keys_of(world)])
        self.assertEqual(answers[0], answers[1])
        self.assertTrue(answers[0][4], "a cell was built")


if __name__ == "__main__":
    unittest.main()
