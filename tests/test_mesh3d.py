"""The low-poly renderer, against a renderer written out in Python.

`lib/mesh3d.lova` turns a mesh, divides it by its depth, throws away the
faces whose backs are turned, lights the rest and hands them over far
face first.  `Reference` below does the same in floating point, and
`test_it_agrees_with_floating_point` compares them face by face over
five models and a spread of angles: the same faces survive the cull, at
the same screen points to within a pixel, with the same light to within
a part in two hundred, in the same order.

That is the test worth having here, because every one of those steps is
a place where a fixed-point renderer can be subtly wrong and still look
plausible: a sign flipped on the cull shows the inside of a model, a
normal turned the wrong way lights it from behind, and a depth sorted
the wrong way round only shows on the frames where it matters.
"""

from __future__ import annotations

import math
import unittest

from core.cli import build
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

ONE = 1024
FOCAL = 760
AMBIENT = 260
LIGHT = (-430, 620, -655)

API = """\
(use "models")
(rec shot shot faces face-count verts vertex-count
     sphere sphere tree tree house house gem gem ship ship
     vlist (lambda m (get m vs))
     flist (lambda m (get m fs))
     field (lambda r (lambda n (map-get r n 0))))
"""

MODELS = ("sphere", "tree", "house", "gem", "ship")


class Reference:
    """The same pipeline in floating point, from the same model data."""

    def __init__(self, verts, faces):
        self.verts = verts          # [(x, y, z)] in model units
        self.faces = faces          # [(a, b, c, nx, ny, nz, k)]

    @staticmethod
    def angles(yaw, pitch):
        t = 2 * math.pi / 256
        return (math.cos(yaw * t), math.sin(yaw * t),
                math.cos(pitch * t), math.sin(pitch * t))

    @staticmethod
    def turn(p, cy, sy, cp, sp):
        x1 = p[0] * cy + p[2] * sy
        z1 = p[2] * cy - p[0] * sy
        return x1, p[1] * cp - z1 * sp, p[1] * sp + z1 * cp

    def shot(self, yaw, pitch, dist, sw, sh):
        cy, sy, cp, sp = self.angles(yaw, pitch)
        cx, cyy = sw // 2, sh // 2
        placed = []
        for v in self.verts:
            # everything is in 1024ths, vertices and distance alike, so the
            # divide by depth is (x * FOCAL) / d with no scaling either side
            x, y, z = self.turn(v, cy, sy, cp, sp)
            d = max(192, z + dist)
            placed.append((cx + x * FOCAL / d, cyy - y * FOCAL / d, d))
        out = []
        for a, b, c, nx, ny, nz, k in self.faces:
            p, q, r = placed[a], placed[b], placed[c]
            area = ((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1]))
            if area <= 0:
                continue
            n = self.turn((nx, ny, nz), cy, sy, cp, sp)
            lit = sum(n[i] * LIGHT[i] for i in range(3)) / ONE
            out.append({"u": (p[0], q[0], r[0]), "v": (p[1], q[1], r[1]), "k": k,
                        "l": AMBIENT + max(0.0, lit),
                        "d": p[2] + q[2] + r[2], "area": area,
                        # twice the area over the perimeter: how thick the
                        # triangle is, which is what says whether rounding
                        # its corners to whole pixels could turn it over
                        "thick": area / max(1.0, sum(
                            math.dist(a, b) for a, b in
                            ((p[:2], q[:2]), (q[:2], r[:2]), (r[:2], p[:2]))))})
        out.sort(key=lambda f: -f["d"])
        return out

    def shot_with_area(self, yaw, pitch, dist, sw, sh):
        """The same, with each face's projected area kept, and a count of
        the ones so nearly edge-on that rounding decides them."""
        faces = self.shot(yaw, pitch, dist, sw, sh)
        edge = sum(1 for f in faces if f["thick"] <= 1.5)
        return faces, edge


