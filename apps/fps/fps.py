"""A window in Python, the game in LOVA: Kenney's FPS starter kit.

    python apps/fps/fps.py
    python apps/fps/fps.py --shot apps/fps/screenshot.png

A port of KenneyNL/Starter-Kit-FPS (MIT, about 1 000 stars): the
player who walks, jumps twice, looks with the mouse and shoots two
blasters; the four enemies that hover, turn to face him and fire every
quarter second; the knockback; the level of platforms and walls.
Everything that decides is `lib/fps.lova`, written against the kit's
GDScript and checked against a transliteration of it in
`tests/test_fps.py`; every number in the picture is
`lib/scene3d.lova` -- the models placed, turned, tilted, divided by
their depth, culled, lit -- and the models and the level are the kit's
own, read out of it by `import_kit.py`.  This shell owns the window,
the keys, the mouse and the clock.

LOVA has no floating point.  The rules run in 65 536ths of a metre and
the picture in 1024ths, and a tick is a sixtieth of a second, the kit's
frame.  The clock here runs the rules at sixty ticks a second of wall
time (falling behind when it must) and draws a frame whenever it can.
The bar says what it managed.

WASD walk, space jumps (twice), E swaps the blaster for the repeater,
the left mouse button shoots, R starts again, Escape leaves -- the
kit's own keys.  The mouse looks: the pointer is warped back to the
middle of the canvas after every motion, as Godot's captured mouse
does, so moving it turns the player; the arrow keys turn as well, for
a machine where the warp is unwelcome, and Tab lets the pointer go.
`--shot file.png` draws one frame with no window at all, through the
platformer's rasteriser, which is how the screenshot was made.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.platformer.platformer import rasterise, write_png
from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.native import Ref, open_session
from core.runtime import Runtime, _call, _map_key, evaluate
from core.runtime import list_to_python as _list_to_python


def list_to_python(value):
    """A LOVA list as a Python one, whichever runtime produced it."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return _list_to_python(value)


SOURCE = """\
(use "fps")
(rec new new-game tick tick input input frame frame
     health health weapon-name weapon-name standing standing
     restarts (lambda w (get w restarts))
     where where)
"""

VIEW_W, VIEW_H = 960, 600
FOCAL = 357                      # the kit's camera: fov 80, vertical, for this height
FAR = 40 * 1024                  # metres from the eye beyond which nothing is drawn
BUDGET = 50_000_000
TICK = 1 / 60
MAX_CATCHUP = 4                  # ticks a frame may run to catch up with the clock
SKY = "#8fb8e8"

F = 65536
A = 16384
SENS = A / (700 * 2 * math.pi)   # mouse_sensitivity 700: A of turn a pixel


def lit(k, l):
    """A 24-bit colour under light `l`, where 1024 is the sun straight on."""
    r, g, b = k >> 16 & 255, k >> 8 & 255, k & 255
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * l // 1024)) for c in (r, g, b))


class Rules:
    """The LOVA program, loaded once; every tick and frame is one call into it."""

    NAMES = ("new", "tick", "input", "frame", "health", "weapon-name", "standing",
             "restarts", "where")

    def __init__(self, native: str = "auto") -> None:
        tree, _report = build(SOURCE)
        self.session = open_session(tree, native, max_steps=BUDGET, max_depth=10_000)
        if self.session is not None:
            self.rt = self.session
            self.fn = {n: self.session.get(n) for n in self.NAMES}
        else:
            self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
            api = evaluate(tree, self.rt)
            self.fn = {n: api.entries[_map_key(n, "rec")][1] for n in self.NAMES}
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

    def call(self, name, *args):
        if self.session is not None:
            return self.session.call(self.fn[name], *args)
        self.rt.steps = 0
        self.rt.mark = 0
        self.rt.current = None
        fn = self.fn[name]
        for arg in args:
            fn = _call(fn, arg, self.rt)
        return fn

    def new_game(self):
        return self.fn["new"]

    def tick(self, world, keys, dyaw=0, dpitch=0):
        """One sixtieth of a second: `keys` is the set of names held, and
        `jump` / `toggle` are in it only on the tick the key went down."""
        held = self.call("input",
                         (1 if "d" in keys else 0) - (1 if "a" in keys else 0),
                         (1 if "s" in keys else 0) - (1 if "w" in keys else 0),
                         1 if "jump" in keys else 0,
                         1 if "shoot" in keys else 0,
                         1 if "toggle" in keys else 0,
                         int(dyaw), int(dpitch))
        world = self.call("tick", world, held)
        if isinstance(held, Ref):
            self.session.release(held)
        return world

    def frame(self, world):
        return list_to_python(self.call("frame", world, FOCAL, VIEW_W, VIEW_H, FAR))


