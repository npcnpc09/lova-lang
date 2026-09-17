"""Take the models, the catalogue and the sample city out of
KenneyNL/Starter-Kit-City-Builder.

    python apps/citybuilder/import_kit.py [path/to/Starter-Kit-City-Builder]

Writes `lib/citybuilder_assets.lova`: the fifteen structures the kit
lets you build, as LOVA meshes simplified to a budget each (by vertex
clustering, from `apps/platformer/import_kit.py`: the edge collapse
that served the platformer's rounded slabs folded these buildings'
walls, and a grid that keeps a window and loses its bevel does not),
the catalogue in the kit's own order with the kit's prices, and
the sample city that ships with it -- which is a Godot *binary*
resource, `sample map/map.res`, read here by a sixty-line parser of
that format: the string table, the two scripts it refers to, a hundred
and twenty-two `DataStructure` records each with a `Vector2i` cell,
an orientation and a structure index, and the cash left over.

An orientation in a Godot GridMap is the index of one of the
twenty-four orthogonal bases; the four the kit's cursor can reach by
turning about the vertical are 0, 22, 10 and 16, which are 0, 90, 180
and 270 degrees, and come out here as quarter turns 0 to 3.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _platformer_importer():
    """The platformer's importer, by path: both files are import_kit.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "platformer_import_kit", ROOT / "apps" / "platformer" / "import_kit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pk = _platformer_importer()
Colormap, emit_mesh, load_model, simplify_to, weld = (
    _pk.Colormap, _pk.emit_mesh, _pk.load_model, _pk.simplify_to, _pk.weld)

OUT = ROOT / "lib" / "citybuilder_assets.lova"

# Triangles a model is allowed after decimation.
BUDGET = {
    "road-straight": 12, "road-straight-lightposts": 36, "road-corner": 24,
    "road-split": 28, "road-intersection": 32, "pavement": 6, "pavement-fountain": 40,
    "building-small-a": 110, "building-small-b": 120, "building-small-c": 130,
    "building-small-d": 110, "building-garage": 64, "grass": 6, "grass-trees": 56,
    "grass-trees-tall": 64,
}

# Godot's orthogonal basis indices for turns about the vertical axis.
QUARTER = {0: 0, 22: 1, 10: 2, 16: 3}


# --- the binary resource ---------------------------------------------------------

def read_res(path: Path):
    """A Godot 4 binary Resource: (type, {property: value}) per internal
    resource, in file order, with object references resolved to the
    index of the resource they name."""
    d = path.read_bytes()
    if d[:4] != b"RSRC":
        raise SystemExit(f"{path}: not a Godot binary resource")

    def u32(o):
        return struct.unpack_from("<I", d, o)[0]

    def text(o):
        n = u32(o)
        return d[o + 4:o + 4 + n].rstrip(b"\0").decode(), o + 4 + n

    o = 4 + 20                                  # endianness, 64-bit, version, format
    _type, o = text(o)
    o += 8                                      # import metadata offset
    flags = u32(o)
    o += 4 + 8                                  # flags, uid
    if flags & 8:
        _script_class, o = text(o)
    o += 4 * 11                                 # reserved
    n = u32(o)
    o += 4
    strings = []
    for _ in range(n):
        s, o = text(o)
        strings.append(s)
    n = u32(o)
    o += 4
    for _ in range(n):                          # external resources
        _t, o = text(o)
        _p, o = text(o)
        if flags & 2:
            o += 8
    n = u32(o)
    o += 4
    internal = []
    for _ in range(n):
        p, o = text(o)
        off = struct.unpack_from("<Q", d, o)[0]
        o += 8
        internal.append((p, off))

    def variant(o):
        t = u32(o) & 0xFFFF
        o += 4
        if t == 2:                              # bool
            return bool(u32(o)), o + 4
        if t == 3:                              # int
            return struct.unpack_from("<i", d, o)[0], o + 4
        if t == 40:                             # int64
            return struct.unpack_from("<q", d, o)[0], o + 8
        if t == 45:                             # Vector2i
            return struct.unpack_from("<ii", d, o), o + 8
        if t == 24:                             # object
            kind = u32(o)
            o += 4
            if kind == 0:
                return None, o
            if kind == 1:                       # external, by path
                _t, o = text(o)
                _p, o = text(o)
                return ("ext", _p), o
            return ("res", u32(o)), o + 4       # 2 internal index, 3 external index
        if t == 30:                             # array
            n = u32(o)
            o += 4
            out = []
            for _ in range(n):
                v, o = variant(o)
                out.append(v)
            return out, o
        raise SystemExit(f"{path}: variant type {t} at {o} is not read")

    out = []
    for _p, off in internal:
        t, o = text(off)
        n = u32(o)
        o += 4
        props = {}
        for _ in range(n):
            name = strings[u32(o)]
            o += 4
            v, o = variant(o)
            props[name] = v
        out.append((t, props))
    return out


