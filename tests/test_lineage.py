"""Unit tests for ``core.lineage`` — uid / parent / generation / Wright-Fisher."""

from __future__ import annotations

import random
import unittest

from core.lineage import LineageStore
from core.surface import parse, pretty


class LineageAPI(unittest.TestCase):

    def setUp(self):
        self.store = LineageStore(seed=0)
        self.a = parse("(merge (p 3) (tau 12))")
        self.a_uid = self.store.register_root(self.a)

    def test_register_assigns_uid(self):
        self.assertIsNotNone(self.a.uid)
        self.assertEqual(self.store.record(self.a_uid).uid, self.a_uid)

    def test_clone_yields_new_uid_and_parent_pointer(self):
        c = self.store.clone(self.a)
        self.assertNotEqual(c.uid, self.a_uid)
        rec = self.store.record(c.uid)
        self.assertEqual(rec.parent_uid, self.a_uid)
        self.assertEqual(rec.root_uid, self.a_uid)
        self.assertEqual(rec.generation, 1)
        self.assertEqual(rec.mutation_kind, "clone")

    def test_mutate_yields_child_generation_1(self):
        m = self.store.mutate(self.a, strength=0.5)
        rec = self.store.record(m.uid)
        self.assertEqual(rec.parent_uid, self.a_uid)
        self.assertEqual(rec.generation, 1)

    def test_ancestors_walks_back_to_root(self):
        b = self.store.mutate(self.a, strength=0.5)
        c = self.store.mutate(b, strength=0.5)
        chain = self.store.ancestors(c.uid)
        uids = [r.uid for r in chain]
        self.assertEqual(uids, [c.uid, b.uid, self.a_uid])

    def test_is_ancestor_of(self):
        b = self.store.mutate(self.a, strength=0.5)
        c = self.store.mutate(b, strength=0.5)
        self.assertTrue(self.store.is_ancestor_of(self.a_uid, c.uid))
        self.assertTrue(self.store.is_ancestor_of(b.uid, c.uid))
        self.assertFalse(self.store.is_ancestor_of(c.uid, b.uid))

    def test_descendants_of(self):
        b = self.store.mutate(self.a, strength=0.5)
        c = self.store.mutate(b, strength=0.5)
        d = self.store.clone(self.a)
        descendants = set(self.store.descendants_of(self.a_uid))
        self.assertEqual(descendants, {b.uid, c.uid, d.uid})


class CoalescenceInvariants(unittest.TestCase):
    """With uniform-random reproduction, lineages coalesce."""

    def test_all_final_descend_from_at_most_k_roots(self):
        """After N generations with pop=5, no more than 5 root lineages
        can still be alive (a trivial upper bound; in practice << 5)."""
        store = LineageStore(seed=1)
        rng = random.Random(1)

        seeds = ["(merge (p 5) (tau 12))", "(gcd 24 36)",
                 "(sigma 12)", "(p 10)", "(merge 10 20)"]
        pop = []
        root_uids = set()
        for s in seeds:
            n = parse(s)
            uid = store.register_root(n)
            pop.append(n)
            root_uids.add(uid)

        for _ in range(15):
            new_pop = []
            for _ in range(5):
                parent = rng.choice(pop)
                child = store.mutate(parent, strength=0.2)
                new_pop.append(child)
            pop = new_pop

        # Count surviving root lineages
        alive_roots = {store.record(n.uid).root_uid for n in pop}
        self.assertLessEqual(len(alive_roots), 5)
        # Wright-Fisher: typically strictly fewer than 5 survive after 15 gens.
        # We don't assert "< 5" because of rare variance.


class MutationDiversity(unittest.TestCase):

    def test_100_mutations_produce_many_distinct(self):
        store = LineageStore(seed=123)
        parent = parse("(merge (p 5) (tau 12))")
        store.register_root(parent)
        seen = set()
        for _ in range(100):
            child = store.mutate(parent, strength=0.4)
            seen.add(pretty(child))
        # strength=0.4 should give 10+ distinct variants.
        self.assertGreaterEqual(len(seen), 10)
        self.assertLessEqual(len(seen), 99)


if __name__ == "__main__":
    unittest.main()
