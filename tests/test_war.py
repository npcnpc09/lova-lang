"""The isometric battlefield as geometry and as rules: `lib/war.lova`.

The map is made once and costs a couple of million steps, so this
module makes it once too, in `setUpClass`, and every test calls into
the same runtime -- which is also how `apps/war/war.py` uses it.

What a test can check that a screenshot cannot: that the ground is
handed over far cells first (a painter has no depth buffer and paints
in the order it is given), that water is exactly flat at sea level,
that the sun falls on the side of a hill it should, that nobody stands
in the sea, that a click on a soldier picks that soldier and a click on
the grass picks none, and that a battle actually ends.
"""

from __future__ import annotations

import unittest

from core.cli import build
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

API = """\
(use "war")
(rec ground terrain new new-war tick tick spr sprites left standing
     select choose all select-all order order pick pick
     light light-of walk walkable wet wet lo cell-lo
     placeu place-u placev place-v n N
     units (lambda w (get w units)))
"""


class War(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.build_steps = cls.rt.steps
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("ground", "new", "tick", "spr", "left", "select", "all",
                            "order", "pick", "light", "walk", "wet", "lo",
                            "placeu", "placev", "n", "units")}
        cls.cells = list_to_python(cls.call("ground"))

    @classmethod
    def call(cls, name, *args):
        cls.rt.steps = 0
        fn = cls.fn[name]
        for arg in args:
            fn = _call(fn, arg, cls.rt)
        return fn

    @staticmethod
    def f(value, *names):
        out = [value.entries[_map_key(n, "get")][1] for n in names]
        return out[0] if len(out) == 1 else out

    # --- the ground ------------------------------------------------------

    def test_the_map_is_the_size_it_says(self):
        n = self.fn["n"]
        self.assertEqual(len(self.cells), n * n)

    def test_it_comes_far_cells_first(self):
        """A painter with no depth buffer paints in the order it is given,
        so the order is the guarantee: the first cell is the far corner of
        the map and the last is the near one, and no cell is ever handed
        over after one that stands in front of it."""
        n = self.fn["n"]
        self.assertLess(self.f(self.cells[0], "v0"), self.f(self.cells[-1], "v0"))
        rows = [self.f(c, "u1") - self.f(c, "u3") for c in self.cells]
        self.assertEqual(set(rows), {32})                   # every cell one tile wide
        # x - y is what the screen column says; within one diagonal (one
        # depth) it rises by two a cell, and a fall in it is the start of
        # the next diagonal.  The diagonals of a square map run
        # 1, 2, ... n, ... 2, 1 -- which is the order a painter needs.
        across = [(self.f(c, "u0") - 16 * n) // 16 for c in self.cells]
        lengths, run = [], 1
        for a, b in zip(across, across[1:]):
            if b == a + 2:
                run += 1
            else:
                lengths.append(run)
                run = 1
        lengths.append(run)
        self.assertEqual(lengths, list(range(1, n + 1)) + list(range(n - 1, 0, -1)))

    def test_water_is_flat(self):
        """Every water cell sits at exactly sea level: the four corners of
        its quad differ only by the tile shape, never by the height under
        it, which is what makes a coast read as a coast."""
        wet = [c for c in self.cells if self.f(c, "t") in (0, 1)]
        self.assertGreater(len(wet), 100)
        for c in wet:
            v0, v1, v2, v3 = self.f(c, "v0", "v1", "v2", "v3")
            self.assertEqual((v1 - v0, v2 - v0, v3 - v0), (8, 16, 8))

    def test_there_is_a_bit_of_everything(self):
        kinds = {self.f(c, "t") for c in self.cells}
        self.assertEqual(kinds, {0, 1, 2, 3, 4, 5, 6})
        trees = [c for c in self.cells if self.f(c, "d") == 1]
        self.assertGreater(len(trees), 30)
        self.assertTrue(all(self.f(c, "t") in (3, 4) for c in trees))

    def test_nothing_grows_in_the_sea(self):
        for c in self.cells:
            if self.f(c, "t") in (0, 1):
                self.assertEqual(self.f(c, "d"), 0)

    def test_the_sun_comes_from_the_north_west(self):
        """`light-of` takes three corner heights; a slope rising away from
        the sun is darker than a flat cell, and one rising toward it is
        brighter.  Ambient keeps the darkest of them off the floor."""
        flat = self.call("light", 500, 500, 500)
        toward = self.call("light", 500, 560, 560)
        away = self.call("light", 500, 440, 440)
        self.assertGreater(toward, flat)
        self.assertLess(away, flat)
        self.assertGreater(away, 300)

    def test_the_map_costs_what_the_window_waits_for(self):
        self.assertLess(self.build_steps, 4_000_000)

    # --- the ground under a unit -----------------------------------------

    def test_a_click_finds_the_cell_it_landed_on(self):
        """`pick` inverts the projection and then corrects with the height
        it finds; on level ground it is exact."""
        for cx, cy in ((10, 10), (18, 20), (25, 12)):
            if self.call("wet", cx, cy):
                continue
            u = self.call("placeu", cx * 1024 + 512, cy * 1024 + 512)
            v = self.call("placev", cx * 1024 + 512, cy * 1024 + 512)
            p = self.call("pick", u, v)
            self.assertLessEqual(abs(self.f(p, "x") - cx), 1, (cx, cy))
            self.assertLessEqual(abs(self.f(p, "y") - cy), 1, (cx, cy))

    def test_the_sea_is_not_walkable(self):
        n = self.fn["n"]
        for x in range(0, n, 3):
            for y in range(0, n, 3):
                if self.call("wet", x, y):
                    self.assertFalse(self.call("walk", x, y))
        self.assertFalse(self.call("walk", -1, 5))
        self.assertFalse(self.call("walk", 5, n))

    # --- the armies ------------------------------------------------------

    def test_both_sides_start_on_dry_land(self):
        w = self.call("new", 1)
        self.assertEqual(self.call("left", w, 0), 6)
        self.assertEqual(self.call("left", w, 1), 6)
        for u in list_to_python(self.call("units", w)):
            cx, cy = self.f(u, "x") // 1024, self.f(u, "y") // 1024
            self.assertTrue(self.call("walk", cx, cy), (cx, cy))

    def test_a_click_on_a_soldier_picks_that_soldier(self):
        w = self.call("new", 1)
        sprites = list_to_python(self.call("spr", w))
        mine = [s for s in sprites if self.f(s, "t") == 0][0]
        theirs = [s for s in sprites if self.f(s, "t") == 1][0]
        picked = self.call("select", w, self.f(mine, "u"), self.f(mine, "v") - 12)
        self.assertEqual(sum(self.f(s, "s") for s in list_to_python(self.call("spr", picked))), 1)
        # their soldiers are not yours to order about
        none = self.call("select", w, self.f(theirs, "u"), self.f(theirs, "v") - 12)
        self.assertEqual(sum(self.f(s, "s") for s in list_to_python(self.call("spr", none))), 0)
        # and neither is the grass
        none = self.call("select", w, 5, 5)
        self.assertEqual(sum(self.f(s, "s") for s in list_to_python(self.call("spr", none))), 0)

    def test_an_order_is_walked_to(self):
        w = self.call("all", self.call("new", 1))
        self.assertEqual(sum(self.f(s, "s") for s in list_to_python(self.call("spr", w))), 6)
        before = [self.f(s, "u") for s in list_to_python(self.call("spr", w)) if self.f(s, "t") == 0]
        w = self.call("order", w, before[0] + 160, 240)
        for _ in range(25):
            w = self.call("tick", w)
        after = [self.f(s, "u") for s in list_to_python(self.call("spr", w)) if self.f(s, "t") == 0]
        self.assertGreater(sum(after) - sum(before), 40)

    def test_the_battle_ends(self):
        """Left alone, your side holds its ground and theirs comes looking;
        in three hundred ticks somebody has fallen."""
        w = self.call("new", 1)
        for _ in range(300):
            w = self.call("tick", w)
        self.assertLess(self.call("left", w, 0) + self.call("left", w, 1), 12)

    def test_a_tick_fits_in_a_frame(self):
        w = self.call("new", 1)
        worst = 0
        for _ in range(60):
            w = self.call("tick", w)
            worst = max(worst, self.rt.steps)
        self.assertLess(worst, 60_000)


if __name__ == "__main__":
    unittest.main()
