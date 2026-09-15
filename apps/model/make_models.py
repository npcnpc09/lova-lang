"""Write `lib/models.lova`: low-poly meshes as LOVA data.

    python apps/model/make_models.py

A mesh reaches LOVA as two lists of records -- vertices in 1024ths of a
model unit, and triangles carrying the vertex numbers, a material and
the face's own unit normal.  The normal is computed here, once, because
a rotation does not change a length: a unit normal stays one however
the model turns, which is what lets `lib/mesh3d.lova` light a face with
three multiplications and no square root.

Everything below is generated, so nothing here is anybody else's art.
`apps/model/obj_to_lova.py` writes the same format out of a `.obj`, for
a model that came from a modeller.
"""

from __future__ import annotations

import math
from pathlib import Path

ONE = 1024
ROOT = Path(__file__).resolve().parents[2]

# Materials, by number; the host owns the colours.
GRASS, BARK, LEAF, STONE, ROOF, WALL, METAL, GEM, GOLD = range(9)


def fix(v):
    return int(round(v * ONE))


class Mesh:
    def __init__(self):
        self.v = []
        self.f = []

    def vert(self, x, y, z):
        self.v.append((x, y, z))
        return len(self.v) - 1

    def tri(self, a, b, c, mat):
        self.f.append((a, b, c, mat))

    def quad(self, a, b, c, d, mat):
        self.tri(a, b, c, mat)
        self.tri(a, c, d, mat)

    def box(self, x0, y0, z0, x1, y1, z1, mat, top=None):
        """An axis-aligned box, wound so every face looks outward."""
        p = [self.vert(x, y, z) for x, y, z in
             ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
              (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1))]
        self.quad(p[4], p[7], p[6], p[5], mat if top is None else top)   # +y
        self.quad(p[0], p[1], p[2], p[3], mat)                           # -y
        self.quad(p[3], p[2], p[6], p[7], mat)                           # +z
        self.quad(p[1], p[0], p[4], p[5], mat)                           # -z
        self.quad(p[2], p[1], p[5], p[6], mat)                           # +x
        self.quad(p[0], p[3], p[7], p[4], mat)                           # -x

    def cone(self, cx, cz, r, y0, y1, sides, mat):
        top = self.vert(cx, y1, cz)
        ring = [self.vert(cx + r * math.cos(2 * math.pi * i / sides), y0,
                          cz + r * math.sin(2 * math.pi * i / sides))
                for i in range(sides)]
        centre = self.vert(cx, y0, cz)
        for i in range(sides):
            j = (i + 1) % sides
            self.tri(top, ring[i], ring[j], mat)
            self.tri(centre, ring[j], ring[i], mat)

    def prism(self, cx, cz, r, y0, y1, sides, mat):
        low = [self.vert(cx + r * math.cos(2 * math.pi * i / sides), y0,
                         cz + r * math.sin(2 * math.pi * i / sides))
               for i in range(sides)]
        high = [self.vert(cx + r * math.cos(2 * math.pi * i / sides), y1,
                          cz + r * math.sin(2 * math.pi * i / sides))
                for i in range(sides)]
        cap, floor = self.vert(cx, y1, cz), self.vert(cx, y0, cz)
        for i in range(sides):
            j = (i + 1) % sides
            self.quad(low[i], low[j], high[j], high[i], mat)
            self.tri(cap, high[i], high[j], mat)
            self.tri(floor, low[j], low[i], mat)


