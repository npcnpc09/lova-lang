"""M23 -- the map reroots instead of copying.

`map-put` used to copy the dict; now one dict serves a family of
versions and moves to whichever is read.  What must not change is
the meaning: every version keeps the entries it had, in the order it
had them, however the versions are read and branched.  The model
these tests check against is the copy.
"""

from __future__ import annotations

import random
import unittest

from core.runtime import MapValue, Runtime, evaluate, list_to_python
from core.surface import parse


def _run(src: str):
    return evaluate(parse(src), Runtime())


def _pairs(m):
    return [list_to_python(p) for p in list_to_python(m)]


class Versions(unittest.TestCase):

    def test_an_old_version_keeps_its_meaning(self):
        src = """(let m1 (map-put (nil) 1 10)
                   (let m2 (map-put m1 2 20)
                     (let m3 (map-put m2 1 11)
                       (list (map-get m1 1 0) (map-get m1 2 0)
                             (map-get m2 1 0) (map-get m2 2 0)
                             (map-get m3 1 0) (map-get m3 2 0)))))"""
        self.assertEqual(list_to_python(_run(src)), [10, 0, 10, 20, 11, 20])

    def test_branching_from_one_base(self):
        src = """(let base (map-put (nil) 1 1)
                   (let left (map-put base 2 2)
                     (let right (map-put base 3 3)
                       (list (map-get left 2 0) (map-get left 3 0)
                             (map-get right 2 0) (map-get right 3 0)
                             (map-get base 2 0) (map-get base 3 0)))))"""
        self.assertEqual(list_to_python(_run(src)), [2, 0, 0, 3, 0, 0])

    def test_pairs_of_an_old_version_keep_their_order(self):
        src = """(let m1 (map-put (map-put (nil) 5 50) 3 30)
                   (let m2 (map-put (map-put m1 7 70) 5 51)
                     (list (map-pairs m1) (map-pairs m2))))"""
        old, new = list_to_python(_run(src))
        self.assertEqual(_pairs(old), [[5, 50], [3, 30]])
        self.assertEqual(_pairs(new), [[5, 51], [3, 30], [7, 70]])

    def test_reading_versions_alternately(self):
        src = """(let m1 (map-put (nil) 1 1)
                   (let m2 (map-put m1 1 2)
                     (merge (merge (map-get m1 1 0) (map-get m2 1 0))
                            (merge (map-get m1 1 0) (map-get m2 1 0)))))"""
        self.assertEqual(_run(src), 6)


class AgainstTheCopy(unittest.TestCase):
    """Random puts and reads over many live versions, checked against
    a version that really copies."""

    def test_random_histories_match_the_copying_model(self):
        for seed in range(20):
            rng = random.Random(seed)
            versions = [MapValue()]
            models = [{}]
            for _ in range(200):
                i = rng.randrange(len(versions))
                key = rng.randrange(8)
                value = rng.randrange(1000)
                versions.append(versions[i].put(("i", key), key, value))
                model = dict(models[i])
                model[("i", key)] = (key, value)
                models.append(model)
                # Read a few versions in a random order, including old ones.
                for j in rng.sample(range(len(versions)), min(4, len(versions))):
                    self.assertEqual(versions[j].entries, models[j], (seed, j))
                    self.assertEqual(list(versions[j].entries), list(models[j]),
                                     (seed, j))   # insertion order too
            for j in range(len(versions)):
                self.assertEqual(versions[j].entries, models[j])


if __name__ == "__main__":
    unittest.main()
