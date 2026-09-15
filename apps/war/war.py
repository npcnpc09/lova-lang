"""A window in Python, the battlefield in LOVA.

    python apps/war/war.py

An isometric battlefield: a height field lit by a sun, with water,
sand, grass, rock, snow, woods and boulders on it, and two sides
fighting over it.  Everything that decides -- the shape of the land,
what each cell is made of, how the light falls on it, what stands on
it, where a soldier may walk, where he walks next, who he fights, when
he dies, and which cell you just clicked on -- is `lib/war.lova`.  This
shell owns the window, the clock, the mouse and the colours, and
nothing else.

LOVA has no floating point.  The terrain is integers throughout: value
noise read off a hashed lattice, an isometric projection, and a surface
normal dotted with a sun direction over its own length (`isqrt`) for
the light.  It is the same `lib/fixed.lova` that the first-person maze
next door casts its rays with.

The ground is asked for once -- 1 300 cells, about 1.6 million steps --
because the camera does not turn, so panning an isometric projection is
a translation and the picture can be drawn into a scrolling canvas and
left there.  Only the soldiers are recomputed, once a tick, at about
7 000 steps for the twelve of them.

Left-click picks a soldier of yours, drag pans, right-click sends the
ones you have picked.  A: all of them.  R: another battle.  The red
side comes looking for you whatever you do.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

SOURCE = """\
(use "war")
(rec ground terrain new new-war tick tick spr sprites
     left standing select select all select-all order order)
"""

VIEW_W, VIEW_H = 1000, 620
BUDGET = 20_000_000
TICK_MS = 100

# What a cell is made of -> its colour in full light.
GROUND = {0: (26, 58, 104),      # deep water
          1: (44, 102, 148),     # shallow water
          2: (206, 186, 126),    # sand
          3: (86, 140, 58),      # grass
          4: (58, 104, 48),      # the dark grass of the uplands
          5: (124, 116, 102),    # rock
          6: (234, 240, 244)}    # snow

TRUNK = (78, 56, 36)
LEAF = (42, 92, 44)
LEAF_HI = (64, 122, 58)
STONE = (136, 132, 124)
SKIN = (222, 184, 146)

TEAM = {0: ((78, 126, 226), (38, 74, 158)),     # yours
        1: ((214, 74, 58), (140, 36, 30))}      # theirs


def shade(rgb, k):
    """`rgb` under light `k`, where 900 is full sun."""
    k = max(120, min(1400, k))
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * k // 900)) for c in rgb)


def rgb(c):
    return "#%02x%02x%02x" % c


class Rules:
    """The LOVA program, loaded once; every tick is a call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.build_steps = self.rt.steps
        self.fn = {name: api.entries[_map_key(name, "rec")][1]
                   for name in ("ground", "new", "tick", "spr", "left",
                                "select", "all", "order")}
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

    def call(self, name, *args):
        self.rt.steps = 0
        fn = self.fn[name]
        for arg in args:
            fn = _call(fn, arg, self.rt)
        return fn

    @staticmethod
    def field(value, name: str):
        return value.entries[_map_key(name, "get")][1]

    def fields(self, value, *names):
        return [self.field(value, n) for n in names]


