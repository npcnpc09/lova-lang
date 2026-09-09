"""Tests for M9 — abstraction, iteration, and the ceilings they need.

Before M9 a LOVA program was a fixed-depth expression over built-ins:
no user-defined functions, no recursion, no loops.  These tests cover
what changed:

- ``LAMBDA`` / ``APPLY``: unary closures, currying, lexical capture
- ``LET`` as a letrec: self-reference, and therefore recursion
- ``LOOP_UNTIL``: iteration as a combinator, without call depth
- ``MUL`` / ``MOD``: the arithmetic that took over 0x0B / 0x0C
- ``DEVIATION`` / ``THRESHOLD``: ordering, built from the surprise family
- ``DepthTrap`` / ``StepTrap``: non-termination as a structured anomaly
- the Stage-1 sugar (``defn``, call syntax, bare names) and its
  desugaring into core tokens
"""

from __future__ import annotations

import math
import unittest

from core.compiler import CompileError, compile
from core.conservation import BudgetTrap, DepthTrap, StepTrap
from core.generator import GenState
from core.observability import static_analyze
from core.runtime import Closure, LoopFn, Runtime, evaluate
from core.surface import parse, pretty
from core.tokens import (
    APPLY, DEVIATION, LAMBDA, LOOP_UNTIL, MOD, MUL, THRESHOLD, decode, encode,
)
from core.types import FN, INT, VALUE, is_subtype


def run(src: str, rt: Runtime = None):
    """Parse and evaluate a surface program."""
    return evaluate(parse(src), rt)


# --- arithmetic -------------------------------------------------------------