def read_sample_map(path: Path):
    """The kit's sample city: (cash, [(x, z, structure, quarter turns)])."""
    resources = read_res(path)
    cash = None
    cells = []
    for _t, props in resources:
        if "cash" in props:
            cash = props["cash"]
            for ref in props["structures"]:
                kind, idx = ref
                if kind != "res":
                    continue
                _st, cell = resources[idx]
                (x, z) = cell.get("position", (0, 0))
                # a property at its default -- structure 0, orientation 0 -- is
                # not written to the file at all
                cells.append((x, z, cell.get("structure", 0), QUARTER[cell.get("orientation", 0)]))
    return cash, cells


# --- the catalogue -----------------------------------------------------------

def read_catalogue(kit: Path):
    """The structures in the order the kit's Builder holds them, with
    their model names and prices."""
    text = (kit / "scenes" / "main.tscn").read_text(encoding="utf-8")
    import re
    ext = {}
    for m in re.finditer(r'\[ext_resource [^\]]*path="res://([^"]+)"[^\]]*id="([^"]+)"\]', text):
        ext[m.group(2)] = m.group(1)
    order = re.search(r"structures = Array\[[^\]]*\]\(\[(.*?)\]\)", text).group(1)
    out = []
    for ident in re.findall(r'ExtResource\("([^"]+)"\)', order):
        tres = kit / ext[ident]
        body = tres.read_text(encoding="utf-8")
        model = re.search(r'path="res://models/([^"]+)\.glb"', body).group(1)
        price = int(re.search(r"price = (\d+)", body).group(1))
        out.append((model, price))
    return out


HEADER = """\
;;; citybuilder_assets.lova  --  the structures and the sample city of Kenney's city builder kit
;;;
;;; Generated by `python apps/citybuilder/import_kit.py`; do not edit by
;;; hand.  The data is KenneyNL/Starter-Kit-City-Builder's (MIT; the
;;; models CC0): its .glb models read, coloured from its colormap and
;;; decimated to a budget each; its catalogue of structures in its own
;;; order with its prices; and the sample city its `sample map/map.res`
;;; holds, read out of Godot's binary resource format.  A vertex is in
;;; 1024ths of a metre and a face carries its unit normal and a 24-bit
;;; colour; a cell is a whole metre, and a turn is in quarters.
;;;
;;; MIT License, Copyright (c) 2025 Kenney -- the text travels in
;;; apps/citybuilder/README.md.

(use "mesh3d")
"""


def main() -> int:
    default = Path(os.environ.get("TMP", "/tmp")) / "Starter-Kit-City-Builder"
    kit = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not (kit / "scenes" / "main.tscn").exists():
        raise SystemExit(f"{kit}: no scenes/main.tscn -- "
                         "clone KenneyNL/Starter-Kit-City-Builder there")
    colormap = Colormap(next((kit / "models").rglob("colormap.png")))
    catalogue = read_catalogue(kit)
    cash, cells = read_sample_map(kit / "sample map" / "map.res")

    out = [HEADER]
    total = 0
    for model, _price in catalogue:
        tris = load_model(kit / "models" / f"{model}.glb")
        verts, faces = weld(tris, colormap)
        before = len(faces)
        verts, faces = simplify_to(verts, faces, BUDGET[model])
        total += len(faces)
        out.append(emit_mesh(model, verts, faces))
        print(f"  {model:26s} {before:4d} -> {len(faces):3d} triangles, {len(verts):3d} vertices")

    out.append(";; The catalogue, in the order the kit's Builder cycles through it:")
    out.append(";; a structure is its index here.  A model by index, and a price.")
    out.append("(def catalogue []")
    out.append("  (list")
    for model, price in catalogue:
        out.append(f'    (rec name "{model}" price {price})')
    out[-1] += "))"
    out.append("")
    out.append("(def model-of [index]")
    out.append("  (cond")
    for i, (model, _price) in enumerate(catalogue):
        out.append(f"    (eq index {i}) {model}")
    out.append(f"    {catalogue[0][0]}))")
    out.append("")
    out.append(";; The sample city: cell, structure, quarter turns; and what was")
    out.append(";; left in the till when it was saved.")
    out.append(f"(def sample-cash [] {cash})")
    out.append("(def sample-city []")
    out.append("  (list")
    for x, z, s, q in cells:
        out.append(f"    (rec x {x:4d} z {z:4d} s {s:2d} q {q})")
    out[-1] += "))"
    out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(catalogue)} structures, {total} triangles, "
          f"a sample city of {len(cells)} cells with {cash} in the till")
    return 0


if __name__ == "__main__":
    sys.exit(main())
