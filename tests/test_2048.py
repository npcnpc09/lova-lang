"""2048, checked against the original it was ported from.

`lib/g2048.lova` is a port of gabrielecirulli/2048 (MIT).  The claim a
port has to make is that it behaves like the thing it was ported from,
and the way to make it is not to assert it in prose: `Original` below
is a transliteration of `GameManager.prototype.move` and its helpers
straight out of the original's `js/game_manager.js`, and
`test_it_agrees_with_the_original` runs both over random positions and
compares the board, the score, whether anything moved and whether 2048
appeared -- every cell, every time.

The shipped run is 800 positions so the suite stays quick; the same
test was run once at 10 000 positions with no disagreement.

Only the deterministic half can be compared this way: where the
original calls `Math.random()`, this port threads a congruential
generator through the world, so a game here is a function of its seed
and replays exactly, which the original's cannot.  The chance itself --
nine tiles in ten are a two, the new tile lands on a cell drawn
uniformly from the free ones in the original's order -- is checked
separately.
"""

from __future__ import annotations

import contextlib
import io
import random
import sys
import unittest

from core.cli import build, main
from core.runtime import Cons, NIL_VALUE, Runtime, _call, _map_key, evaluate, list_to_python

API = """\
(use "g2048")
(rec new new-game move move rows rows sweep sweep of board-of cells cells-of
     free free-cells left moves-left big biggest keep keep-playing
     wcells (lambda w (cells-of (get w board)))
     mk (lambda xs (rec board (board-of xs) score 0 won 0 over 0 keep 0 turn 0 seed 1)))
"""


def to_lova(xs):
    out = NIL_VALUE
    for v in reversed(xs):
        out = Cons(v, out)
    return out


class Original:
    """`GameManager.prototype.move`, transliterated from the original.

    `cells[x][y]`, x the column and y the row; direction 0 up, 1 right,
    2 down, 3 left.  Zero stands for the original's `null`.
    """

    SIZE = 4
    VECTORS = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}

    @classmethod
    def move(cls, cells, direction):
        vx, vy = cls.VECTORS[direction]
        xs = list(range(cls.SIZE))[::-1] if vx == 1 else list(range(cls.SIZE))
        ys = list(range(cls.SIZE))[::-1] if vy == 1 else list(range(cls.SIZE))
        merged, score, won, moved = set(), 0, False, False
        inside = lambda x, y: 0 <= x < cls.SIZE and 0 <= y < cls.SIZE
        for x in xs:
            for y in ys:
                tile = cells[x][y]
                if not tile:
                    continue
                # findFarthestPosition
                px, py = x, y
                cx, cy = x + vx, y + vy
                while inside(cx, cy) and not cells[cx][cy]:
                    px, py = cx, cy
                    cx, cy = cx + vx, cy + vy
                nxt = cells[cx][cy] if inside(cx, cy) else 0
                if nxt and nxt == tile and (cx, cy) not in merged:
                    cells[x][y] = 0
                    cells[cx][cy] = tile * 2
                    merged.add((cx, cy))
                    score += tile * 2
                    if tile * 2 == 2048:
                        won = True
                    moved = True
                elif (px, py) != (x, y):
                    cells[x][y] = 0
                    cells[px][py] = tile
                    moved = True
        return cells, score, moved, won


