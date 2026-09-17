"""The city builder, checked against the kit it was ported from.

`lib/citybuilder.lova` is a port of the rules of
KenneyNL/Starter-Kit-City-Builder (MIT).  `Original` below is a
transliteration of the kit's `builder.gd` and `view.gd` in floating
point: the till charged only when the cell's previous structure was a
different one, demolition of what is there and nothing otherwise, the
cursor's quarter turns and the catalogue's wrap-around, the cursor's
lerp of two thirds, the camera's pan of a quarter metre a frame turned
by its yaw and cut to unit length, its turn of a tenth of a degree per
pixel of mouse travel, its zoom in steps of five between fifteen and
eighty, and its three lerps -- and `Camera3D.project_ray_origin` /
`project_ray_normal` / `Plane.intersects_ray`, which is what a click
means.

`test_it_agrees_tick_by_tick` runs both from the same state one tick
at a time over a scripted session -- panning, turning, zooming,
cycling the catalogue, building, building over, demolishing -- and
compares the till, the catalogue index, the cursor's cell and turn,
the city's cells and the camera to within a few thousandths.
`test_the_mouse_lands_on_the_same_cell` unprojects a grid of pixels
through both and asks for the same cell wherever the floating-point
answer is not within eight hundredths of a cell boundary.
"""

from __future__ import annotations

import math
import unittest

from core.cli import build
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

F = 65536
A = 16384
DT = 1 / 60
TAU = 2 * math.pi
FOCAL, SW, SH = 391, 960, 600

API = """\
(use "citybuilder")
(rec new new-game sample sample-game tick tick input input
     cells city-cells ground ground-at
     cash (lambda w (get w cash))
     index (lambda w (get w index))
     cursor (lambda w (get w cursor))
     cam (lambda w (get w cam))
     prices (map (lambda c (get c price)) catalogue))
"""


