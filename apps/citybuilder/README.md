# citybuilder -- Kenney's city builder starter kit, in LOVA

    python apps/citybuilder/citybuilder.py            # the kit's sample city
    python apps/citybuilder/citybuilder.py --empty    # a clean grid and $10 000
    python apps/citybuilder/citybuilder.py --shot apps/citybuilder/screenshot.png

![the kit's sample city, drawn by lib/scene3d.lova](screenshot.png)

A port of [KenneyNL/Starter-Kit-City-Builder](https://github.com/KenneyNL/Starter-Kit-City-Builder)
(MIT, about 1 500 stars): a grid to place fifteen kinds of structure
on -- roads, pavements, four small buildings, a garage, grass and
trees -- a till that pays for each, a cursor that follows the mouse
across the ground and turns in quarters, a catalogue to cycle
through, and a camera that pans, turns under the middle button and
zooms in steps.

| What | Where | Whose |
|---|---|---|
| The rules -- the grid, the till, the cursor, the catalogue, the camera, what a click means | `lib/citybuilder.lova` | ours, written against the kit's GDScript |
| The picture | `lib/scene3d.lova` over `lib/mesh3d.lova` | ours |
| The structures, their prices, the sample city | `lib/citybuilder_assets.lova` (generated) | the kit's, read by `import_kit.py` |
| The window, the mouse, the keys, the save file | `citybuilder.py` | ours |
| The check: `builder.gd` and `view.gd` transliterated, run beside the port | `tests/test_citybuilder.py` | ours |

**What came across unchanged**: the till of 10 000 charged only when
a cell's previous structure was a different one; demolition of what
is there; the cursor's quarter turns and its lerp of two thirds; the
catalogue's order and prices; the pan of a quarter metre a frame
turned by the camera's yaw; the turn of a tenth of a degree per pixel
of mouse travel; the zoom in steps of five between 15 and 80; the
three lerps; and the sample city, all 122 cells of it with the 5 860
left in its till.

**What a click means is a rule.** The kit asks Godot where the mouse's
ray meets the ground plane; the port carries the pixel back through
the camera in integers -- 1024ths of a metre, sines from a table of
256ths of a turn -- and rounds to a cell.  The test unprojects a grid
of pixels through both and asks for the same cell wherever the
floating-point answer is more than eight hundredths from a cell
boundary, and for the same ground point to one part in a hundred of
its distance.

**The sample city is a Godot binary resource.** `sample map/map.res`
is not text; `import_kit.py` has a sixty-line reader of that format --
the string table, the resource index, the variant encodings of an
int, a Vector2i, an object reference and an array -- and the one
thing about it that cost an hour: a property at its default value is
not written at all, so a cell with structure 0 facing 0 has neither.
An orientation is the index of one of Godot's twenty-four orthogonal
bases; the four the cursor can reach are 0, 22, 10 and 16.

**The models are simplified by clustering, not collapsing.** The
platformer's quadric edge collapse folded these buildings' walls: their
four hundred triangles are bevels a few centimetres wide around
windows, and no budget of a hundred keeps both the bevels and the
box.  Vertex clustering -- snap to a grid, merge what lands together
-- keeps the box, the roof and the door and loses the bevels; the
windows become patches of their own colour.  The grid is the finest
that brings a model within its budget.

**Speed, honestly.** A tick is about 500 LOVA steps.  The whole sample
city is some 2 500 visible triangles and a million steps, three
seconds of CPython, so the window draws the city only when the camera
or a cell has changed and draws the cursor's preview over the kept
picture on its own.  Panning is slow; looking, building and choosing
are not.  PyPy runs the same code about six times faster.

**Two windows.**  `citybuilder.py` opens an SDL window (pygame) when
pygame is installed and the Tk one otherwise; `--host tk` asks for the
old one and `--host sdl` insists on the new.  The rules, the mouse and
the keys are the same, and so is what makes the city worth drawing
again -- `city-key` and `cursor-key`.  What changes is where the faces
go: the kept city is drawn once into a surface of its own and blitted
after that, so looking around costs a blit and only a pan pays for the
city.  `--bench N` pans, stands still and pans back, and prints the
split; on this machine, native runtime, the sample city at 2 458 faces:

| part | median | p95 |
|---|---|---|
| LOVA tick | 7.3 ms | 9.3 ms |
| LOVA city frame (a pan only) | 77.5 ms | 92.2 ms |
| LOVA cursor frame | 1.0 ms | 1.2 ms |
| draw (the city's 2 458 faces on a pan, else a blit) | 16.5 ms | 19.5 ms |
| **a frame with the city kept** | **16.6 ms (60 fps)** | **17.5 ms** |
| **a frame with the city redrawn** | **107 ms (9 fps)** | **132 ms** |

So the still camera is smooth at sixty and a pan is nine frames a
second, three quarters of which is `frame-city` in LOVA -- the 840 000
steps `tests/test_frame_cost.py` pins -- and not the window.  That is
the next number to cut, and it is the language's, not the host's.
`set_mode(vsync=1)` is accepted by this driver but does not block, so
the cadence is held by `Clock.tick(60)`.

## Licence of the data

`lib/citybuilder_assets.lova` is derived from the kit's models, its
structure resources and its sample map, which are:

    MIT License

    Copyright (c) 2025 Kenney

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
