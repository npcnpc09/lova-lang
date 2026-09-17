"""The platformer, checked against the kit it was ported from.

`lib/platformer.lova` is a port of the rules of
KenneyNL/Starter-Kit-3D-Platformer (MIT).  `Original` below is a
transliteration of the kit's `player.gd`, `view.gd`, `coin.gd`,
`platform_falling.gd` and `brick.gd` -- the wanted velocity turned by
the camera, the lerp of a sixth, gravity's gain of twenty-five a
second and its cancellation on the floor, the jump of seven and the
second jump, the landing squash, the camera's lerps of a fifteenth, a
tenth and two fifteenths, the coin's reach, the falling platform's
fifteen a second, the brick struck from below, the world's bottom at
minus ten -- in floating point, with the same collision model the port
uses in its place of Godot's physics: boxes and cylinders under a
segment with a radius.  That model is the one thing here that is ours
rather than the kit's, and the header of `lib/platformer.lova` says so.

`test_it_agrees_tick_by_tick` runs both from the same state for one
tick at a time over a scripted play -- standing, walking onto the next
platform, jumping twice, taking a coin, walking off the world -- and
compares the player, the camera and every changed thing to within a
few thousandths.  `test_it_agrees_over_a_run` lets the two run free
over the same keys and checks that the same things happened: the same
coins taken, the same bricks broken, the same platforms fallen, the
same number of falls off the world.
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

API = """\
(use "platformer")
(rec new new-game tick tick input input still still
     p (lambda w (get w p))
     cam (lambda w (get w cam))
     statics (lambda w (get w statics))
     dynamics (lambda w (get w dynamics))
     field (lambda r (lambda n (map-get r n -1))))