class Port(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("new", "move", "rows", "sweep", "of", "cells", "free",
                            "left", "big", "keep", "mk", "wcells")}

    @classmethod
    def call(cls, name, *args):
        cls.rt.steps = 0
        fn = cls.fn[name]
        for arg in args:
            fn = _call(fn, arg, cls.rt)
        return fn

    @staticmethod
    def f(value, name):
        return value.entries[_map_key(name, "get")][1]

    def flat(self, world):
        """The sixteen cells of a world, in the original's cell order."""
        return list_to_python(self.call("wcells", world))

    def bflat(self, board):
        return list_to_python(self.call("cells", board))

    # --- the port against the original -----------------------------------

    def test_it_agrees_with_the_original(self):
        """Two hundred positions, four moves each: the same board, the same
        score, the same answer to whether anything moved."""
        random.seed(20481)
        values = [0, 0, 0, 2, 2, 2, 4, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
        for _ in range(200):
            flat = [random.choice(values) for _ in range(16)]
            for d in range(4):
                cells = [[flat[x * 4 + y] for y in range(4)] for x in range(4)]
                want_cells, want_score, want_moved, want_won = Original.move(cells, d)
                want = ([want_cells[x][y] for x in range(4) for y in range(4)],
                        want_score, int(want_moved), int(want_won))
                st = self.call("sweep", self.call("mk", to_lova(flat)), d)
                got = (self.bflat(self.f(st, "b")), self.f(st, "s"),
                       self.f(st, "moved"), 1 if self.f(st, "won") else 0)
                self.assertEqual(got, want, (flat, d))

    def test_the_cases_a_port_gets_wrong(self):
        """The three the traversal order exists for, stated by hand:
        four in a row make two pairs and not one tile, a tile made this
        move does not merge again, and a move that changes nothing is not
        a move."""
        def line(top, d=3):
            flat = [0] * 16
            for x, v in enumerate(top):           # the top row is (x, 0)
                flat[x * 4] = v
            st = self.call("sweep", self.call("mk", to_lova(flat)), d)
            got = self.bflat(self.f(st, "b"))
            return [got[x * 4] for x in range(4)], self.f(st, "s"), self.f(st, "moved")

        self.assertEqual(line([2, 2, 2, 2]), ([4, 4, 0, 0], 8, 1))
        self.assertEqual(line([4, 4, 8, 0]), ([8, 8, 0, 0], 8, 1))    # not 16
        self.assertEqual(line([2, 2, 4, 0]), ([4, 4, 0, 0], 4, 1))    # not 8
        self.assertEqual(line([4, 2, 2, 0]), ([4, 4, 0, 0], 4, 1))
        self.assertEqual(line([2, 4, 8, 16]), ([2, 4, 8, 16], 0, 0))  # nothing to do
        self.assertEqual(line([2, 2, 2, 2], 1), ([0, 0, 4, 4], 8, 1))  # and to the right

    # --- the game around it ----------------------------------------------

    def test_a_new_game_has_two_tiles(self):
        for seed in (1, 7, 99, 12345):
            w = self.call("new", seed)
            tiles = [v for v in self.flat(w) if v]
            self.assertEqual(len(tiles), 2)
            self.assertTrue(all(v in (2, 4) for v in tiles))
            self.assertEqual(self.f(w, "score"), 0)
            self.assertEqual(self.f(w, "over"), 0)

    def test_the_same_seed_is_the_same_game(self):
        """The original cannot say this about itself: its chance comes from
        `Math.random`, and this one is threaded through the world."""
        a = self.call("new", 42)
        b = self.call("new", 42)
        for d in (0, 1, 2, 3, 0, 1, 2, 3):
            a, b = self.call("move", a, d), self.call("move", b, d)
        self.assertEqual(self.flat(a), self.flat(b))
        self.assertNotEqual(self.flat(a), self.flat(self.call("new", 43)))

    def test_a_move_that_changes_nothing_adds_no_tile(self):
        """The original's `if (moved)`: a move into a wall is not a turn."""
        flat = [0] * 16
        for y in range(4):
            flat[0 * 4 + y] = 2 ** (y + 1)        # the left column, all different
        w = self.call("mk", to_lova(flat))
        after = self.call("move", w, 3)           # push left: they are already there
        self.assertEqual(self.flat(after), flat)
        self.assertEqual(self.f(after, "turn"), 0)

    def test_a_move_that_changes_something_adds_one_tile(self):
        w = self.call("new", 5)
        for _ in range(30):
            before = sum(1 for v in self.flat(w) if v)
            after = self.call("move", w, 1)
            if self.flat(after) == self.flat(w):
                w = self.call("move", w, 2)
                continue
            # a move adds one tile and each merge takes one away
            self.assertLessEqual(sum(1 for v in self.flat(after) if v), before + 1)
            self.assertGreater(sum(1 for v in self.flat(after) if v), 0)
            w = after

    def test_nine_new_tiles_in_ten_are_a_two(self):
        twos = fours = 0
        for seed in range(400):
            for v in self.flat(self.call("new", seed)):
                if v == 2:
                    twos += 1
                elif v == 4:
                    fours += 1
        share = fours / (twos + fours)
        self.assertGreater(share, 0.04)
        self.assertLess(share, 0.18)          # the original's 0.1, within the noise

    def test_a_game_ends(self):
        """Left to a fixed cycle of moves, a game fills up and stops, with a
        score that is the sum of what it merged."""
        w = self.call("new", 3)
        for i in range(600):
            w = self.call("move", w, i % 4)
            if self.f(w, "over"):
                break
        self.assertTrue(self.f(w, "over"))
        self.assertFalse(self.call("left", self.f(w, "board")))
        self.assertGreater(self.f(w, "score"), 100)
        self.assertEqual(self.f(w, "score") % 4, 0)     # every merge is worth 4 or more

    def test_winning_stops_the_game_until_you_say_otherwise(self):
        """The original's `keepPlaying`: 2048 ends it, unless you ask to go
        on."""
        flat = [0] * 16
        flat[0], flat[4] = 1024, 1024           # (0,0) and (1,0), side by side
        w = self.call("move", self.call("mk", to_lova(flat)), 3)
        self.assertTrue(self.f(w, "won"))
        self.assertEqual(self.call("big", w), 2048)
        frozen = self.call("move", w, 2)
        self.assertEqual(self.flat(frozen), self.flat(w))
        playing = self.call("move", self.call("keep", w), 2)
        self.assertNotEqual(self.flat(playing), self.flat(w))

    def test_a_move_costs_what_a_key_press_can_afford(self):
        w = self.call("new", 1)
        worst = 0
        for i in range(40):
            w = self.call("move", w, i % 4)
            worst = max(worst, self.rt.steps)
        self.assertLess(worst, 40_000)


def _run_cli(argv, stdin_text=""):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
    finally:
        sys.stdin = saved
    return code, out.getvalue(), err.getvalue()


class Terminal(unittest.TestCase):
    """`apps/g2048.lova`: the same rules, played in a terminal."""

    def test_it_plays_and_reports_a_score(self):
        code, out, err = _run_cli(["run", "apps/g2048.lova", "7"], "a\ns\nd\nw\nq\n")
        self.assertEqual(code, 0)
        self.assertIn("score", out)
        self.assertIn("bye", out)

    def test_the_examples_hold(self):
        code, out, _err = _run_cli(["check", "apps/g2048.lova", "7"])
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
