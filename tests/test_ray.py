"""The 3D as geometry: `lib/fixed.lova`, `lib/ray.lova` and
`apps/cube.lova` put to the tests a picture cannot be eyeballed for.

LOVA has no floating point, so the 3D is fixed point -- lengths in
1024ths of a cell, angles in 256ths of a turn, sines from a 65-entry
table.  What a test can check that a screenshot cannot: that the table
really is a sine, that a flat wall reports one distance across every
column that hits it (the fisheye correction, the one thing a hand-rolled
raycaster gets wrong), that a wall stops you and a corner slides you,
that an orb behind a wall is not drawn, and that the door knows what you
are carrying.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest

from core.cli import main
from core.compiler import compile
from core.runtime import Runtime, evaluate, list_to_python
from core.surface import parse_with_prelude

ONE = 1024


def run(src: str, **kw):
    """Evaluate a program with `lib/ray.lova` included."""
    return evaluate(compile(parse_with_prelude('(use "ray")\n' + src))[0],
                    Runtime(max_steps=5_000_000, max_call_depth=10_000, **kw))


def at(x, y, ang, expr, got=""):
    """`expr` evaluated in a world standing at cell (x, y) facing `ang`.

    Positions are cell centres in the language's fixed point; `got` is a
    LOVA expression for the map of orbs already taken.
    """
    world = (f"(put (put (put (put (new-game 0) px {int(x * ONE)}) "
             f"py {int(y * ONE)}) ang {ang}) got {got or '(nil)'})")
    return run(f"(let w {world} {expr})")


def fields(value, *names):
    from core.runtime import _map_key
    return [value.entries[_map_key(n, "get")][1] for n in names]


class FixedPoint(unittest.TestCase):
    """`lib/fixed.lova`: the arithmetic both 3D programs stand on."""

    def test_the_square_root(self):
        import math
        ns = [0, 1, 4, 100, 9999, 250_000, 1024 * 1024]
        got = list_to_python(run("(map isqrt (list %s))" % " ".join(map(str, ns))))
        for n, g in zip(ns, got):
            want = math.isqrt(n)
            # Newton from ONE: exact where it matters, never low, and at
            # the very bottom of the range no more than a few units high
            self.assertGreaterEqual(g, want)
            self.assertLessEqual(g - want, max(2, want // 100))

    def test_the_unit_circle_on_the_square_root(self):
        """What an orb's round edge is: sqrt(ONE^2 - k^2) at k = 0 is ONE
        and at k = ONE is nothing."""
        self.assertEqual(run("(isqrt (mul ONE ONE))"), 1024)
        self.assertEqual(run("(isqrt 0)"), 0)


class Trigonometry(unittest.TestCase):
    """A sine from a table of 65 integers, reflected into four quadrants."""

    def test_the_quadrants(self):
        self.assertEqual(list_to_python(run("(map sin (list 0 64 128 192 256))")),
                         [0, 1024, 0, -1024, 0])
        self.assertEqual(list_to_python(run("(map cos (list 0 64 128 192))")),
                         [1024, 0, -1024, 0])

    def test_it_is_a_circle(self):
        """sin^2 + cos^2 is 1 at every angle, to a part in a thousand."""
        sq = run("(map (lambda a (merge (mul (sin a) (sin a)) (mul (cos a) (cos a))))"
                 "     (range 0 256))")
        for value in list_to_python(sq):
            self.assertAlmostEqual(value / (ONE * ONE), 1.0, delta=0.002)

    def test_negative_angles_are_the_same_circle(self):
        self.assertEqual(run("(sin -64)"), run("(sin 192)"))


class TheMaze(unittest.TestCase):

    def test_the_shell_is_unbroken(self):
        """Nothing inside can look out of the grid, which is what lets the
        ray marcher skip its bounds test."""
        rows = [row for row in list_to_python(run("level"))]
        self.assertEqual(len(rows), 23)
        self.assertTrue(all(len(row) == 23 for row in rows))
        self.assertTrue(all(ch != "." for ch in rows[0] + rows[-1]))
        self.assertTrue(all(row[0] != "." and row[-1] != "." for row in rows))

    def test_outside_the_grid_is_solid(self):
        self.assertTrue(run("(wall-at -1 5)"))
        self.assertTrue(run("(wall-at 5 99)"))
        self.assertFalse(run("(wall-at 1 1)"))


class Casting(unittest.TestCase):

    def test_a_wall_straight_ahead_is_where_the_map_says(self):
        """From the middle of cell (1, 1) facing east, the wall at x = 8
        is 6.5 cells away and is built of `1`."""
        d, k = list_to_python(at(1.5, 1.5, 0, "(let c (nth (get (frame w 9 100) cols) 4)"
                                              "  (list (get c d) (get c k)))"))
        self.assertAlmostEqual(d / ONE, 6.5, delta=0.02)
        self.assertEqual(k, ord("1"))

    def test_a_flat_wall_is_flat(self):
        """The fisheye correction: every column that lands on the same
        face reports the same distance, not a longer one at the edges."""
        ds = list_to_python(at(1.5, 1.5, 0,
                               "(map (lambda c (get c d))"
                               "     (filter (lambda c (and (eq (get c k) 49) (not (get c s))))"
                               "             (get (frame w 41 100) cols)))"))
        self.assertGreaterEqual(len(ds), 5)
        self.assertEqual(max(ds) - min(ds), 0)

    def test_walking_closer_makes_the_wall_taller(self):
        far = at(1.5, 1.5, 0, "(get (nth (get (frame w 9 100) cols) 4) h)")
        near = at(5.5, 1.5, 0, "(get (nth (get (frame w 9 100) cols) 4) h)")
        self.assertGreater(near, far * 2)

    def test_the_two_faces_of_a_corner_are_told_apart(self):
        """`s` says which face you see -- it is the whole of the shading."""
        sides = set(list_to_python(at(1.5, 1.5, 0,
                                      "(map (lambda c (get c s))"
                                      "     (get (frame w 41 100) cols))")))
        self.assertEqual(sides, {0, 1})

    def test_a_frame_is_a_function_of_the_world(self):
        pair = at(3.5, 1.5, 32,
                  "(let a (frame w 24 80) (let b (frame w 24 80)"
                  "  (eq (text-cmp (map (lambda c (get c h)) (get a cols))"
                  "                (map (lambda c (get c h)) (get b cols))) 0)))")
        self.assertEqual(pair, 1)

    def test_every_column_of_every_view_hits_something(self):
        """A ray that ran out of maze would come back at the far ceiling,
        40 cells out; none does, from anywhere you can stand."""
        worst = run("(fold (lambda m (lambda p"
                    "        (max m (fold (lambda n (lambda c (max n (get c d)))) 0"
                    "                     (get (frame (put (put (put (new-game 0) px (head p))"
                    "                                            py (head (tail p)))"
                    "                                       ang (head (tail (tail p))))"
                    "                                 24 80) cols)))))"
                    "      0"
                    "      (list (list 1536 1536 0) (list 1536 1536 64)"
                    "            (list 9728 9728 32) (list 20992 20992 160)"
                    "            (list 16896 9728 96)))")
        self.assertLess(worst, 40 * ONE)


class Walking(unittest.TestCase):

    def test_a_wall_stops_you(self):
        """Facing the wall at x = 8 from cell 7, forward does not move you."""
        x = at(7.5, 1.5, 0, "(get (step (step (step w 1) 1) 1) px)")
        self.assertLess(x / ONE, 7.75)

    def test_a_corner_slides_you_along(self):
        """Into a wall at an angle: the axis that is free still moves."""
        after = list_to_python(
            at(7.5, 1.5, 16, "(let v (fold (lambda ww (lambda i (step ww 1))) w (range 0 4))"
                             "  (list (sub (get v px) (get w px)) (sub (get v py) (get w py))))"))
        self.assertLess(after[0], 250)       # x stops at the wall, one step in
        self.assertGreater(after[1], 350)    # y walks on, four steps' worth

    def test_turning_comes_back_round(self):
        self.assertEqual(at(1.5, 1.5, 0,
                            "(get (fold (lambda ww (lambda i (step ww 4))) w (range 0 32)) ang)"),
                         0)


class Orbs(unittest.TestCase):

    def test_standing_in_the_cell_takes_the_orb(self):
        before, after = list_to_python(
            at(20.5, 1.5, 0, "(list (orbs-left w) (orbs-left (step (step (step w 1) 1) 1)))"))
        self.assertEqual(before, 6)
        self.assertEqual(after, 5)

    def test_an_orb_ahead_of_you_is_drawn_where_it_stands(self):
        """The orb in cell (21, 1), seen from (17.5, 1.5) facing east: four
        cells out, in the middle of the screen, resting on the floor."""
        cols = list_to_python(at(17.5, 1.5, 0, "(get (frame w 40 20) spr)"))
        self.assertTrue(cols)
        xs = [fields(s, "c")[0] for s in cols]
        self.assertTrue(all(16 <= x <= 23 for x in xs), xs)
        self.assertEqual({fields(s, "d")[0] for s in cols}, {4 * ONE})
        spans = [fields(s, "u")[0] - fields(s, "t")[0] for s in cols]
        # an orb is a ball: tallest in the middle, nothing at the rim
        self.assertEqual(max(spans), max(spans[len(spans) // 2 - 1:len(spans) // 2 + 1]))
        self.assertEqual(min(spans), spans[0])
        middle = cols[len(cols) // 2]
        top, bot = fields(middle, "t", "u")
        self.assertLessEqual(top, 11)             # the horizon of a 20-row view
        self.assertGreaterEqual(bot, 11)          # and resting on the floor below it

    def test_an_orb_off_to_the_side_is_not_drawn(self):
        """Facing north from (17.5, 1.5): the two orbs in the row are due
        east and due west of you, so neither is in front of the camera."""
        self.assertEqual(list_to_python(at(17.5, 1.5, 192, "(get (frame w 40 20) spr)")), [])

    def test_an_orb_behind_a_wall_is_not_drawn(self):
        """From cell (3, 1) the orb at (13, 1) is there, and so is the wall
        at x = 8 in front of it."""
        self.assertEqual(list_to_python(at(3.5, 1.5, 0, "(get (frame w 40 20) spr)")), [])

    def test_an_orb_taken_is_gone_from_the_picture(self):
        got = "(map-put (nil) (cell-key 21 1) 1)"
        world = (f"(put (put (put (put (new-game 0) px {int(17.5 * ONE)}) py {1536}) "
                 f"ang 0) got {got})")
        self.assertEqual(list_to_python(run(f"(let w {world} (get (frame w 40 20) spr))")), [])


class TheDoor(unittest.TestCase):

    ALL_SIX = ("(fold (lambda m (lambda o (map-put m (cell-key (get o x) (get o y)) 1)))"
               " (nil) orb-cells)")

    def test_it_is_sealed_until_you_have_them_all(self):
        status = at(20.5, 20.5, 0, "(get (step (step w 1) 1) status)")
        self.assertEqual(status, 0)
        msg = at(20.5, 20.5, 0, "(get (step (step w 1) 1) msg)")
        self.assertIn("sealed", msg)

    def test_it_opens_when_you_have(self):
        status = at(20.5, 20.5, 0, "(get (step (step w 1) 1) status)", got=self.ALL_SIX)
        self.assertEqual(status, 1)

    def test_a_wall_is_not_a_door(self):
        status = at(7.5, 1.5, 0, "(get (step (step w 1) 1) status)", got=self.ALL_SIX)
        self.assertEqual(status, 0)


class Cost(unittest.TestCase):
    """The budget the hosts set is real: a frame has to fit in a tick."""

    def test_a_frame_of_eighty_columns_costs_what_the_window_allows(self):
        rt = Runtime(max_steps=5_000_000, max_call_depth=10_000)
        tree = compile(parse_with_prelude(
            '(use "ray")\n(len (get (frame (new-game 0) 80 420) cols))'))[0]
        self.assertEqual(evaluate(tree, rt), 80)
        self.assertLess(rt.steps, 120_000)


class TheCube(unittest.TestCase):
    """`apps/cube.lova`: the other kind of 3D -- eight corners, a
    rotation about two axes, and a perspective divide."""

    SRC = open("apps/cube.lova", encoding="utf-8").read()

    def cube(self, expr):
        """The cube's definitions, without its input loop."""
        body = self.SRC.split('(use "fixed")')[1].split(";; --- the loop")[0]
        return evaluate(compile(parse_with_prelude(
            '(use "fixed")\n' + body + expr))[0],
            Runtime(max_steps=5_000_000, max_call_depth=10_000))

    def test_a_corner_keeps_its_distance_from_the_middle(self):
        """Unturned, the eight corners project to four screen points, two
        deep each, symmetric about the middle of the screen."""
        pts = list_to_python(self.cube(
            "(map (lambda v (let p (project (spin v 0 0)) (list (get p c) (get p r))))"
            "     corners)"))
        cs = sorted({list_to_python(p)[0] for p in pts})
        rs = sorted({list_to_python(p)[1] for p in pts})
        self.assertEqual(len(cs), 4)                  # two depths, two sides
        # symmetric about the middle of the screen, to the rounding:
        # `div` floors, so a corner below the middle and its mirror above
        # can land a row apart
        self.assertLessEqual(abs(cs[0] + cs[-1] - 2 * 31), 1)
        self.assertLessEqual(abs(rs[0] + rs[-1] - 2 * 12), 1)

    def test_the_far_face_is_the_smaller_one(self):
        """The perspective divide, which is the whole of the 3D."""
        widths = list_to_python(self.cube(
            "(map (lambda s"
            "       (let ps (map (lambda v (project (spin v 0 0)))"
            "                    (filter (lambda v (eq (get v z) s)) corners))"
            "         (sub (fold (lambda m (lambda p (max m (get p c)))) 0 ps)"
            "              (fold (lambda m (lambda p (min m (get p c)))) 999 ps))))"
            "     (list (neg ONE) ONE))"))
        near, far = widths
        self.assertGreater(near, far)
        self.assertGreater(near, far * 3 // 2)

    def test_the_picture_is_the_size_it_says(self):
        rows = [row for row in list_to_python(self.cube(
            "(map (lambda r (row-text (draw 28 20) r)) (range 0 H))"))]
        self.assertEqual(len(rows), 25)
        self.assertTrue(all(len(row) == 62 for row in rows))
        self.assertIn("@", "".join(rows))             # the nearest edge

    def test_it_runs_and_stops(self):
        code, out, err = _run_cli(["run", "apps/cube.lova"], "\n3\nq\n")
        self.assertEqual(code, 0)
        self.assertIn("turn 28 of 256", out)          # the first frame
        self.assertIn("=> 4", err)                    # one step, then three


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


class TheTerminal(unittest.TestCase):
    """`apps/maze.lova`: the same rules, drawn in characters."""

    def test_it_draws_a_view_and_a_plan(self):
        code, out, err = _run_cli(["run", "apps/maze.lova", "0"], "ww\nq\n")
        self.assertEqual(code, 0)
        self.assertIn("orbs left  6", out)
        self.assertIn("bye", out)
        # the plan in the corner has you in it, facing east
        self.assertIn("E", out)
        # every drawn row is the view plus, for the first nine, the plan
        rows = [line for line in out.split("\n") if line.startswith("#")]
        self.assertTrue(rows)
        self.assertTrue(all(len(row) in (60, 71) for row in rows), sorted({len(r) for r in rows}))

    def test_the_end_of_the_input_leaves_the_maze(self):
        code, out, err = _run_cli(["run", "apps/maze.lova", "0"], "")
        self.assertEqual(code, 0)
        self.assertIn("bye", out)
        self.assertIn("=> 0", err)

    def test_the_examples_in_the_library_hold(self):
        code, out, _err = _run_cli(["check", "apps/maze.lova", "0"])
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
