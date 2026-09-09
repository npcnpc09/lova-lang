"""Unit tests for ``core.compiler`` — scope / type / fold passes."""

from __future__ import annotations

import unittest

from core.compiler import CompileError, compile
from core.runtime import evaluate
from core.surface import parse, pretty
from core.tokens import LIT_INT


class CompileApiBasics(unittest.TestCase):

    def test_returns_node_and_report(self):
        tree = parse("(merge (p 3) (tau 12))")
        compiled, report = compile(tree)
        self.assertIsNotNone(compiled)
        self.assertGreaterEqual(report.original_nodes, report.compiled_nodes)

    def test_compile_produces_literal_on_pure_program(self):
        tree = parse("(merge (p 3) (tau 12))")
        compiled, _ = compile(tree)
        self.assertEqual(compiled.op, LIT_INT)
        self.assertEqual(compiled.args[0], 9)

    def test_compile_preserves_semantics(self):
        for src in (
            "(p 12)",
            "(gcd 12 18)",
            "(merge (p 3) (tau 12))",
            "(let 0 10 (merge (tau (ref 0)) (sigma (ref 0))))",
            "(seq (p 3) (p 4) (p 5))",
        ):
            with self.subTest(src=src):
                compiled, _ = compile(parse(src))
                self.assertEqual(evaluate(parse(src)), evaluate(compiled))


class ScopeCheck(unittest.TestCase):

    def test_let_ref_valid_binding_compiles(self):
        compile(parse("(let 0 5 (ref 0))"))

    def test_unbound_ref_raises_compile_error(self):
        with self.assertRaises(CompileError) as ctx:
            compile(parse("(ref 99)"))
        a = ctx.exception.anomaly
        self.assertEqual(a["kind"], "unbound-ref")
        self.assertEqual(a["stage"], "compile")
        self.assertEqual(a["detail"]["name_id"], 99)
        self.assertIn("repair_hint", a)

    def test_nested_let_bindings(self):
        compile(parse("(let 0 5 (let 1 7 (merge (ref 0) (ref 1))))"))

    def test_ref_in_value_slot_uses_outer_env(self):
        # (let 1 5 (let 2 (ref 1) (ref 2)))  -- ref 1 needs outer binding
        # Here we wrap in an outer let so ref 1 is bound.
        compile(parse("(let 1 5 (let 2 (ref 1) (ref 2)))"))

    def test_ref_outside_of_let_unbound(self):
        with self.assertRaises(CompileError):
            compile(parse("(merge (ref 0) (p 3))"))


class TypeCheck(unittest.TestCase):

    def test_let_name_non_literal_rejected(self):
        """LET's name slot demands LiteralInt; computed int rejected."""
        # Build manually since parse won't accept a non-literal name.
        from core.tokens import Node, LET, P, Lit
        # (let (p 3) 5 (p 3))  -- name slot is (p 3), not a literal
        bad = Node(op=LET, args=[
            Node(op=P, args=[Lit(3)]),
            Lit(5),
            Node(op=P, args=[Lit(3)]),
        ])
        with self.assertRaises(CompileError) as ctx:
            compile(bad)
        a = ctx.exception.anomaly
        self.assertEqual(a["kind"], "type-mismatch")
        self.assertIn("LET", a["detail"]["context"])


class ConstantFolding(unittest.TestCase):

    def test_pure_program_folds_to_single_literal(self):
        for src in (
            "(p 12)",
            "(tau 100)",
            "(sigma 6)",
            "(merge (p 3) (tau 12))",
            "(gcd (sigma 12) (sigma 18))",
        ):
            with self.subTest(src=src):
                compiled, _ = compile(parse(src))
                self.assertEqual(compiled.op, LIT_INT,
                                 f"{src} should fold to LIT_INT, "
                                 f"got {pretty(compiled)}")

    def test_impure_operators_block_fold(self):
        """SEQ / SURPRISE / LET / CONSERVE / IF_SURPRISE are not folded."""
        # SEQ is impure (affects surprise trace through children)
        compiled_seq, _ = compile(parse("(seq (p 3) (p 5))"))
        self.assertNotEqual(compiled_seq.op, LIT_INT)

        # LET binds a name — not folded (technically could be with inlining)
        compiled_let, _ = compile(parse("(let 0 5 (p (ref 0)))"))
        self.assertNotEqual(compiled_let.op, LIT_INT)

        # SURPRISE writes to the surprise trace — not pure
        compiled_s, _ = compile(parse("(surprise 10 (p 12))"))
        self.assertNotEqual(compiled_s.op, LIT_INT)

    def test_fold_is_idempotent(self):
        src = "(merge (p 3) (tau 12))"
        once, _ = compile(parse(src))
        twice, _ = compile(once)
        self.assertEqual(once, twice)

    def test_partial_fold_preserves_ref(self):
        """In (let 0 5 (merge (p 3) (ref 0))), (p 3) folds but outer cannot."""
        src = "(let 0 5 (merge (p 3) (ref 0)))"
        compiled, _ = compile(parse(src))
        # outer LET preserved; inner (p 3) folded to literal 3
        from core.tokens import LET, MERGE
        self.assertEqual(compiled.op, LET)
        merge = compiled.args[2]
        self.assertEqual(merge.op, MERGE)
        self.assertEqual(merge.args[0].op, LIT_INT)
        self.assertEqual(merge.args[0].args[0], 3)


class AnomalyShapeUnification(unittest.TestCase):

    def test_compile_error_has_l2_fields(self):
        try:
            compile(parse("(ref 99)"))
        except CompileError as e:
            for k in ("kind", "stage", "detail", "position_path",
                      "offending_op", "offending_op_name",
                      "valid_alternatives", "repair_hint"):
                self.assertIn(k, e.anomaly)
            self.assertEqual(e.anomaly["stage"], "compile")


if __name__ == "__main__":
    unittest.main()
