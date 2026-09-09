"""Tests for M14 — programs as values, and Axiom 5 inside the language.

Axiom 1 says a program *is* an integer; Axiom 5 says provenance is
queryable *in the language*; Stage 3's only human interface is
``(explain program)``. Until M14 none of the three was reachable from
inside LOVA, because nothing produced a program as a value. ``quote``
does; ``eval`` runs one; the Meta family asks about one; ``clone`` and
``mutate`` derive one and record how.
"""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.conservation import DomainTrap, StepTrap
from core.generator import GenState, completion_cost
from core.observability import static_analyze
from core.runtime import (
    Runtime, evaluate, is_program_value, list_to_python,
)
from core.surface import parse, parse_with_prelude, pretty
from core.tokens import (
    EVAL, LIT_INT, MERGE, Node, QUOTE, SIGNATURES, TYPED_TOKENS, decode,
    encode,
)
from core.types import INT, LIST, PROGRAM, VALUE, is_subtype


def run(src: str, rt: Runtime = None):
    node, _ = compile(parse(src))
    return evaluate(node, rt or Runtime())


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


# --- quote / eval -----------------------------------------------------------

class TestQuoteEval(unittest.TestCase):

    def test_quote_yields_the_tree_unevaluated(self):
        value = run("(quote (merge 1 2))")
        self.assertTrue(is_program_value(value))
        self.assertEqual(value, parse("(merge 1 2)"))

    def test_quote_copies(self):
        # Registering or mutating the value must never reach back into the
        # program that contains the quote.
        outer = parse("(quote (merge 1 2))")
        value = evaluate(outer)
        self.assertIsNot(value, outer.args[0])

    def test_eval_runs_it(self):
        self.assertEqual(run("(eval (quote (merge 1 2)))"), 3)

    def test_eval_sees_the_current_environment(self):
        self.assertEqual(run("(let 0 40 (eval (quote (merge (ref 0) 2))))"), 42)

    def test_eval_result_follows_the_context(self):
        # A conditional returning a list, evaluated, still fits a List slot.
        value = run("(head (eval (quote (list 7 8))))")
        self.assertEqual(value, 7)

    def test_eval_charges_the_run(self):
        rt = Runtime()
        run("(eval (quote (merge 1 2)))", rt)
        self.assertGreater(rt.steps, 3)

    def test_eval_cannot_escape_the_step_ceiling(self):
        spin = "(eval (quote (apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1)))"
        with self.assertRaises(StepTrap):
            evaluate(parse(spin), Runtime(max_steps=2000))

    def test_eval_of_a_non_program_is_loud(self):
        with self.assertRaises(DomainTrap) as ctx:
            evaluate(Node(op=EVAL, args=[Node(op=LIT_INT, args=[5])]))
        self.assertEqual(ctx.exception.anomaly["kind"], "type-violation")

    def test_a_quoted_unbound_reference_fails_at_eval_time(self):
        # Data until evaluated; its references are resolved then.
        compile(parse("(quote (ref 99))"))           # compiles
        with self.assertRaises(DomainTrap) as ctx:
            run("(eval (quote (ref 99)))")            # runs, and says why
        self.assertEqual(ctx.exception.anomaly["kind"], "unbound-ref")


# --- the compiler leaves quoted code alone ----------------------------------