class Original:
    """builder.gd and view.gd, transliterated."""

    def __init__(self, prices, cells=(), cash=10000):
        self.prices = list(prices)
        self.cash = cash
        self.index = 0
        self.city = {(x, z): (s, q) for x, z, s, q in cells}
        self.cursor = dict(x=0.0, z=0.0, cx=0, cz=0, q=0)
        self.cam = dict(x=0.0, z=0.0, tx=0.0, tz=0.0, yaw=math.radians(45),
                        tyaw=math.radians(45), pitch=math.radians(-35), zoom=30.0, tzoom=30.0)

    # --- the camera as Godot has it ---

    @staticmethod
    def basis(yaw, pitch):
        """Ry(yaw) . Rx(pitch), as rows."""
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
        rx = [[1, 0, 0], [0, cp, -sp], [0, sp, cp]]
        return [[sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    @staticmethod
    def coarse(angle):
        """An angle as the port's sine table sees it: whole 256ths of a turn."""
        return math.floor(angle / TAU * 256) * TAU / 256

    def ground_at(self, u, v):
        """`plane.intersects_ray(project_ray_origin(m), project_ray_normal(m))`."""
        c = self.cam
        b = self.basis(self.coarse(c["yaw"]), self.coarse(c["pitch"]))
        eye = [c["x"], 0.0, c["z"]]
        eye = [eye[i] + b[i][2] * c["zoom"] for i in range(3)]
        d = [u - SW / 2, SH / 2 - v, -FOCAL]
        d = [sum(b[i][k] * d[k] for k in range(3)) for i in range(3)]
        if d[1] >= 0:
            return None
        t = -eye[1] / d[1]
        return eye[0] + d[0] * t, eye[2] + d[2] * t

    def tick(self, mx, mz, rot, zoom, centre, build, demolish, rotate, nxt, prev, mu, mv):
        # action_structure_toggle
        self.index = (self.index + nxt - prev) % len(self.prices)
        # the cursor
        if mu >= 0:
            ground = self.ground_at(mu, mv)
            if ground is not None:
                self.cursor["cx"] = int(round(ground[0])) if abs(ground[0] % 1 - 0.5) > 1e-9 else int(math.floor(ground[0]) + (1 if ground[0] > 0 else 0))
                self.cursor["cz"] = int(round(ground[1])) if abs(ground[1] % 1 - 0.5) > 1e-9 else int(math.floor(ground[1]) + (1 if ground[1] > 0 else 0))
        self.cursor["x"] += (self.cursor["cx"] - self.cursor["x"]) * min(DT * 40, 1.0)
        self.cursor["z"] += (self.cursor["cz"] - self.cursor["z"]) * min(DT * 40, 1.0)
        if rotate:
            self.cursor["q"] = (self.cursor["q"] + 1) % 4
        cell = (self.cursor["cx"], self.cursor["cz"])
        # action_build
        if build:
            previous = self.city.get(cell, (-1, 0))[0]
            self.city[cell] = (self.index, self.cursor["q"])
            if previous != self.index:
                self.cash -= self.prices[self.index]
        # action_demolish
        if demolish and cell in self.city:
            del self.city[cell]
        # view.gd
        c = self.cam
        a = self.coarse(c["yaw"])
        ix = mx * math.cos(a) + mz * math.sin(a)
        iz = -mx * math.sin(a) + mz * math.cos(a)
        length = math.hypot(ix, iz)
        if length > 0:
            ix, iz = ix / length, iz / length
        c["tx"] += ix / 4
        c["tz"] += iz / 4
        if centre:
            c["tx"] = c["tz"] = 0.0
        c["tyaw"] -= math.radians(rot / 10)
        if zoom < 0:
            c["tzoom"] = max(15.0, c["tzoom"] - 5)
        elif zoom > 0:
            c["tzoom"] = min(80.0, c["tzoom"] + 5)
        c["x"] += (c["tx"] - c["x"]) * DT * 8
        c["z"] += (c["tz"] - c["z"]) * DT * 8
        c["yaw"] += (c["tyaw"] - c["yaw"]) * DT * 6
        c["zoom"] += (c["tzoom"] - c["zoom"]) * DT * 8


class Port(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=200_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("new", "sample", "tick", "input", "cells", "ground", "cash",
                            "index", "cursor", "cam", "prices")}
        cls.prices = list_to_python(cls.fn["prices"])

    @classmethod
    def call(cls, name, *args):
        cls.rt.steps = 0
        fn = cls.fn[name]
        for arg in args:
            fn = _call(fn, arg, cls.rt)
        return fn

    @staticmethod
    def get(value, name):
        return value.entries[_map_key(name, "get")][1]

    def cells_of(self, world):
        return {(x, z): (s, q) for x, z, s, q in
                (list_to_python(c) for c in list_to_python(self.call("cells", world)))}

    def state_of(self, world):
        cur = self.get(world, "cursor")
        cam = self.get(world, "cam")
        return (dict(x=self.get(cur, "x") / F, z=self.get(cur, "z") / F,
                     cx=self.get(cur, "cx"), cz=self.get(cur, "cz"), q=self.get(cur, "q")),
                dict(x=self.get(cam, "x") / F, z=self.get(cam, "z") / F,
                     tx=self.get(cam, "tx") / F, tz=self.get(cam, "tz") / F,
                     yaw=self.get(cam, "yaw") / A * TAU, tyaw=self.get(cam, "tyaw") / A * TAU,
                     pitch=self.get(cam, "pitch") / A * TAU,
                     zoom=self.get(cam, "zoom") / F, tzoom=self.get(cam, "tzoom") / F))

    @staticmethod
    def session():
        """(ticks, (mx mz rot zoom centre build demolish rotate next prev mu mv))."""
        quiet = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, -1)
        at = lambda u, v, **k: (k.get("mx", 0), k.get("mz", 0), k.get("rot", 0), k.get("zoom", 0),  # noqa: E731
                                k.get("centre", 0), k.get("build", 0), k.get("demolish", 0),
                                k.get("rotate", 0), k.get("next", 0), k.get("prev", 0), u, v)
        return [(20, quiet), (1, at(480, 300, build=1)), (1, at(480, 300, build=1)),
                (3, at(520, 300, next=1)), (1, at(520, 300, rotate=1)), (1, at(520, 300, build=1)),
                (30, at(600, 350, mx=1)), (30, at(600, 350, mx=1, mz=1)), (1, at(600, 350, build=1)),
                (1, at(600, 350, demolish=1)), (10, at(640, 380, rot=25)), (30, at(640, 380)),
                (1, at(640, 380, zoom=-1)), (1, at(640, 380, zoom=-1)), (40, at(640, 380)),
                (1, at(640, 380, prev=1)), (1, at(640, 380, prev=1)), (1, at(640, 380, build=1)),
                (1, at(300, 420, zoom=1)), (30, at(300, 420, mz=-1)), (1, at(300, 420, centre=1)),
                (60, quiet)]

    def keys(self):
        for ticks, held in self.session():
            for _ in range(ticks):
                yield held

    def test_it_agrees_tick_by_tick(self):
        world = self.fn["sample"]
        ref = Original(self.prices, [(x, z, s, q) for (x, z), (s, q) in self.cells_of(world).items()],
                       cash=self.call("cash", world))
        ticks = 0
        edge_ticks = 0
        for held in self.keys():
            # the reference takes the port's state, then both take one tick
            cur, cam = self.state_of(world)
            ref.cursor.update(cur)
            ref.cam.update(cam)
            ref.cash = self.call("cash", world)
            ref.index = self.call("index", world)
            ref.city = dict(self.cells_of(world))
            # the ground under the mouse as this tick saw it, before the
            # camera moved on
            ground = ref.ground_at(held[10], held[11]) if held[10] >= 0 else None
            ref.tick(*held)
            world = self.call("tick", world, self.call("input", *held), FOCAL, SW, SH)
            ticks += 1
            cur, cam = self.state_of(world)
            self.assertEqual(self.call("index", world), ref.index, f"tick {ticks}: index")
            self.assertEqual(cur["q"], ref.cursor["q"], f"tick {ticks}: turn")
            if (cur["cx"], cur["cz"]) != (ref.cursor["cx"], ref.cursor["cz"]):
                # the two may round a point near a cell boundary apart:
                # the port's angles are to 1.4 degrees.  Allowed there,
                # and only there; the reference takes the port's cell
                # again at the top of the next tick.
                self.assertIsNotNone(ground, f"tick {ticks}: cursor")
                self.assertTrue(any(abs(w % 1 - 0.5) < 0.05 for w in ground),
                                f"tick {ticks}: cursor {cur['cx']},{cur['cz']} against "
                                f"{ref.cursor['cx']},{ref.cursor['cz']} at {ground}")
                edge_ticks += 1
            else:
                self.assertEqual(self.call("cash", world), ref.cash, f"tick {ticks}: cash")
                self.assertEqual(self.cells_of(world), ref.city, f"tick {ticks}: city")
                for name in ("x", "z"):
                    self.assertAlmostEqual(cur[name], ref.cursor[name], delta=0.002,
                                           msg=f"tick {ticks}: cursor {name}")
            for name in ("x", "z", "tx", "tz", "zoom", "tzoom"):
                self.assertAlmostEqual(cam[name], ref.cam[name], delta=0.004,
                                       msg=f"tick {ticks}: camera {name}")
            for name in ("yaw", "tyaw"):
                diff = (cam[name] - ref.cam[name] + math.pi) % TAU - math.pi
                self.assertLess(abs(diff), math.radians(0.05), f"tick {ticks}: camera {name}")
        self.assertGreater(ticks, 250)
        self.assertLess(edge_ticks, ticks // 10)
        self.assertNotEqual(self.call("cash", world), 5860)

    def test_the_mouse_lands_on_the_same_cell(self):
        """A grid of pixels, unprojected by both, names the same cell
        wherever the floating-point point is not within 0.08 of a cell
        boundary -- the port's angles are to 1.4 degrees and its
        positions to 1024ths."""
        world = self.fn["sample"]
        for _ in range(30):
            world = self.call("tick", world, self.call("input", 1, 0, 30, -1, 0, 0, 0, 0, 0, 0, -1, -1),
                              FOCAL, SW, SH)
        ref = Original(self.prices)
        cur, cam = self.state_of(world)
        ref.cam.update(cam)
        compared = agreed = 0
        camera = self.get(world, "cam")
        for u in range(40, SW, 80):
            for v in range(200, SH, 40):
                want = ref.ground_at(u, v)
                got = self.call("ground", camera, u, v, FOCAL, SW, SH)
                if want is None:
                    self.assertEqual(self.get(got, "ok"), 0, f"pixel {u},{v}")
                    continue
                self.assertEqual(self.get(got, "ok"), 1, f"pixel {u},{v}")
                gx, gz = self.get(got, "x") / 1024, self.get(got, "z") / 1024
                # the same ground point, to a few centimetres at a distance
                # of thirty metres
                far = math.hypot(want[0] - cam["x"], want[1] - cam["z"])
                tol = 0.01 * max(10.0, far)
                self.assertAlmostEqual(gx, want[0], delta=tol, msg=f"pixel {u},{v}: x")
                self.assertAlmostEqual(gz, want[1], delta=tol, msg=f"pixel {u},{v}: z")
                if far < 40 and all(abs(w % 1 - 0.5) > 0.08 for w in want):
                    compared += 1
                    if (round(want[0]), round(want[1])) == (round(gx), round(gz)):
                        agreed += 1
        self.assertGreater(compared, 30)
        self.assertEqual(agreed, compared)


if __name__ == "__main__":
    unittest.main()
