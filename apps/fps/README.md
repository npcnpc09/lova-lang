# fps -- Kenney's FPS starter kit, in LOVA

    python apps/fps/fps.py
    python apps/fps/fps.py --shot apps/fps/screenshot.png

![the level from the eye, drawn by lib/scene3d.lova](screenshot.png)

A port of [KenneyNL/Starter-Kit-FPS](https://github.com/KenneyNL/Starter-Kit-FPS)
(MIT, about 1 000 stars): a player who walks, jumps twice, looks with
the mouse and shoots two blasters; four flying enemies that hover,
turn to face him and fire every quarter second; a knockback that
throws the shooter back and kicks the aim up; a level of platforms and
walls under a sky of clouds; health that runs out, and a fall off the
world -- either of which starts everything again.

| What | Where | Whose |
|---|---|---|
| The rules -- player, weapons, shots, enemies, health, restart | `lib/fps.lova` | ours, written against the kit's GDScript |
| The picture -- objects placed, turned, tilted, culled, lit, ordered, from the eye | `lib/scene3d.lova` over `lib/mesh3d.lova` | ours |
| The models, the level, the enemies, the clouds | `lib/fps_assets.lova` (generated) | the kit's, read by `import_kit.py` |
| The window, the keys, the mouse, the clock, the screenshot rasteriser | `fps.py` | ours |
| The check: a transliteration of the kit's scripts, run against the port | `tests/test_fps.py` | ours |

**What came across unchanged**: movement speed 5, two jumps of 8,
gravity 20 a second cancelled on the floor and the ceiling, the
velocity lerp of a tenth of a second, the capsule's 0.3 by 1.0 centred
at 0.55, the head a metre up, the camera's dip of -0.1 eased at a
fifth of a second, the field of view of 80 degrees, health 100 and the
restart below zero, the bottom of the world at -10, mouse sensitivity
700, the pitch clamped to a quarter turn; the blaster's damage 25,
cooldown 0.25, spread 1.0, three shots, knockback 40 and aim kick of
0.025-0.045 by 0.025-0.04 radians, the repeater's 10, 0.1, 0.5, one
shot, 10 and 0.001-0.0025 by 0.001-0.002; the ten-metre shot; the
enemies' sphere of 0.75 at +0.25, their hover of `cos(time * 5)` a
metre a second, their look at the player plus half a metre, their
five-metre ray, their timer of 0.25 s and their five damage; the
weapon held at the container offset (1.2, -1.1, -2.75) turned 180
degrees and seen through the kit's second camera of 40 degrees (below);
and every position, turn and scale in `scenes/main.tscn`.

**What is ours instead of Godot's**: the collision and the rays.  The
kit gives each platform and wall a concave collision mesh, the player
a capsule and each enemy a sphere, and lets Jolt and `RayCast3D` sort
it out; the port makes each solid the box of *the kit's own collision
shape* -- not of its model, which is bevelled a little wider, so
`wall-low`'s box reaches from -0.35 to +0.735 in z as its shape does
and not symmetrically -- the player a vertical segment with a radius,
and every shot a segment tested against the enemy spheres and those
boxes, nearest hit winning.  An enemy's shot is the same segment
against a sphere of the player's radius at the point it aims for.  A
body pushed out of a box slides as `move_and_slide` does: it comes out
along the face's normal and keeps only the velocity that runs along
the face, so walking at a wall does not store up speed that is spent
the moment you turn away.  The transliteration in the test uses the
same model, so the test checks the port against the kit's *rules*, not
against Jolt.

Ours too: the randomness.  The kit calls `randf_range` for a shot's
spread and for the knockback and `randi() % 2` for its sign; the port
carries a linear congruential generator in the world and draws from it
in the kit's own order -- each shot's x and y spread, then the
knockback's sign as a draw's parity, its x and its y -- so a run
repeats exactly and the test can draw the same numbers.

**What LOVA has to do without**: floating point.  The rules run in
65 536ths of a metre and 16 384ths of a turn; the picture in 1024ths
and 256ths.  Sines are a table of 256ths of a turn, so a direction is
known to 1.4 degrees, and the transliteration takes the port's
quantised sines and its integer unit ray direction before doing the
intersection in floats -- a hit is a quarter of an enemy's health or
nothing, and the two should not disagree about a shot neither got
wrong.

**What is different on purpose.**  Most of it is in the picture:

*The weapon.*  The kit draws it with a second camera -- a Camera3D of
40 degrees inside a SubViewport stretched over the whole screen --
while the world is seen at 80, so the weapon is magnified by
tan(40)/tan(20) = 2.305 and is never clipped by the world.  There is
one camera here, so the port keeps the kit's container offset across
and down and divides the one along the view by that ratio: at the
kit's own fields of view the projection is then the same map, and the
blaster lands where the kit's screenshot has it -- big, in the bottom
right, cropped by the corner -- at the same size.  What does not carry
over is the depth: the model is a world object, so a platform standing
between the eye and 1.2 metres of nothing could in principle cut
across it, and the model is turned by the player's yaw alone, so it
keeps its place on the screen but stays level with the world when you
look far up or down.  The kit also lerps the container against the
player's own velocity (`container_offset - basis.inverse() *
velocity / 30`), a sway when you start and stop; the port holds the
offset still.

*The rest of the picture.*  The kit's impact is a 2D animated sprite;
there is no sprite in this renderer, so `model-of` gives "impact" the
cloud's cube, drawn small and shrinking over the fifth of a second the
mark lives.  The kit's weapon change runs a tween of a tenth of a
second; here it is immediate.  An enemy's `look_at` is a full
orientation in the kit -- it tips toward a player below it -- and the
port draws only the yaw of it, though the five-metre ray it fires is
the full direction.  Muzzle flashes, sound and the blob shadow are not
drawn at all.

*In the rules*, one thing: the knockback's kick to the aim is clamped
to a quarter turn either way, as the mouse's own pitch is.  The kit
adds it to `camera.rotation.x` unclamped, so a long burst there can
tip the view past vertical until the next mouse move pulls it back.
The velocity slide, which was the other difference, is implemented, so
there is nothing left to say about it.

First person needed one thing of `lib/scene3d.lova`, which was written
for a camera that follows a character from ten metres back:
`scene-inside` stands the camera at the eye with a zoom of nothing,
keeps an object close enough to be around the viewer however its
centre projects -- the platform under your feet has its centre at no
depth at all -- and drops a face whose three corners are all behind
the near plane.  `scene-shot` is unchanged, and the platformer and the
city builder draw exactly what they drew.

**Speed, honestly.**  A tick of the rules is about **4 700** LOVA
steps standing still and **7 100** walking and shooting; a frame is
**116 000 to 180 000**, most of it the renderer's two hundred steps a
triangle.  The measurement is `python tools/bench_native.py 3 fps`,
which runs `tools/bench/fps.lova` -- the world built, N ticks, one
frame -- through the command line on each runtime and subtracts the
parse-and-compile floor:

| row | steps | Python eval | native eval | ratio | native steps/s |
|---|---|---|---|---|---|
| `fps frame` | 133 083 | 0.30 s | under 20 ms | >15 | -- |
| `fps 60t+frame` | 574 949 | 1.58 s | 0.07 s | 22 | 8 M |
| `fps 300t+frame` | 2 392 742 | 6.88 s | 0.50 s | **13.7** | **4.8 M** |

The first two rows sit near the tool's own resolution -- a floor of
three quarters of a second measured separately, which is why the
60-tick row swung between 16 and 25 over four runs -- so the 300-tick
row is the one to quote: **13.7x** (14.2 on a re-run).  Measured
inside the app instead, best of five, a tick is **12.9 ms on CPython
and 2.5 ms native** and a frame **221 ms and 20.6 ms** -- 5.1x and
10.7x, about 5.6 million
steps a second.  That is three or four frames a second on CPython
while the rules keep sixty ticks of wall time, and thirty to fifty
native.  Both runtimes produce the same screenshot byte for byte.  The
step counter in the bar is the honest number.

**Two windows.**  `fps.py` opens an SDL window (pygame) when pygame is
installed and the Tk one otherwise; `--host tk` asks for the old one
and `--host sdl` insists on the new.  The game is the same either way
-- the same `Rules`, the same keys, the same sixtieth of a second --
and only the surface differs: the Tk canvas deleted and re-created
every polygon every frame, which cost **21 ms on the median here and
up to 250 ms**, and that was the stutter.  `pygame.draw.polygon` into
one buffer, flipped once, costs **5 ms** for the same faces.  `--bench
N` plays N frames to a script and prints the split; on this machine,
native runtime, 164 faces a frame:

| part | median | p95 |
|---|---|---|
| LOVA tick | 2.1 ms | 4.1 ms |
| LOVA frame | 8.1 ms | 10.9 ms |
| draw | 5.0 ms | 6.5 ms |
| flip | 0.5 ms | 0.8 ms |
| **a frame, end to end** | **16.6 ms (60 fps)** | **20.6 ms** |

So the window now keeps sixty frames a second and what is left to cut
is LOVA's own frame, not the drawing.  Two notes on the honesty of
that: `set_mode(vsync=1)` is accepted by this driver but does not
block -- the flip returns in half a millisecond -- so the cadence is
held by `Clock.tick(60)`; and a face whose three corners are all off
one side of the view is dropped before SDL sees it, because SDL walks
a polygon's whole vertical span before it clips and 38 of the 160
faces were more than half the milliseconds.  Dropping them changes no
pixel.

## Checked against the kit

`tests/test_fps.py` transliterates `objects/player.gd`,
`objects/enemy.gd` and `scripts/weapon.gd` with both weapon resources
into floating-point Python over the port's collision model, and runs
the two side by side for **642 ticks** of a scripted play -- landing,
stepping sideways and diagonally, looking round, jumping twice,
walking into an enemy's fire, emptying the repeater and then the
blaster into it until it is destroyed, crossing the gap to the next
island with a jump, walking into the low wall and sliding along it,
then stepping clear and off the edge of the world -- comparing, every
tick, the player's position, velocity, gravity, camera dip, yaw,
pitch, jumps, health, weapon and cooldown, each enemy's position,
facing, health, whether it is alive and its firing timer, and every
impact's position and age.  Positions agree to within **four
thousandths of a metre**, which is the port's rounding; the counted
things, the angles and the facings agree exactly.  A second test lets
both run free over the same keys and checks that the same things
happened, and a third asserts the play is worth running: it jumps
twice, destroys an enemy, takes fire, loses a metre a second to a wall
and falls off the world.

The test's docstring lists what its oracle *shares* with the port and
therefore cannot catch: the weapon table, the random generator, the
sine table, the integer unit ray direction and the bisection behind
`atan2`.  Everything else is written out from the GDScript.

## The models

The kit's models are CC0; the kit itself is MIT.  `import_kit.py`
reads the `.glb` files, looks each triangle's colour up in the kit's
colormap, and decimates each model to a budget, exactly as the
platformer's importer does.  It writes the models, the level, the
enemies and the clouds -- and not the boxes the rules collide against,
which are the kit's collision shapes and live in `lib/fps.lova`: a
table of model extents beside them would be a second answer to a
question that has one.

To regenerate: clone the kit into `%TMP%` (or pass its path) and run
`python apps/fps/import_kit.py`.

## Licence of the data

`lib/fps_assets.lova` is derived from the kit's models and scene,
which are:

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

## Controls

| Key | What |
|---|---|
| W A S D | walk |
| mouse | look (SDL: the pointer is grabbed to the window and hidden and the motion read as a delta, put back in the middle when it strays far, because a grab stops it at the edge; Tk: the pointer is warped back to the middle after every motion, which is what a captured mouse amounts to there.  **Tab** lets it go in both) |
| arrow keys | look, at the kit's gamepad rate of 120 degrees a second, for a machine where the warp is unwelcome |
| left mouse button | shoot |
| space | jump (twice) |
| E | swap the blaster for the repeater |
| R | start again |
| Escape | leave |
