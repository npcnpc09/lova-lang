# fps, in Godot -- the kit's picture, LOVA's rules

    cargo build --release --manifest-path native/lova-godot/Cargo.toml
    python apps/godot/fps/build.py [path/to/Starter-Kit-FPS] --run
    python apps/godot/fps/build.py --shot=apps/godot/fps/screenshot.png
    python apps/godot/fps/build.py --smoke          # headless, no window
    python apps/godot/fps/build.py --movie=apps/godot/fps/demo.mp4   # the recording

![Kenney's FPS kit drawn by Godot, its rules run by LOVA](screenshot.png)

[`demo.mp4`](demo.mp4) is seven seconds of the demo playing itself
in Godot's movie-maker mode -- a frame a tick, the sound with it: it
walks in, jumps, looks round, then turns to the nearest enemy and
takes three of the four with the repeater and the blaster.  The aim is
computed from the enemies' places the rules report each tick; what it
hits is decided by the rules' own ray.  The fourth enemy stands
seventeen metres away, beyond the ten-metre shot, so the demo ends.

The same port as [`apps/fps`](../../fps/README.md), the other way
round.  There, LOVA draws the picture too, through `lib/scene3d.lova`,
and the models are decimated to what a LOVA renderer can afford.  Here
Godot draws -- the kit's own project, its models, sky, sounds, muzzle
flashes, impact sprites and HUD, untouched -- and LOVA runs the rules:
`lib/fps.lova`, the same file, tick for tick.

| What | Where | Whose |
|---|---|---|
| The rules -- player, weapons, shots, enemies, health, restart | `lib/fps.lova` | ours, unchanged |
| What Godot is told after a tick | `fps_godot.lova`, one `scene` function | ours |
| The runtime inside Godot | `native/lova-godot`, a GDExtension class `LovaRuntime` | ours |
| The kit's scripts, with the rules taken out | `overlay/objects/player.gd`, `overlay/objects/enemy.gd` | ours, over the kit's |
| Everything drawn, heard or clicked | the kit's project, copied by `build.py` | Kenney's (MIT, models CC0) |

## How a tick goes

`player.gd` keeps a `LovaRuntime`.  In `_ready` it opens the compiled
program (`res://lova/fps_godot.hex`) and takes handles on `new`,
`tick`, `input` and `scene`.  Every `_physics_process`:

1. the keys and the mouse become `(input mx mz jump shoot toggle dyaw
   dpitch)` -- the mouse's travel turned into 16 384ths of a turn, as
   the kit turns by `relative / 700` radians;
2. `(tick world held)` gives the next world; the old handles are
   released;
3. `(scene world)` answers three lists -- the player (position, yaw,
   pitch, dip, health, weapon, whether a shot went off this tick, the
   tick, the restarts), the enemies (position, yaw, alive, health,
   whether the timer went off), the impacts (position, whether it was
   made this tick);
4. the script divides by F and A and writes the answer into the kit's
   nodes: the player's transform, the camera's pitch and dip, the
   weapon sway, footsteps, the HUD's health, the weapon-change tween,
   the muzzle flash on a shot, each enemy's place and facing, a hurt
   or destroy sound when its health falls, an impact sprite where a
   shot landed.

Nothing fractional enters the runtime.  A float handed to `call` is
refused with a message naming it.

## What is the kit's and what is not

The rules are the kit's numbers, checked tick by tick in
`tests/test_fps.py` against a transliteration of `player.gd` and
`enemy.gd`.  What differs from the kit running its own scripts:

- the kit reloads the scene when the player falls or dies; the rules
  start a new game inside the same world (the random generator runs
  on), so the enemies are shown again rather than rebuilt;
- collisions are the rules' boxes and spheres, not Jolt's; the kit's
  collision nodes are still in the scene but nothing moves through
  them;
- an enemy's muzzle flashes when its shot hit (the player's health
  fell that tick), as the kit's does when the ray finds the player.

## Building

`native/lova-godot` needs Rust 1.94 or later and builds against
Godot's 4.6 API (`api-4-6`), so Godot 4.6 or later runs it.  `build.py`
copies the kit to `apps/godot/fps/project/` (not tracked), lays the
overlay over it, copies the built `lova_godot.dll` to `bin/`, writes
the compiled program to `lova/fps_godot.hex`, registers the extension
and imports the project's resources with the editor, headlessly.  The
Godot binary is `$GODOT` or the one in `D:/game/godot`; `--gl` picks
the OpenGL compatibility renderer for a machine whose Vulkan driver
cannot build the Forward+ shaders.

`--smoke` runs `lova_smoke.gd` under `--headless`: opens the program,
runs three hundred ticks, prints the cost, refuses a float, reports a
trap.  `tests/test_godot.py` runs it when Godot, the kit and the built
extension are on the machine, and skips otherwise.

## Cost

On this machine, inside Godot: a tick of the rules 3 900-6 700 steps,
0.56-0.70 ms, three channel round trips included.  Godot's physics
tick is 16.7 ms.