class Battlefield(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules) -> None:
        super().__init__(master, bg="#0a0c10")
        self.rules = rules
        # the same colour the water is drawn in, so the sea does not stop
        # at the edge of the map
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H,
                                bg=shade(GROUND[0], 690), highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(self, anchor="w", bg="#0a0c10", fg="#c8d0da",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.bar.config(text="making the map ...")
        self.update_idletasks()
        self.anomaly = None
        self.tick_steps = 0
        self.dragged = False
        self.ground()
        self.world = self.rules.call("new", 1)
        master.bind("<KeyPress>", self.on_key)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.on_order)
        self.paint()
        self.after(TICK_MS, self.tick)

    # --- the ground, drawn once ------------------------------------------

    def ground(self) -> None:
        cells = list_to_python(self.rules.call("ground"))
        c = self.canvas
        for cell in cells:
            u0, v0, u1, v1, u2, v2, u3, v3, t, l, d, s = self.rules.fields(
                cell, "u0", "v0", "u1", "v1", "u2", "v2", "u3", "v3", "t", "l", "d", "s")
            fill = shade(GROUND[t], l)
            # the outline is the fill: without it the rounding between two
            # quads shows as a hairline of the background
            c.create_polygon(u0, v0, u1, v1, u2, v2, u3, v3, fill=fill, outline=fill)
            if d:
                mx = (u0 + u2) // 2
                my = (v0 + v1 + v2 + v3) // 4
                (self.tree if d == 1 else self.boulder)(mx, my, s, l)
        self.cells = len(cells)
        bounds = c.bbox("all")
        c.config(scrollregion=(bounds[0] - 40, bounds[1] - 40, bounds[2] + 40, bounds[3] + 40))
        c.xview_moveto(0.24)
        c.yview_moveto(0.18)

    def tree(self, x: int, y: int, size: int, l: int) -> None:
        c = self.canvas
        h = 16 * size // 1000
        c.create_polygon(x - 2, y, x + 2, y, x + 2, y - h, x - 2, y - h,
                         fill=shade(TRUNK, l), outline="")
        for i in range(3):
            top = y - h - 11 * size // 1000 * (2 - i) // 2
            spread = 6 + 3 * i
            c.create_polygon(x, top - 15 * size // 1000,
                             x + spread, top + 5, x, top + 8, x - spread, top + 5,
                             fill=shade(LEAF_HI if i == 2 else LEAF, l + 30 * i), outline="")

    def boulder(self, x: int, y: int, size: int, l: int) -> None:
        r = 7 * size // 1000
        self.canvas.create_polygon(x - r, y, x - r // 2, y - r, x + r // 2, y - r,
                                   x + r, y, x + r // 2, y + r // 3, x - r // 2, y + r // 3,
                                   fill=shade(STONE, l), outline="")

    # --- the soldiers, redrawn every tick --------------------------------

    def soldier(self, u: int, v: int, team: int, hp: int, sel: int, fire: int) -> None:
        c = self.canvas
        body, dark = TEAM[team]
        c.create_oval(u - 7, v - 3, u + 7, v + 3, fill="#1d2a1c", outline="", tags="unit")
        if sel:
            c.create_oval(u - 11, v - 5, u + 11, v + 5, outline="#7ff07f", width=2, tags="unit")
        c.create_line(u - 3, v, u - 3, v - 7, fill=rgb(dark), width=3, tags="unit")
        c.create_line(u + 3, v, u + 3, v - 7, fill=rgb(dark), width=3, tags="unit")
        c.create_polygon(u - 6, v - 6, u + 6, v - 6, u + 5, v - 16, u - 5, v - 16,
                         fill=rgb(body), outline=rgb(dark), tags="unit")
        c.create_oval(u - 4, v - 23, u + 4, v - 15, fill=rgb(SKIN), outline="", tags="unit")
        c.create_arc(u - 5, v - 25, u + 5, v - 16, start=0, extent=180,
                     fill=rgb(dark), outline="", tags="unit")
        # the spear, and the flash of it landing
        c.create_line(u + 7, v - 2, u + 9, v - 24, fill="#6b5436", width=2, tags="unit")
        if fire:
            c.create_line(u + 9, v - 24, u + 15, v - 12, fill="#ffe066", width=3, tags="unit")
        if hp < 100 or sel:
            w = 20 * hp // 100
            c.create_rectangle(u - 10, v - 31, u + 10, v - 27, fill="#20241c",
                               outline="#0d0f0b", tags="unit")
            c.create_rectangle(u - 10, v - 31, u - 10 + w, v - 27,
                               fill="#5fd45f" if hp > 50 else "#e0a03c" if hp > 25 else "#e04c3c",
                               outline="", tags="unit")

    def paint(self) -> None:
        c = self.canvas
        c.delete("unit")
        if self.anomaly is None:
            for s in list_to_python(self.rules.call("spr", self.world)):
                self.soldier(*self.rules.fields(s, "u", "v", "t", "hp", "s", "f"))
            blue = self.rules.call("left", self.world, 0)
            red = self.rules.call("left", self.world, 1)
            over = ("  --  you hold the field, R for another" if not red else
                    "  --  your side is gone, R for another" if not blue else "")
            self.bar.config(
                text=f"yours {blue}   theirs {red}   "
                     f"tick {self.rules.field(self.world, 'turn')}   "
                     f"LOVA steps: {self.rules.build_steps:,} for the map, "
                     f"{self.tick_steps:,} the tick"
                     f"   left-click picks, right-click sends, A all, R again{over}")
        else:
            self.bar.config(text=f"the rules faulted: {self.anomaly.get('kind')} "
                                 f"{self.anomaly.get('repair') or ''}")

    # --- the loop --------------------------------------------------------

    def tick(self) -> None:
        if self.anomaly is None:
            try:
                self.world = self.rules.call("tick", self.world)
                self.tick_steps = self.rules.rt.steps
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": "error",
                                                                 "repair": str(exc)}
        self.paint()
        self.after(TICK_MS, self.tick)

    # --- the mouse and the keys ------------------------------------------

    def on_press(self, event: tk.Event) -> None:
        self.dragged = False
        self.press = (event.x, event.y)
        self.canvas.scan_mark(event.x, event.y)

    def on_drag(self, event: tk.Event) -> None:
        if abs(event.x - self.press[0]) + abs(event.y - self.press[1]) > 4:
            self.dragged = True
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_release(self, event: tk.Event) -> None:
        if self.dragged or self.anomaly is not None:
            return
        self.world = self.rules.call("select", self.world,
                                     int(self.canvas.canvasx(event.x)),
                                     int(self.canvas.canvasy(event.y)))
        self.paint()

    def on_order(self, event: tk.Event) -> None:
        if self.anomaly is not None:
            return
        self.world = self.rules.call("order", self.world,
                                     int(self.canvas.canvasx(event.x)),
                                     int(self.canvas.canvasy(event.y)))
        self.paint()

    def on_key(self, event: tk.Event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key in ("a", "A"):
            self.world = self.rules.call("all", self.world)
            self.paint()
        elif key in ("r", "R"):
            self.anomaly = None
            self.world = self.rules.call("new", 1)
            self.paint()
        elif key in ("Left", "Right"):
            self.canvas.xview_scroll(-3 if key == "Left" else 3, "units")
        elif key in ("Up", "Down"):
            self.canvas.yview_scroll(-3 if key == "Up" else 3, "units")


def main() -> int:
    rules = Rules()
    root = tk.Tk()
    root.title("war -- the window is Python, the battlefield is LOVA")
    root.configure(bg="#0a0c10")
    root.resizable(False, False)
    field = Battlefield(root, rules)
    field.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