"""


# --- the kit's rules, in floating point ----------------------------------------

class Original:
    """The kit's GDScript, transliterated, over the port's collision model."""

    SPEED = 250
    JUMP = 7.0
    GRAVITY = 25.0
    FEET, HEAD, RADIUS = 0.05, 1.05, 0.3
    SEGLO, SEGHI = 0.35, 0.75
    EDGE, STEP, SNAP = 0.2, 0.1, 0.02
    COIN_REACH = 0.8
    BOTTOM = -10.0
    NEAR_XZ, NEAR_Y = 4.0, 3.0

    HALF = {"platform": 1.0, "platform-medium": 1.5, "platform-grass-large-round": 2.5,
            "platform-falling": 1.1, "brick": 0.375}
    TOP = {"platform-grass-large-round": 0.5, "platform-falling": 0.5, "brick": 0.75}

    def __init__(self, level, start):
        self.things = []
        for i, it in enumerate(level):
            self.things.append(dict(it, id=i, taken=False, falling=False, fv=0.0, dy=0.0,
                                    gone=False, puff=0.0))
        self.start = start
        self.reset()
        self.resets = 0

    def reset(self):
        self.x, self.y, self.z = self.start
        self.vx = self.vz = 0.0
        self.wx = self.wz = 0.0
        self.gravity = 0.0
        self.face = self.fdir = 0.0          # radians
        self.jump_single = self.jump_double = True
        self.floored = self.prev = False
        self.sx = self.sy = 1.0
        self.struck = -1
        self.cam = dict(x=0.0, y=0.0, z=0.0, yaw=math.radians(45), pitch=math.radians(-25),
                        tyaw=math.radians(45), tpitch=math.radians(-25), zoom=10.0, tzoom=10.0)
        for it in self.things:
            it.update(taken=False, falling=False, fv=0.0, dy=0.0, gone=False, puff=0.0)
        self.t = 0
        self.coins = 0

    # --- solids ---

    @staticmethod
    def solid(it):
        return it["kind"] in ("platform", "round", "falling", "brick") and not it["gone"]

    def local(self, it, px, pz):
        a = it["yaw"]
        dx, dz = px - it["x"], pz - it["z"]
        return dx * math.cos(a) - dz * math.sin(a), dx * math.sin(a) + dz * math.cos(a)

    def over(self, it, px, pz, margin):
        reach = self.HALF[it["model"]] + margin
        if it["kind"] == "round":
            return (px - it["x"]) ** 2 + (pz - it["z"]) ** 2 <= reach * reach
        lx, lz = self.local(it, px, pz)
        return abs(lx) <= reach and abs(lz) <= reach

    def top(self, it):
        return it["y"] + it["dy"] + self.TOP.get(it["model"], 0.55)

    def bottom(self, it):
        return it["y"] + it["dy"]

    def near(self, it):
        return (abs(it["x"] - self.x) <= self.NEAR_XZ and abs(it["z"] - self.z) <= self.NEAR_XZ
                and abs(it["y"] + it["dy"] - self.y) <= self.NEAR_Y)

    # --- a tick ---

    @staticmethod
    def coarse(angle):
        """An angle as the port's sine table sees it: whole 256ths of a turn."""
        return math.floor(angle / TAU * 256) * TAU / 256

    def tick(self, mx, mz, jump, cx, cy, zoom):
        # handle_controls
        a = self.coarse(self.cam["yaw"])
        ix = mx * math.cos(a) + mz * math.sin(a)
        iz = -mx * math.sin(a) + mz * math.cos(a)
        length = math.hypot(ix, iz)
        if length > 1:
            ix, iz = ix / length, iz / length
        self.wx = ix * self.SPEED * DT
        self.wz = iz * self.SPEED * DT
        if jump and (self.jump_single or self.jump_double):
            self.gravity = -self.JUMP
            self.sx, self.sy = 0.5, 1.5
            if self.jump_single:
                self.jump_single, self.jump_double = False, True
            else:
                self.jump_double = False
        # handle_gravity
        self.gravity += self.GRAVITY * DT
        if self.gravity > 0 and self.floored:
            self.jump_single = True
            self.gravity = 0.0
        # the move
        solids = [it for it in self.things if self.solid(it) and self.near(it)]
        self.vx += (self.wx - self.vx) * DT * 10
        self.vz += (self.wz - self.vz) * DT * 10
        y0 = self.y
        self.x += self.vx * DT
        self.z += self.vz * DT
        self.floored = False
        self.struck = -1
        for it in solids:
            self.push_out(it)
        self.y -= self.gravity * DT
        for it in solids:
            self.land(it, y0)
            self.bump(it, y0)
        # after the move
        if self.vx or self.vz:
            self.fdir = math.atan2(self.vx, self.vz)
        diff = (self.fdir - self.face + math.pi) % TAU - math.pi
        self.face = (self.face + diff / 6) % TAU
        landed = self.floored and self.gravity > 2 and not self.prev
        if landed:
            self.sx, self.sy = 1.25, 0.75
        else:
            self.sx += (1 - self.sx) / 6
            self.sy += (1 - self.sy) / 6
        self.prev = self.floored
        # the things
        for it in self.things:
            self.thing_tick(it)
        # the camera
        c = self.cam
        c["tyaw"] += cx * math.radians(120) * DT
        c["tpitch"] = max(math.radians(-80), min(math.radians(-10),
                                                  c["tpitch"] + cy * math.radians(120) * DT))
        c["tzoom"] = max(4.0, min(16.0, c["tzoom"] + zoom * 10 * DT))
        c["x"] += (self.x - c["x"]) * DT * 4
        c["y"] += (self.y - c["y"]) * DT * 4
        c["z"] += (self.z - c["z"]) * DT * 4
        c["yaw"] += (c["tyaw"] - c["yaw"]) * DT * 6
        c["pitch"] += (c["tpitch"] - c["pitch"]) * DT * 6
        c["zoom"] += (c["tzoom"] - c["zoom"]) * DT * 8
        self.coins = sum(1 for it in self.things if it["taken"])
        self.t += 1
        if self.y < self.BOTTOM:
            t = self.t
            self.reset()
            self.t = t
            self.resets += 1

    def push_out(self, it):
        if not (self.top(it) > self.y + self.FEET + self.STEP and self.bottom(it) < self.y + self.HEAD):
            return
        reach = self.HALF[it["model"]] + self.RADIUS
        if it["kind"] == "round":
            dx, dz = self.x - it["x"], self.z - it["z"]
            d = math.hypot(dx, dz)
            if d < reach:
                d = max(d, 1e-9)
                self.x = it["x"] + dx / d * reach
                self.z = it["z"] + dz / d * reach
            return
        lx, lz = self.local(it, self.x, self.z)
        if abs(lx) >= reach or abs(lz) >= reach:
            return
        ox, oz = reach - abs(lx), reach - abs(lz)
        if ox <= oz:
            px, pz = (ox if lx >= 0 else -ox), 0.0
        else:
            px, pz = 0.0, (oz if lz >= 0 else -oz)
        a = it["yaw"]
        self.x += px * math.cos(a) + pz * math.sin(a)
        self.z += pz * math.cos(a) - px * math.sin(a)

    def land(self, it, y0):
        if (self.gravity >= 0 and self.over(it, self.x, self.z, self.EDGE)
                and y0 + self.FEET >= self.top(it) - self.SNAP
                and self.y + self.FEET <= self.top(it)):
            self.y = self.top(it) - self.FEET
            self.floored = True

    def bump(self, it, y0):
        if (self.gravity < 0 and self.over(it, self.x, self.z, self.RADIUS)
                and y0 + self.HEAD <= self.bottom(it) and self.y + self.HEAD > self.bottom(it)):
            self.y = self.bottom(it) - self.HEAD
            self.struck = it["id"]

    def coin_hit(self, it):
        # the port's bob is 217 sixteen-thousandths of a turn a tick (five
        # radians a second), read from its table in 256ths
        cy = it["y"] + 0.5 + 0.2 * math.sin(self.coarse(217 * self.t / A * TAU))
        sy = max(self.y + self.SEGLO, min(self.y + self.SEGHI, cy))
        return ((it["x"] - self.x) ** 2 + (cy - sy) ** 2 + (it["z"] - self.z) ** 2
                <= self.COIN_REACH ** 2)

    def thing_tick(self, it):
        k = it["kind"]
        if k == "coin":
            if not it["taken"] and self.near(it) and self.coin_hit(it):
                it["taken"] = True
        elif k == "falling":
            on_it = (self.floored and self.over(it, self.x, self.z, self.EDGE)
                     and abs(self.y + self.FEET - self.top(it)) < 1e-6)
            if it["falling"] or (self.near(it) and on_it):
                it["fv"] += 15.0 * DT
                it["dy"] -= it["fv"] * DT
                it["puff"] = it["puff"] - it["puff"] / 6 if it["falling"] else 0.25
                it["falling"] = True
                if self.bottom(it) < self.BOTTOM:
                    it["gone"] = True
        elif k == "brick":
            if self.struck == it["id"]:
                it["gone"] = True


