"""Unit tests for ``core.observability`` — TokenChoice, static_analyze,
trap enrichment."""

from __future__ import annotations

import unittest

from core.conservation import BudgetTrap, DeltaTrap
from core.generator import GenState
from core.observability import (
    StaticAnalysis, TokenChoice, static_analyze, suggest_alternatives,
    valid_next_with_stats,
)
from core.runtime import evaluate
from core.surface import parse
from core.tokens import (
    CONSERVE, LET, LIT_INT, MERGE, MOBIUS, P, SEQ, SIGMA, TAU, VIOLATE,
)


class ValidNextStats(unittest.TestCase):

    def test_fresh_state_returns_tokenchoices(self):
        choices = valid_next_with_stats(GenState.fresh())
        self.assertGreater(len(choices), 0)
        self.assertTrue(all(isinstance(c, TokenChoice) for c in choices))

    def test_every_choice_has_required_fields(self):
        choices = valid_next_with_stats(GenState.fresh())
        for c in choices:
            self.assertIsInstance(c.token, int)
            self.assertIsInstance(c.name, str)
            self.assertIsInstance(c.depth_delta, int)
            self.assertIsInstance(c.terminating, bool)
            self.assertIsInstance(c.effects, frozenset)

    def test_lit_is_terminating(self):
        choices = valid_next_with_stats(GenState.fresh())
        lit_choices = [c for c in choices if c.token == LIT_INT]
        self.assertEqual(len(lit_choices), 1)
        self.assertTrue(lit_choices[0].terminating)
        self.assertEqual(lit_choices[0].depth_delta, -1)

    def test_merge_is_non_terminating(self):
        choices = valid_next_with_stats(GenState.fresh())
        merge_choices = [c for c in choices if c.token == MERGE]
        self.assertEqual(len(merge_choices), 1)
        self.assertFalse(merge_choices[0].terminating)
        self.assertEqual(merge_choices[0].depth_delta, 1)

    def test_let_slot_only_allows_lit(self):
        choices = valid_next_with_stats(GenState.fresh().step(LET))
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].token, LIT_INT)

    def test_surprise_op_has_effect_tag(self):
        choices = valid_next_with_stats(GenState.fresh())
        surprise_choices = [c for c in choices
                             if c.name == "surprise"]
        self.assertEqual(len(surprise_choices), 1)
        self.assertIn("write-surprise-trace", surprise_choices[0].effects)

    def test_conserve_op_has_effect_tag(self):
        choices = valid_next_with_stats(GenState.fresh())
        conserve_choices = [c for c in choices if c.name == "conserve"]
        self.assertEqual(len(conserve_choices), 1)
        self.assertIn("conservation-check", conserve_choices[0].effects)


class SuggestAlternatives(unittest.TestCase):

    def test_nt_unary_group(self):
        alts = set(suggest_alternatives(P))
        self.assertEqual(alts, {TAU, SIGMA, MOBIUS})

    def test_binary_group(self):
        from core.tokens import GCD
        alts = set(suggest_alternatives(MERGE))
        self.assertEqual(alts, {GCD})

    def test_violate_suggests_identity(self):
        from core.tokens import IDENTITY
        alts = set(suggest_alternatives(VIOLATE))
        self.assertEqual(alts, {IDENTITY})

    def test_unknown_returns_empty(self):
        # END has no swap group
        from core.tokens import END
        self.assertEqual(suggest_alternatives(END), ())


class StaticAnalyze(unittest.TestCase):

    def _analyze(self, src: str) -> StaticAnalysis:
        return static_analyze(parse(src))

    def test_pure_program_has_no_effects(self):
        a = self._analyze("(merge (p 12) (tau 100))")
        self.assertEqual(a.effects, frozenset())
        self.assertFalse(a.uses_conservation)
        self.assertFalse(a.uses_surprise)

    def test_conservation_program_flagged(self):
        a = self._analyze("(budget 100 (merge (p 12) (sigma 12)))")
        self.assertIn("budget-scope", a.effects)
        self.assertTrue(a.uses_conservation)

    def test_surprise_program_flagged(self):
        a = self._analyze("(if-surprise (surprise 10 (p 12)) 99 0)")
        self.assertIn("read-surprise", a.effects)
        self.assertIn("write-surprise-trace", a.effects)
        self.assertTrue(a.uses_surprise)

    def test_node_count_matches_tree_shape(self):
        # (merge (p 3) (tau 12)) = MERGE + P + LIT(3) + TAU + LIT(12) = 5 nodes
        a = self._analyze("(merge (p 3) (tau 12))")
        self.assertEqual(a.node_count, 5)

    def test_budget_upper_bound_is_node_count(self):
        src = "(merge (p 12) (tau 100))"
        a = self._analyze(src)
        self.assertEqual(a.budget_upper_bound, a.node_count)