class TestQuoteIsOpaque(unittest.TestCase):

    def test_not_folded(self):
        # The value is the tree, not its result: folding would change
        # what `hash` and `explain` report.
        node, _ = compile(parse("(quote (merge 1 2))"))
        self.assertEqual(node, parse("(quote (merge 1 2))"))
        self.assertEqual(text(run("(explain (quote (merge 1 2)))")),
                         "(merge 1 2)")

    def test_not_rewritten_by_drop_unused(self):
        node, _ = compile(parse("(quote (let 0 5 7))"))
        self.assertEqual(node, parse("(quote (let 0 5 7))"))

    def test_references_inside_keep_a_binding_alive(self):
        # Conservative: the quoted program may be evaluated.
        node, report = compile(parse("(let 0 5 (eval (quote (ref 0))))"))
        self.assertEqual(report.dropped_bindings, 0)
        self.assertEqual(evaluate(node), 5)

    def test_quoting_has_no_effect_even_if_the_code_does(self):
        _node, report = compile(parse("(let 0 (quote (stdout 5)) 7)"))
        self.assertEqual(report.dropped_bindings, 1)

    def test_the_quoted_body_must_still_be_well_formed(self):
        with self.assertRaises(CompileError):
            compile(parse("(quote (merge (nil) 1))"))

    def test_a_program_in_an_int_slot_is_a_compile_error(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(merge (quote 1) 2)"))
        self.assertEqual(ctx.exception.anomaly["detail"]["produces"], "Program")


# --- Axiom 1, reachable -----------------------------------------------------

class TestHashAndExplain(unittest.TestCase):

    def test_hash_is_the_encoding_as_an_integer(self):
        program = parse("(merge (p 3) (tau 12))")
        self.assertEqual(run("(hash (quote (merge (p 3) (tau 12))))"),
                         int.from_bytes(encode(program), "big"))

    def test_hash_reproduces_experiment_01(self):
        # The integer Exp 01 quoted as the proof of Axiom 1, now produced
        # from inside the language.
        self.assertEqual(run("(hash (quote (merge (p 3) (tau 12))))"),
                         55916975560956379404)

    def test_explain_is_the_stage1_projection(self):
        for src in ("(merge (p 3) (tau 12))",
                    "(let 0 12 (p (ref 0)))",
                    "(if-surprise 1 2 3)"):
            with self.subTest(src=src):
                self.assertEqual(text(run(f"(explain (quote {src}))")),
                                 pretty(parse(src)))

    def test_explain_can_be_written_out(self):
        rt = Runtime()
        run("(stdout (explain (quote (merge 1 2))))", rt)
        self.assertEqual(rt.written(), "(merge 1 2)")

    def test_a_program_cannot_be_written_directly(self):
        with self.assertRaises(DomainTrap) as ctx:
            run("(stdout (quote 1))")
        self.assertIn("explain", ctx.exception.anomaly["repair_hint"])


# --- Axiom 5, in the language -----------------------------------------------

class TestLineage(unittest.TestCase):

    def test_a_fresh_quote_has_no_history(self):
        self.assertEqual(run("(uid (quote 1))"), 0)
        self.assertEqual(run("(generation (quote 1))"), 0)
        self.assertEqual(list_to_python(run("(lineage-query (quote 1))")), [])
        self.assertEqual(text(run("(why (quote 1))")), "unregistered")

    def test_clone_registers_and_derives(self):
        src = "(let 0 (quote (merge 1 2)) (let 1 (clone (ref 0)) {q}))"
        self.assertEqual(run(src.replace("{q}", "(uid (ref 0))")), 1)
        self.assertEqual(run(src.replace("{q}", "(uid (ref 1))")), 2)
        self.assertEqual(run(src.replace("{q}", "(generation (ref 1))")), 1)
        self.assertEqual(run(src.replace("{q}", "(ancestor-of (ref 0) (ref 1))")), 1)
        self.assertEqual(run(src.replace("{q}", "(ancestor-of (ref 1) (ref 0))")), 0)
        self.assertEqual(text(run(src.replace("{q}", "(why (ref 1))"))), "clone")

    def test_a_clone_is_the_same_program(self):
        self.assertEqual(run("(eval (clone (quote (merge 1 2))))"), 3)
        self.assertEqual(
            text(run("(explain (clone (quote (merge 1 2))))")), "(merge 1 2)")

    def test_lineage_query_walks_to_the_root(self):
        src = ("(let 0 (quote 5) (let 1 (mutate (ref 0) 30) "
               "(let 2 (mutate (ref 1) 30) (lineage-query (ref 2)))))")
        self.assertEqual(list_to_python(run(src)), [3, 2, 1])

    def test_generation_counts_derivations(self):
        src = "(let 0 (quote 5) (generation (mutate (mutate (ref 0) 30) 30)))"
        self.assertEqual(run(src), 2)

    def test_why_records_the_mutation(self):
        why = text(run("(why (mutate (quote (merge 1 2)) 50))"))
        self.assertTrue(why.startswith("mutate"))
        self.assertIn("strength=0.5", why)

    def test_mutate_strength_is_a_percentage(self):
        with self.assertRaises(DomainTrap):
            run("(mutate (quote 1) 150)")

    def test_mutate_is_reproducible(self):
        # Same store seed, same mutation: a derivation can be replayed
        # from the run that made it.
        src = "(explain (mutate (quote (merge (p 3) (tau 4))) 100))"
        self.assertEqual(text(run(src)), text(run(src)))

    def test_lineage_is_per_run(self):
        # Two runs do not share a store: uids restart.
        self.assertEqual(run("(uid (clone (quote 1)))"), 2)
        self.assertEqual(run("(uid (clone (quote 1)))"), 2)


# --- trace ------------------------------------------------------------------

class TestTrace(unittest.TestCase):

    def test_trace_returns_the_deviations(self):
        src = "(trace (quote (seq (surprise 3 10) (surprise 5 5) (surprise 0 2))))"
        self.assertEqual(list_to_python(run(src)), [7, 0, 2])

    def test_trace_runs_in_a_sandbox(self):
        # Nothing the traced program writes reaches this run's trace.
        rt = Runtime()
        run("(trace (quote (surprise 1 2)))", rt)
        self.assertEqual(rt.surprise.events, [])

    def test_trace_sees_the_environment(self):
        self.assertEqual(
            list_to_python(run("(let 0 9 (trace (quote (surprise (ref 0) 0))))")),
            [9])

    def test_trace_charges_its_steps_to_the_run(self):
        rt = Runtime()
        run("(trace (quote (merge 1 2)))", rt)
        self.assertGreater(rt.steps, 4)

    def test_nested_traces_cannot_escape_the_ceiling(self):
        spin = ("(trace (quote (apply (loop-until (lambda 0 0) "
                "(lambda 0 (ref 0))) 1)))")
        with self.assertRaises(StepTrap):
            evaluate(parse(spin), Runtime(max_steps=2000))


# --- types and generation ---------------------------------------------------

class TestProgramType(unittest.TestCase):

    def test_program_is_disjoint(self):
        for other in (INT, LIST):
            self.assertFalse(is_subtype(PROGRAM, other))
            self.assertFalse(is_subtype(other, PROGRAM))
        self.assertTrue(is_subtype(PROGRAM, VALUE))

    def test_a_program_slot_offers_program_producers(self):
        from core.tokens import CLONE, MUTATE, RESULT_NOT_STATIC, SELECT, VARIANT
        valid = GenState.fresh().step(0x3C).valid_next()     # hash's slot
        producers = frozenset({QUOTE, CLONE, MUTATE, VARIANT, SELECT})
        self.assertLessEqual(producers, valid)
        self.assertLessEqual(valid, producers | RESULT_NOT_STATIC)
        self.assertNotIn(MERGE, valid)

    def test_generation_can_close_a_program_slot(self):
        self.assertEqual(completion_cost(PROGRAM), 2)       # quote + a literal

    def test_a_quoted_program_survives_the_bytes(self):
        tree = parse("(explain (quote (merge (p 3) (tau 12))))")
        self.assertEqual(decode(encode(tree)), tree)


# --- static view ------------------------------------------------------------

class TestObservability(unittest.TestCase):

    def test_eval_is_an_unbounded_effect(self):
        analysis = static_analyze(parse("(eval (quote 1))"))
        self.assertIn("eval", analysis.effects)
        self.assertFalse(analysis.is_cost_bounded)

    def test_quote_is_pure(self):
        analysis = static_analyze(parse("(quote (stdout 1))"))
        self.assertNotIn("write-stdout", analysis.effects)

    def test_lineage_operators_count_as_lineage_use(self):
        self.assertTrue(static_analyze(parse("(uid (quote 1))")).uses_lineage)

    def test_the_slots(self):
        for byte, name in ((0x29, "quote"), (0x1C, "eval"), (0x3B, "explain"),
                           (0x3C, "hash"), (0x3D, "uid"), (0x38, "lineage-query"),
                           (0x39, "why"), (0x3A, "trace"), (0x3E, "ancestor-of"),
                           (0x3F, "generation"), (0x25, "clone"), (0x24, "mutate")):
            self.assertEqual(SIGNATURES[byte]["name"], name)
            self.assertIn(byte, TYPED_TOKENS)


# --- the prelude ruling -----------------------------------------------------

class TestNthIsLoud(unittest.TestCase):

    def test_nth_in_range(self):
        node, _ = compile(parse_with_prelude("(nth (list 7 8 9) 2)"))
        self.assertEqual(evaluate(node), 9)

    def test_nth_past_the_end_is_a_domain_error_not_a_zero(self):
        node, _ = compile(parse_with_prelude("(nth (list 7 8 9) 5)"))
        with self.assertRaises(DomainTrap) as ctx:
            evaluate(node)
        self.assertEqual(ctx.exception.anomaly["kind"], "domain-error")


if __name__ == "__main__":
    unittest.main()
