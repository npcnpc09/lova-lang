"""Unit tests for ``core.telemetry`` — pass-rate counters + TokenChoice
enrichment (Q22, M6 Day 3)."""

from __future__ import annotations

import os
import tempfile
import unittest

from core.generator import GenState
from core.observability import valid_next_with_stats
from core.surface import parse
from core.telemetry import TelemetryDB, TokenStats
from core.tokens import CONSERVE, LIT_INT, MERGE, SIGMA, VIOLATE


class TokenStatsBasics(unittest.TestCase):

    def test_empty_stats_have_none_rate(self):
        s = TokenStats.empty()
        self.assertEqual(s.hits, 0)
        self.assertEqual(s.misses, 0)
        self.assertEqual(s.sample_count, 0)
        self.assertIsNone(s.pass_rate)

    def test_mixed_stats_compute_rate(self):
        s = TokenStats(hits=3, misses=1)
        self.assertEqual(s.sample_count, 4)
        self.assertAlmostEqual(s.pass_rate, 0.75)


class DBRecordAndLookup(unittest.TestCase):

    def test_empty_lookup_returns_empty_stats(self):
        db = TelemetryDB.empty()
        self.assertEqual(db.lookup_global(LIT_INT).sample_count, 0)
        self.assertEqual(db.lookup(LIT_INT).pass_rate, None)

    def test_record_bumps_global_and_context(self):
        db = TelemetryDB.empty()
        # (merge 3 4) passes; increments counts for MERGE (root) and for
        # LIT_INT twice as child of MERGE.
        db.record(parse("(merge 3 4)"), passed=True)
        self.assertEqual(db.lookup_global(MERGE).hits, 1)
        self.assertEqual(db.lookup_global(LIT_INT).hits, 2)
        self.assertEqual(db.lookup_context(LIT_INT, MERGE).hits, 2)
        self.assertEqual(db.total_programs, 1)

    def test_fail_records_as_miss(self):
        db = TelemetryDB.empty()
        db.record(parse("(violate 3)"), passed=False)
        self.assertEqual(db.lookup_global(VIOLATE).misses, 1)
        self.assertEqual(db.lookup_global(VIOLATE).hits, 0)
        self.assertEqual(db.lookup_context(LIT_INT, VIOLATE).misses, 1)

    def test_context_lookup_falls_back_to_global(self):
        db = TelemetryDB.empty()
        db.record(parse("(merge 1 2)"), passed=True)  # MERGE root, LIT children
        # LIT was never seen with parent=SIGMA; lookup(parent=SIGMA) should
        # fall back to global LIT stats.
        stats = db.lookup(LIT_INT, parent_op=SIGMA)
        self.assertEqual(stats.hits, 2)  # from global

    def test_lookup_context_does_not_fall_back(self):
        db = TelemetryDB.empty()
        db.record(parse("(merge 1 2)"), passed=True)
        self.assertEqual(db.lookup_context(LIT_INT, SIGMA).sample_count, 0)

    def test_distinct_context_rates(self):
        """LIT as child of CONSERVE vs as child of MERGE can diverge."""
        db = TelemetryDB.empty()
        # 3 passing merges
        for _ in range(3):
            db.record(parse("(merge 1 2)"), passed=True)
        # 3 failing conserves (VIOLATE in body makes them trap)
        for _ in range(3):
            db.record(parse("(conserve 5 (violate 5))"), passed=False)

        # LIT child-of-MERGE: hits=6 (2 LITs × 3 progs)
        stats_merge = db.lookup_context(LIT_INT, MERGE)
        self.assertEqual(stats_merge.hits, 6)
        self.assertEqual(stats_merge.misses, 0)
        # LIT child-of-CONSERVE: only the contract literal (first arg of
        # each program), 1 LIT × 3 progs = 3 misses.
        stats_conserve = db.lookup_context(LIT_INT, CONSERVE)
        self.assertEqual(stats_conserve.hits, 0)
        self.assertEqual(stats_conserve.misses, 3)


class DBSerialisation(unittest.TestCase):

    def test_roundtrip_preserves_counters(self):
        db = TelemetryDB.empty()
        db.record(parse("(merge 3 4)"), passed=True)
        db.record(parse("(violate 3)"), passed=False)
        data = db.to_dict()
        rebuilt = TelemetryDB.from_dict(data)
        self.assertEqual(rebuilt.total_programs, 2)
        self.assertEqual(
            rebuilt.lookup_global(MERGE).hits,
            db.lookup_global(MERGE).hits,
        )
        self.assertEqual(
            rebuilt.lookup_context(LIT_INT, MERGE).hits,
            db.lookup_context(LIT_INT, MERGE).hits,
        )

    def test_save_load_roundtrip(self):
        db = TelemetryDB.empty()
        db.record(parse("(merge 3 4)"), passed=True)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            db.save(path)
            loaded = TelemetryDB.load(path)
            self.assertEqual(loaded.total_programs, 1)
            self.assertEqual(loaded.lookup_global(MERGE).hits, 1)
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_empty(self):
        missing = os.path.join(
            tempfile.gettempdir(), "no_such_telemetry_file_xyz.json"
        )
        if os.path.exists(missing):
            os.unlink(missing)
        db = TelemetryDB.load(missing)
        self.assertEqual(db.total_programs, 0)


class TokenChoiceWithTelemetry(unittest.TestCase):

    def test_no_telemetry_leaves_fields_none(self):
        choices = valid_next_with_stats(GenState.fresh())
        for c in choices:
            self.assertIsNone(c.prior_pass_rate)
            self.assertEqual(c.prior_sample_count, 0)
            self.assertIsNone(c.prior_pass_rate_ctx)
            self.assertEqual(c.prior_sample_count_ctx, 0)

    def test_telemetry_fills_global_fields(self):
        db = TelemetryDB.empty()
        for _ in range(4):
            db.record(parse("(merge 3 4)"), passed=True)
        choices = valid_next_with_stats(GenState.fresh(), telemetry=db)
        merge_choice = next(c for c in choices if c.token == MERGE)
        self.assertEqual(merge_choice.prior_sample_count, 4)
        self.assertAlmostEqual(merge_choice.prior_pass_rate, 1.0)

    def test_context_fields_reflect_parent_op(self):
        """After stepping into a merge, the pending slot has parent_op=MERGE.
        TokenChoice should report context-specific stats."""
        db = TelemetryDB.empty()
        db.record(parse("(merge 3 4)"), passed=True)  # LIT as child of MERGE: 2 hits
        db.record(parse("(violate 3)"), passed=False)  # LIT as child of VIOLATE: 1 miss
        # Step through MERGE first, now in child slot with parent_op=MERGE
        state = GenState.fresh().step(MERGE)
        choices = valid_next_with_stats(state, telemetry=db)
        lit_choice = next(c for c in choices if c.token == LIT_INT)
        self.assertEqual(lit_choice.prior_sample_count_ctx, 2)
        self.assertAlmostEqual(lit_choice.prior_pass_rate_ctx, 1.0)
        # Global rate blends LIT-as-child-of-{MERGE, VIOLATE}: 2 hits / 3 total
        self.assertEqual(lit_choice.prior_sample_count, 3)
        self.assertAlmostEqual(lit_choice.prior_pass_rate, 2 / 3)


if __name__ == "__main__":
    unittest.main()
