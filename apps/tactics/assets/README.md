# Where this art comes from

These seven PNGs are **not ours**. They are the character sprites of
[ramaureirac/godot-tactical-rpg](https://github.com/ramaureirac/godot-tactical-rpg),
taken from its `assets/textures/actor/` on the `development` branch, and
they are here under that project's MIT licence, whose text is beside
them in `LICENSE-godot-tactical-rpg.txt`:

> Copyright (c) 2019 Rodrigo Maureira Contreras

| file | used for |
|---|---|
| `chr_pawn_knight.png` | your soldier (movement 3, reach 1, power 2) |
| `chr_pawn_chemist.png` | your scout (movement 5, climbs two tiles) |
| `chr_pawn_archer.png` | your archer (reach 3, power 1) |
| `chr_pawn_skeleton.png` | their soldier |
| `chr_pawn_skeleton_cpt.png` | their scout |
| `chr_pawn_skeleton_mage.png` | their archer |
| `chr_pawn_mage.png` | unused; kept so the set is whole |

Each file is a 128 x 256 sheet of two frames (`vframes = 2` on the
`Sprite3D` in the original's `pawn.tscn`): the upper one faces away and
the lower one faces the camera. `apps/tactics/tactics.py` crops the
lower frame to the rows that are actually drawn in it (y 8 to y 120,
the same for all seven) and halves it, which puts a figure one tile
tall with its feet on the tile's middle. Tk reads PNG and its alpha,
and `copy -from` crops, so nothing outside the standard library is
needed for any of it.

**The arena is from the same project**: `lib/tactics.lova`'s `level`
is its `assets/maps/level/arena/test_arena.tscn`, read out as two
hundred tiles on a ten-by-twenty grid with a height each. That file
holds no model — every "mesh" in it is a one-by-one quad, the top face
of a tile, and the height lives in the node's transform. What was
designed there is the layout, and the layout is what was taken.

The rules in `lib/tactics.lova` are a **reimplementation** written
against that project's GDScript, not a copy of it; what agrees with it,
what deliberately does not, and how the agreement is checked are in the
header of that file and in `tests/test_tactics.py`.

If you would rather ship this without third-party art, delete these
PNGs: `apps/tactics/tactics.py` falls back to figures it draws itself.
