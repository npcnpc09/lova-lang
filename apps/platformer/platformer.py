"""A window in Python, the game in LOVA: Kenney's 3D platformer.

    python apps/platformer/platformer.py
    python apps/platformer/platformer.py --shot apps/platformer/screenshot.png

A port of KenneyNL/Starter-Kit-3D-Platformer (MIT, ~1 200 stars): the
character, the coins, the platforms that give way, the bricks broken
from below, the camera that follows.  Everything that decides is
`lib/platformer.lova`, written against the kit's GDScript and checked
against a transliteration of it in `tests/test_platformer.py`; every
number in the picture is `lib/scene3d.lova` -- the models placed,
turned, tilted, divided by their depth, culled, lit -- and the models
and the level are the kit's own, read out of it by `import_kit.py`.
This shell owns the window, the keys and the clock.

LOVA has no floating point.  The rules run in 65 536ths of a metre and
the picture in 1024ths, and a tick is a sixtieth of a second, the kit's
physics step.  The clock here runs the rules at sixty ticks a second of
wall time (falling behind when it must -- a tick is about six thousand
LOVA steps, a frame a hundred thousand or more, and CPython does about
seven hundred thousand a second; PyPy does four million) and draws a
frame whenever it can.  The bar says what it managed.

WASD walk, space jumps (twice), the arrow keys turn and tilt the
camera, + and - zoom, R starts again, Escape leaves -- the kit's own
keys.  `--shot file.png` draws one frame with no window at all, through
a forty-line rasteriser at the bottom of this file, which is how the
screenshot was made.

There are two windows for the same game.  `--host sdl` (the default
where pygame is installed) draws the faces with `pygame.draw.polygon`
into one buffer and flips it: 4.6 ms for the level's 305 faces, and
fifty to fifty-three frames a second on the native runtime.  `--host
tk` is the original canvas, which deleted and re-created every polygon every
frame at 21 ms on the median and spikes to a quarter of a second --
the stutter this replaced.  Nothing else differs.  `--bench N` plays N
frames to a script and prints what each part of a frame cost.
"""

from __future__ import annotations

import argparse
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.native import Ref, open_session
from core.runtime import Runtime, _call, _map_key, evaluate
from core.runtime import list_to_python as _list_to_python


def list_to_python(value):
    """A LOVA list as a Python one, whichever runtime produced it.

    A native session hands a list over as a Python list already (and
    `nil` -- the empty list -- as `None`); the Python runtime hands over
    a cons chain.  Both arrive here.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return _list_to_python(value)

SOURCE = """\
(use "platformer")
(rec new new-game tick tick input input frame frame
     coins (lambda w (get w coins))
     resets (lambda w (get w resets))
     where (lambda w (list (get (get w p) x) (get (get w p) y) (get (get w p) z))))