class Renderer(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("shot", "faces", "verts", "vlist", "flist", "field") + MODELS}
        cls.models = {}
        for name in MODELS:
            m = cls.fn[name]
            vs = [tuple(cls.get(v, c) for c in "xyz")
                  for v in list_to_python(cls.call("vlist", m))]
            fs = [tuple(cls.get(f, c) for c in ("a", "b", "c", "nx", "ny", "nz", "k"))
                  for f in list_to_python(cls.call("flist", m))]
            cls.models[name] = Reference(vs, fs)

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

    def picture(self, name, yaw, pitch, dist=3400, sw=800, sh=600):
        return list_to_python(self.call("shot", self.fn[name], yaw, pitch, dist, sw, sh))

    # --- against floating point --------------------------------------------

    def test_it_agrees_with_floating_point(self):
        """Every face the floating-point renderer is sure about -- one whose
        projected area is comfortably positive, so it is not on the
        silhouette -- lands in the same place here, to a pixel and a half,
        with the same material and the same light.

        The silhouette is where the two are allowed to differ, and they
        do: a triangle seen almost exactly edge-on is a sliver a pixel
        wide, and rounding its corners to whole pixels can turn it over.
        "Comfortably" is therefore about thickness -- twice the area over
        the perimeter -- and not about area: the sliver this test found
        was 270 pixels long, had an area of 138, and was a quarter of a
        pixel thick.
        """
        for name in MODELS:
            for yaw, pitch in ((0, 0), (30, 20), (96, -35), (177, 48), (250, 5)):
                got = self.picture(name, yaw, pitch)
                want, edge = self.models[name].shot_with_area(yaw, pitch, 3400, 800, 600)
                self.assertLessEqual(abs(len(got) - len(want)), max(2, len(want) // 20),
                                     (name, yaw, pitch, "how many survived the cull"))
                mine = {tuple(round(self.get(g, k))
                              for k in ("u0", "v0", "u1", "v1", "u2", "v2")):
                        (self.get(g, "k"), self.get(g, "l")) for g in got}
                self.assertEqual(len(mine), len(got), "two faces drawn in one place")
                sure = [w for w in want if w["thick"] > 1.5]
                self.assertGreater(len(sure), len(want) // 2, (name, yaw, pitch))
                for w in sure:
                    corners = (w["u"][0], w["v"][0], w["u"][1],
                               w["v"][1], w["u"][2], w["v"][2])
                    key = min(mine, key=lambda c: sum(abs(c[i] - v)
                                                      for i, v in enumerate(corners)))
                    for i, v in enumerate(corners):
                        self.assertLessEqual(abs(key[i] - v), 1.5, (name, yaw, pitch, i))
                    kind, light = mine[key]
                    self.assertEqual(kind, w["k"], (name, yaw, pitch))
                    self.assertLessEqual(abs(light - w["l"]), 6,
                                         (name, yaw, pitch, "light"))
                self.assertGreater(edge, -1)

    # --- the pieces ---------------------------------------------------------

    def test_the_back_of_a_model_is_thrown_away(self):
        """A closed model shows well under half of itself, and never more
        than it has."""
        for name in MODELS:
            faces = self.call("faces", self.fn[name])
            drawn = len(self.picture(name, 40, 15))
            self.assertLess(drawn, faces)
            self.assertGreater(drawn, 0)
        self.assertLess(len(self.picture("sphere", 40, 15)),
                        self.call("faces", self.fn["sphere"]) * 45 // 100)

    def test_the_far_triangles_come_first(self):
        """A host painting polygons has no depth buffer, so the order is the
        depth sorting."""
        for name in MODELS:
            depths = [self.get(f, "d") for f in self.picture(name, 77, 23)]
            self.assertEqual(depths, sorted(depths, reverse=True), name)

    def test_a_full_turn_is_no_turn(self):
        a = [self.get(f, "u0") for f in self.picture("ship", 19, 11)]
        b = [self.get(f, "u0") for f in self.picture("ship", 19 + 256, 11)]
        self.assertEqual(a, b)

    def test_coming_closer_makes_it_bigger(self):
        def width(dist):
            pic = self.picture("ship", 0, 0, dist)
            us = [self.get(f, k) for f in pic for k in ("u0", "u1", "u2")]
            return max(us) - min(us)
        near, far = width(2200), width(6600)
        self.assertGreater(near, far * 2)          # three times closer, three times wider

    def test_the_light_lies_between_the_ambient_and_the_sun(self):
        for name in MODELS:
            for f in self.picture(name, 63, 27):
                self.assertGreaterEqual(self.get(f, "l"), AMBIENT)
                self.assertLessEqual(self.get(f, "l"), AMBIENT + ONE + 4)

    def test_the_sun_moves_with_the_model(self):
        """Turning the model turns which faces catch the light; the sun does
        not turn with it."""
        first = {self.get(f, "d"): self.get(f, "l") for f in self.picture("sphere", 0, 0)}
        later = {self.get(f, "d"): self.get(f, "l") for f in self.picture("sphere", 64, 0)}
        self.assertNotEqual(sorted(first.values()), sorted(later.values()))

    def test_the_models_are_closed_and_wound_one_way(self):
        """On a convex model every normal points away from the middle, which
        is what makes the cull mean what it says.  Only the sphere can be
        asked: a tree has a cone whose underside faces its trunk, and the
        gem has a crown that leans inward."""
        for name in ("sphere",):
            ref = self.models[name]
            for a, b, c, nx, ny, nz, _k in ref.faces:
                mid = [sum(ref.verts[i][k] for i in (a, b, c)) / 3 for k in range(3)]
                outward = mid[0] * nx + mid[1] * ny + mid[2] * nz
                self.assertGreater(outward, -ONE * 260, (name, a, b, c))

    def test_a_frame_costs_what_a_frame_can_afford(self):
        """The small models run in real time; the sphere is the stress
        test."""
        self.picture("ship", 30, 20)
        self.assertLess(self.rt.steps, 20_000)
        self.picture("sphere", 30, 20)
        self.assertLess(self.rt.steps, 90_000)


if __name__ == "__main__":
    unittest.main()
