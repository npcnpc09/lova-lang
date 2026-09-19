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
kit's own keys.  The mouse looks, as Godot's captured mouse does, so
moving it turns the player; the arrow keys turn as well, and Tab lets
the pointer go.
`--shot file.png` draws one frame with no window at all, through the
platformer's rasteriser, which is how the screenshot was made.

There are two windows for the same game.  `--host sdl` (the default
where pygame is installed) draws the faces with `pygame.draw.polygon`
into one buffer and flips it: 5 ms for the kit's 164 faces, and sixty
frames a second.  `--host tk` is the original canvas, which deleted
and re-created every polygon every frame at 21 ms on the median and
spikes to a quarter of a second -- the stutter this replaced.  Nothing
else differs: the same `Rules`, the same keys, the same cadence.
`--bench N` plays N frames to a script and prints what each part of a
frame cost.
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
                # The mouse is spent by a tick, not by a pass of this
                # loop: asking for it when no tick will run threw the
                # motion since the last pass away, and this loop runs
                # sixty times a tick.
                dyaw, dpitch = self.look() if self.behind >= TICK else (0, 0)
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
                # Only a tick can change the picture, and this loop runs
                # every millisecond: painting on every pass drew the
                # same frame sixty times over, at twenty to thirty
                # milliseconds each, and that is what the ticks then
                # fell behind by.
                if ran:
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


# --- the same game in an SDL window ------------------------------------------

SKY_RGB = tuple(int(SKY[i:i + 2], 16) for i in (1, 3, 5))


