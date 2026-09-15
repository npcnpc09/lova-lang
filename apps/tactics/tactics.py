"""A window in Python, the battle in LOVA.

    python apps/tactics/tactics.py

A port of the rules of ramaureirac/godot-tactical-rpg (MIT, ~960
stars), a Final-Fantasy-Tactics-shaped demo for Godot.  Everything that
decides is `lib/tactics.lova`, written against that project's GDScript:
the breadth-first flood a pawn's movement makes across blocks it can
climb, the marking of reachable and attackable tiles, damage that is
the attacker's attack power and nothing else, and an opponent that goes
for the tile beside the nearest enemy and then strikes the weakest
thing in reach.  Even what a click *means* is decided there, because it
is a rule.  This shell owns the window, the mouse and the colours.

LOVA has no floating point.  The arena is blocks on an integer grid
drawn in an isometric projection -- the same `lib/fixed.lova` the
first-person maze casts rays with.

Click one of your three (blue) to pick it up: blue tiles are where it
can go, red tiles what it can hit once it has moved.  Space ends your
turn and lets them have theirs, a step every quarter second.  R starts
again.
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
(use "tactics")
(rec new new-battle scene scene pick pick click click
     endturn end-turn ai ai-step done side-done winner winner
     sel (lambda w (get w sel))
     side (lambda w (get w side))
     round (lambda w (get w round))
     msg (lambda w (get w msg))
     left (lambda w (lambda s (len (side-of w s)))))
"""

VIEW_W, VIEW_H = 980, 540
BUDGET = 20_000_000
AI_MS = 260

TW, TH, ZH = 56, 28, 22          # the block sizes lib/tactics.lova projects with

# The ground, by height: a low block is grass, a high one is stone.
TOP = {0: (96, 132, 70), 1: (104, 142, 76), 2: (120, 148, 84),
       3: (150, 146, 112), 4: (176, 170, 150), 5: (198, 196, 184)}
LEFT_DIM, RIGHT_DIM = 62, 82     # the two side faces, as a percentage of the top
EDGE = "#2b3226"

MOVE_TINT = (90, 150, 240)
HIT_TINT = (230, 90, 80)
HOVER = "#ffffff"

TEAM = {0: ((86, 132, 226), (40, 76, 158)), 1: ((214, 78, 62), (140, 38, 32))}
SKIN = (226, 190, 152)