class TestArithmetic(unittest.TestCase):
    """0x0B / 0x0C carry mul / mod since M9 (they were mock-theta stubs)."""

    def test_mul(self):
        self.assertEqual(run("(mul 6 7)"), 42)
        self.assertEqual(run("(mul -3 5)"), -15)

    def test_mul_unicode_alias(self):
        self.assertEqual(run("(⊗ 6 7)"), 42)

    def test_mod(self):
        self.assertEqual(run("(mod 17 5)"), 2)
        self.assertEqual(run("(mod 10 2)"), 0)

    def test_mod_by_zero_is_loud(self):
        # Constraint 5: no silent failures.  A zero divisor is an error,
        # not a quietly-returned zero.
        with self.assertRaises(ValueError):
            run("(mod 3 0)")

    def test_mul_result_is_bounded(self):
        # Nested squaring is the cheapest way for a generated program to
        # ask for an unbounded allocation.
        from core.runtime import MAX_INT_BITS
        big = 2 ** (MAX_INT_BITS // 2 + 1)
        with self.assertRaises(ValueError):
            run(f"(mul {big} {big})")


# --- ordering ---------------------------------------------------------------

class TestOrdering(unittest.TestCase):
    """DEVIATION + THRESHOLD give ordering without new tokens."""

    def test_deviation_is_signed(self):
        self.assertEqual(run("(deviation 3 10)"), -7)
        self.assertEqual(run("(deviation 10 3)"), 7)

    def test_surprise_stays_absolute(self):
        # DEVIATION is the signed sibling; SURPRISE keeps |a - b|.
        self.assertEqual(run("(surprise 3 10)"), 7)

    def test_threshold_is_a_sign_test(self):
        self.assertEqual(run("(threshold 5)"), 1)
        self.assertEqual(run("(threshold 0)"), 0)
        self.assertEqual(run("(threshold -5)"), 0)

    def test_less_than(self):
        # (a < b) == (threshold (deviation b a))
        self.assertEqual(run("(threshold (deviation 5 3))"), 1)
        self.assertEqual(run("(threshold (deviation 3 5))"), 0)
        self.assertEqual(run("(threshold (deviation 3 3))"), 0)

    def test_deviation_emits_no_surprise_event(self):
        # A comparison is not an observation about a prediction.
        rt = Runtime()
        run("(deviation 3 10)", rt)
        self.assertEqual(rt.surprise.events, [])


# --- closures ---------------------------------------------------------------

class TestClosures(unittest.TestCase):

    def test_lambda_evaluates_to_a_closure(self):
        value = run("(lambda 0 (ref 0))")
        self.assertIsInstance(value, Closure)

    def test_apply_one_argument(self):
        self.assertEqual(run("(apply (lambda 0 (mul (ref 0) (ref 0))) 7)"), 49)

    def test_currying(self):
        src = "(apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 3 4)"
        self.assertEqual(run(src), 7)

    def test_partial_application_returns_a_function(self):
        src = "(apply (lambda 0 (lambda 1 (merge (ref 0) (ref 1)))) 3)"
        self.assertIsInstance(run(src), Closure)

    def test_lexical_capture(self):
        # The inner lambda closes over the LET binding, not over whatever
        # happens to be in scope at the call site.
        src = "(let 0 10 (apply (lambda 1 (merge (ref 0) (ref 1))) 5))"
        self.assertEqual(run(src), 15)

    def test_shadowing(self):
        src = "(let 0 1 (apply (lambda 0 (ref 0)) 99))"
        self.assertEqual(run(src), 99)

    def test_binding_is_restored_after_the_call(self):
        src = "(let 0 1 (merge (apply (lambda 0 (ref 0)) 99) (ref 0)))"
        self.assertEqual(run(src), 100)

    def test_apply_on_a_non_function_is_loud(self):
        with self.assertRaises(ValueError):
            evaluate(parse("(apply 5 1)"))


# --- recursion --------------------------------------------------------------

class TestRecursion(unittest.TestCase):
    """LET is a letrec, which is what makes recursion expressible."""

    FACTORIAL = (
        "(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))"
        "(fact {n})"
    )

    def test_factorial(self):
        for n in (0, 1, 5, 10, 20):
            with self.subTest(n=n):
                self.assertEqual(
                    run(self.FACTORIAL.replace("{n}", str(n))),
                    math.factorial(n),
                )

    def test_deep_recursion_within_the_ceiling(self):
        # 150 frames is below MAX_CALL_DEPTH and must not exhaust the
        # host interpreter's stack.
        self.assertEqual(
            run(self.FACTORIAL.replace("{n}", "150")), math.factorial(150)
        )

    def test_fibonacci_tree_recursion(self):
        src = (
            "(defn fib [n]"
            "  (if-surprise (threshold (deviation n 1))"
            "    (merge (fib (merge n -1)) (fib (merge n -2)))"
            "    n))"
            "(fib 15)"
        )
        self.assertEqual(run(src), 610)

    def test_a_definition_sees_earlier_definitions(self):
        src = (
            "(defn double [x] (mul x 2))"
            "(defn quadruple [x] (double (double x)))"
            "(quadruple 5)"
        )
        self.assertEqual(run(src), 20)

    def test_forward_reference_works_since_m12(self):
        # M9 made this an `unbound-ref` compile error; M12 gives a chain
        # of definitions one shared frame, so order stopped mattering.
        src = (
            "(defn f [x] (g x))"
            "(defn g [x] x)"
            "(f 1)"
        )
        node, _ = compile(parse(src))
        self.assertEqual(evaluate(node), 1)

    def test_mutual_recursion(self):
        src = (
            "(defn ev [n] (if-surprise n (od (merge n -1)) 1))"
            "(defn od [n] (if-surprise n (ev (merge n -1)) 0))"
            "(ev {n})"
        )
        for n in (0, 1, 2, 7, 10, 11):
            with self.subTest(n=n):
                node, _ = compile(parse(src.replace("{n}", str(n))))
                self.assertEqual(evaluate(node), 1 if n % 2 == 0 else 0)

    def test_a_reference_to_nothing_is_still_an_error(self):
        # Widening the group must not turn every typo into a runtime
        # failure: a name nobody binds is still caught at compile time.
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(defn f [x] (nope x))(f 1)"))
        self.assertEqual(ctx.exception.anomaly["kind"], "unbound-ref")

    def test_letrec_does_not_change_existing_programs(self):
        # Before M9 a self-reference in a value slot was an unbound-ref
        # error, so nothing that used to compile changes meaning.
        src = "(let 0 12 (merge (p (ref 0)) (tau (ref 0))))"
        self.assertEqual(run(src), evaluate(compile(parse(src))[0]))


class TestBindingGroups(unittest.TestCase):
    """M12 — a chain of LETs shares one environment frame.

    That is what makes mutual recursion work, and the boundaries of
    "a chain" are what keep it from leaking a binding somewhere it does
    not belong.
    """

    def test_a_chain_shares_a_frame(self):
        # `g` is bound after `f`'s closure was built, and `f` still sees it.
        src = ("(let 0 (lambda 9 (apply (ref 1) (ref 9))) "
               "  (let 1 (lambda 9 (ref 9)) (apply (ref 0) 42)))")
        self.assertEqual(run(src), 42)

    def test_shadowing_starts_a_new_frame(self):
        # Re-binding a name the group already holds must not reach back
        # and change what an earlier closure sees.
        src = ("(let 0 1 "
               "  (let 9 (lambda 8 (ref 0)) "
               "    (let 0 2 "
               "      (merge (apply (ref 9) 0) (ref 0)))))")
        # The closure sees the outer 0 (= 1); the body sees the inner (= 2).
        self.assertEqual(run(src), 3)

    def test_a_let_in_argument_position_does_not_extend(self):
        # Only a LET in another LET's *body* joins the group.  Built by
        # hand, because the scope pass rejects the reference that would
        # observe a leak.
        from core.tokens import LET, MERGE, REF, Lit, Node
        inner = Node(op=LET, args=[Lit(7), Lit(1), Node(op=REF, args=[Lit(7)])])
        tree = Node(op=MERGE, args=[inner, Node(op=REF, args=[Lit(7)])])
        with self.assertRaises(ValueError) as ctx:
            evaluate(tree)
        self.assertIn("unbound ref", str(ctx.exception))

    def test_a_let_inside_a_lambda_does_not_extend_the_call_frame(self):
        from core.tokens import LET, MERGE, REF, Lit, Node
        inner = Node(op=LET, args=[Lit(7), Lit(1), Node(op=REF, args=[Lit(7)])])
        body = Node(op=MERGE, args=[inner, Node(op=REF, args=[Lit(7)])])
        tree = parse("(apply (lambda 5 0) 0)")
        tree.args[0].args[1] = body
        with self.assertRaises(ValueError):
            evaluate(tree)

    def test_the_group_widens_what_compiles_and_nothing_else(self):
        # Every program that compiled before still compiles and still
        # means the same thing.
        for src, want in (
            ("(let 0 12 (merge (p (ref 0)) (tau (ref 0))))", 83),
            ("(let 0 1 (let 1 2 (merge (ref 0) (ref 1))))", 3),
            ("(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))"
             "(fact 5)", 120),
        ):
            with self.subTest(src=src):
                self.assertEqual(run(src), want)
                self.assertEqual(evaluate(compile(parse(src))[0]), want)

    def test_a_mutually_recursive_pair_is_not_dropped_as_unused(self):
        # `od` is reachable only from `ev`'s *value*, never from a body,
        # so a body-only liveness check deletes it and the program stops
        # running.  Liveness has to be a fixpoint over the group.
        src = ("(defn ev [n] (if-surprise n (od (merge n -1)) 1))"
               "(defn od [n] (if-surprise n (ev (merge n -1)) 0))"
               "(ev 4)")
        node, report = compile(parse(src))
        self.assertEqual(report.dropped_bindings, 0)
        self.assertEqual(evaluate(node), 1)

    def test_an_unused_mutually_recursive_pair_is_still_dropped(self):
        # Reachability, not mere mention: a pair nothing calls goes, even
        # though each half references the other.
        src = ("(defn ev [n] (od n))"
               "(defn od [n] (ev n))"
               "7")
        node, report = compile(parse(src))
        self.assertEqual(report.dropped_bindings, 2)
        self.assertEqual(evaluate(node), 7)


# --- iteration --------------------------------------------------------------

class TestLoopUntil(unittest.TestCase):

    def test_loop_until_is_a_combinator(self):
        value = run("(loop-until (lambda 0 1) (lambda 0 (ref 0)))")
        self.assertIsInstance(value, LoopFn)

    def test_countdown(self):
        # Subtract 3 until the value drops below 1.
        src = (
            "(apply (loop-until (lambda 0 (threshold (deviation 1 (ref 0))))"
            "                   (lambda 0 (merge (ref 0) -3))) 100)"
        )
        self.assertEqual(run(src), -2)

    def test_predicate_true_at_the_seed_returns_the_seed(self):
        src = "(apply (loop-until (lambda 0 1) (lambda 0 (merge (ref 0) 1))) 7)"
        self.assertEqual(run(src), 7)

    def test_iteration_does_not_consume_call_depth(self):
        # A million rounds of iteration in one frame is the whole point
        # of making loop-until iterative rather than recursive.
        rt = Runtime(max_call_depth=4, max_steps=200_000)
        src = (
            "(apply (loop-until (lambda 0 (threshold (deviation 1 (ref 0))))"
            "                   (lambda 0 (merge (ref 0) -1))) 500)"
        )
        self.assertEqual(evaluate(parse(src), rt), 0)

    def test_non_function_slot_is_loud(self):
        # Not reachable from well-typed source -- both slots are typed Fn
        # -- so build the tree by hand, the way a mutation would.
        from core.tokens import Lit, Node
        with self.assertRaises(ValueError):
            evaluate(Node(op=LOOP_UNTIL, args=[Lit(1), Lit(1)]))


# --- ceilings ---------------------------------------------------------------

class TestCeilings(unittest.TestCase):
    """Non-termination must be an anomaly, not a traceback or a hang."""

    RUNAWAY = "(defn f [x] (f x))(f 1)"
    SPINNER = "(apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1)"

    def test_runaway_recursion_raises_depth_trap(self):
        with self.assertRaises(DepthTrap) as ctx:
            run(self.RUNAWAY)
        self.assertEqual(
            ctx.exception.anomaly["kind"], "recursion-depth-exceeded"
        )

    def test_depth_trap_is_a_budget_trap(self):
        # One error handler covers every ceiling.
        with self.assertRaises(BudgetTrap):
            run(self.RUNAWAY)

    def test_depth_trap_carries_the_l2_anomaly_schema(self):
        with self.assertRaises(DepthTrap) as ctx:
            run(self.RUNAWAY)
        anomaly = ctx.exception.anomaly
        for field in ("kind", "detail", "position_path", "offending_op",
                      "offending_op_name", "valid_alternatives",
                      "repair_hint"):
            self.assertIn(field, anomaly)
        self.assertTrue(anomaly["repair_hint"])
        # The runtime enriches on the innermost frame, as for every trap.
        self.assertTrue(anomaly.get("_enriched"))

    def test_depth_ceiling_is_configurable(self):
        rt = Runtime(max_call_depth=10)
        with self.assertRaises(DepthTrap) as ctx:
            evaluate(parse(self.RUNAWAY), rt)
        self.assertEqual(ctx.exception.anomaly["detail"]["limit"], 10)

    def test_endless_loop_raises_step_trap(self):
        rt = Runtime(max_steps=5_000)
        with self.assertRaises(StepTrap) as ctx:
            evaluate(parse(self.SPINNER), rt)
        self.assertEqual(ctx.exception.anomaly["kind"], "step-limit-exceeded")

    def test_step_ceiling_applies_without_a_declared_budget(self):
        # BUDGET is what a program declares about itself; MAX_STEPS is
        # what the substrate guarantees regardless.
        rt = Runtime(max_steps=100)
        self.assertEqual(rt.budget_stack, [])
        with self.assertRaises(StepTrap):
            evaluate(parse(self.SPINNER), rt)

    def test_terminating_programs_are_unaffected(self):
        rt = Runtime()
        self.assertEqual(evaluate(parse("(mul 6 7)"), rt), 42)
        self.assertLess(rt.steps, 10)


# --- types ------------------------------------------------------------------

class TestFunctionTypes(unittest.TestCase):

    def test_fn_is_disjoint_from_int(self):
        self.assertFalse(is_subtype(FN, INT))
        self.assertFalse(is_subtype(INT, FN))

    def test_value_is_the_top_type(self):
        for t in (INT, FN, VALUE):
            self.assertTrue(is_subtype(t, VALUE))
        self.assertFalse(is_subtype(VALUE, INT))

    def test_int_slot_never_offers_a_function(self):
        valid = GenState.fresh().valid_next()
        self.assertNotIn(LAMBDA, valid)
        self.assertNotIn(LOOP_UNTIL, valid)

    def test_apply_head_slot_offers_functions_and_nothing_typed_otherwise(self):
        # M12 widened this: `(apply (if c f g) x)` chooses between two
        # functions, and `(apply (ref f) x)` calls a bound one.  Both are
        # legitimate, and neither is an Fn *producer* the machine can see.
        from core.tokens import RESULT_NOT_STATIC
        valid = GenState.fresh().step(APPLY).valid_next()
        self.assertLessEqual(frozenset({LAMBDA, LOOP_UNTIL}), valid)
        self.assertLessEqual(valid,
                             frozenset({LAMBDA, LOOP_UNTIL}) | RESULT_NOT_STATIC)
        # An Int producer is still refused.
        from core.tokens import MERGE, P
        self.assertNotIn(MERGE, valid)
        self.assertNotIn(P, valid)

    def test_let_value_slot_accepts_both(self):
        # The one Value slot in the language: a binding may hold either.
        valid = GenState.fresh().step(0x2E).step(0x01).valid_next()
        self.assertIn(LAMBDA, valid)
        self.assertIn(MUL, valid)

    def test_new_arithmetic_is_generation_reachable(self):
        valid = GenState.fresh().valid_next()
        for tok in (MUL, MOD, DEVIATION, THRESHOLD):
            self.assertIn(tok, valid)

    def test_function_in_an_int_slot_is_a_compile_error(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (lambda 0 (ref 0)) 1)"))
        self.assertEqual(ctx.exception.anomaly["kind"], "type-mismatch")

    def test_reference_to_a_function_in_an_int_slot_is_a_compile_error(self):
        # Needs the scope-aware type environment: REF declares Int, but
        # this binding holds an Fn.
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(let 0 (lambda 1 (ref 1)) (merge (ref 0) 1))"))
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "type-mismatch")
        self.assertEqual(anomaly["detail"]["produces"], "Fn")

    def test_reference_to_a_function_in_the_head_slot_type_checks(self):
        node, _ = compile(parse("(let 0 (lambda 1 (mul (ref 1) 2)) (apply (ref 0) 21))"))
        self.assertEqual(evaluate(node), 42)


