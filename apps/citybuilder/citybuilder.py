"""A window in Python, the city in LOVA: Kenney's city builder.

    python apps/citybuilder/citybuilder.py            # the kit's sample city
    python apps/citybuilder/citybuilder.py --empty    # a clean grid and 10 000
    python apps/citybuilder/citybuilder.py --shot apps/citybuilder/screenshot.png

A port of KenneyNL/Starter-Kit-City-Builder (MIT, ~1 500 stars): a
grid to place fifteen kinds of structure on -- roads, pavements, four
small buildings, a garage, grass and trees -- a till that pays for each,
a cursor that follows the mouse across the ground, and a camera that
pans, turns under the middle button and zooms in steps.  Everything
that decides is `lib/citybuilder.lova`, written against the kit's
`builder.gd` and `view.gd` and checked against a transliteration of
them in `tests/test_citybuilder.py` -- including what a click means,
which is the mouse carried back through the camera to the ground.
Every number in the picture is `lib/scene3d.lova`; the models, the
prices and the sample city are the kit's own, read out of it (the
sample city out of a Godot binary resource) by `import_kit.py`.  This
shell owns the window, the mouse, the keys, the clock and the save
file.

The kit's keys: WASD pan, F back to the centre, the middle button held
turns the camera, the wheel zooms, left click builds, right click
turns the structure, Delete removes, Q and E cycle the catalogue, F1
saves, F2 loads, F3 loads the sample city, Escape leaves.  The city is
only drawn again when the camera or a cell has moved -- a hundred and
twenty cells are some thousands of triangles, seconds of CPython --
and the cursor's preview, which follows the mouse, is drawn over the
kept picture on its own, so the window is quiet while you look and
busy while you pan.
`--shot file.png` draws one frame with no window at all.

There are two windows for the same city.  `--host sdl` (the default
where pygame is installed) keeps the city in a surface of its own and
blits it, drawing only the cursor's dozen faces afresh: sixty frames a
second while you look, and nine while you pan, three quarters of which
is `frame-city` in LOVA.  `--host tk` is the original canvas, which
deleted and re-created every one of the city's two and a half thousand
polygons whenever the camera moved.  Nothing else differs.  `--bench
N` pans, stands still and pans back, and prints what each part of a
frame cost.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.native import Ref, open_session
from core.runtime import Runtime, _call, _map_key, evaluate
from core.runtime import list_to_python as _list_to_python

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platformer"))
from platformer import rasterise, write_png  # noqa: E402


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
(use "citybuilder")
(rec new new-game sample sample-game tick tick input input frame frame
     city frame-city cursor frame-cursor ckey city-key ukey cursor-key
     cells city-cells key view-key
     cash (lambda w (get w cash))
     index (lambda w (get w index))
     name (lambda w (name-of (get w index)))
     price (lambda w (price-of (get w index)))
     load (lambda w (lambda cells
             (put w city (fold (lambda m (lambda c
                                 (map-put m (cell-key (nth c 0) (nth c 1))
                                          (rec s (nth c 2) q (nth c 3)))))
                               (nil) cells)))))
"""

VIEW_W, VIEW_H = 960, 600
FOCAL = 391                      # the kit's camera: the default 75 degree field of view
FAR = 60 * 1024
BUDGET = 200_000_000
TICK = 1 / 60
SAVE = Path(__file__).with_name("map.json")
SKY = "#9fc2e6"


def lit(k, l):
    r, g, b = k >> 16 & 255, k >> 8 & 255, k & 255
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * l // 1024)) for c in (r, g, b))


