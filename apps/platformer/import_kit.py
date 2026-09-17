"""Take the models and the level out of KenneyNL/Starter-Kit-3D-Platformer.

    python apps/platformer/import_kit.py [path/to/Starter-Kit-3D-Platformer]

Writes `lib/platformer_assets.lova`: every model the level uses as a
LOVA mesh in the format of `lib/models.lova`, and the level itself --
which object stands where, turned how much -- read out of the kit's
`scenes/main.tscn`.  Everything here is the original's data, under the
MIT licence in the header of the file written; the code that reads it
is ours and needs nothing outside the standard library.

What it does to a model on the way in:

- reads the glTF binary: the vertices, the triangles, the texture
  coordinates, and the node tree with its translations, so a model of
  several parts (the character: two legs, a torso, two arms and an
  antenna) is flattened into one mesh in its rest pose -- with the
  pose the kit's `character.tscn` gives those parts, not the file's;
- looks each triangle's colour up in the kit's colormap, because these
  models carry no colour of their own: a texture coordinate points into
  a 512 x 512 palette image, and the face's material becomes the
  24-bit colour it points at;
- **decimates** it.  A Kenney platform is 144 triangles because every
  edge is bevelled; the level has thirty-odd objects and the renderer
  costs about two hundred LOVA steps a triangle, so the models are
  brought down to a budget each by collapsing the edges whose removal
  moves the surface least (Garland and Heckbert's quadric error), with
  a collapse across a colour boundary charged extra so the paint stays
  where it was.  The budgets are in `BUDGET` below and the count before
  and after is printed.

The vertex welding, the quadrics and the collapse are about a hundred
lines; a face's normal is recomputed from its surviving corners, so
every face carries the unit normal `lib/mesh3d.lova` expects.
"""

from __future__ import annotations

import heapq
import json
import math
import os
import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "lib" / "platformer_assets.lova"
ONE = 1024

# Triangles a model is allowed after decimation.
BUDGET = {
    "platform": 32, "platform-medium": 36, "platform-grass-large-round": 48,
    "platform-falling": 32, "brick": 24, "coin": 12, "flag": 24, "cloud": 24,
    "grass": 8, "grass-small": 6, "character": 96,
}

# --- glTF binary --------------------------------------------------------------

FMT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path):
    data = path.read_bytes()
    magic, _version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise SystemExit(f"{path}: not a .glb")
    js = None
    bin_ = b""
    off = 12
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            bin_ = chunk
    return js, bin_


def accessor(js, bin_, idx):
    acc = js["accessors"][idx]
    bv = js["bufferViews"][acc["bufferView"]]
    n = NCOMP[acc["type"]]
    f = FMT[acc["componentType"]]
    size = struct.calcsize(f) * n
    stride = bv.get("byteStride", size)
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return [struct.unpack_from("<" + f * n, bin_, base + i * stride)
            for i in range(acc["count"])]


def quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def node_matrix(node):
    """A node's local transform as (3x3 rows, translation)."""
    t = node.get("translation", [0, 0, 0])
    r = quat_matrix(node.get("rotation", [0, 0, 0, 1]))
    s = node.get("scale", [1, 1, 1])
    m = [[r[i][j] * s[j] for j in range(3)] for i in range(3)]
    return m, list(t)


