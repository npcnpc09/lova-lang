"""Tests for M13 — the error model, made uniform and made reachable.

Two halves:

- **``DomainTrap``.** Division by zero, the head of an empty list, a
  reference to nothing — each raised a bare ``ValueError`` with a
  sentence in it and no ``kind``, so the "one handler for every fault"
  property (Exp 08) actually held for two of four fault classes. All of
  them now carry the L2 anomaly schema. ``DomainTrap`` subclasses
  ``ValueError``, so nothing that caught the old shape breaks.

- **``when-anomaly`` (0x1A).** A program can respond to its own
  anomaly, which Axiom 7 always implied and the language never
  allowed. The handler receives the anomaly's integer code, because a
  handler told nothing can only guess.

One fault is deliberately not catchable: ``StepTrap``. The step ceiling
is the substrate's guarantee that a program terminates, and a guarantee
a program can mask is not one.
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.conservation import (
    ANOMALY_CODES, ANOMALY_KINDS, BudgetTrap, DeltaTrap, DepthTrap,
    DomainTrap, StepTrap, anomaly_code,
)
from core.observability import static_analyze
from core.runtime import Runtime, evaluate, list_to_python
from core.surface import parse
from core.tokens import SIGNATURES, TYPED_TOKENS, WHEN_ANOMALY

L2_FIELDS = ("kind", "detail", "position_path", "offending_op",
             "offending_op_name", "valid_alternatives", "repair_hint")


def run(src: str, rt: Runtime = None):
    return evaluate(parse(src), rt or Runtime())


# --- the fault classes ------------------------------------------------------

class TestDomainTrap(unittest.TestCase):

    FAULTS = {
        "(div 1 0)": "domain-error",
        "(mod 1 0)": "domain-error",
        "(head (nil))": "domain-error",
        "(tail (nil))": "domain-error",
        "(ref 99)": "unbound-ref",
        "(apply 5 1)": "type-violation",
        "(merge (nil) 1)": "type-violation",
        "(stdout (lambda 0 (ref 0)))": "type-violation",
        "(p 99999)": "domain-error",
    }

    def test_every_runtime_fault_carries_a_kind(self):
        for src, kind in self.FAULTS.items():
            with self.subTest(src=src):
                with self.assertRaises(DomainTrap) as ctx:
                    run(src)
                self.assertEqual(ctx.exception.anomaly["kind"], kind)

    def test_every_runtime_fault_carries_the_l2_schema(self):
        for src in self.FAULTS:
            with self.subTest(src=src):
                with self.assertRaises(DomainTrap) as ctx:
                    run(src)
                anomaly = ctx.exception.anomaly
                for field in L2_FIELDS:
                    self.assertIn(field, anomaly)
                self.assertTrue(anomaly["repair_hint"], src)

    def test_domain_trap_is_still_a_value_error(self):
        # Backward compatibility is the point of the subclassing: every
        # handler and test written against the old shape keeps working.
        for src in self.FAULTS:
            with self.subTest(src=src):
                with self.assertRaises(ValueError):
                    run(src)

    def test_the_detail_names_the_operator(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(div 1 0)")
        self.assertEqual(ctx.exception.anomaly["detail"]["operator"], "div")

    def test_unbound_ref_lists_what_is_bound(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(let 3 1 (ref 99))")
        self.assertEqual(ctx.exception.anomaly["detail"]["bound_names"], [3])

    def test_codes_are_distinct_and_stable(self):
        self.assertEqual(len(set(ANOMALY_CODES.values())), len(ANOMALY_CODES))
        self.assertEqual(ANOMALY_KINDS[ANOMALY_CODES["domain-error"]],
                         "domain-error")
        self.assertEqual(anomaly_code({"kind": "nonsense"}), 0)


# --- catching ---------------------------------------------------------------

class TestWhenAnomaly(unittest.TestCase):

    def test_a_clean_body_returns_its_own_value(self):
        self.assertEqual(run("(when-anomaly (div 10 2) (lambda 9 -1))"), 5)

    def test_a_trapping_body_returns_the_handler_value(self):
        self.assertEqual(run("(when-anomaly (div 1 0) (lambda 9 -1))"), -1)

    def test_the_handler_receives_the_anomaly_code(self):
        cases = {
            "(div 1 0)": "domain-error",
            "(ref 99)": "unbound-ref",
            "(budget 2 (merge (p 3) (tau 4)))": "budget-exceeded",
            "(conserve 5 (violate 5))": "conservation-violated",
            "(apply 5 1)": "type-violation",
        }
        for body, kind in cases.items():
            with self.subTest(body=body):
                got = run(f"(when-anomaly {body} (lambda 9 (ref 9)))")
                self.assertEqual(ANOMALY_KINDS[got], kind)

    def test_a_handled_anomaly_is_recorded(self):
        # Caught is not invisible: an agent reading the run afterwards
        # must be able to see what the program swallowed (Axiom 7).
        rt = Runtime()
        run("(try (div 1 0) -1)", rt)
        self.assertEqual([a["kind"] for a in rt.caught], ["domain-error"])

    def test_a_handled_anomaly_reaches_the_surprise_trace(self):
        rt = Runtime()
        run("(try (div 1 0) -1)", rt)
        self.assertEqual([e["ctx"] for e in rt.surprise.events],
                         ["when-anomaly"])

    def test_nothing_is_recorded_when_nothing_trapped(self):
        rt = Runtime()
        run("(try (div 10 2) -1)", rt)
        self.assertEqual(rt.caught, [])

    def test_depth_is_recoverable(self):
        # Running out of stack is a condition a program may reasonably
        # expect, like Python's RecursionError.
        rt = Runtime(max_call_depth=20)
        self.assertEqual(run("(def f [x] (f x))(try (f 1) -1)", rt), -1)
        self.assertEqual(rt.caught[0]["kind"], "recursion-depth-exceeded")

    def test_the_step_ceiling_cannot_be_masked(self):
        # The substrate's termination guarantee is not a condition.
        spin = ("(try (apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1) "
                "999)")
        with self.assertRaises(StepTrap):
            evaluate(parse(spin), Runtime(max_steps=3000))

    def test_nesting(self):
        src = "(try (try (div 1 0) (head (nil))) -2)"
        self.assertEqual(run(src), -2)

    def test_the_handler_may_itself_trap(self):
        with self.assertRaises(DomainTrap):
            run("(when-anomaly (div 1 0) (lambda 9 (head (nil))))")

    def test_a_guard_stands_where_the_unguarded_expression_could(self):
        # The result type follows the body, so wrapping changes nothing
        # about where an expression may appear.
        self.assertEqual(run("(merge (try (div 1 0) 100) 1)"), 101)

    def test_it_can_guard_a_list_expression(self):
        node, _ = compile(parse("(try (tail (nil)) (list 1 2))"))
        self.assertEqual(list_to_python(evaluate(node)), [1, 2])

    def test_a_non_function_handler_is_a_compile_error(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(when-anomaly (div 1 0) 5)"))
        self.assertEqual(ctx.exception.anomaly["kind"], "type-mismatch")


# --- the try macro ----------------------------------------------------------

class TestTryMacro(unittest.TestCase):

    def test_try_expands_to_when_anomaly(self):
        from core.surface import MACROS
        self.assertIn("try", MACROS)
        tree = parse("(try (div 1 0) -1)")
        self.assertEqual(tree.op, WHEN_ANOMALY)

    def test_try_costs_no_new_tokens(self):
        ops = set()

        def collect(node):
            ops.add(node.op)
            if node.op != 0x01:
                for child in node.args:
                    collect(child)

        collect(parse("(try (div 1 0) -1)"))
        for op in ops:
            self.assertIn(op, TYPED_TOKENS)

    def test_the_fallback_may_use_the_enclosing_scope(self):
        self.assertEqual(run("(let 0 7 (try (div 1 0) (ref 0)))"), 7)


# --- static view ------------------------------------------------------------

class TestObservability(unittest.TestCase):

    def test_handling_is_a_declared_effect(self):
        analysis = static_analyze(parse("(try (div 1 0) 0)"))
        self.assertIn("handle-anomaly", analysis.effects)

    def test_a_guarded_program_is_still_deterministic(self):
        self.assertTrue(static_analyze(parse("(try (div 1 0) 0)")).is_deterministic)

    def test_the_slot_was_what_the_table_named_it(self):
        # An activation, not a reallocation: 0x1A was `when-anomaly` in
        # the original table.
        self.assertEqual(SIGNATURES[0x1A]["name"], "when-anomaly")
        self.assertIn(WHEN_ANOMALY, TYPED_TOKENS)


if __name__ == "__main__":
    unittest.main()
