"""Take the models and the level out of KenneyNL/Starter-Kit-FPS.

    python apps/fps/import_kit.py [path/to/Starter-Kit-FPS]

Writes `lib/fps_assets.lova`: every model the level uses as a LOVA mesh
in the format of `lib/mesh3d.lova`, and the level itself -- which
object stands where, turned how much -- read out of the kit's
`scenes/main.tscn`.  Everything here is the original's data, under the
MIT licence in the header of the file written; the code that reads it
is the platformer importer's, imported rather than copied.

`apps/platformer/import_kit.py` does the reading: the glTF binary (the
vertices, the triangles, the texture coordinates and the node tree),
the colormap lookup that gives a face its 24-bit colour, the weld, and
the two simplifiers -- `decimate` (quadric edge collapse) and
`simplify_to` (vertex clustering).  This file says which model gets
which and at what budget, and writes the tables the rules read; every
model of this kit takes the edge collapse, for the reason measured
beside `BUDGET`.

What this kit needs that the platformer's did not:

- the **cloud**'s mesh node is pushed half a metre down by
  `objects/cloud.tscn`, so the model is centred on its origin and not
  standing on it; that pose is applied on the way in, as the
  platformer applied its character's;
- the **grass** that each big platform carries in
  `objects/platform_large_grass.tscn` is brought along with it, as the
  platformer brought its round platform's;
- the **decoration clouds** are placed by a full 3x3 basis -- an
  arbitrary rotation with a non-uniform scale.  `lib/scene3d.lova`
  draws a yaw and one scale, so each is reduced to the yaw its x axis
  carries and the cube root of the basis's determinant, which is the
  scale that keeps the volume;
- the level's own transforms are **pure yaw rotations** and are checked
  to be so before the yaw is taken (`assert_yaw`);
- the **collision boxes are not written here**.  The rules collide
  against the kit's own collision shapes, which `lib/fps.lova` carries,
  and those are not the models' extents: a Kenney platform is bevelled
  wider than the shape Godot collides with, and `wall-low`'s shape is
  not centred on its node.  A table of model extents beside the rules'
  own numbers would be a second answer to a question that has one.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "lib" / "fps_assets.lova"
ONE = 1024                      # the picture's unit: 1024ths of a metre
F = 65536                       # the rules' unit: 65 536ths of a metre


def _platformer_importer():
    """The platformer's importer, by path: both files are import_kit.py."""
    spec = importlib.util.spec_from_file_location(
        "platformer_import_kit", ROOT / "apps" / "platformer" / "import_kit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pk = _platformer_importer()
Colormap, compose, decimate = _pk.Colormap, _pk.compose, _pk.decimate
emit_mesh, fix, load_model = _pk.emit_mesh, _pk.fix, _pk.load_model
read_scene, simplify_to, weld, yaw_of = (
    _pk.read_scene, _pk.simplify_to, _pk.weld, _pk.yaw_of)

# Each model: how it is simplified, and the triangles it is allowed
# afterwards.  The two blasters are drawn small in front of the camera
# and the enemy is never close for long, so both are decimated hard.
#
# The slabs and the walls are decimated too, which the city builder's
# buildings were not: clustering was tried on them first and there is
# no grid that lands in the budget.  Measured, triangles after a
# cluster at each grid (the model is 180-208 triangles):
#
#       grid          1/4  1/3  1/2  1/1.5  1/1
#       platform      132   92   84     98     4
#       wall-low       58   40   48     50     8
#
# -- a Kenney slab is 2.2 metres of flat face with a 5 cm bevel around
# it, so every grid fine enough to keep the two faces apart keeps the
# bevel as well, and the first one that does not merges the whole slab
# into four triangles.  The edge collapse has no such step: it eats the
# bevel first, because that is where the quadric error is smallest, and
# the paint boundaries hold the top's colour in place.
BUDGET = {
    "platform": ("decimate", 48),
    "platform-large-grass": ("decimate", 48),
    "wall-low": ("decimate", 40),
    "wall-high": ("decimate", 40),
    "cloud": ("decimate", 24),
    "grass": ("decimate", 8),
    "grass-small": ("decimate", 6),
    "enemy-flying": ("decimate", 64),
    "blaster": ("decimate", 48),
    "blaster-repeater": ("decimate", 48),
}

# Which .tscn object is which model, and the kind id the rules carry.
# A kind is a number because a text is compared a codepoint at a time
# and a tick asks every solid what it is.
KINDS = {
    "objects/platform.tscn": (1, "platform"),
    "objects/wall_low.tscn": (2, "wall-low"),
    "objects/wall_high.tscn": (3, "wall-high"),
    "objects/platform_large_grass.tscn": (4, "platform-large-grass"),
}
GRASS_KIND = 0                  # the grass tufts a big platform carries: no solid

HEADER = """\
;;; fps_assets.lova  --  the models and the level of Kenney's FPS starter kit
;;;
;;; Generated by `python apps/fps/import_kit.py`; do not edit by hand.
;;; The data is KenneyNL/Starter-Kit-FPS's (MIT; the models CC0): its
;;; .glb models read, coloured from its colormap, simplified to a
;;; budget each, and its scenes/main.tscn read for where everything
;;; stands.  A vertex is in 1024ths of a metre, a face carries its unit
;;; normal and a 24-bit colour, and a placed object carries its
;;; position in 1024ths and its turn in 256ths of a circle.
;;;
;;; What the rules collide against is not here: those boxes are the
;;; kit's own collision shapes and `lib/fps.lova` carries them, because
;;; they are not the models' extents -- a Kenney platform is bevelled
;;; wider than the shape Godot collides with.
;;;
;;; MIT License, Copyright (c) 2025 Kenney -- the text travels in
;;; apps/fps/README.md.

(use "mesh3d")
"""


def assert_yaw(m, who):
    """A basis that is a turn about the vertical axis and nothing else."""
    for i, j, want in ((0, 1, 0), (1, 0, 0), (1, 2, 0), (2, 1, 0), (1, 1, 1)):
        if abs(m[i][j] - want) > 1e-4:
            raise SystemExit(f"{who}: not a yaw rotation -- m[{i}][{j}] = {m[i][j]}")
    if abs(m[0][0] ** 2 + m[2][0] ** 2 - 1) > 1e-4:
        raise SystemExit(f"{who}: the x axis is scaled")


def det(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def cond_table(name, arg, pairs, default):
    """`(def name [arg] (cond (eq arg k) v ... default))`."""
    lines = [f"(def {name} [{arg}]", "  (cond"]
    for key, value in pairs:
        lines.append(f"    (eq {arg} {key}) {value}")
    lines.append(f"    {default}))")
    return "\n".join(lines) + "\n"


def main() -> int:
    kit = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\SSH\Starter-Kit-FPS")
    if not (kit / "scenes" / "main.tscn").exists():
        raise SystemExit(f"{kit}: no scenes/main.tscn -- "
                         "clone KenneyNL/Starter-Kit-FPS there")
    colormap = Colormap(kit / "models" / "Textures" / "colormap.png")

    # the cloud's mesh is pushed down half a metre by its own scene, so
    # that the model is centred on the origin the level places
    pose = {}
    for name, _t, _p, _i, xf in read_scene(kit / "objects" / "cloud.tscn"):
        if name == "cube":
            pose[name] = xf

    out = [HEADER]
    total = 0
    for name, (how, budget) in BUDGET.items():
        tris = load_model(kit / "models" / f"{name}.glb",
                          pose if name == "cloud" else None)
        verts, faces = weld(tris, colormap)
        before = len(faces)
        if how == "cluster":
            verts, faces = simplify_to(verts, faces, budget)
        else:
            verts, faces = decimate(verts, faces, budget)
        total += len(faces)
        out.append(emit_mesh(name, verts, faces))
        print(f"  {name:22s} {before:4d} -> {len(faces):3d} triangles, "
              f"{len(verts):3d} vertices ({how})")

    # the grass each big platform carries, in the platform's own frame
    grass = []
    for name, _t, _p, inst, xf in read_scene(
            kit / "objects" / "platform_large_grass.tscn"):
        if inst and inst.startswith("models/grass"):
            grass.append((Path(inst).stem, xf))

    nodes = read_scene(kit / "scenes" / "main.tscn")

    # --- the level: the Level node's instances, with their grass ------
    items = []
    for name, _t, parent, inst, xf in nodes:
        if parent != "Level" or inst not in KINDS:
            continue
        kind, model = KINDS[inst]
        m, t = xf
        assert_yaw(m, name)
        items.append((kind, model, t, yaw_of(m), 1.0))
        if model == "platform-large-grass":
            for gname, gxf in grass:
                gm, gt = compose(xf, gxf)
                items.append((GRASS_KIND, gname, gt, yaw_of(gm), 1.0))
    out.append(";; The level: the kind the rules see, the model the picture")
    out.append(";; draws, where it stands and how far it is turned.  Kind 0 is")
    out.append(";; decoration -- the grass each big platform carries.")
    out.append("(def fps-level []")
    out.append("  (list")
    for kind, model, (x, y, z), yaw, scale in items:
        out.append(f'    (rec kind {kind} model "{model}" x {fix(x):6d} y {fix(y):6d} '
                   f"z {fix(z):6d} yaw {yaw:4d} scale {fix(scale):5d})")
    out[-1] += "))"
    out.append("")

    # --- the enemies --------------------------------------------------
    enemies = []
    for name, _t, parent, _i, xf in nodes:
        if parent != "Enemies":
            continue
        m, t = xf
        assert_yaw(m, name)
        enemies.append((t, yaw_of(m)))
    out.append(";; The four flying enemies of the Enemies node, where they wait")
    out.append(";; and which way they look.")
    out.append("(def fps-enemies []")
    out.append("  (list")
    for (x, y, z), yaw in enemies:
        out.append(f'    (rec model "enemy-flying" x {fix(x):6d} y {fix(y):6d} '
                   f"z {fix(z):6d} yaw {yaw:4d} scale {ONE})")
    out[-1] += "))"
    out.append("")

    # --- the clouds ---------------------------------------------------
    clouds = []
    for name, _t, parent, _i, xf in nodes:
        if parent != "Decoration":
            continue
        m, t = xf
        scale = abs(det(m)) ** (1 / 3)
        clouds.append((t, yaw_of(m), scale))
    out.append(";; The Decoration node's clouds.  Each stands in the kit under a")
    out.append(";; full basis -- an arbitrary rotation with a non-uniform scale;")
    out.append(";; the picture draws a yaw and one scale, so each is the yaw its")
    out.append(";; x axis carries and the cube root of the basis's determinant,")
    out.append(";; which keeps the volume the kit gave it.")
    out.append("(def fps-clouds []")
    out.append("  (list")
    for (x, y, z), yaw, scale in clouds:
        out.append(f'    (rec model "cloud" x {fix(x):6d} y {fix(y):6d} '
                   f"z {fix(z):6d} yaw {yaw:4d} scale {fix(scale):5d})")
    out[-1] += "))"
    out.append("")

    # --- the player's start -------------------------------------------
    start = (0.0, 0.5, 0.0)
    for name, _t, _p, _i, xf in read_scene(kit / "objects" / "player.tscn"):
        if name == "Player":
            start = tuple(xf[1])
    out.append(";; Where the player stands, from the Player node of objects/player.tscn.")
    out.append(f"(def fps-player-start [] (rec x {fix(start[0])} y {fix(start[1])} "
               f"z {fix(start[2])}))")
    out.append("")

    # --- the tables ---------------------------------------------------
    out.append(";; A model by name, for the picture.  `impact` is the one name")
    out.append(";; here the kit has no model for -- its burst is a 2D animated")
    out.append(";; sprite, sprites/burst_animation.tres -- and the cloud's cube")
    out.append(";; stands in for it, small and white, until there is better.")
    out.append(cond_table("fps-model-of", "name",
                          [(f'"{n}"', n) for n in BUDGET] + [('"impact"', "cloud")],
                          "platform").rstrip())
    out.append("")
    out.append(";; The names the rules use: `level` and `model-of`, as the")
    out.append(";; platformer's assets spell them.")
    out.append("(def level [] fps-level)")
    out.append("(def model-of [name] (fps-model-of name))")
    out.append("")
    out.append(";; The model a kind is drawn with.")
    kind_model = sorted({k: m for k, m in KINDS.values()}.items())
    out.append(cond_table("fps-kind-model", "k",
                          [(k, f'"{m}"') for k, m in kind_model], '"grass"').rstrip())
    out.append("")
    # The boxes the rules collide against are NOT written here.  They
    # are the kit's own collision shapes, which `lib/fps.lova` carries,
    # and they are not the models' extents: a Kenney platform is
    # bevelled wider than the shape Godot collides with, and wall-low's
    # shape is not centred on its node.  A table of model extents beside
    # the rules' own numbers would be a second answer to a question that
    # has one.

    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(items)} placed objects, "
          f"{len(enemies)} enemies, {len(clouds)} clouds, "
          f"{total} triangles across {len(BUDGET)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