def compose(a, b):
    """a after b: (Ma, ta) . (Mb, tb)."""
    ma, ta = a
    mb, tb = b
    m = [[sum(ma[i][k] * mb[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = [sum(ma[i][k] * tb[k] for k in range(3)) + ta[i] for i in range(3)]
    return m, t


def apply(xf, p):
    m, t = xf
    return tuple(sum(m[i][k] * p[k] for k in range(3)) + t[i] for i in range(3))


IDENTITY = ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0])


def parse_transform3d(text):
    """Godot's `Transform3D(xx, xy, xz, yx, yy, yz, zx, zy, zz, ox, oy, oz)`.

    The twelve numbers are the basis's three *rows* and then the origin;
    the image of the x axis is the first column, (xx, yx, zx).
    """
    inner = text[text.index("(") + 1:text.rindex(")")]
    v = [float(x) for x in inner.split(",")]
    if len(v) != 12:
        raise ValueError(text)
    m = [[v[0], v[1], v[2]], [v[3], v[4], v[5]], [v[6], v[7], v[8]]]
    return m, v[9:12]


def load_model(path: Path, overrides=None):
    """Every triangle of a .glb in one list: (p0, p1, p2, uv0, uv1, uv2).

    `overrides` maps a node name to a (matrix, translation) that
    replaces the node's own transform -- the pose a .tscn gives it.
    """
    js, bin_ = read_glb(path)
    nodes = js.get("nodes", [])
    tris = []

    def visit(idx, parent_xf):
        node = nodes[idx]
        local = node_matrix(node)
        if overrides and node.get("name") in overrides:
            local = overrides[node["name"]]
        xf = compose(parent_xf, local)
        if "mesh" in node:
            for prim in js["meshes"][node["mesh"]]["primitives"]:
                attrs = prim["attributes"]
                pos = accessor(js, bin_, attrs["POSITION"])
                uv = accessor(js, bin_, attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else None
                if "indices" in prim:
                    idxs = [i[0] for i in accessor(js, bin_, prim["indices"])]
                else:
                    idxs = list(range(len(pos)))
                for k in range(0, len(idxs) - 2, 3):
                    a, b, c = idxs[k], idxs[k + 1], idxs[k + 2]
                    tris.append((apply(xf, pos[a]), apply(xf, pos[b]), apply(xf, pos[c]),
                                 uv[a] if uv else (0, 0), uv[b] if uv else (0, 0),
                                 uv[c] if uv else (0, 0)))
        for child in node.get("children", []):
            visit(child, xf)

    scene = js.get("scenes", [{}])[js.get("scene", 0)]
    for root in scene.get("nodes", []):
        visit(root, IDENTITY)
    return tris


# --- the colormap -----------------------------------------------------------------

def read_png(path: Path):
    """An 8-bit RGB or RGBA, non-interlaced PNG as (w, h, rows of (r, g, b))."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path}: not a PNG")
    off = 8
    w = h = 0
    channels = 0
    idat = b""
    while off < len(data):
        (clen,) = struct.unpack_from(">I", data, off)
        ctype = data[off + 4:off + 8]
        body = data[off + 8:off + 8 + clen]
        off += 12 + clen
        if ctype == b"IHDR":
            w, h, depth, colour, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or interlace != 0 or colour not in (2, 6):
                raise SystemExit(f"{path}: only 8-bit RGB/RGBA non-interlaced PNG is read")
            channels = 3 if colour == 2 else 4
        elif ctype == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride = w * channels
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _y in range(h):
        filt = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        bpp = channels
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if filt == 1:
                line[i] = (line[i] + a) & 255
            elif filt == 2:
                line[i] = (line[i] + b) & 255
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        rows.append([tuple(line[i * channels:i * channels + 3]) for i in range(w)])
        prev = line
    return w, h, rows


class Colormap:
    def __init__(self, path: Path):
        self.w, self.h, self.rows = read_png(path)

    def at(self, uv):
        u, v = uv
        x = min(self.w - 1, max(0, int(u * self.w)))
        y = min(self.h - 1, max(0, int(v * self.h)))
        r, g, b = self.rows[y][x]
        return (r << 16) | (g << 8) | b


# --- decimation -----------------------------------------------------------------

def weld(tris, colormap):
    """Triangles to (vertices, faces with a colour), duplicates merged."""
    verts = []
    index = {}
    faces = []
    for p0, p1, p2, uv0, uv1, uv2 in tris:
        ids = []
        for p in (p0, p1, p2):
            key = tuple(round(c, 4) for c in p)
            if key not in index:
                index[key] = len(verts)
                verts.append(list(p))
            ids.append(index[key])
        if len(set(ids)) < 3:
            continue
        centre = ((uv0[0] + uv1[0] + uv2[0]) / 3, (uv0[1] + uv1[1] + uv2[1]) / 3)
        faces.append([ids[0], ids[1], ids[2], colormap.at(centre)])
    return verts, faces


def plane(verts, f):
    a, b, c = (verts[i] for i in f[:3])
    u = [b[k] - a[k] for k in range(3)]
    w = [c[k] - a[k] for k in range(3)]
    n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
    length = math.sqrt(sum(x * x for x in n))
    if length < 1e-12:
        return None
    n = [x / length for x in n]
    return n, -sum(n[k] * a[k] for k in range(3))


def quadric(n, d):
    v = n + [d]
    return [[v[i] * v[j] for j in range(4)] for i in range(4)]


def qadd(a, b):
    return [[a[i][j] + b[i][j] for j in range(4)] for i in range(4)]


def qcost(q, p):
    v = list(p) + [1.0]
    return sum(v[i] * q[i][j] * v[j] for i in range(4) for j in range(4))


def regions_of(faces, reach=48):
    """Each face colour's region: shades within `reach` of each other in
    RGB, chained, are one region -- the six shades of a Kenney orange are
    one paint job, and the grey top of a platform another."""
    colours = sorted({f[3] for f in faces})
    parent = {c: c for c in colours}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    def rgb(c):
        return (c >> 16 & 255, c >> 8 & 255, c & 255)

    for i, a in enumerate(colours):
        for b in colours[i + 1:]:
            if math.dist(rgb(a), rgb(b)) <= reach:
                parent[find(a)] = find(b)
    return {c: find(c) for c in colours}


def decimate(verts, faces, target):
    """Collapse edges, cheapest first, until `target` faces remain.

    A vertex belongs to the regions of the faces around it.  An edge
    whose ends belong to the same regions collapses freely; one whose
    end belongs to a subset of the other's collapses into the larger
    end, which keeps every boundary between two paints where it was;
    any other edge is left alone.  A face that would turn by more than
    about fifty degrees blocks the collapse.
    """
    verts = [list(v) for v in verts]
    faces = [list(f) for f in faces]
    region = regions_of(faces)
    alive = [True] * len(faces)
    q = [[[0.0] * 4 for _ in range(4)] for _ in verts]
    vfaces = [set() for _ in verts]
    for i, f in enumerate(faces):
        pl = plane(verts, f)
        if pl is None:
            alive[i] = False
            continue
        for v in f[:3]:
            q[v] = qadd(q[v], quadric(*pl))
            vfaces[v].add(i)

    def colours(v):
        return {region[faces[i][3]] for i in vfaces[v] if alive[i]}

    def edge_cost(a, b):
        """(cost, position) or None if the edge may not collapse."""
        qq = qadd(q[a], q[b])
        ca, cb = colours(a), colours(b)
        if ca == cb:
            mid = [(verts[a][k] + verts[b][k]) / 2 for k in range(3)]
            cost, _, p = min((qcost(qq, p), n, p)
                             for n, p in ((0, verts[a]), (1, verts[b]), (2, mid)))
            if len(ca) > 1:
                # both ends are on the same paint boundary: the quadric
                # is blind to a boundary moving across a flat face, so
                # the edge's own length is the price, shortest first
                cost += 4 * math.dist(verts[a], verts[b]) ** 2
            return cost, p
        if cb < ca:
            return qcost(qq, verts[a]) + 1e-6, verts[a]
        if ca < cb:
            return qcost(qq, verts[b]) + 1e-6, verts[b]
        return None

    def edges_of(v):
        out = set()
        for i in vfaces[v]:
            if alive[i]:
                for u in faces[i][:3]:
                    if u != v:
                        out.add((min(u, v), max(u, v)))
        return out

    heap = []
    version = [0] * len(verts)
    seen = set()

    def offer(e):
        found = edge_cost(*e)
        if found is not None:
            cost, p = found
            heapq.heappush(heap, (cost, e, version[e[0]], version[e[1]], p))

    for v in range(len(verts)):
        for e in edges_of(v):
            if e not in seen:
                seen.add(e)
                offer(e)

    count = sum(alive)
    remaining = {}
    for i, f in enumerate(faces):
        if alive[i]:
            remaining[region[f[3]]] = remaining.get(region[f[3]], 0) + 1
    while count > target and heap:
        cost, (a, b), va, vb, p = heapq.heappop(heap)
        if version[a] != va or version[b] != vb:
            continue
        shared = {i for i in vfaces[a] & vfaces[b] if alive[i]}
        # a paint must keep at least three faces: the green top of a
        # round platform is fourteen and must not go to nothing
        lost = {}
        for i in shared:
            lost[region[faces[i][3]]] = lost.get(region[faces[i][3]], 0) + 1
        if any(remaining[r] - n < 3 for r, n in lost.items()):
            continue
        # would any face around a or b turn over?
        flips = False
        for i in (vfaces[a] | vfaces[b]) - shared:
            if not alive[i]:
                continue
            before = plane(verts, faces[i])
            saved = {v: verts[v] for v in (a, b)}
            verts[a] = list(p)
            verts[b] = list(p)
            after = plane(verts, faces[i])
            verts[a], verts[b] = saved[a], saved[b]
            if (before is None or after is None
                    or sum(before[0][k] * after[0][k] for k in range(3)) < 0.6):
                flips = True
                break
        if flips:
            continue
        # collapse b into a at p
        verts[a] = list(p)
        for i in shared:
            alive[i] = False
            count -= 1
            remaining[region[faces[i][3]]] -= 1
        for i in vfaces[b]:
            if alive[i]:
                faces[i] = [a if v == b else v for v in faces[i][:3]] + [faces[i][3]]
                vfaces[a].add(i)
        vfaces[b] = set()
        q[a] = qadd(q[a], q[b])
        version[a] += 1
        version[b] += 1
        for e in edges_of(a):
            offer(e)
    keep = [f for f, ok in zip(faces, alive) if ok]
    used = sorted({v for f in keep for v in f[:3]})
    renum = {v: i for i, v in enumerate(used)}
    return ([verts[v] for v in used],
            [[renum[f[0]], renum[f[1]], renum[f[2]], f[3]] for f in keep])


def cluster(verts, faces, size):
    """Simplify by snapping every vertex to a grid of `size` and merging
    what lands together: Rossignac and Borrel's vertex clustering.  It
    never folds a surface the way an edge collapse can -- a face keeps
    its colour, and three corners that fall in three cells stay a face
    -- which is what the kit's buildings needed: their four hundred
    triangles are bevels a few centimetres wide around windows, and a
    quarter-metre grid keeps the windows and loses the bevels."""
    cells = {}
    where = []
    for v in verts:
        key = tuple(round(c / size) for c in v)
        if key not in cells:
            cells[key] = [len(cells), [0.0, 0.0, 0.0], 0]
        entry = cells[key]
        for k in range(3):
            entry[1][k] += v[k]
        entry[2] += 1
        where.append(entry[0])
    new_verts = [None] * len(cells)
    for idx, total, n in cells.values():
        new_verts[idx] = [c / n for c in total]
    seen = set()
    new_faces = []
    for a, b, c, k in faces:
        na, nb, nc = where[a], where[b], where[c]
        if len({na, nb, nc}) < 3:
            continue
        key = (min(na, nb, nc), na + nb + nc, k)
        if (na, nb, nc, k) in seen:
            continue
        seen.add((na, nb, nc, k))
        new_faces.append([na, nb, nc, k])
    return new_verts, new_faces


def simplify_to(verts, faces, target, sizes=(1 / 64, 1 / 48, 1 / 32, 1 / 24, 1 / 16, 1 / 12, 1 / 8, 1 / 6, 1 / 4)):
    """Cluster on the finest grid that brings the model within `target`
    faces; the coarsest grid if none does."""
    best = None
    for size in sizes:
        v, f = cluster(verts, faces, size)
        best = (v, f)
        if len(f) <= target:
            break
    return best


# --- writing --------------------------------------------------------------------

def fix(v):
    return int(round(v * ONE))


def emit_mesh(name, verts, faces):
    ident = name.replace("_", "-")
    lines = [f"(def {ident}-vs []", "  (list"]
    lines += [f"    (rec x {fix(x):6d} y {fix(y):6d} z {fix(z):6d})" for x, y, z in verts]
    lines[-1] += "))"
    lines += ["", f"(def {ident}-fs []", "  (list"]
    for a, b, c, k in faces:
        pl = plane(verts, (a, b, c))
        nx, ny, nz = pl[0] if pl else (0, 1, 0)
        lines.append(f"    (rec a {a:3d} b {b:3d} c {c:3d} "
                     f"nx {fix(nx):5d} ny {fix(ny):5d} nz {fix(nz):5d} k {k})")
    lines[-1] += "))"
    lines += ["", f"(def {ident} [] (mesh {ident}-vs {ident}-fs))", ""]
    return "\n".join(lines)


# --- the level ------------------------------------------------------------------

def yaw_of(m):
    """The turn about the vertical axis a basis carries, in 256ths."""
    # the image of the x axis is the first column
    return round(math.atan2(-m[2][0], m[0][0]) * 256 / (2 * math.pi))


def scale_of(m):
    return math.sqrt(sum(m[i][0] ** 2 for i in range(3)))


def read_scene(path: Path):
    """Every node of a .tscn: (name, type, parent, instanced resource, transform)."""
    text = path.read_text(encoding="utf-8")
    ext = {}
    for m in re.finditer(r'\[ext_resource [^\]]*path="res://([^"]+)"[^\]]*id="([^"]+)"\]', text):
        ext[m.group(2)] = m.group(1)
    nodes = []
    for block in re.split(r"\n(?=\[node )", text):
        head = re.match(r'\[node name="([^"]+)"(?: type="([^"]+)")?(?: parent="([^"]+)")?'
                        r'[^\]]*?(?: instance=ExtResource\("([^"]+)"\))?\]', block)
        if not head:
            continue
        name, ntype, parent, inst = head.groups()
        tm = re.search(r"transform = (Transform3D\([^)]*\))", block)
        xf = parse_transform3d(tm.group(1)) if tm else IDENTITY
        nodes.append((name, ntype, parent, ext.get(inst), xf))
    return nodes


# which .tscn object is which model, and what the rules need to know of it
KINDS = {
    "objects/platform.tscn": ("platform", "platform"),
    "objects/platform_medium.tscn": ("platform", "platform-medium"),
    "objects/platform_grass_large_round.tscn": ("round", "platform-grass-large-round"),
    "objects/platform_falling.tscn": ("falling", "platform-falling"),
    "objects/brick.tscn": ("brick", "brick"),
    "objects/coin.tscn": ("coin", "coin"),
    "objects/cloud.tscn": ("cloud", "cloud"),
    "models/flag.glb": ("flag", "flag"),
}

HEADER = """\
;;; platformer_assets.lova  --  the models and the level of Kenney's 3D platformer kit
;;;
;;; Generated by `python apps/platformer/import_kit.py`; do not edit by
;;; hand.  The data is KenneyNL/Starter-Kit-3D-Platformer's (MIT; the
;;; models CC0): its .glb models read, coloured from its colormap,
;;; decimated to a budget each, and its scenes/main.tscn read for where
;;; everything stands.  A vertex is in 1024ths of a metre, a face
;;; carries its unit normal and a 24-bit colour, and a placed object
;;; carries its position in 1024ths and its turn in 256ths of a circle.
;;;
;;; MIT License, Copyright (c) 2023 Kenney -- the text travels in
;;; apps/platformer/README.md.

(use "mesh3d")
"""


def main() -> int:
    default = Path(os.environ.get("TMP", "/tmp")) / "Starter-Kit-3D-Platformer"
    kit = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not (kit / "scenes" / "main.tscn").exists():
        raise SystemExit(f"{kit}: no scenes/main.tscn -- "
                         "clone KenneyNL/Starter-Kit-3D-Platformer there")
    colormap = Colormap(kit / "models" / "Textures" / "colormap.png")

    # the character's pose is the .tscn's, not the file's
    pose = {}
    for name, _t, _p, _i, xf in read_scene(kit / "objects" / "character.tscn"):
        if name in ("leg-left", "leg-right", "torso", "arm-left", "arm-right", "antenna"):
            pose[name] = xf

    out = [HEADER]
    total = 0
    for name, budget in BUDGET.items():
        tris = load_model(kit / "models" / f"{name}.glb", pose if name == "character" else None)
        verts, faces = weld(tris, colormap)
        before = len(faces)
        verts, faces = decimate(verts, faces, budget)
        total += len(faces)
        out.append(emit_mesh(name, verts, faces))
        print(f"  {name:28s} {before:4d} -> {len(faces):3d} triangles, {len(verts):3d} vertices")

    # the level: instances in the main scene, with the round platforms'
    # grass brought along from their own scene
    items = []
    grass = []
    for name, _t, parent, inst, xf in read_scene(kit / "objects" / "platform_grass_large_round.tscn"):
        if inst and inst.startswith("models/grass"):
            grass.append((Path(inst).stem, xf))
    main_nodes = read_scene(kit / "scenes" / "main.tscn")
    for name, _t, parent, inst, xf in main_nodes:
        if parent != "World" or inst not in KINDS:
            continue
        kind, model = KINDS[inst]
        m, t = xf
        items.append((kind, model, t, yaw_of(m), scale_of(m)))
        if kind == "round":
            for gname, gxf in grass:
                gm, gt = compose(xf, gxf)
                items.append(("grass", gname, gt, yaw_of(gm), 1.0))
    out.append(";; The level: kind, model, position, turn, scale.  `kind` is what the")
    out.append(";; rules see; the model is what the picture draws.")
    out.append("(def level []")
    out.append("  (list")
    for kind, model, (x, y, z), yaw, scale in items:
        out.append(f'    (rec kind "{kind}" model "{model}" x {fix(x):6d} y {fix(y):6d} '
                   f"z {fix(z):6d} yaw {yaw:4d} scale {fix(scale):5d})")
    out[-1] += "))"
    out.append("")
    out.append(";; The player's start, from the Player node of the same scene.")
    for name, _t, parent, inst, xf in main_nodes:
        if name == "Player":
            x, y, z = xf[1]
            out.append(f"(def start [] (rec x {fix(x)} y {fix(y)} z {fix(z)}))")
    out.append("")
    out.append(";; A model by name, for the picture.")
    out.append("(def model-of [name]")
    out.append("  (cond")
    for name in BUDGET:
        out.append(f'    (eq name "{name}") {name}')
    out.append("    platform))")
    out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(items)} placed objects, "
          f"{total} triangles across {len(BUDGET)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