def icosphere(subdiv, mat):
    """An icosahedron, each face split into four, twice: 80 triangles."""
    t = (1 + 5 ** 0.5) / 2
    base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
            (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
             (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
             (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
             (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    pts = [tuple(c / math.sqrt(x * x + y * y + z * z) for c in (x, y, z))
           for x, y, z in base]
    for _ in range(subdiv):
        out, cache = [], {}

        def middle(i, j):
            key = (min(i, j), max(i, j))
            if key not in cache:
                a, b = pts[i], pts[j]
                m = tuple((a[k] + b[k]) / 2 for k in range(3))
                n = math.sqrt(sum(c * c for c in m))
                pts.append(tuple(c / n for c in m))
                cache[key] = len(pts) - 1
            return cache[key]

        for a, b, c in faces:
            ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
            out += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = out
    m = Mesh()
    for x, y, z in pts:
        m.vert(x * 0.9, y * 0.9, z * 0.9)
    for a, b, c in faces:
        m.tri(a, b, c, mat)
    return m


def tree():
    m = Mesh()
    m.prism(0, 0, 0.13, -1.0, -0.25, 6, BARK)
    for i, (y0, y1, r) in enumerate(((-0.45, 0.15, 0.62),
                                     (-0.05, 0.55, 0.48),
                                     (0.35, 1.0, 0.32))):
        m.cone(0, 0, r, y0, y1, 7, LEAF)
    return m


def house():
    m = Mesh()
    m.box(-0.62, -1.0, -0.48, 0.62, 0.05, 0.48, WALL)
    # the roof: two slopes and two gables
    ra = m.vert(0, 0.72, -0.56)
    rb = m.vert(0, 0.72, 0.56)
    c = [m.vert(x, 0.05, z) for x, z in
         ((-0.74, -0.56), (0.74, -0.56), (0.74, 0.56), (-0.74, 0.56))]
    m.quad(c[0], ra, rb, c[3], ROOF)
    m.quad(c[1], c[2], rb, ra, ROOF)
    m.tri(c[0], c[1], ra, ROOF)
    m.tri(c[2], c[3], rb, ROOF)
    m.box(-0.18, -1.0, 0.44, 0.18, -0.35, 0.52, BARK)          # the door
    m.box(0.24, -0.62, 0.44, 0.48, -0.36, 0.52, GEM)           # a window
    return m


def gem():
    m = Mesh()
    top, bottom = m.vert(0, 1.0, 0), m.vert(0, -1.0, 0)
    sides = 8
    ring = [m.vert(0.62 * math.cos(2 * math.pi * i / sides), 0.12,
                   0.62 * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    low = [m.vert(0.44 * math.cos(2 * math.pi * (i + 0.5) / sides), -0.34,
                  0.44 * math.sin(2 * math.pi * (i + 0.5) / sides)) for i in range(sides)]
    for i in range(sides):
        j = (i + 1) % sides
        m.tri(top, ring[i], ring[j], GEM)
        m.tri(ring[i], low[i], ring[j], GEM)
        m.tri(ring[j], low[i], low[j], GEM)
        m.tri(bottom, low[j], low[i], GEM)
    return m


def ship():
    m = Mesh()
    m.box(-0.22, -0.16, -0.95, 0.22, 0.16, 0.5, METAL)          # hull
    nose = m.vert(0, 0, -1.35)
    ring = [m.vert(x, y, -0.95) for x, y in
            ((-0.22, -0.16), (0.22, -0.16), (0.22, 0.16), (-0.22, 0.16))]
    m.tri(nose, ring[1], ring[0], METAL)
    m.tri(nose, ring[2], ring[1], METAL)
    m.tri(nose, ring[3], ring[2], METAL)
    m.tri(nose, ring[0], ring[3], METAL)
    for side in (-1, 1):
        tip = m.vert(side * 1.05, -0.02, 0.42)
        a = m.vert(side * 0.22, 0.02, -0.5)
        b = m.vert(side * 0.22, 0.02, 0.36)
        c = m.vert(side * 0.22, -0.06, -0.5)
        d = m.vert(side * 0.22, -0.06, 0.36)
        if side > 0:
            m.tri(a, b, tip, METAL); m.tri(d, c, tip, METAL)
            m.tri(b, d, tip, METAL); m.tri(c, a, tip, METAL)
        else:
            m.tri(b, a, tip, METAL); m.tri(c, d, tip, METAL)
            m.tri(d, b, tip, METAL); m.tri(a, c, tip, METAL)
    m.box(-0.14, 0.16, -0.3, 0.14, 0.34, 0.12, GEM)             # the canopy
    m.box(-0.16, -0.12, 0.5, 0.16, 0.12, 0.62, GOLD)            # the engine
    return m


def normal(m, face):
    a, b, c = (m.v[i] for i in face[:3])
    u = tuple(b[k] - a[k] for k in range(3))
    w = tuple(c[k] - a[k] for k in range(3))
    n = (u[1] * w[2] - u[2] * w[1],
         u[2] * w[0] - u[0] * w[2],
         u[0] * w[1] - u[1] * w[0])
    length = math.sqrt(sum(c * c for c in n)) or 1.0
    return tuple(c / length for c in n)


def emit(name, m):
    lines = [f"(def {name}-vs []", "  (list"]
    lines += [f"    (rec x {fix(x):5d} y {fix(y):5d} z {fix(z):5d})" for x, y, z in m.v]
    lines[-1] += "))"
    lines += ["", f"(def {name}-fs []", "  (list"]
    for a, b, c, mat in m.f:
        nx, ny, nz = normal(m, (a, b, c))
        lines.append(f"    (rec a {a:3d} b {b:3d} c {c:3d} "
                     f"nx {fix(nx):5d} ny {fix(ny):5d} nz {fix(nz):5d} k {mat})")
    lines[-1] += "))"
    lines += ["", f"(def {name} [] (mesh {name}-vs {name}-fs))", ""]
    return "\n".join(lines)


def main() -> int:
    models = [("sphere", icosphere(2, STONE)), ("tree", tree()),
              ("house", house()), ("gem", gem()), ("ship", ship())]
    out = ['''\
;;; models.lova  --  low-poly meshes, as data
;;;
;;; Generated by `python apps/model/make_models.py`; do not edit by
;;; hand.  Every vertex is in 1024ths of a model unit and every face
;;; carries its own unit normal, computed when this file was written --
;;; a rotation does not change a length, so the renderer never needs a
;;; square root.  `k` is the material, and the host owns the colours.
;;;
;;; Nothing here is anybody else\'s art: the five are built out of boxes,
;;; cones, prisms and a twice-subdivided icosahedron.
;;; `apps/model/obj_to_lova.py` writes this same format out of a `.obj`.

(use "mesh3d")
''']
    for name, m in models:
        out.append(emit(name, m))
        print(f"  {name:8s} {len(m.v):4d} vertices  {len(m.f):4d} triangles")
    (ROOT / "lib" / "models.lova").write_text("\n".join(out), encoding="utf-8")
    print("wrote lib/models.lova")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