class Game:
    """The window: keys and mouse in, polygons out."""

    def __init__(self, master, rules: Rules) -> None:
        import tkinter as tk
        self.tk = tk
        self.master = master
        self.rules = rules
        self.canvas = tk.Canvas(master, width=VIEW_W, height=VIEW_H, bg=SKY,
                                highlightthickness=0, cursor="none")
        self.canvas.pack()
        self.bar = tk.Label(master, anchor="w", bg="#0e1116", fg="#c8d2de",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.world = rules.new_game()
        self.keys: set = set()
        self.jump_pending = False
        self.toggle_pending = False
        self.dyaw = 0.0
        self.dpitch = 0.0
        self.captured = True
        self.anomaly = None
        self.clock = time.perf_counter()
        self.behind = 0.0
        self.tick_ms = self.frame_ms = 0.0
        self.tick_steps = self.frame_steps = 0
        master.bind("<KeyPress>", self.on_press)
        master.bind("<KeyRelease>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.keys.add("shoot"))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.keys.discard("shoot"))
        master.after(10, self.loop)

    # --- input -----------------------------------------------------------

    KEYS = {"w": "w", "a": "a", "s": "s", "d": "d",
            "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right"}

    def on_press(self, event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key == "Tab":
            self.captured = not self.captured
            self.canvas.config(cursor="" if not self.captured else "none")
        elif key == "space":
            if "space" not in self.keys:
                self.jump_pending = True
            self.keys.add("space")
        elif key in ("e", "E"):
            if "e" not in self.keys:
                self.toggle_pending = True
            self.keys.add("e")
        elif key in ("r", "R"):
            self.world = self.rules.new_game()
            self.anomaly = None
        elif key in self.KEYS:
            self.keys.add(self.KEYS[key])

    def on_release(self, event) -> None:
        key = event.keysym
        if key == "space":
            self.keys.discard("space")
        elif key in ("e", "E"):
            self.keys.discard("e")
        elif key in self.KEYS:
            self.keys.discard(self.KEYS[key])

    def on_motion(self, event) -> None:
        """The pointer warped back to the middle after every motion, which
        is what a captured mouse amounts to in Tk."""
        if not self.captured:
            return
        cx, cy = VIEW_W // 2, VIEW_H // 2
        dx, dy = event.x - cx, event.y - cy
        if dx == 0 and dy == 0:
            return
        # the kit: rotation_target += Vector3(-yRot, -xRot, 0) / mouse_sensitivity
        self.dyaw -= dx * SENS
        self.dpitch -= dy * SENS
        self.canvas.event_generate("<Motion>", warp=True, x=cx, y=cy)

    def look(self):
        """What the mouse and the arrow keys asked for this tick, in A."""
        dyaw, dpitch = self.dyaw, self.dpitch
        self.dyaw = self.dpitch = 0.0
        turn = 120 * A / 360 / 60           # the kit's gamepad turn, a tick
        dyaw += turn * ((1 if "Left" in self.keys else 0) - (1 if "Right" in self.keys else 0))
        dpitch += turn * ((1 if "Up" in self.keys else 0) - (1 if "Down" in self.keys else 0))
        return round(dyaw), round(dpitch)

    # --- the loop --------------------------------------------------------

    def loop(self) -> None:
        now = time.perf_counter()
        self.behind += now - self.clock
        self.clock = now
        ran = 0
        if self.anomaly is None:
            try:
                dyaw, dpitch = self.look()
                while self.behind >= TICK and ran < MAX_CATCHUP:
                    keys = set(self.keys)
                    if self.jump_pending:
                        keys.add("jump")
                        self.jump_pending = False
                    if self.toggle_pending:
                        keys.add("toggle")
                        self.toggle_pending = False
                    t0 = time.perf_counter()
                    self.world = self.rules.tick(self.world, keys, dyaw, dpitch)
                    dyaw = dpitch = 0          # the mouse is spent on the first tick
                    self.tick_ms = (time.perf_counter() - t0) * 1000
                    self.tick_steps = self.rules.rt.steps
                    self.behind -= TICK
                    ran += 1
                if self.behind >= TICK:          # too slow to keep up: drop the debt
                    self.behind = 0.0
                self.paint()
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
                self.bar.config(text=f"the rules faulted: {self.anomaly.get('kind')}")
        self.master.after(1, self.loop)

    def paint(self) -> None:
        c = self.canvas
        t0 = time.perf_counter()
        faces = self.rules.frame(self.world)
        self.frame_steps = self.rules.rt.steps
        self.frame_ms = (time.perf_counter() - t0) * 1000
        c.delete("all")
        for f in faces:
            u0, v0, u1, v1, u2, v2, k, l = list_to_python(f)
            fill = lit(k, l)
            c.create_polygon(u0, v0, u1, v1, u2, v2, fill=fill, outline=fill)
        crosshair(c.create_line, VIEW_W // 2, VIEW_H // 2)
        health = self.rules.call("health", self.world)
        left = self.rules.call("standing", self.world)
        name = self.rules.call("weapon-name", self.world)
        if not isinstance(name, str):
            name = "".join(chr(ch) for ch in list_to_python(name))
        c.create_text(24, VIEW_H - 28, anchor="w", text=f"{max(health, 0)}%",
                      fill="#ffffff", font=("Consolas", 26, "bold"))
        c.create_text(VIEW_W - 24, VIEW_H - 28, anchor="e",
                      text=f"{name}   {left} left", fill="#ffe08a",
                      font=("Consolas", 14, "bold"))
        self.bar.config(
            text=f"tick {self.tick_steps:,} steps / {self.tick_ms:.1f} ms   "
                 f"frame {len(faces)} faces, {self.frame_steps:,} steps / {self.frame_ms:.0f} ms "
                 f"({1000 / max(self.frame_ms + self.tick_ms, 1):.1f} fps)   "
                 f"[WASD, mouse looks, click shoots, space jumps, E swaps, R restarts]")


def crosshair(line, cx, cy):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        line(cx + dx * 6, cy + dy * 6, cx + dx * 14, cy + dy * 14,
             fill="#ffffff", width=2)


# --- a frame with no window --------------------------------------------------

def shot(rules: Rules, path: str) -> None:
    """Play a little with no window, then write one frame: stand up, turn
    onto the first enemy, and empty the blaster into it."""
    world = rules.new_game()
    script = [(40, set(), 0, 0),                     # fall onto the platform
              (1, set(), 1377, 0),                   # turn toward the first enemy
              (1, {"jump"}, 0, 0),                   # up, and up again at the top
              (25, set(), 0, 0),
              (1, {"jump"}, 0, 0),
              (22, set(), 0, 0),
              (1, set(), 0, -350),                   # aim down onto it
              (1, {"shoot"}, 0, 0),                  # one pull: three rays, 75 of its 100
              (3, set(), 0, 0)]
    for ticks, keys, dyaw, dpitch in script:
        for i in range(ticks):
            world = rules.tick(world, keys, dyaw if i == 0 else 0, dpitch if i == 0 else 0)
    t0 = time.perf_counter()
    faces = [list_to_python(f) for f in rules.frame(world)]
    steps = rules.rt.steps
    px = rasterise(faces, VIEW_W, VIEW_H)
    mark(px, VIEW_W, VIEW_H)
    write_png(path, px, VIEW_W, VIEW_H)
    x, y, z = (v / F for v in list_to_python(rules.call("where", world)))
    print(f"{path}: {len(faces)} faces, {steps:,} LOVA steps in "
          f"{(time.perf_counter() - t0) * 1000:.0f} ms; the player at "
          f"({x:.2f}, {y:.2f}, {z:.2f}) with {rules.call('health', world)}% health, "
          f"{rules.call('standing', world)} enemies standing")


def mark(px, w, h):
    """The crosshair, into the buffer the rasteriser filled: four arms
    two pixels thick, the same as the window draws."""
    cx, cy = w // 2, h // 2
    for d in range(6, 15):
        for u, v in ((cx - d, cy), (cx + d, cy), (cx, cy - d), (cx, cy + d)):
            for k in (0, 1):
                x, y = (u, v + k) if v == cy else (u + k, v)
                i = (y * w + x) * 3
                px[i] = px[i + 1] = px[i + 2] = 255


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kenney's FPS starter kit: the window is Python, the game is LOVA")
    parser.add_argument("--shot", metavar="file.png",
                        help="no window: play the script and write one frame")
    parser.add_argument("--native", choices=("auto", "on", "off"), default="auto",
                        help="run the game in a native runtime (auto: if there "
                             "is one and it takes this program)")
    args = parser.parse_args()
    rules = Rules(native=args.native)
    if args.shot:
        shot(rules, args.shot)
        return 0
    import tkinter as tk
    root = tk.Tk()
    root.title("fps -- the window is Python, the game is LOVA")
    root.configure(bg="#0e1116")
    root.resizable(False, False)
    Game(root, rules)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