# --- compiler ---------------------------------------------------------------

class TestCompilerOnAbstraction(unittest.TestCase):

    def test_lambda_parameter_is_in_scope_in_the_body(self):
        node, _ = compile(parse("(apply (lambda 0 (mul (ref 0) 3)) 4)"))
        self.assertEqual(evaluate(node), 12)

    def test_lambda_parameter_is_not_in_scope_outside(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (apply (lambda 0 (ref 0)) 1) (ref 0))"))
        self.assertEqual(ctx.exception.anomaly["kind"], "unbound-ref")

    def test_new_pure_operators_fold(self):
        node, _ = compile(parse("(mul (mod 17 5) (threshold (deviation 5 3)))"))
        self.assertEqual(pretty(node), "2")

    def test_division_by_zero_does_not_fold(self):
        # Folding evaluates; an evaluation that fails leaves the node in
        # place for the runtime to report.
        node, _ = compile(parse("(mod 3 0)"))
        self.assertNotEqual(pretty(node), "0")

    def test_calls_do_not_fold(self):
        src = "(defn f [x] (mul x 2))(f 21)"
        node, report = compile(parse(src))
        self.assertEqual(evaluate(node), 42)
        self.assertGreater(report.compiled_nodes, 1)

    def test_recursive_program_compiles_and_runs(self):
        src = "(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))(fact 6)"
        node, _ = compile(parse(src))
        self.assertEqual(evaluate(node), 720)