class SdlGame:
    """The window again, drawn by SDL instead of a Tk canvas.

    The game is untouched -- the same `Rules`, the same keys, the same
    sixtieth of a second with the same catch-up bound, the mouse still
    spent by a tick and not by a pass of the loop.  What changes is the
    surface: `pygame.draw.polygon` into a buffer flipped once, where the
    canvas deleted and re-created every polygon every frame.

    The mouse is captured the way SDL does it -- the pointer grabbed to
    the window and hidden, the motion read as a delta with
    `pygame.mouse.get_rel()` -- instead of Tk's warp-and-subtract.  The
    pointer is put back in the middle when it strays far, because a grab
    stops it at the edge of the window and the deltas would stop with
    it.  Tab lets it go, as before.
    """

    TITLE = "fps -- the window is Python, the game is LOVA"

    def __init__(self, rules: Rules, bench: int = 0) -> None:
        from apps.sdlhost import Stats, Window
        self.rules = rules
        self.win = Window(self.TITLE, VIEW_W, VIEW_H, SKY_RGB)
        pg = self.win.pg
        self.pg = pg
        self.KEYS = {pg.K_w: "w", pg.K_a: "a", pg.K_s: "s", pg.K_d: "d",
                     pg.K_UP: "Up", pg.K_DOWN: "Down", pg.K_LEFT: "Left",
                     pg.K_RIGHT: "Right"}
        self.health_font = self.win.font(28, bold=True)
        self.weapon_font = self.win.font(16, bold=True)
        self.world = rules.new_game()
        self.keys: set = set()
        self.jump_pending = False
        self.toggle_pending = False
        self.dyaw = 0.0
        self.dpitch = 0.0
        self.captured = not bench
        self.anomaly = None
        self.running = True
        self.behind = 0.0
        self.tick_ms = self.frame_ms = self.draw_ms = self.flip_ms = 0.0
        self.pass_ms = 1000 / 60
        self.tick_steps = self.frame_steps = 0
        self.faces: list = []
        self.bench = bench
        self.stats = Stats()
        self.grab(self.captured)

    # --- input -----------------------------------------------------------

    def grab(self, on: bool) -> None:
        self.pg.event.set_grab(on)
        self.pg.mouse.set_visible(not on)
        self.pg.mouse.get_rel()          # the motion up to here is not a turn

    def events(self) -> None:
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
                key = event.key
                if key == pg.K_ESCAPE:
                    self.running = False
                elif key == pg.K_TAB:
                    self.captured = not self.captured
                    self.grab(self.captured)
                elif key == pg.K_SPACE:
                    if "space" not in self.keys:
                        self.jump_pending = True
                    self.keys.add("space")
                elif key == pg.K_e:
                    if "e" not in self.keys:
                        self.toggle_pending = True
                    self.keys.add("e")
                elif key == pg.K_r:
                    self.world = self.rules.new_game()
                    self.anomaly = None
                elif key in self.KEYS:
                    self.keys.add(self.KEYS[key])
            elif event.type == pg.KEYUP:
                key = event.key
                if key == pg.K_SPACE:
                    self.keys.discard("space")
                elif key == pg.K_e:
                    self.keys.discard("e")
                elif key in self.KEYS:
                    self.keys.discard(self.KEYS[key])
            elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                self.keys.add("shoot")
            elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
                self.keys.discard("shoot")
        self.mouse()

    def mouse(self) -> None:
        """The pointer's travel since the last pass, as a turn."""
        if not self.captured:
            return
        pg = self.pg
        dx, dy = pg.mouse.get_rel()
        # the kit: rotation_target += Vector3(-yRot, -xRot, 0) / mouse_sensitivity
        self.dyaw -= dx * SENS
        self.dpitch -= dy * SENS
        cx, cy = VIEW_W // 2, VIEW_H // 2
        x, y = pg.mouse.get_pos()
        if abs(x - cx) > VIEW_W // 4 or abs(y - cy) > VIEW_H // 4:
            # A grab stops the pointer at the edge of the window and the
            # deltas stop with it, so it is put back in the middle -- and
            # the warp's own motion is thrown away, not turned into a turn.
            pg.mouse.set_pos((cx, cy))
            pg.mouse.get_rel()

    def look(self):
        """What the mouse and the arrow keys asked for this tick, in A."""
        dyaw, dpitch = self.dyaw, self.dpitch
        self.dyaw = self.dpitch = 0.0
        turn = 120 * A / 360 / 60           # the kit's gamepad turn, a tick
        dyaw += turn * ((1 if "Left" in self.keys else 0) - (1 if "Right" in self.keys else 0))
        dpitch += turn * ((1 if "Up" in self.keys else 0) - (1 if "Down" in self.keys else 0))
        return round(dyaw), round(dpitch)

    def script(self, frame: int) -> None:
        """`--bench`: walk, turn and shoot, with no one at the keys."""
        self.keys = {"w"} if frame % 90 < 60 else {"d"}
        self.dyaw += 40 if frame % 240 < 120 else -40
        if frame % 30 == 0:
            self.keys.add("shoot")
        if frame % 150 == 0:
            self.jump_pending = True

    # --- the loop --------------------------------------------------------

    def run(self) -> int:
        clock = time.perf_counter()
        drawn = 0
        while self.running:
            now = time.perf_counter()
            self.behind += now - clock
            clock = now
            if self.bench:
                self.pg.event.pump()
                self.script(drawn)
            else:
                self.events()
            ran = 0
            tick_ms = 0.0
            if self.anomaly is None:
                try:
                    # The mouse is spent by a tick, not by a pass of this
                    # loop, as the Tk host does it.
                    dyaw, dpitch = self.look() if self.behind >= TICK else (0, 0)
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
                        dyaw = dpitch = 0      # the mouse is spent on the first tick
                        self.tick_ms = (time.perf_counter() - t0) * 1000
                        tick_ms += self.tick_ms
                        self.tick_steps = self.rules.rt.steps
                        self.behind -= TICK
                        ran += 1
                    if self.behind >= TICK:      # too slow to keep up: drop the debt
                        self.behind = 0.0
                except (BudgetTrap, DeltaTrap, ValueError) as exc:
                    self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
            painted = ran or not self.faces
            if painted:
                self.paint(tick_ms)
                drawn += 1
                if self.bench and drawn >= self.bench:
                    self.running = False
            self.win.cap(60)
            # The cadence a frame was drawn at is this pass end to end,
            # the wait for the sixtieth included -- measured after it,
            # and charged to the frame that did the work.
            self.pass_ms = (time.perf_counter() - now) * 1000
            if painted and self.bench:
                self.stats.add("lova tick", tick_ms)
                self.stats.add("lova frame", self.frame_ms)
                self.stats.add("draw", self.draw_ms)
                self.stats.add("flip", self.flip_ms)
                self.stats.add("total", self.pass_ms)
                self.stats.add("faces", len(self.faces))
        if self.bench:
            self.stats.report("fps", extra=self.win.vsync_note())
        self.win.close()
        return 0

    def paint(self, tick_ms: float) -> None:
        win, pg = self.win, self.pg
        t0 = time.perf_counter()
        self.faces = [list_to_python(f) for f in self.rules.frame(self.world)]
        self.frame_steps = self.rules.rt.steps
        self.frame_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        win.fill_sky()
        win.faces(self.faces)
        cx, cy = VIEW_W // 2, VIEW_H // 2
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            pg.draw.line(win.screen, (255, 255, 255),
                         (cx + dx * 6, cy + dy * 6), (cx + dx * 14, cy + dy * 14), 2)
        health = self.rules.call("health", self.world)
        left = self.rules.call("standing", self.world)
        name = self.rules.call("weapon-name", self.world)
        if not isinstance(name, str):
            name = "".join(chr(ch) for ch in list_to_python(name))
        win.text(f"{max(health, 0)}%", 24, VIEW_H - 28 - self.health_font.get_height() // 2,
                 (255, 255, 255), self.health_font)
        win.text(f"{name}   {left} left", VIEW_W - 24,
                 VIEW_H - 28 - self.weapon_font.get_height() // 2,
                 (0xff, 0xe0, 0x8a), self.weapon_font, anchor="ne")
        if self.anomaly is not None:
            win.bar(f"the rules faulted: {self.anomaly.get('kind')}")
        else:
            win.bar(
                f"tick {self.tick_steps:,} steps / {self.tick_ms:.1f} ms   "
                f"frame {len(self.faces)} faces, {self.frame_steps:,} steps / "
                f"{self.frame_ms:.1f} ms   "
                f"({1000 / max(self.pass_ms, 1e-9):.0f} fps)   "
                f"[WASD, mouse looks, click shoots, space jumps, E swaps, R restarts]")
        self.draw_ms = (time.perf_counter() - t1) * 1000
        self.flip_ms = win.flip()


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
    parser.add_argument("--host", choices=("auto", "sdl", "tk"), default="auto",
                        help="the window: SDL (pygame, smooth) or the Tk "
                             "canvas (auto: SDL if pygame is installed)")
    parser.add_argument("--bench", type=int, metavar="N", default=0,
                        help="play N frames to a script in the SDL window and "
                             "print what each part of a frame cost")
    args = parser.parse_args()
    rules = Rules(native=args.native)
    if args.shot:
        shot(rules, args.shot)
        return 0
    from apps.sdlhost import pick_host
    if pick_host("sdl" if args.host == "auto" else args.host) == "sdl":
        return SdlGame(rules, bench=args.bench).run()
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
