"""Tests for M19 — the world, under a declared boundary.

``external-boundary`` (0x30) declares, as a literal bitmask, which
effects its body may use; ``fs-read`` / ``fs-write`` (0x33 / 0x34) and
``clock`` (0x37) are the effects.  Axiom 4 asks for effect bounds in the
signature, checked at the declaration site and at run time: the
compiler's capability pass refuses a use outside a boundary that
declares it, and the runtime traps a boundary the host did not grant.
The boundary is lexical -- a closure keeps the capabilities of the
place it was written -- which is the only rule a static pass can
enforce, so it is the rule the runtime keeps too.

Nothing is granted by default: a test, an experiment, or a generated
program cannot touch the world by accident.  The CLI grants with
``--allow``.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest

from core.cli import main as cli_main, parse_allow
from core.compiler import CompileError, compile
from core.conservation import ANOMALY_CODES, DomainTrap
from core.generator import GenState, constrained_random, validates
from core.observability import static_analyze
from core.runtime import Runtime, evaluate, list_to_python
from core.surface import parse, pretty
from core.tokens import (
    ALL_CAPABILITIES, CAPABILITY_BITS, CLOCK, EXTERNAL_BOUNDARY, FS_READ,
    FS_WRITE, LIT_INT, RESULT_FOLLOWS_OPERANDS, SIGNATURES, TYPED_TOKENS,
    capability_names, decode, encode,
)
from core.types import INT, LIST


def run(src: str, **runtime_kw):
    return evaluate(compile(parse(src))[0], Runtime(**runtime_kw))


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


def fs_path(directory: str, name: str) -> str:
    # A path inside a LOVA string; forward slashes read the same on
    # every platform and need no escaping.
    return os.path.join(directory, name).replace(os.sep, "/")


class TestSlots(unittest.TestCase):

    def test_io_activated_its_own_slots(self):
        # Activations, not reallocations: the original table named them.
        self.assertEqual(SIGNATURES[0x30]["name"], "external-boundary")
        self.assertEqual(SIGNATURES[0x33]["name"], "fs-read")
        self.assertEqual(SIGNATURES[0x34]["name"], "fs-write")
        self.assertEqual(SIGNATURES[0x37]["name"], "clock")
        for token in (EXTERNAL_BOUNDARY, FS_READ, FS_WRITE, CLOCK):
            self.assertIn(token, TYPED_TOKENS)

    def test_the_boundary_is_transparent(self):
        self.assertIn(EXTERNAL_BOUNDARY, RESULT_FOLLOWS_OPERANDS)

    def test_capability_bits_are_distinct(self):
        bits = list(CAPABILITY_BITS.values())
        self.assertEqual(len(set(bits)), len(bits))
        self.assertEqual(capability_names(5), ["fs-read", "clock"])
        self.assertEqual(capability_names(0), [])
        self.assertEqual(ALL_CAPABILITIES, 7)      # net is reserved, not granted by `all`

    def test_capability_denied_has_a_code(self):
        self.assertEqual(ANOMALY_CODES["capability-denied"], 9)


class TestSurface(unittest.TestCase):

    def test_boundary_names_become_a_mask(self):
        self.assertEqual(pretty(parse('(boundary "fs-read clock" 1)')),
                         "(external-boundary 5 1)")
        self.assertEqual(pretty(parse('(boundary "fs-write" 1)')),
                         "(external-boundary 2 1)")

    def test_boundary_accepts_a_literal_mask(self):
        # What `explain` prints and `read` reads back.
        self.assertEqual(pretty(parse("(boundary 5 1)")), "(external-boundary 5 1)")

    def test_an_unknown_capability_is_a_parse_error(self):
        with self.assertRaises(ValueError):
            parse('(boundary "teleport" 1)')

    def test_the_boundary_survives_the_bytes(self):
        tree = parse('(boundary "clock" (merge (clock) 1))')
        self.assertEqual(decode(encode(tree)), tree)


class TestStaticCheck(unittest.TestCase):

    def test_an_undeclared_effect_is_a_compile_error(self):
        for src in ("(clock)", '(fs-read "x")', '(fs-write "x" "y")',
                    "(merge 1 (clock))"):
            with self.subTest(src=src):
                with self.assertRaises(CompileError) as ctx:
                    compile(parse(src))
                self.assertEqual(ctx.exception.anomaly["kind"], "capability-denied")

    def test_a_declared_effect_compiles(self):
        compile(parse('(boundary "clock" (clock))'))
        compile(parse('(boundary "fs-read fs-write" (fs-write "a" (fs-read "b")))'))

    def test_the_wrong_declaration_does_not_cover(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse('(boundary "fs-read" (clock))'))
        detail = ctx.exception.anomaly["detail"]
        self.assertEqual(detail["needs"], "clock")
        self.assertEqual(detail["declared"], ["fs-read"])

    def test_the_boundary_is_lexical(self):
        # A lambda written inside may use the world wherever it is
        # applied; one written outside may not, even if applied inside.
        compile(parse('(apply (boundary "clock" (lambda 9 (clock))) 0)'))
        with self.assertRaises(CompileError):
            compile(parse('(let 0 (lambda 9 (clock)) (boundary "clock" (apply (ref 0) 0)))'))

    def test_an_inner_boundary_replaces_the_outer(self):
        with self.assertRaises(CompileError):
            compile(parse('(boundary "clock" (boundary "fs-read" (clock)))'))

    def test_an_unused_binding_still_has_to_declare(self):
        # Checked before drop-unused: a program that lies about its
        # effects is refused even where the lie would be dropped.
        with self.assertRaises(CompileError):
            compile(parse("(let 0 (clock) 1)"))

    def test_quoted_code_is_data(self):
        compile(parse("(quote (clock))"))
        compile(parse("(hash (quote (clock)))"))

    def test_the_pass_is_reported(self):
        _tree, report = compile(parse("1"))
        self.assertIn("capability-check", report.passes)


class TestRuntimeCheck(unittest.TestCase):

    def test_nothing_is_granted_by_default(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(boundary "clock" (clock))')
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "capability-denied")
        self.assertEqual(anomaly["detail"]["missing"], ["clock"])

    def test_the_boundary_traps_before_the_body_runs(self):
        calls = []
        with self.assertRaises(DomainTrap):
            run('(boundary "clock" (clock))', clock=lambda: calls.append(1) or 1)
        self.assertEqual(calls, [])

    def test_a_granted_boundary_runs(self):
        self.assertEqual(run('(boundary "clock" (clock))', granted=4, clock=lambda: 1234), 1234)

    def test_a_partial_grant_is_a_trap(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(boundary "fs-read clock" 1)', granted=4)
        self.assertEqual(ctx.exception.anomaly["detail"]["missing"], ["fs-read"])

    def test_the_trap_is_catchable_and_has_code_9(self):
        self.assertEqual(
            run('(when-anomaly (boundary "clock" (clock)) (lambda 9 (ref 9)))'), 9)

    def test_a_closure_keeps_its_boundary(self):
        self.assertEqual(
            run('(apply (boundary "clock" (lambda 9 (clock))) 0)', granted=4, clock=lambda: 7),
            7)

    def test_evaluated_code_is_checked_at_run_time(self):
        # The static pass cannot see inside a quote; the runtime can.
        with self.assertRaises(DomainTrap) as ctx:
            run("(eval (quote (clock)))", granted=4)
        self.assertEqual(ctx.exception.anomaly["kind"], "capability-denied")
        self.assertEqual(
            run('(boundary "clock" (eval (quote (clock))))', granted=4, clock=lambda: 5), 5)

    def test_read_text_is_checked_at_run_time(self):
        self.assertEqual(
            run('(boundary "clock" (eval (read "(clock)")))', granted=4, clock=lambda: 3), 3)
        with self.assertRaises(DomainTrap):
            run('(eval (read "(clock)"))', granted=4)

    def test_the_real_clock_is_milliseconds(self):
        import time
        before = time.time_ns() // 1_000_000
        value = run('(boundary "clock" (clock))', granted=4)
        after = time.time_ns() // 1_000_000
        self.assertTrue(before <= value <= after)


class TestFilesystem(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_then_read(self):
        path = fs_path(self.dir, "note.txt")
        self.assertEqual(run(f'(boundary "fs-write" (fs-write "{path}" "hello"))', granted=2), 5)
        self.assertEqual(text(run(f'(boundary "fs-read" (fs-read "{path}"))', granted=1)), "hello")

    def test_a_round_trip_keeps_newlines(self):
        path = fs_path(self.dir, "lines.txt")
        src = (f'(boundary "fs-read fs-write" '
               f'(seq (fs-write "{path}" (list 97 10 98 10)) (fs-read "{path}")))')
        self.assertEqual(text(run(src, granted=3)), "a\nb\n")

    def test_an_integer_writes_as_digits(self):
        path = fs_path(self.dir, "n.txt")
        run(f'(boundary "fs-write" (fs-write "{path}" 42))', granted=2)
        with open(os.path.join(self.dir, "n.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "42")

    def test_a_missing_file_is_a_domain_error(self):
        path = fs_path(self.dir, "absent.txt")
        with self.assertRaises(DomainTrap) as ctx:
            run(f'(boundary "fs-read" (fs-read "{path}"))', granted=1)
        self.assertEqual(ctx.exception.anomaly["kind"], "domain-error")
        self.assertEqual(ctx.exception.anomaly["detail"]["operator"], "fs-read")

    def test_reading_needs_its_own_bit(self):
        path = fs_path(self.dir, "x.txt")
        with self.assertRaises(CompileError):
            compile(parse(f'(boundary "fs-write" (fs-read "{path}"))'))

    def test_a_program_can_write_itself_and_read_it_back(self):
        path = fs_path(self.dir, "p.lova")
        src = (f'(boundary "fs-read fs-write" '
               f'(seq (fs-write "{path}" (explain (quote (mul 6 7)))) '
               f'(eval (read (fs-read "{path}")))))')
        self.assertEqual(run(src, granted=3), 42)


class TestEffects(unittest.TestCase):

    def test_effects_are_declared(self):
        effects = static_analyze(
            parse('(boundary "fs-read fs-write clock" (seq (fs-write "a" (fs-read "b")) (clock)))')).effects
        self.assertTrue({"read-fs", "write-fs", "read-clock"} <= effects)

    def test_reading_the_world_is_non_deterministic(self):
        self.assertFalse(static_analyze(parse('(boundary "clock" (clock))')).is_deterministic)
        self.assertFalse(static_analyze(parse('(boundary "fs-read" (fs-read "a"))')).is_deterministic)
        self.assertTrue(static_analyze(parse('(boundary "fs-write" (fs-write "a" "b"))')).is_deterministic)

    def test_declaring_is_pure(self):
        self.assertEqual(static_analyze(parse('(boundary "clock" 1)')).effects, frozenset())


class TestGeneration(unittest.TestCase):

    def test_the_world_is_not_offered_outside_a_boundary(self):
        self.assertNotIn(CLOCK, GenState.fresh(INT).valid_next())
        self.assertNotIn(FS_READ, GenState.fresh(LIST).valid_next())

    def test_the_world_is_offered_inside_a_declaring_boundary(self):
        inside = GenState.fresh(INT).step(EXTERNAL_BOUNDARY).step(LIT_INT, 4)
        self.assertIn(CLOCK, inside.valid_next())
        other = GenState.fresh(INT).step(EXTERNAL_BOUNDARY).step(LIT_INT, 1)
        self.assertNotIn(CLOCK, other.valid_next())

    def test_children_inherit_the_declaration(self):
        state = (GenState.fresh(INT).step(EXTERNAL_BOUNDARY).step(LIT_INT, 4)
                 .step(0x03))                                   # merge
        self.assertIn(CLOCK, state.valid_next())

    def test_the_declaration_ends_with_the_boundary(self):
        state = (GenState.fresh(INT).step(0x03)                 # merge
                 .step(EXTERNAL_BOUNDARY).step(LIT_INT, 4).step(CLOCK))
        self.assertNotIn(CLOCK, state.valid_next())            # merge's second slot

    def test_validates_agrees_with_the_compiler(self):
        self.assertTrue(validates(encode(parse('(boundary "clock" (clock))'))))
        self.assertFalse(validates(encode(parse("(clock)"))))
        self.assertFalse(validates(encode(parse('(boundary "fs-read" (clock))'))))

    def test_the_caps_literal_is_a_small_mask(self):
        import random
        state = GenState.fresh(INT).step(EXTERNAL_BOUNDARY)
        self.assertEqual(state.stack[-1].role, "caps")
        for seed in range(20):
            self.assertIn(state.literal_for(random.Random(seed)), range(8))

    def test_generation_still_terminates_and_validates(self):
        self.assertTrue(all(validates(constrained_random(seed=s, max_depth=6))
                            for s in range(200)))


class TestCLI(unittest.TestCase):

    def _capture(self, argv, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli_main(argv)
        finally:
            sys.stdin = saved_stdin
        return code, out.getvalue(), err.getvalue()

    def test_parse_allow(self):
        self.assertEqual(parse_allow(None), 0)
        self.assertEqual(parse_allow(["fs-read,clock"]), 5)
        self.assertEqual(parse_allow(["fs-read", "clock"]), 5)
        self.assertEqual(parse_allow(["all"]), ALL_CAPABILITIES)
        with self.assertRaises(ValueError):
            parse_allow(["teleport"])

    def test_a_program_needs_the_grant(self):
        code, _out, err = self._capture(
            ["run", "-", "--no-prelude"], stdin_text='(boundary "clock" (clock))')
        self.assertEqual(code, 2)
        self.assertIn("capability-denied", err)
        self.assertIn("--allow clock", err)

    def test_the_grant_lets_it_run(self):
        code, _out, err = self._capture(
            ["run", "-", "--no-prelude", "--allow", "clock"],
            stdin_text='(boundary "clock" (gt (clock) 0))')
        self.assertEqual(code, 0)
        self.assertIn("=> 1", err)

    def test_an_undeclared_use_is_refused_before_running(self):
        code, _out, err = self._capture(
            ["run", "-", "--no-prelude", "--allow", "clock"], stdin_text="(clock)")
        self.assertEqual(code, 2)
        self.assertIn("capability-denied", err)

    def test_an_unknown_grant_is_an_error(self):
        code, _out, err = self._capture(
            ["run", "-", "--no-prelude", "--allow", "teleport"], stdin_text="1")
        self.assertNotEqual(code, 0)
        self.assertIn("teleport", err)


if __name__ == "__main__":
    unittest.main()