def mix(rgb, tint, k):
    return tuple((c * (100 - k) + t * k) // 100 for c, t in zip(rgb, tint))


def dim(rgb, k):
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * k // 100)) for c in rgb)


def rgb(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


class Rules:
    """The LOVA program, loaded once; every click is a call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.fn = {n: api.entries[_map_key(n, "rec")][1]
                   for n in ("new", "scene", "pick", "click", "endturn", "ai", "done",
                             "winner", "sel", "side", "round", "msg", "left")}
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


class Battle(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules) -> None:
        super().__init__(master, bg="#10131a")
        self.rules = rules
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H, bg="#10131a",
                                highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(self, anchor="w", bg="#10131a", fg="#c9d2de",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.anomaly = None
        self.steps = 0
        self.thinking = False
        self.hover = -1
        self.scene = []
        master.bind("<KeyPress>", self.on_key)
        self.canvas.bind("<Motion>", self.on_move)
        self.canvas.bind("<Button-1>", self.on_click)
        self.world = self.rules.call("new", 0)
        self.refresh()
        self.paint()

    # --- painting --------------------------------------------------------

    def block(self, b) -> None:
        k, u, v, h, r, a = self.rules.fields(b, "k", "u", "v", "h", "r", "a")
        hov = k == self.hover
        base = TOP.get(h, TOP[5])
        if r:
            base = mix(base, MOVE_TINT, 55)
        elif a:
            base = mix(base, HIT_TINT, 55)
        c = self.canvas
        depth = h * ZH + 16
        # the two faces you can see, then the top: the near block is drawn
        # after the far one, so the order the rules hand them over is the
        # whole of the depth sorting
        c.create_polygon(u - TW // 2, v, u, v + TH // 2, u, v + TH // 2 + depth,
                         u - TW // 2, v + depth,
                         fill=dim(base, LEFT_DIM), outline=EDGE)
        c.create_polygon(u, v + TH // 2, u + TW // 2, v, u + TW // 2, v + depth,
                         u, v + TH // 2 + depth,
                         fill=dim(base, RIGHT_DIM), outline=EDGE)
        c.create_polygon(u, v - TH // 2, u + TW // 2, v, u, v + TH // 2, u - TW // 2, v,
                         fill=rgb(base), outline=HOVER if hov else EDGE,
                         width=2 if hov else 1)

    def pawn(self, b) -> None:
        u, v = self.rules.fields(b, "u", "v")
        team, kind, hp, mx = self.rules.fields(b, "pteam", "pkind", "php", "pmax")
        sel, done = self.rules.fields(b, "psel", "pdone")
        body, dark = TEAM[team]
        if done:
            body, dark = dim(body, 55), dim(dark, 55)
            body = tuple(int(body[i:i + 2], 16) for i in (1, 3, 5))
            dark = tuple(int(dark[i:i + 2], 16) for i in (1, 3, 5))
        c = self.canvas
        if sel:
            c.create_oval(u - 16, v - 8, u + 16, v + 8, outline="#ffe066", width=3)
        c.create_oval(u - 11, v - 5, u + 11, v + 5, fill="#1b2318", outline="")
        top = v - 34
        c.create_line(u - 4, v - 2, u - 4, v - 12, fill=rgb(dark), width=4)
        c.create_line(u + 4, v - 2, u + 4, v - 12, fill=rgb(dark), width=4)
        c.create_polygon(u - 8, v - 10, u + 8, v - 10, u + 7, top + 10, u - 7, top + 10,
                         fill=rgb(body), outline=rgb(dark))
        c.create_oval(u - 6, top - 2, u + 6, top + 10, fill=rgb(SKIN), outline="")
        c.create_arc(u - 7, top - 5, u + 7, top + 9, start=0, extent=180,
                     fill=rgb(dark), outline="")
        if kind == 2:                      # the archer carries a bow
            c.create_arc(u + 9, top + 2, u + 19, v - 6, start=100, extent=160,
                         style=tk.ARC, outline="#8a6a3a", width=2)
        elif kind == 1:                    # the scout, a light spear
            c.create_line(u + 10, v - 4, u + 13, top - 4, fill="#7a6240", width=2)
        else:
            c.create_polygon(u + 9, v - 22, u + 17, v - 26, u + 17, v - 14,
                             fill="#c9ced8", outline=rgb(dark))
        w = 26 * hp // max(1, mx)
        c.create_rectangle(u - 13, top - 14, u + 13, top - 9, fill="#161a12", outline="#0c0e08")
        c.create_rectangle(u - 13, top - 14, u - 13 + w, top - 9,
                           fill="#63d463" if team == 0 else "#e0663c", outline="")

    def refresh(self) -> None:
        """Ask the rules for the picture again -- after a click, not after
        a mouse move: what is under the cursor is the host's business and
        an outline costs nothing."""
        self.scene = list_to_python(self.rules.call("scene", self.world))
        self.steps = self.rules.rt.steps

    def paint(self) -> None:
        c = self.canvas
        c.delete("all")
        if self.anomaly is None:
            for b in self.scene:
                self.block(b)
                if self.rules.field(b, "pid") >= 0:
                    self.pawn(b)
            mine = self.rules.call("left", self.world, 0)
            theirs = self.rules.call("left", self.world, 1)
            won = self.rules.call("winner", self.world)
            side = self.rules.call("side", self.world)
            msg = "".join(chr(ch) for ch in list_to_python(self.rules.call("msg", self.world)))
            state = ("you hold the field" if won == 0 else
                     "they hold the field" if won == 1 else
                     "your move" if side == 0 else "they are moving")
            self.bar.config(
                text=f"yours {mine}   theirs {theirs}   round "
                     f"{self.rules.call('round', self.world)}   {state}   {msg}"
                     f"      {self.steps:,} LOVA steps for the picture"
                     f"   [click to pick, space ends your turn, R again]")
        else:
            self.bar.config(text=f"the rules faulted: {self.anomaly.get('kind')} "
                                 f"{self.anomaly.get('repair') or ''}")

    # --- input -----------------------------------------------------------

    def cell(self, event) -> int:
        return self.rules.call("pick", self.world, int(event.x), int(event.y))

    def on_move(self, event: tk.Event) -> None:
        if self.anomaly is not None:
            return
        k = self.cell(event)
        if k != self.hover:
            self.hover = k
            self.paint()

    def on_click(self, event: tk.Event) -> None:
        if self.anomaly is not None or self.thinking:
            return
        k = self.cell(event)
        if k >= 0:
            self.guard(lambda: self.rules.call("click", self.world, k))
            self.refresh()
            self.paint()

    def on_key(self, event: tk.Event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key in ("r", "R"):
            self.anomaly = None
            self.thinking = False
            self.world = self.rules.call("new", 0)
            self.refresh()
            self.paint()
        elif key == "space" and not self.thinking and self.anomaly is None:
            if self.rules.call("winner", self.world) < 0:
                self.guard(lambda: self.rules.call("endturn", self.world))
                self.thinking = True
                self.refresh()
                self.paint()
                self.after(AI_MS, self.ai_step)

    def guard(self, thunk) -> None:
        try:
            self.world = thunk()
        except (BudgetTrap, DeltaTrap, ValueError) as exc:
            self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}

    def ai_step(self) -> None:
        """One action of theirs, so a turn can be watched rather than
        arriving all at once."""
        if self.anomaly is not None:
            return
        if self.rules.call("side", self.world) == 0 or self.rules.call("winner", self.world) >= 0:
            self.thinking = False
            self.refresh()
            self.paint()
            return
        self.guard(lambda: self.rules.call("ai", self.world))
        self.refresh()
        self.paint()
        self.after(AI_MS, self.ai_step)


def main() -> int:
    rules = Rules()
    root = tk.Tk()
    root.title("tactics -- the window is Python, the battle is LOVA")
    root.configure(bg="#10131a")
    root.resizable(False, False)
    battle = Battle(root, rules)
    battle.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