"""

VIEW_W, VIEW_H = 960, 600
FOCAL = 824                      # the kit's camera: a 40 degree field of view, tall
FAR = 12 * 1024                  # metres from the camera's target beyond which nothing is drawn
BUDGET = 50_000_000
TICK = 1 / 60
MAX_CATCHUP = 4                  # ticks a frame may run to catch up with the clock
SKY = "#8fb8e8"

F = 65536


def lit(k, l):
    """A 24-bit colour under light `l`, where 1024 is the sun straight on."""
    r, g, b = k >> 16 & 255, k >> 8 & 255, k & 255
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * l // 1024)) for c in (r, g, b))


class Rules:
    """The LOVA program, loaded once; every tick and frame is one call into it."""

    NAMES = ("new", "tick", "input", "frame", "coins", "resets", "where")

    def __init__(self, native: str = "auto") -> None:
        tree, _report = build(SOURCE)
        self.session = open_session(tree, native, max_steps=BUDGET,
                                    max_depth=10_000)
        if self.session is not None:
            # A session in a native runtime: the world is a handle and
            # the session carries `steps` of the last call, which is
            # what the window reads off `rt`.
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
        # Steps start at zero for every call, and so does the `hot`
        # interval (`mark` / `current`), as the session protocol's
        # `call` does: with `mark` left at its post-load value a step
        # trap's attribution went negative (found at Q126).
        self.rt.steps = 0
        self.rt.mark = 0
        self.rt.current = None
        fn = self.fn[name]
        for arg in args:
            fn = _call(fn, arg, self.rt)
        return fn

    def new_game(self):
        return self.fn["new"]

    def tick(self, world, keys):
        """One sixtieth of a second: `keys` is the set of names held, and
        `jump` is in it only on the tick space went down."""
        held = self.call("input",
                         (1 if "d" in keys else 0) - (1 if "a" in keys else 0),
                         (1 if "s" in keys else 0) - (1 if "w" in keys else 0),
                         1 if "jump" in keys else 0,
                         (1 if "Right" in keys else 0) - (1 if "Left" in keys else 0),
                         (1 if "Down" in keys else 0) - (1 if "Up" in keys else 0),
                         (1 if "minus" in keys else 0) - (1 if "plus" in keys else 0))
        world = self.call("tick", world, held)
        if isinstance(held, Ref):
            # The input record never leaves this method: a handle the
            # driver does not release is kept for the life of the
            # session, and this one is sixty a second.
            self.session.release(held)
        return world

    def frame(self, world):
        return list_to_python(self.call("frame", world, FOCAL, VIEW_W, VIEW_H, FAR))


class Game:
    """The window: keys in, polygons out."""

    def __init__(self, master, rules: Rules) -> None:
        import tkinter as tk
        self.tk = tk
        self.master = master
        self.rules = rules
        self.canvas = tk.Canvas(master, width=VIEW_W, height=VIEW_H, bg=SKY,
                                highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(master, anchor="w", bg="#0e1116", fg="#c8d2de",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.world = rules.new_game()
        self.keys: set = set()
        self.jump_pending = False
        self.anomaly = None
        self.clock = time.perf_counter()
        self.behind = 0.0
        self.tick_ms = self.frame_ms = 0.0
        self.tick_steps = self.frame_steps = 0
        self.ticks = 0
        master.bind("<KeyPress>", self.on_press)
        master.bind("<KeyRelease>", self.on_release)
        master.after(10, self.loop)

    # --- input -----------------------------------------------------------

    KEYS = {"w": "w", "a": "a", "s": "s", "d": "d", "Up": "Up", "Down": "Down",
            "Left": "Left", "Right": "Right", "plus": "plus", "equal": "plus",
            "KP_Add": "plus", "minus": "minus", "KP_Subtract": "minus"}

    def on_press(self, event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key == "space":
            if "space" not in self.keys:
                self.jump_pending = True
            self.keys.add("space")
        elif key in ("r", "R"):
            self.world = self.rules.new_game()
            self.anomaly = None
        elif key in self.KEYS:
            self.keys.add(self.KEYS[key])

    def on_release(self, event) -> None:
        key = event.keysym
        if key == "space":
            self.keys.discard("space")
        elif key in self.KEYS:
            self.keys.discard(self.KEYS[key])

    # --- the loop --------------------------------------------------------

    def loop(self) -> None:
        now = time.perf_counter()
        self.behind += now - self.clock
        self.clock = now
        ran = 0
        if self.anomaly is None:
            try:
                while self.behind >= TICK and ran < MAX_CATCHUP:
                    keys = set(self.keys)
                    if self.jump_pending:
                        keys.add("jump")
                        self.jump_pending = False
                    t0 = time.perf_counter()
                    self.world = self.rules.tick(self.world, keys)
                    self.tick_ms = (time.perf_counter() - t0) * 1000
                    self.tick_steps = self.rules.rt.steps
                    self.behind -= TICK
                    ran += 1
                    self.ticks += 1
                if self.behind >= TICK:          # too slow to keep up: drop the debt
                    self.behind = 0.0
                # A frame is worth drawing only when something moved.
                # This loop runs every millisecond, and painting on each
                # pass drew the same picture sixty times over -- twenty
                # to thirty milliseconds of it each -- which is the time
                # the ticks then fell behind by.
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
        coins = self.rules.call("coins", self.world)
        resets = self.rules.call("resets", self.world)
        c.create_text(18, 16, anchor="nw", text=f"coins {coins}", fill="#ffffff",
                      font=("Consolas", 22, "bold"))
        if resets:
            c.create_text(18, 52, anchor="nw", text=f"fell {resets}x", fill="#ffe08a",
                          font=("Consolas", 12))
        self.bar.config(
            text=f"tick {self.tick_steps:,} steps / {self.tick_ms:.1f} ms   "
                 f"frame {len(faces)} faces, {self.frame_steps:,} steps / {self.frame_ms:.0f} ms "
                 f"({1000 / max(self.frame_ms + self.tick_ms, 1):.1f} fps)   "
                 f"[WASD walk, space jump, arrows camera, +/- zoom, R restart]")


# --- the same game in an SDL window ------------------------------------------

SKY_RGB = tuple(int(SKY[i:i + 2], 16) for i in (1, 3, 5))


class SdlGame:
    """The window again, drawn by SDL instead of a Tk canvas.

    Nothing about the game changes: the same `Rules`, the same keys, the
    same sixtieth-of-a-second cadence with the same catch-up bound.  What
    changes is the surface -- `pygame.draw.polygon` into a buffer that is
    flipped once, where the canvas deleted and re-created a few hundred
    items every frame.
    """

    TITLE = "platformer -- the window is Python, the game is LOVA"

    KEYS = None                      # filled in once pygame is imported

    def __init__(self, rules: Rules, bench: int = 0) -> None:
        from apps.sdlhost import Stats, Window
        self.rules = rules
        self.win = Window(self.TITLE, VIEW_W, VIEW_H, SKY_RGB)
        pg = self.win.pg
        self.pg = pg
        self.KEYS = {pg.K_w: "w", pg.K_a: "a", pg.K_s: "s", pg.K_d: "d",
                     pg.K_UP: "Up", pg.K_DOWN: "Down", pg.K_LEFT: "Left",
                     pg.K_RIGHT: "Right", pg.K_PLUS: "plus", pg.K_EQUALS: "plus",
                     pg.K_KP_PLUS: "plus", pg.K_MINUS: "minus",
                     pg.K_KP_MINUS: "minus"}
        self.coin_font = self.win.font(24, bold=True)
        self.fell_font = self.win.font(14)
        self.world = rules.new_game()
        self.keys: set = set()
        self.jump_pending = False
        self.anomaly = None
        self.running = True
        self.behind = 0.0
        self.tick_ms = self.frame_ms = self.draw_ms = self.flip_ms = 0.0
        self.pass_ms = 1000 / 60
        self.tick_steps = self.frame_steps = 0
        self.faces: list = []
        self.bench = bench
        self.stats = Stats()

    # --- input -----------------------------------------------------------

    def events(self) -> None:
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    self.running = False
                elif event.key == pg.K_SPACE:
                    if "space" not in self.keys:
                        self.jump_pending = True
                    self.keys.add("space")
                elif event.key == pg.K_r:
                    self.world = self.rules.new_game()
                    self.anomaly = None
                elif event.key in self.KEYS:
                    self.keys.add(self.KEYS[event.key])
            elif event.type == pg.KEYUP:
                if event.key == pg.K_SPACE:
                    self.keys.discard("space")
                elif event.key in self.KEYS:
                    self.keys.discard(self.KEYS[event.key])

    def script(self, frame: int) -> None:
        """`--bench`: walk, turn the camera and jump, with no one at the keys."""
        self.keys = {"d", "w"} if frame % 120 < 60 else {"a", "Right"}
        if frame % 40 == 0:
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
                    while self.behind >= TICK and ran < MAX_CATCHUP:
                        keys = set(self.keys)
                        if self.jump_pending:
                            keys.add("jump")
                            self.jump_pending = False
                        t0 = time.perf_counter()
                        self.world = self.rules.tick(self.world, keys)
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
            self.stats.report("platformer", extra=self.win.vsync_note())
        self.win.close()
        return 0

    def paint(self, tick_ms: float) -> None:
        win = self.win
        t0 = time.perf_counter()
        self.faces = [list_to_python(f) for f in self.rules.frame(self.world)]
        self.frame_steps = self.rules.rt.steps
        self.frame_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        win.fill_sky()
        win.faces(self.faces)
        coins = self.rules.call("coins", self.world)
        resets = self.rules.call("resets", self.world)
        win.text(f"coins {coins}", 18, 16, (255, 255, 255), self.coin_font)
        if resets:
            win.text(f"fell {resets}x", 18, 52, (0xff, 0xe0, 0x8a), self.fell_font)
        if self.anomaly is not None:
            win.bar(f"the rules faulted: {self.anomaly.get('kind')}")
        else:
            win.bar(
                f"tick {self.tick_steps:,} steps / {self.tick_ms:.1f} ms   "
                f"frame {len(self.faces)} faces, {self.frame_steps:,} steps / "
                f"{self.frame_ms:.1f} ms   "
                f"({1000 / max(self.pass_ms, 1e-9):.0f} fps)   "
                f"[WASD walk, space jump, arrows camera, +/- zoom, R restart]")
        self.draw_ms = (time.perf_counter() - t1) * 1000
        self.flip_ms = win.flip()


# --- a frame with no window --------------------------------------------------

def rasterise(faces, w, h, sky=(0x8f, 0xb8, 0xe8)):
    """The faces painted into an RGB buffer, in the order given."""
    px = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            px[(y * w + x) * 3:(y * w + x) * 3 + 3] = bytes(sky)
    for f in faces:
        u0, v0, u1, v1, u2, v2, k, l = f
        r, g, b = (max(0, min(255, (k >> s & 255) * l // 1024)) for s in (16, 8, 0))
        pts = sorted(((u0, v0), (u1, v1), (u2, v2)), key=lambda p: p[1])
        (xa, ya), (xb, yb), (xc, yc) = pts
        for y in range(max(0, ya), min(h - 1, yc) + 1):
            # the long edge a-c and the short one a-b or b-c
            if yc == ya:
                xs = [xa, xb, xc]
            else:
                xl = xa + (xc - xa) * (y - ya) / (yc - ya)
                if y < yb and yb != ya:
                    xr = xa + (xb - xa) * (y - ya) / (yb - ya)
                elif yc != yb:
                    xr = xb + (xc - xb) * (y - yb) / (yc - yb)
                else:
                    xr = xb
                xs = [xl, xr]
            lo, hi = int(min(xs)), int(max(xs))
            for x in range(max(0, lo), min(w - 1, hi) + 1):
                i = (y * w + x) * 3
                px[i] = r
                px[i + 1] = g
                px[i + 2] = b
    return px


def write_png(path, px, w, h):
    raw = b"".join(b"\x00" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(kind, body):
        return (len(body).to_bytes(4, "big") + kind + body
                + zlib.crc32(kind + body).to_bytes(4, "big"))
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    Path(path).write_bytes(data)


def shot(rules: Rules, path: str, script=None) -> None:
    """Play `script` -- (ticks, keys) pairs -- with no window, then write
    one frame.  The default walks onto the level and jumps for a coin."""
    world = rules.new_game()
    # W and A together walk straight along -x under the kit's 45 degree
    # camera: onto the medium platform three metres over, through its
    # coin, and a jump toward the brick above it
    script = script or [(60, set()), (44, {"a", "w"}), (20, set()), (1, {"jump"}), (14, set())]
    for ticks, keys in script:
        for _ in range(ticks):
            world = rules.tick(world, keys)
    t0 = time.perf_counter()
    faces = [list_to_python(f) for f in rules.frame(world)]
    steps = rules.rt.steps
    write_png(path, rasterise(faces, VIEW_W, VIEW_H), VIEW_W, VIEW_H)
    x, y, z = (v / F for v in list_to_python(rules.call("where", world)))
    print(f"{path}: {len(faces)} faces, {steps:,} LOVA steps in "
          f"{(time.perf_counter() - t0) * 1000:.0f} ms; the player at "
          f"({x:.2f}, {y:.2f}, {z:.2f}) with {rules.call('coins', world)} coin(s)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kenney's 3D platformer: the window is Python, the game "
                    "is LOVA")
    parser.add_argument("--shot", metavar="file.png",
                        help="no window: play the script and write one frame")
    parser.add_argument("--native", choices=("auto", "on", "off"),
                        default="auto",
                        help="run the game in a native runtime (auto: if "
                             "there is one and it takes this program)")
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
    root.title("platformer -- the window is Python, the game is LOVA")
    root.configure(bg="#0e1116")
    root.resizable(False, False)
    Game(root, rules)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