class Rules:
    NAMES = ("new", "sample", "tick", "input", "frame", "city", "cursor",
             "ckey", "ukey", "cells", "key", "cash", "index", "name",
             "price", "load")

    def __init__(self, native: str = "auto") -> None:
        tree, _report = build(SOURCE)
        self.session = open_session(tree, native, max_steps=BUDGET,
                                    max_depth=10_000)
        if self.session is not None:
            # A session in a native runtime: the city is a handle and
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

    def tick(self, world, ev):
        """One sixtieth of a second.  `ev` is what happened: held pan
        keys, mouse travel under the middle button, wheel notches,
        the buttons that went down, and where the mouse is."""
        held = self.call("input",
                         (1 if "d" in ev["keys"] else 0) - (1 if "a" in ev["keys"] else 0),
                         (1 if "s" in ev["keys"] else 0) - (1 if "w" in ev["keys"] else 0),
                         ev.get("rot", 0), ev.get("zoom", 0), ev.get("centre", 0),
                         ev.get("build", 0), ev.get("demolish", 0), ev.get("rotate", 0),
                         ev.get("next", 0), ev.get("prev", 0),
                         ev.get("mu", -1), ev.get("mv", -1))
        world = self.call("tick", world, held, FOCAL, VIEW_W, VIEW_H)
        if isinstance(held, Ref):
            # The input record never leaves this method, and a handle
            # the driver does not release is kept for the life of the
            # session -- this one would be sixty a second.
            self.session.release(held)
        return world

    def frame(self, world, which="frame"):
        return [list_to_python(f) for f in
                list_to_python(self.call(which, world, FOCAL, VIEW_W, VIEW_H, FAR))]

    def keys_of(self, world):
        return (list_to_python(self.call("ckey", world)), list_to_python(self.call("ukey", world)))

    def cells(self, world):
        return [list_to_python(c) for c in list_to_python(self.call("cells", world))]

    def view_key(self, world):
        return list_to_python(self.call("key", world))

    def text(self, world):
        return str(self.call("name", world))


