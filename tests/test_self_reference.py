"""Q79 -- a strict self-reference in a `let` group is refused before it
runs, by the compiler and by the generator, and reported by name.

The runtime installs a binding after its value exists, so a reference
to a group member from inside a value that is evaluated strictly is
unbound at run time.  Under a lambda it is the letrec every recursive
function needs.  Until Q79 the compiler accepted both and the strict
one trapped at run time with an integer for a name; `guess.lova` met
it by hand and Exp 16's re-run counted it at 8/1000 generated programs.
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
from core.generator import GenState, validates
from core.surface import parse
from core.tokens import APPLY, LAMBDA, LET, LIT_INT, MERGE, REF, encode


def _verdict(src: str):
    try:
        lova_compile(parse(src))
        return "compiles"
    except CompileError as exc:
        return exc.anomaly["kind"], exc.anomaly["detail"].get("reason")


class Compiler(unittest.TestCase):

    def test_a_strict_self_reference_is_refused(self):
        self.assertEqual(_verdict("(let 0 (merge (ref 0) 1) 0)"),
                         ("unbound-ref", "strict-self-reference"))

    def test_a_reference_under_a_lambda_is_a_letrec(self):
        self.assertEqual(_verdict("(let 0 (lambda 1 (apply (ref 0) (ref 1))) 5)"),
                         "compiles")

    def test_a_strict_reference_to_a_later_member_is_refused(self):
        self.assertEqual(_verdict("(let 0 (ref 1) (let 1 2 (ref 0)))"),
                         ("unbound-ref", "strict-self-reference"))

    def test_an_earlier_member_is_installed_and_may_be_used(self):
        self.assertEqual(_verdict("(let 0 2 (let 1 (merge (ref 0) 1) (ref 1)))"),
                         "compiles")

    def test_mutual_recursion_still_compiles(self):
        src = ("(def ev [n] (if n (od (sub n 1)) 1))"
               "(def od [n] (if n (ev (sub n 1)) 0))(ev 4)")
        self.assertEqual(_verdict(src), "compiles")

    def test_a_zero_parameter_def_that_calls_itself_is_refused_by_name(self):
        # `(def f [] body)` is a constant, evaluated where it is defined.
        verdict = _verdict("(def f [] (merge (f) 1))(f)")
        self.assertEqual(verdict, ("unbound-ref", "strict-self-reference"))

    def test_the_repair_hint_says_what_to_do(self):
        with self.assertRaises(CompileError) as ctx:
            lova_compile(parse("(let 0 (merge (ref 0) 1) 0)"))
        self.assertIn("under a `lambda`", ctx.exception.anomaly["repair_hint"])


class Generator(unittest.TestCase):
    """The state machine does not offer a pending name, except under a
    lambda opened inside the value."""

    def test_the_binding_is_not_offered_inside_its_own_value(self):
        # (let 0 (merge _ ...: no name fits, so `ref` is not even offered.
        state = GenState.fresh().step(LET).step(LIT_INT, 0).step(MERGE)
        self.assertNotIn(REF, state.valid_next())

    def test_the_binding_is_offered_under_a_lambda(self):
        # (let 0 (lambda 1 (apply _ ...: the head slot wants an Fn, and
        # the binding is one; under the lambda it may name itself.
        state = (GenState.fresh().step(LET).step(LIT_INT, 0)
                 .step(LAMBDA).step(LIT_INT, 1).step(APPLY).step(REF))
        self.assertIn(0, state.valid_names())

    def test_the_binding_is_offered_in_the_body(self):
        state = GenState.fresh().step(LET).step(LIT_INT, 0).step(LIT_INT, 7)
        state = state.step(REF)                            # body: (ref _
        self.assertEqual(state.valid_names(), [0])

    def test_validates_rejects_a_strict_self_reference(self):
        tree = parse("(let 0 (merge (ref 0) 1) 0)")
        self.assertFalse(validates(encode(tree)))
        self.assertTrue(validates(encode(parse("(let 0 7 (merge (ref 0) 1))"))))


class CommandLine(unittest.TestCase):

    def test_the_report_names_the_binding(self):
        fd, path = tempfile.mkstemp(suffix=".lova")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("(def read-guess [] (merge (read-guess) 1))(read-guess)")
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["run", path])
        finally:
            os.remove(path)
        self.assertNotEqual(code, 0)
        self.assertIn("unbound-ref", err.getvalue())
        self.assertIn("'name': 'read-guess'", err.getvalue())
        self.assertIn("strict-self-reference", err.getvalue())


if __name__ == "__main__":
    unittest.main()