# --- observability ----------------------------------------------------------

class TestStaticAnalysisOnAbstraction(unittest.TestCase):

    def test_node_count_stops_being_a_cost_bound(self):
        analysis = static_analyze(parse("(defn f [n] (f n))(f 1)"))
        self.assertFalse(analysis.is_cost_bounded)
        self.assertTrue(analysis.uses_abstraction)
        self.assertIn("unbounded-cost", analysis.effects)

    def test_call_free_programs_stay_bounded(self):
        analysis = static_analyze(parse("(merge (p 3) (tau 12))"))
        self.assertTrue(analysis.is_cost_bounded)
        self.assertFalse(analysis.uses_abstraction)
        self.assertEqual(analysis.budget_upper_bound, analysis.node_count)


# --- surface sugar ----------------------------------------------------------

class TestSugar(unittest.TestCase):
    """All Stage-1 sugar must compile to the existing 64 tokens."""

    def test_defn_desugars_to_let_lambda(self):
        sugared = parse("(defn square [n] (mul n n))(square 5)")
        explicit = parse("(let 0 (lambda 1 (mul (ref 1) (ref 1))) (apply (ref 0) 5))")
        self.assertEqual(sugared, explicit)

    def test_call_sugar_desugars_to_apply(self):
        self.assertEqual(
            parse("(defn f [x] x)(f 1)"),
            parse("(let 0 (lambda 1 (ref 1)) (apply (ref 0) 1))"),
        )

    def test_multi_parameter_defn_curries(self):
        self.assertEqual(
            parse("(defn add [a b] (merge a b))(add 1 2)"),
            parse("(let 0 (lambda 1 (lambda 2 (merge (ref 1) (ref 2))))"
                  "     (apply (ref 0) 1 2))"),
        )

    def test_zero_parameter_defn_is_a_constant(self):
        self.assertEqual(run("(defn answer [] 42)(answer)"), 42)

    def test_symbolic_names_do_not_collide_with_explicit_ids(self):
        # A source that mixes interned identifiers with hand-written
        # numeric ids must not alias the two onto each other.
        node = parse("(defn f [x] (mul x 2))(let 7 5 (f (ref 7)))")
        self.assertEqual(evaluate(node), 10)
        # Interning started above the explicit id, so nothing shadows 7.
        from core.surface import SymbolTable, _explicit_name_ids, _tokenize
        tokens = _tokenize("(defn f [x] (mul x 2))(let 7 5 (f (ref 7)))")
        self.assertEqual(max(_explicit_name_ids(tokens)), 7)
        self.assertEqual(SymbolTable(base=8).intern("f"), 8)

    def test_desugaring_introduces_no_new_tokens(self):
        node = parse("(defn square [n] (mul n n))(square 5)")
        ops = set()

        def collect(n):
            ops.add(n.op)
            if n.op != 0x01:
                for child in n.args:
                    collect(child)

        collect(node)
        for op in ops:
            self.assertLessEqual(op, 0x3F)

    def test_sugar_survives_encode_decode(self):
        node = parse("(defn square [n] (mul n n))(square 5)")
        self.assertEqual(decode(encode(node)), node)

    def test_defn_is_top_level_only(self):
        with self.assertRaises(ValueError):
            parse("(merge (defn f [x] x) 1)")

    def test_definitions_without_an_expression_are_rejected(self):
        with self.assertRaises(ValueError):
            parse("(defn f [x] x)")

    def test_two_top_level_expressions_are_rejected(self):
        with self.assertRaises(ValueError):
            parse("(p 3) (p 4)")

    def test_bare_name_in_an_argument_is_a_reference(self):
        self.assertEqual(
            parse("(defn f [x] (mul x 2))(f 3)"),
            parse("(let 0 (lambda 1 (mul (ref 1) 2)) (apply (ref 0) 3))"),
        )

    def test_typo_reports_as_unbound_ref(self):
        # A misspelled call is a reference to a name nobody bound, which
        # is a better error than "unknown operator" because it comes
        # with the names that are in scope.
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(defn square [n] (mul n n))(sqare 5)"))
        self.assertEqual(ctx.exception.anomaly["kind"], "unbound-ref")

    def test_pretty_prints_the_integer_name(self):
        # Interning is one-way on purpose: the integer is the program.
        self.assertEqual(
            pretty(parse("(defn f [x] x)(f 1)")),
            "(let 0 (lambda 1 (ref 1)) (apply (ref 0) 1))",
        )


if __name__ == "__main__":
    unittest.main()
