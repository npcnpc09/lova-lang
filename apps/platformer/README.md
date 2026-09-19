# platformer -- Kenney's 3D platformer starter kit, in LOVA

    python apps/platformer/platformer.py
    python apps/platformer/platformer.py --shot apps/platformer/screenshot.png

![the level, drawn by lib/scene3d.lova](screenshot.png)

A port of [KenneyNL/Starter-Kit-3D-Platformer](https://github.com/KenneyNL/Starter-Kit-3D-Platformer)
(MIT, about 1 200 stars): a character that walks, jumps twice and
squashes when it lands; coins that bob and spin; platforms that give
way when stood on; bricks broken from below; a camera that follows,
turns and zooms; and a fall off the world that starts everything
again.

| What | Where | Whose |
|---|---|---|
| The rules -- player, coins, falling platforms, bricks, camera, reset | `lib/platformer.lova` | ours, written against the kit's GDScript |
| The picture -- objects placed, turned, tilted, culled, lit, ordered | `lib/scene3d.lova` over `lib/mesh3d.lova` | ours |
| The models and the level | `lib/platformer_assets.lova` (generated) | the kit's, read by `import_kit.py` |
| The window, the keys, the clock, the screenshot rasteriser | `platformer.py` | ours |
| The check: a transliteration of the kit's scripts, run against the port | `tests/test_platformer.py` | ours |

**What came across unchanged**: speed 250, jump 7, gravity 25 a
second, the lerps of a tenth and a sixth, the capsule's 0.3 by 1.0,
the coin's 0.5, the falling platform's 15 a second, the camera's 120
degrees a second between -80 and -10 and its zoom between 4 and 16 at
10 a second, the bottom of the world at -10, and every position, turn
and scale in `scenes/main.tscn`.

**What is ours instead of Godot's**: the collision.  The kit gives
each platform a concave collision mesh and the player a capsule and
lets Jolt sort it out; the port makes each solid the box (or, for the
round platforms, the cylinder) of its model and the player a vertical
segment with a radius, and resolves walls, floors and ceilings in that
order.  The transliteration in the test uses the same model, so the
test checks the port against the kit's *rules*, not against Jolt.

**What LOVA has to do without**: floating point.  The rules run in
65 536ths of a metre and 16 384ths of a turn; the picture in 1024ths
and 256ths.  Sines are a table of 256ths of a turn, so a direction is
known to 1.4 degrees, and the transliteration quantises its angles the
same way before comparing.

**Speed, honestly.** A tick of the rules is about 4 000 LOVA steps; a
frame is 100 000 to 160 000, most of it the renderer's two hundred
steps a triangle.  CPython runs about 700 000 steps a second, so the
window manages three to four frames a second while keeping the rules
at sixty ticks of wall time; PyPy runs the same code about six times
faster.  The step counter in the bar is the honest number.  On the
native runtime a tick is 2.2 ms and a frame 11.3 ms, and the window
keeps up.

**Two windows.**  `platformer.py` opens an SDL window (pygame) when
pygame is installed and the Tk one otherwise; `--host tk` asks for the
old one and `--host sdl` insists on the new.  The game is the same
either way -- the same `Rules`, the same keys, the same sixtieth of a
second -- and only the surface differs: the Tk canvas deleted and
re-created every polygon every frame, 21 ms on the median here with
spikes to a quarter of a second, and that was the stutter.  `--bench
N` plays N frames to a script and prints the split; on this machine,
native runtime, 305 faces a frame:

| part | median | p95 |
|---|---|---|
| LOVA tick | 2.2 ms | 4.7 ms |
| LOVA frame | 11.3 ms | 14.7 ms |
| draw | 4.6 ms | 6.2 ms |
| flip | 0.5 ms | 0.6 ms |
| **a frame, end to end** | **18.8 ms (53 fps)** | **25.3 ms** |

(50 to 53 frames a second over four runs of `--bench 240`.)

Fifty frames a second where the Tk window managed three or four,
and the three milliseconds that are still missing from sixty are
LOVA's frame, not the drawing.  `set_mode(vsync=1)` is accepted by
this driver but does not block -- the flip returns in half a
millisecond -- so the cadence is held by `Clock.tick(60)`.

## The models

The kit's models are CC0; the kit itself is MIT.  `import_kit.py`
reads the `.glb` files (the vertices, triangles, texture coordinates
and node tree, with the character posed as the kit's `character.tscn`
poses it), looks each triangle's colour up in the kit's colormap, and
**decimates** each model to a budget -- a Kenney platform is 144
triangles because every edge is bevelled, and the renderer cannot
afford that forty-six times a frame.  The decimation is Garland and
Heckbert's quadric edge collapse with one addition: the paint.  Faces
are grouped into regions of like colour, an edge may collapse only
within a region or from a region's interior onto its boundary, a
boundary edge pays its own length, and no region may fall below three
faces -- because without that the green top of the round platform
went to nothing on the first try, and the grey tops of the yellow
platforms with it.

To regenerate: clone the kit into `%TMP%` (or pass its path) and run
`python apps/platformer/import_kit.py`.

## Licence of the data

`lib/platformer_assets.lova` is derived from the kit's models and
scene, which are:

    MIT License

    Copyright (c) 2023 Kenney

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
