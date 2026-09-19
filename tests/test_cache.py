"""The compiled-program cache (Q125): fast, keyed honestly, never fatal.

`core/cache.py` keeps what `core.cli.build` returned on disk, so a run
of a program that uses one of the 3D libraries does not pay a second
time for a parse it already did.  What these tests hold to:

* a hit gives back the same program -- the same bytes, the same source
  spans, the same symbol table -- because a cache that changed the
  tree would change every span a fault is reported at;
* the key names everything the build depends on: the text of a library
  the program `use`s, the flags, and the implementation itself;
* `LOVA_CACHE=off` writes nothing anywhere;
* a corrupt entry is deleted and the build succeeds regardless, which
  is the one property that keeps a cache from becoming a liability.
"""

from __future__ import annotations

import os
import pickle
import shutil
import tempfile
import unittest

from core import cache
from core.cli import build
from core.tokens import encode


PROGRAM = """
(def double [n] (mul n 2))
(def quad [n] (double (double n)))
(quad 5)
"""


def _spans(node):
    out = [getattr(node, "span", None)]
    for arg in node.args:
        if hasattr(arg, "op"):
            out.extend(_spans(arg))
    return out


class CacheHarness(unittest.TestCase):
    """Each test gets its own empty directory and no minimum build time."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lova-cache-test-")
        self._env = {k: os.environ.get(k) for k in ("LOVA_CACHE", "LOVA_CACHE_MIN_MS")}
        os.environ["LOVA_CACHE"] = self.dir
        os.environ["LOVA_CACHE_MIN_MS"] = "0"

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.dir, ignore_errors=True)

    def entries(self):
        return [n for n in os.listdir(self.dir) if n.endswith(".pkl")]


class Roundtrip(CacheHarness):

    def test_a_build_is_written_and_the_second_is_a_hit(self):
        first, report = build(PROGRAM)
        self.assertEqual(len(self.entries()), 1)
        second, report2 = build(PROGRAM)
        self.assertIsNot(first, second)          # a fresh tree, never a shared one
        self.assertEqual(encode(first), encode(second))
        self.assertEqual(_spans(first), _spans(second))
        self.assertEqual(first.symbols.as_dict(), second.symbols.as_dict())
        self.assertEqual(report, report2)

    def test_the_cached_tree_still_carries_its_spans(self):
        build(PROGRAM)
        tree, _ = build(PROGRAM)
        spans = [s for s in _spans(tree) if s is not None]
        self.assertTrue(spans)
        for start, end in spans:
            self.assertLessEqual(end, len(PROGRAM) + 1)
            self.assertLess(start, end)

    def test_the_cached_tree_runs_to_the_same_value(self):
        from core.runtime import Runtime, evaluate
        cold, _ = build(PROGRAM)
        warm, _ = build(PROGRAM)
        self.assertEqual(evaluate(cold, Runtime()), evaluate(warm, Runtime()))

    def test_examples_survive_the_round_trip(self):
        # The examples ride on the symbol table (`core/examples.py`
        # reads them there), nodes and spans and all.
        source = "(def sq [n] (mul n n))\n(example (sq 3) 9)\n(sq 4)\n"
        build(source)
        tree, _ = build(source)
        examples = tree.symbols.examples
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["expr"].span,
                         (source.index("(sq 3)"), source.index("(sq 3)") + len("(sq 3)")))

    def test_a_flag_is_part_of_the_key(self):
        keys = {
            cache.key_for(PROGRAM, prelude=p, stage2=False, do_compile=c)
            for p in (True, False) for c in (True, False)
        }
        self.assertEqual(len(keys), 4)


class KeyInputs(CacheHarness):

    def test_a_change_to_a_used_library_changes_the_key(self):
        from core import surface
        lib = os.path.join(surface.LIB_DIR, "cache_test_lib.lova")
        source = '(use "cache_test_lib")\n(twice 4)\n'
        try:
            with open(lib, "w", encoding="utf-8") as handle:
                handle.write("(def twice [n] (mul n 2))\n")
            before = cache.key_for(source, prelude=True, stage2=False, do_compile=True)
            tree, _ = build(source)
            from core.runtime import Runtime, evaluate
            self.assertEqual(evaluate(tree, Runtime()), 8)
            with open(lib, "w", encoding="utf-8") as handle:
                handle.write("(def twice [n] (mul n 3))\n")
            after = cache.key_for(source, prelude=True, stage2=False, do_compile=True)
            self.assertNotEqual(before, after)
            tree, _ = build(source)
            self.assertEqual(evaluate(tree, Runtime()), 12)   # not the cached one
        finally:
            if os.path.exists(lib):
                os.remove(lib)

    def test_the_core_fingerprint_invalidates_every_entry(self):
        before = cache.key_for(PROGRAM, prelude=True, stage2=False, do_compile=True)
        build(PROGRAM)
        self.assertEqual(len(self.entries()), 1)
        saved = cache._fingerprint
        try:
            cache._fingerprint = "a compiler that is not this one"
            after = cache.key_for(PROGRAM, prelude=True, stage2=False, do_compile=True)
            self.assertNotEqual(before, after)
            build(PROGRAM)
            self.assertEqual(len(self.entries()), 2)          # the old entry is not read
        finally:
            cache._fingerprint = saved

    def test_the_fingerprint_covers_the_core_and_the_prelude(self):
        cache._fingerprint = None
        try:
            first = cache._core_fingerprint()
            cache._fingerprint = None
            self.assertEqual(first, cache._core_fingerprint())
        finally:
            cache._fingerprint = None
            cache._core_fingerprint()


class Off(CacheHarness):

    def test_off_touches_nothing(self):
        os.environ["LOVA_CACHE"] = "off"
        empty = tempfile.mkdtemp(prefix="lova-cache-off-")
        try:
            self.assertIsNone(cache.cache_dir())
            self.assertIsNone(cache.key_for(PROGRAM, prelude=True, stage2=False,
                                            do_compile=True))
            tree, _ = build(PROGRAM)
            self.assertTrue(encode(tree))
            self.assertEqual(self.entries(), [])
            self.assertEqual(os.listdir(empty), [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_a_trivial_build_is_not_worth_a_file(self):
        os.environ["LOVA_CACHE_MIN_MS"] = "100000"
        build(PROGRAM)
        self.assertEqual(self.entries(), [])


class Failures(CacheHarness):

    def test_a_corrupt_entry_is_deleted_and_the_build_succeeds(self):
        build(PROGRAM)
        name, = self.entries()
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(b"this is not a pickle")
        tree, _ = build(PROGRAM)
        self.assertTrue(encode(tree))
        # deleted on the way past, then written again by the build
        self.assertEqual(self.entries(), [name])
        with open(path, "rb") as handle:
            self.assertNotEqual(handle.read(), b"this is not a pickle")

    def test_an_entry_that_is_not_a_pair_is_deleted(self):
        key = cache.key_for(PROGRAM, prelude=True, stage2=False, do_compile=True)
        path = os.path.join(self.dir, key + ".pkl")
        with open(path, "wb") as handle:
            handle.write(pickle.dumps(["not", "a", "pair"]))
        self.assertIsNone(cache.load(key))
        self.assertFalse(os.path.exists(path))
        tree, _ = build(PROGRAM)
        self.assertTrue(encode(tree))

    def test_a_directory_that_cannot_be_written_is_not_an_error(self):
        os.environ["LOVA_CACHE"] = os.path.join(self.dir, "a-file")
        with open(os.environ["LOVA_CACHE"], "w", encoding="utf-8") as handle:
            handle.write("in the way")
        key = cache.key_for(PROGRAM, prelude=True, stage2=False, do_compile=True)
        self.assertFalse(cache.store(key, (1, 2), elapsed=1.0))
        self.assertIsNone(cache.load(key))
        tree, _ = build(PROGRAM)
        self.assertTrue(encode(tree))

    def test_a_tree_pickle_cannot_walk_is_not_stored(self):
        # Pickle gives up on a deep enough tree (the parser gives up
        # before that, so this one is built by hand); `store` says no
        # and raises nothing.
        from core.tokens import MERGE, Lit, Node
        deep = Lit(1)
        for i in range(2000):
            deep = Node(op=MERGE, args=[deep, Lit(i)])
        key = cache.key_for(PROGRAM, prelude=True, stage2=False, do_compile=True)
        self.assertFalse(cache.store(key, (deep, None), elapsed=1.0))
        self.assertEqual(self.entries(), [])

    def test_a_failed_build_is_not_cached(self):
        from core.compiler import CompileError
        with self.assertRaises((CompileError, ValueError)):
            build("(nope 1 2)")
        self.assertEqual(self.entries(), [])


class Location(unittest.TestCase):

    def test_the_default_directory_is_the_platform_one(self):
        saved = os.environ.pop("LOVA_CACHE", None)
        try:
            where = cache.cache_dir()
            self.assertIsNotNone(where)
            if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
                self.assertTrue(where.endswith(os.path.join("lova", "cache")))
            else:
                self.assertTrue(where.endswith(os.path.join(".cache", "lova")))
        finally:
            if saved is not None:
                os.environ["LOVA_CACHE"] = saved


if __name__ == "__main__":
    unittest.main()