class TrapEnrichment(unittest.TestCase):
    """Traps must carry the L2 observability fields after runtime catch."""

    def test_budget_trap_fields(self):
        try:
            evaluate(parse("(budget 1 (p 12))"))
        except BudgetTrap as t:
            a = t.anomaly
            self.assertEqual(a["kind"], "budget-exceeded")
            self.assertIn("detail", a)
            self.assertIn("position_path", a)
            self.assertIn("repair_hint", a)
            # Position path is a tuple of op bytes
            self.assertIsInstance(a["position_path"], tuple)
            # Offending op should be set
            self.assertIsNotNone(a["offending_op"])

    def test_delta_trap_fields(self):
        try:
            evaluate(parse("(conserve 77 (violate 77))"))
        except DeltaTrap as t:
            a = t.anomaly
            self.assertEqual(a["kind"], "conservation-violated")
            self.assertEqual(a["detail"]["entry"], 77)
            self.assertEqual(a["detail"]["exit"], 78)
            self.assertIn("repair_hint", a)


class BodyOffenderScan(unittest.TestCase):
    """Q20: DeltaTrap anomaly carries ``body_offender`` — probe-based
    scan of the conserve body, identifying the deepest sub-expression
    whose replacement restores the invariant.  This moves the trap's
    semantic focus from the outer CONSERVE frame to the actual fault."""

    def _trap(self, src: str) -> DeltaTrap:
        with self.assertRaises(DeltaTrap) as ctx:
            evaluate(parse(src))
        return ctx.exception

    def test_violate_at_root_is_offender(self):
        t = self._trap("(conserve 77 (violate 77))")
        bo = t.anomaly["body_offender"]
        self.assertIsNotNone(bo)
        self.assertEqual(bo["op"], VIOLATE)
        self.assertEqual(bo["op_name"], "violate")
        self.assertEqual(bo["path"], ())  # body is the violate itself
        self.assertEqual(bo["observed"], 78)
        self.assertEqual(bo["needed"], 77)
        self.assertEqual(bo["correction"], -1)

    def test_nested_violate_chosen_over_outer_op(self):
        """Deepest-first: inner violate picked, not the wrapping merge."""
        t = self._trap("(conserve 10 (merge (violate 3) 4))")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["op"], VIOLATE)
        self.assertEqual(bo["path"], (0,))  # merge.arg0
        self.assertEqual(bo["depth"], 1)
        self.assertEqual(bo["correction"], +2)

    def test_deepest_violate_in_chain(self):
        """Two violates nested — innermost picked."""
        t = self._trap("(conserve 5 (violate (violate 2)))")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["op"], VIOLATE)
        self.assertEqual(bo["path"], (0,))  # outer_violate.arg0 = inner_violate
        self.assertEqual(bo["depth"], 1)

    def test_bare_literal_body_offender_is_root_lit(self):
        """Body is just a wrong literal — LIT_INT at root IS the offender."""
        t = self._trap("(conserve 10 7)")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["op"], LIT_INT)
        self.assertEqual(bo["path"], ())
        self.assertEqual(bo["correction"], +3)

    def test_nonroot_literals_are_skipped(self):
        """In ``(merge 7 4)`` with contract 10, literals are skipped and
        MERGE at root is flagged (semantic offender over band-aid fix)."""
        t = self._trap("(conserve 10 (merge 7 4))")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["op"], MERGE)
        self.assertEqual(bo["path"], ())

    def test_repair_hint_names_the_offender(self):
        t = self._trap("(conserve 77 (violate 77))")
        hint = t.anomaly["repair_hint"]
        self.assertIn("violate", hint)
        self.assertIn("path", hint)
        self.assertIn("77", hint)

    def test_valid_alternatives_follow_inner_offender(self):
        """Alternatives come from the body-level op, not outer CONSERVE."""
        t = self._trap("(conserve 77 (violate 77))")
        # suggest_alternatives(VIOLATE) == (IDENTITY,)
        from core.tokens import IDENTITY
        self.assertEqual(t.anomaly["valid_alternatives"], (IDENTITY,))

    def test_operator_swap_pass_picks_violate_over_inner_merge(self):
        """Pass A: `(conserve N (violate (merge a b)))` — VIOLATE -> IDENTITY
        fixes conservation, so VIOLATE should be flagged (operator-swap fix),
        not the deeper MERGE (which would be a LIT_INT band-aid)."""
        t = self._trap("(conserve 9 (violate (merge 5 4)))")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["op"], VIOLATE)
        self.assertEqual(bo["path"], ())  # outer VIOLATE
        self.assertEqual(bo["fix"], "operator-swap")
        from core.tokens import IDENTITY
        self.assertEqual(bo["alternative_op"], IDENTITY)

    def test_literal_replacement_pass_labels_fix(self):
        """When no operator swap restores the invariant, fix is labelled
        ``literal-replacement``."""
        t = self._trap("(conserve 10 (merge 7 4))")
        bo = t.anomaly["body_offender"]
        self.assertEqual(bo["fix"], "literal-replacement")


if __name__ == "__main__":
    unittest.main()