# --- the port -------------------------------------------------------------------

class Port(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=200_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("new", "tick", "input", "still", "p", "cam", "statics",
                            "dynamics", "field")}

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

    def things_of(self, world):
        out = []
        for it in list_to_python(self.call("statics", world)) + list_to_python(self.call("dynamics", world)):
            out.append({n: self.get(it, n) for n in
                        ("id", "x", "y", "z", "yaw", "taken", "falling", "fv", "dy",
                         "gone", "puff", "model", "kind")})
        return sorted(out, key=lambda it: it["id"])

    def level_of(self, world):
        """The level as the original wants it: metres and radians, in id order."""
        return [dict(kind=it["kind"], model=it["model"], x=it["x"] / F, y=it["y"] / F,
                     z=it["z"] / F, yaw=it["yaw"] / A * TAU) for it in self.things_of(world)]

    def player_of(self, world):
        p = self.get(world, "p")
        return {n: self.get(p, n) for n in ("x", "y", "z", "vx", "vz", "g", "face", "j1", "j2",
                                             "floored", "sx", "sy", "struck")}

    def camera_of(self, world):
        c = self.get(world, "cam")
        return {n: self.get(c, n) for n in ("x", "y", "z", "yaw", "pitch", "zoom")}

    # --- the plays ---

    @staticmethod
    def script():
        """(ticks, (mx, mz, jump, cx, cy, zoom)): a play across the level."""
        still = (0, 0, 0, 0, 0, 0)
        west = (-1, -1, 0, 0, 0, 0)           # W and A: straight along -x under a 45 degree camera
        return ([(30, still), (44, west), (10, still), (1, (0, 0, 1, 0, 0, 0)), (12, still),
                 (1, (0, 0, 1, 0, 0, 0)), (40, still), (20, (-1, -1, 0, 1, 0, 0)),
                 (20, (0, -1, 0, 0, 1, -1)), (30, (-1, 0, 0, 0, 0, 1)), (1, (0, 0, 1, 0, 0, 0)),
                 (60, (-1, -1, 0, 0, 0, 0)), (1, (-1, -1, 1, 0, 0, 0)), (90, (-1, -1, 0, 0, 0, 0)),
                 (200, (0, 1, 0, 0, 0, 0))])

    def keys(self):
        for ticks, held in self.script():
            for _ in range(ticks):
                yield held

    # --- one tick at a time ---

    def test_it_agrees_tick_by_tick(self):
        """From the same state, one tick of each lands within a few
        thousandths: the port's rounding to 65 536ths is the only
        difference there is."""
        world = self.fn["new"]
        start = tuple(self.player_of(world)[n] / F for n in "xyz")
        ref = Original(self.level_of(world), start)
        ticks = 0
        for held in self.keys():
            # the reference takes the port's state, then both take one tick
            p, c = self.player_of(world), self.camera_of(world)
            ref.x, ref.y, ref.z = p["x"] / F, p["y"] / F, p["z"] / F
            ref.vx, ref.vz = p["vx"] / F, p["vz"] / F
            ref.gravity = p["g"] / F
            ref.face = p["face"] / A * TAU
            ref.jump_single, ref.jump_double = bool(p["j1"]), bool(p["j2"])
            ref.floored = ref.prev = bool(p["floored"])
            ref.sx, ref.sy = p["sx"] / F, p["sy"] / F
            ref.cam.update(x=c["x"] / F, y=c["y"] / F, z=c["z"] / F, zoom=c["zoom"] / F,
                           yaw=c["yaw"] / A * TAU, pitch=c["pitch"] / A * TAU)
            cam = self.get(world, "cam")
            ref.cam.update(tyaw=self.get(cam, "tyaw") / A * TAU,
                           tpitch=self.get(cam, "tpitch") / A * TAU,
                           tzoom=self.get(cam, "tzoom") / F)
            things = self.things_of(world)
            for it, rit in zip(things, ref.things):
                rit.update(taken=bool(it["taken"]), falling=bool(it["falling"]),
                           fv=it["fv"] / F, dy=it["dy"] / F, gone=bool(it["gone"]),
                           puff=it["puff"] / F)
            ref.t = self.get(world, "t")
            ref.tick(*held)
            world = self.call("tick", world, self.call("input", *held))
            ticks += 1
            if ref.resets:
                # both fell off the world this tick; the port starts over too
                self.assertEqual(self.get(world, "resets"), 1, ticks)
                break
            p, c = self.player_of(world), self.camera_of(world)
            tol = 0.004
            for name, got, want in (("x", p["x"] / F, ref.x), ("y", p["y"] / F, ref.y),
                                    ("z", p["z"] / F, ref.z), ("vx", p["vx"] / F, ref.vx),
                                    ("vz", p["vz"] / F, ref.vz), ("g", p["g"] / F, ref.gravity),
                                    ("sx", p["sx"] / F, ref.sx), ("sy", p["sy"] / F, ref.sy),
                                    ("cam x", c["x"] / F, ref.cam["x"]),
                                    ("cam y", c["y"] / F, ref.cam["y"]),
                                    ("cam z", c["z"] / F, ref.cam["z"]),
                                    ("zoom", c["zoom"] / F, ref.cam["zoom"])):
                self.assertAlmostEqual(got, want, delta=tol, msg=f"tick {ticks}: {name}")
            for name, got, want in (("yaw", c["yaw"] / A * TAU, ref.cam["yaw"]),
                                    ("pitch", c["pitch"] / A * TAU, ref.cam["pitch"]),
                                    ("face", p["face"] / A * TAU, ref.face)):
                diff = (got - want + math.pi) % TAU - math.pi
                # the port's atan2 is to 1.4 degrees, and the facing lerps toward it
                self.assertLess(abs(diff), math.radians(2.0), f"tick {ticks}: {name}")
            self.assertEqual(bool(p["floored"]), ref.floored, f"tick {ticks}: floored")
            self.assertEqual(bool(p["j1"]), ref.jump_single, f"tick {ticks}: jump_single")
            self.assertEqual(bool(p["j2"]), ref.jump_double, f"tick {ticks}: jump_double")
            for it, rit in zip(self.things_of(world), ref.things):
                self.assertEqual(bool(it["taken"]), rit["taken"], f"tick {ticks}: coin {it['id']}")
                self.assertEqual(bool(it["gone"]), rit["gone"], f"tick {ticks}: thing {it['id']}")
                self.assertEqual(bool(it["falling"]), rit["falling"], f"tick {ticks}: platform {it['id']}")
                self.assertAlmostEqual(it["dy"] / F, rit["dy"], delta=tol, msg=f"tick {ticks}: dy {it['id']}")
        self.assertGreater(ticks, 200)

    # --- a whole run ---

    def test_it_agrees_over_a_run(self):
        """Left to run free over the same keys, the same things happen."""
        world = self.fn["new"]
        start = tuple(self.player_of(world)[n] / F for n in "xyz")
        ref = Original(self.level_of(world), start)
        for held in self.keys():
            ref.tick(*held)
            world = self.call("tick", world, self.call("input", *held))
        things = self.things_of(world)
        taken = sorted(it["id"] for it in things if it["taken"])
        gone = sorted(it["id"] for it in things if it["gone"])
        fallen = sorted(it["id"] for it in things if it["falling"])
        self.assertEqual(taken, sorted(it["id"] for it in ref.things if it["taken"]))
        self.assertEqual(gone, sorted(it["id"] for it in ref.things if it["gone"]))
        self.assertEqual(fallen, sorted(it["id"] for it in ref.things if it["falling"]))
        self.assertEqual(self.get(world, "resets"), ref.resets)
        self.assertEqual(self.get(world, "coins"), ref.coins)
        p = self.player_of(world)
        self.assertAlmostEqual(p["x"] / F, ref.x, delta=0.05)
        self.assertAlmostEqual(p["z"] / F, ref.z, delta=0.05)

    # --- the play itself did something ---

    def test_the_play_exercises_the_rules(self):
        """The script is worth running: it takes a coin, jumps twice,
        and falls off the world at least once."""
        world = self.fn["new"]
        jumps = 0
        fell = 0
        for held in self.keys():
            before = self.player_of(world)
            world = self.call("tick", world, self.call("input", *held))
            after = self.player_of(world)
            if held[2] and after["g"] < before["g"]:
                jumps += 1
            fell = self.get(world, "resets")
        self.assertGreaterEqual(jumps, 2)
        self.assertGreaterEqual(fell, 1)
        # the coins taken before the fall are counted in the run above;
        # here, that the first walk across takes the first coin
        world = self.fn["new"]
        for held in list(self.keys())[:80]:
            world = self.call("tick", world, self.call("input", *held))
        self.assertGreaterEqual(self.get(world, "coins"), 1)


if __name__ == "__main__":
    unittest.main()