class City:
    def __init__(self, master, rules: Rules, world) -> None:
        import tkinter as tk
        self.master = master
        self.rules = rules
        self.world = world
        self.canvas = tk.Canvas(master, width=VIEW_W, height=VIEW_H, bg=SKY,
                                highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(master, anchor="w", bg="#0e1116", fg="#c8d2de",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.keys: set = set()
        self.pending: dict = {}
        self.mouse = (-1, -1)
        self.middle = None
        self.anomaly = None
        self.last_key = (None, None)
        self.city_faces: list = []
        self.city_steps = 0
        self.city_ms = 0.0
        self.clock = time.perf_counter()
        self.behind = 0.0
        self.frame_ms = 0.0
        self.frame_steps = 0
        self.faces = 0
        master.bind("<KeyPress>", self.on_press)
        master.bind("<KeyRelease>", self.on_release)
        c = self.canvas
        c.bind("<Motion>", self.on_motion)
        c.bind("<ButtonPress-1>", lambda e: self.pending.__setitem__("build", 1))
        c.bind("<ButtonPress-3>", lambda e: self.pending.__setitem__("rotate", 1))
        c.bind("<ButtonPress-2>", self.on_middle)
        c.bind("<B2-Motion>", self.on_middle_drag)
        c.bind("<ButtonRelease-2>", lambda e: setattr(self, "middle", None))
        c.bind("<MouseWheel>", self.on_wheel)
        master.after(10, self.loop)

    # --- input -----------------------------------------------------------

    def on_press(self, event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key in ("w", "a", "s", "d", "W", "A", "S", "D"):
            self.keys.add(key.lower())
        elif key in ("f", "F"):
            self.pending["centre"] = 1
        elif key in ("e", "E"):
            self.pending["next"] = 1
        elif key in ("q", "Q"):
            self.pending["prev"] = 1
        elif key == "Delete":
            self.pending["demolish"] = 1
        elif key == "F1":
            SAVE.write_text(json.dumps({"cash": self.rules.call("cash", self.world),
                                        "cells": self.rules.cells(self.world)}))
        elif key == "F2":
            if SAVE.exists():
                saved = json.loads(SAVE.read_text())
                from core.runtime import Cons, NIL_VALUE
                cells = NIL_VALUE
                for c in reversed(saved["cells"]):
                    row = NIL_VALUE
                    for v in reversed(c):
                        row = Cons(v, row)
                    cells = Cons(row, cells)
                self.world = self.rules.call("load", self.rules.fn["new"], cells)
        elif key == "F3":
            self.world = self.rules.fn["sample"]

    def on_release(self, event) -> None:
        self.keys.discard(event.keysym.lower())

    def on_motion(self, event) -> None:
        self.mouse = (event.x, event.y)

    def on_middle(self, event) -> None:
        self.middle = event.x

    def on_middle_drag(self, event) -> None:
        if self.middle is not None:
            self.pending["rot"] = self.pending.get("rot", 0) + (event.x - self.middle)
            self.middle = event.x
        self.mouse = (event.x, event.y)

    def on_wheel(self, event) -> None:
        self.pending["zoom"] = self.pending.get("zoom", 0) + (-1 if event.delta > 0 else 1)

    # --- the loop --------------------------------------------------------

    def loop(self) -> None:
        now = time.perf_counter()
        self.behind += now - self.clock
        self.clock = now
        if self.anomaly is None:
            try:
                ran = 0
                while self.behind >= TICK and ran < 4:
                    ev = dict(self.pending, keys=set(self.keys), mu=self.mouse[0], mv=self.mouse[1])
                    self.pending = {}
                    self.world = self.rules.tick(self.world, ev)
                    self.behind -= TICK
                    ran += 1
                if self.behind >= TICK:
                    self.behind = 0.0
                # Only a tick can move the view, and this loop runs
                # every millisecond: asking the rules for the view key
                # on every pass was a thousand calls a second for an
                # answer that changes sixty times at most.
                if ran:
                    key = self.rules.keys_of(self.world)
                    if key != self.last_key:
                        self.paint(key[0] != self.last_key[0])
                        self.last_key = key
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
                self.bar.config(text=f"the rules faulted: {self.anomaly.get('kind')}")
        self.master.after(1, self.loop)

    def paint(self, city_moved: bool) -> None:
        """The city's faces are kept from frame to frame while only the
        cursor moves; the cursor's are always drawn afresh, over them."""
        c = self.canvas
        if city_moved or not self.city_faces:
            t0 = time.perf_counter()
            self.city_faces = self.rules.frame(self.world, "city")
            self.city_steps = self.rules.rt.steps
            self.city_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        cursor = self.rules.frame(self.world, "cursor")
        cursor_ms = (time.perf_counter() - t0) * 1000
        c.delete("all")
        for u0, v0, u1, v1, u2, v2, k, l in self.city_faces + cursor:
            fill = lit(k, l)
            c.create_polygon(u0, v0, u1, v1, u2, v2, fill=fill, outline=fill)
        cash = self.rules.call("cash", self.world)
        c.create_text(18, 16, anchor="nw", text=f"${cash}", fill="#ffffff",
                      font=("Consolas", 22, "bold"))
        c.create_text(18, VIEW_H - 30, anchor="nw",
                      text=f"{self.rules.text(self.world)}  ${self.rules.call('price', self.world)}"
                           "   [Q/E change, right-click turn, click build, Delete remove]",
                      fill="#ffffff", font=("Consolas", 12))
        self.bar.config(
            text=f"city {len(self.city_faces)} faces, {self.city_steps:,} LOVA steps / "
                 f"{self.city_ms:.0f} ms   cursor {len(cursor)} faces / {cursor_ms:.0f} ms   "
                 f"[WASD pan, middle-drag turn, wheel zoom, F centre, F1 save, F2 load, F3 sample]")


# --- the same city in an SDL window ------------------------------------------

SKY_RGB = tuple(int(SKY[i:i + 2], 16) for i in (1, 3, 5))


class SdlCity:
    """The city again, drawn by SDL instead of a Tk canvas.

    The rules, the keys and the mouse are the Tk window's; so is what
    makes the city worth drawing again -- the camera or a cell moving,
    which `city-key` says and `cursor-key` says separately.  Here the
    kept city is drawn once into a surface of its own and blitted, and
    only the cursor's dozen faces are drawn afresh: a pan costs the city
    a redraw, and looking around costs a blit.
    """

    TITLE = "city builder -- the window is Python, the city is LOVA"

    def __init__(self, rules: Rules, world, bench: int = 0) -> None:
        from apps.sdlhost import Stats, Window
        self.rules = rules
        self.world = world
        self.win = Window(self.TITLE, VIEW_W, VIEW_H, SKY_RGB)
        pg = self.win.pg
        self.pg = pg
        self.cash_font = self.win.font(24, bold=True)
        self.line_font = self.win.font(14)
        self.city = pg.Surface((VIEW_W, VIEW_H))
        self.city.fill(SKY_RGB)
        self.city_faces: list = []
        self.cursor_faces: list = []
        self.keys: set = set()
        self.pending: dict = {}
        self.mouse = (-1, -1)
        self.middle = None
        self.anomaly = None
        self.running = True
        self.last_key = (None, None)
        self.hud = ("", "")
        self.behind = 0.0
        self.city_ms = self.cursor_ms = self.tick_ms = 0.0
        self.draw_ms = self.flip_ms = self.city_draw_ms = 0.0
        self.pass_ms = 1000 / 60
        self.city_steps = 0
        self.bench = bench
        self.stats = Stats()

    # --- input -----------------------------------------------------------

    def events(self) -> None:
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
                self.key(event.key)
            elif event.type == pg.KEYUP:
                if event.key in (pg.K_w, pg.K_a, pg.K_s, pg.K_d):
                    self.keys.discard(pg.key.name(event.key))
            elif event.type == pg.MOUSEMOTION:
                if event.pos[1] < VIEW_H:
                    self.mouse = event.pos
                if self.middle is not None:
                    self.pending["rot"] = self.pending.get("rot", 0) + (event.pos[0] - self.middle)
                    self.middle = event.pos[0]
            elif event.type == pg.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.pending["build"] = 1
                elif event.button == 3:
                    self.pending["rotate"] = 1
                elif event.button == 2:
                    self.middle = event.pos[0]
            elif event.type == pg.MOUSEBUTTONUP and event.button == 2:
                self.middle = None
            elif event.type == pg.MOUSEWHEEL:
                # the kit zooms in a notch on a wheel up, as the Tk window does
                self.pending["zoom"] = self.pending.get("zoom", 0) + (-1 if event.y > 0 else 1)

    def key(self, key) -> None:
        pg = self.pg
        if key == pg.K_ESCAPE:
            self.running = False
        elif key in (pg.K_w, pg.K_a, pg.K_s, pg.K_d):
            self.keys.add(pg.key.name(key))
        elif key == pg.K_f:
            self.pending["centre"] = 1
        elif key == pg.K_e:
            self.pending["next"] = 1
        elif key == pg.K_q:
            self.pending["prev"] = 1
        elif key == pg.K_DELETE:
            self.pending["demolish"] = 1
        elif key == pg.K_F1:
            SAVE.write_text(json.dumps({"cash": self.rules.call("cash", self.world),
                                        "cells": self.rules.cells(self.world)}))
        elif key == pg.K_F2:
            if SAVE.exists():
                saved = json.loads(SAVE.read_text())
                from core.runtime import Cons, NIL_VALUE
                cells = NIL_VALUE
                for c in reversed(saved["cells"]):
                    row = NIL_VALUE
                    for v in reversed(c):
                        row = Cons(v, row)
                    cells = Cons(row, cells)
                self.world = self.rules.call("load", self.rules.fn["new"], cells)
        elif key == pg.K_F3:
            self.world = self.rules.fn["sample"]

    def script(self, frame: int) -> None:
        """`--bench`: pan, turn and look around, with no one at the keys.

        A pan moves the camera every tick, which is the city's worst
        case -- every face of it computed and drawn again.
        """
        block = frame // 30 % 4
        # a pan, then a still camera with the mouse moving, then the
        # pan back: the city's two regimes, which the report separates
        self.keys = ({"d"}, set(), {"a"}, set())[block]
        self.mouse = (300 + (frame * 7) % 360, 200 + (frame * 5) % 240)
        if frame % 90 == 45:
            self.pending["rot"] = 12
        if frame % 150 == 75:
            self.pending["zoom"] = 1 if (frame // 150) % 2 else -1

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
            built = "build" in self.pending or "demolish" in self.pending
            if self.anomaly is None:
                try:
                    while self.behind >= TICK and ran < 4:
                        ev = dict(self.pending, keys=set(self.keys),
                                  mu=self.mouse[0], mv=self.mouse[1])
                        self.pending = {}
                        t0 = time.perf_counter()
                        self.world = self.rules.tick(self.world, ev)
                        self.tick_ms = (time.perf_counter() - t0) * 1000
                        tick_ms += self.tick_ms
                        self.behind -= TICK
                        ran += 1
                    if self.behind >= TICK:
                        self.behind = 0.0
                except (BudgetTrap, DeltaTrap, ValueError) as exc:
                    self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
            painted = ran or not self.city_faces
            if painted:
                self.refresh(built)
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
                self.stats.add("lova city", self.city_ms)
                self.stats.add("lova cursor", self.cursor_ms)
                self.stats.add("draw", self.draw_ms)
                self.stats.add("flip", self.flip_ms)
                self.stats.add("total", self.pass_ms)
                self.stats.add("total, the city redrawn" if self.city_ms
                               else "total, the city kept", self.pass_ms)
                self.stats.add("faces", len(self.city_faces) + len(self.cursor_faces))
        if self.bench:
            self.stats.report("citybuilder",
                              order=("total", "total, the city redrawn",
                                     "total, the city kept", "lova tick",
                                     "lova city", "lova cursor", "draw", "flip"),
                              extra=self.win.vsync_note())
        self.win.close()
        return 0

    def refresh(self, built: bool) -> None:
        """What the rules were asked for: the city only when it moved."""
        key = self.rules.keys_of(self.world)
        if key[0] != self.last_key[0] or not self.city_faces:
            t0 = time.perf_counter()
            self.city_faces = self.rules.frame(self.world, "city")
            self.city_steps = self.rules.rt.steps
            self.city_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            self.city.fill(SKY_RGB)
            self.win.faces(self.city_faces, surface=self.city)
            # the city's own polygons, drawn once into a surface of
            # their own: the rest of the frame is a blit of it
            self.city_draw_ms = (time.perf_counter() - t0) * 1000
        else:
            self.city_ms = self.city_draw_ms = 0.0
        if key[1] != self.last_key[1] or not self.cursor_faces:
            t0 = time.perf_counter()
            self.cursor_faces = self.rules.frame(self.world, "cursor")
            self.cursor_ms = (time.perf_counter() - t0) * 1000
        else:
            self.cursor_ms = 0.0
        if key != self.last_key or built or not self.hud[0]:
            self.hud = (f"${self.rules.call('cash', self.world)}",
                        f"{self.rules.text(self.world)}  "
                        f"${self.rules.call('price', self.world)}"
                        "   [Q/E change, right-click turn, click build, Delete remove]")
        self.last_key = key

    def paint(self, tick_ms: float) -> None:
        win = self.win
        t0 = time.perf_counter()
        win.screen.blit(self.city, (0, 0))
        win.faces(self.cursor_faces)
        win.text(self.hud[0], 18, 16, (255, 255, 255), self.cash_font)
        win.text(self.hud[1], 18, VIEW_H - 30, (255, 255, 255), self.line_font)
        if self.anomaly is not None:
            win.bar(f"the rules faulted: {self.anomaly.get('kind')}")
        else:
            win.bar(
                f"city {len(self.city_faces)} faces, {self.city_steps:,} LOVA steps / "
                f"{self.city_ms:.0f} ms   cursor {len(self.cursor_faces)} faces / "
                f"{self.cursor_ms:.1f} ms   ({1000 / max(self.pass_ms, 1e-9):.0f} fps)   "
                f"[WASD pan, middle-drag turn, wheel zoom, F centre, F1 save, F2 load, F3 sample]")
        self.draw_ms = (time.perf_counter() - t0) * 1000 + self.city_draw_ms
        self.flip_ms = win.flip()


def shot(rules: Rules, path: str) -> None:
    world = rules.fn["sample"]
    # the mouse over a cell near the middle, the cursor holding a tree,
    # and the camera settled
    ev = {"keys": set(), "mu": 560, "mv": 330}
    for _ in range(13):
        world = rules.tick(world, dict(ev, next=1))
    for _ in range(3):
        world = rules.tick(world, dict(ev, zoom=-1))
    for _ in range(120):
        world = rules.tick(world, ev)
    t0 = time.perf_counter()
    faces = rules.frame(world)
    steps = rules.rt.steps
    write_png(path, rasterise(faces, VIEW_W, VIEW_H, sky=(0x9f, 0xc2, 0xe6)), VIEW_W, VIEW_H)
    print(f"{path}: {len(faces)} faces, {steps:,} LOVA steps in "
          f"{(time.perf_counter() - t0) * 1000:.0f} ms; {len(rules.cells(world))} cells, "
          f"${rules.call('cash', world)} in the till")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kenney's city builder: the window is Python, the city "
                    "is LOVA")
    parser.add_argument("--shot", metavar="file.png",
                        help="no window: settle the camera and write one frame")
    parser.add_argument("--empty", action="store_true",
                        help="a clean grid and 10 000, not the kit's sample city")
    parser.add_argument("--native", choices=("auto", "on", "off"),
                        default="auto",
                        help="run the city in a native runtime (auto: if "
                             "there is one and it takes this program)")
    parser.add_argument("--host", choices=("auto", "sdl", "tk"), default="auto",
                        help="the window: SDL (pygame, smooth) or the Tk "
                             "canvas (auto: SDL if pygame is installed)")
    parser.add_argument("--bench", type=int, metavar="N", default=0,
                        help="pan the camera for N frames in the SDL window "
                             "and print what each part of a frame cost")
    args = parser.parse_args()
    rules = Rules(native=args.native)
    if args.shot:
        shot(rules, args.shot)
        return 0
    world = rules.fn["new"] if args.empty else rules.fn["sample"]
    from apps.sdlhost import pick_host
    if pick_host("sdl" if args.host == "auto" else args.host) == "sdl":
        return SdlCity(rules, world, bench=args.bench).run()
    import tkinter as tk
    root = tk.Tk()
    root.title("city builder -- the window is Python, the city is LOVA")
    root.configure(bg="#0e1116")
    root.resizable(False, False)
    City(root, rules, world)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
