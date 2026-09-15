"""A window in Python, the 3D in LOVA.

    python apps/maze/maze3d.py          # W/S walk, A/D turn, Q/E sidestep, R restarts

A first-person maze, in real time.  Every rule and every number behind
the picture -- the maze, where you stand, which way you face, where
each of the eighty rays stops, how tall that wall stands on the screen,
which orb is in front of which wall, whether the door opens -- is
`lib/ray.lova`, the same file that `apps/maze.lova` draws in characters
in a terminal.  This shell owns the window, the clock and the keyboard,
and nothing else: eight times a second it hands the LOVA program the
world and the keys you are holding, gets the next world back, asks it
for a frame -- a list of columns, each with a height, a wall and a
distance -- and paints the columns.

LOVA has no floating point.  The raycaster is integers throughout:
lengths in 1024ths of a cell, angles in 256ths of a turn, sines from a
65-entry table, and one `div` for the perspective.  Nothing in the
language was added for this; the game is written in what was already
there.

The point is the division of labour.  The world is a LOVA value that
Python never looks inside; a tick is a pure function of it, run under a
step budget, and a rule that misbehaved -- a loop, a ray that never
stopped -- would arrive here as a structured anomaly, not a crash.  The
steps each frame costs are shown in the corner, because with LOVA that
number is always available.

Standard library only: tkinter for the window, the LOVA core for the
game.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

# The interface to the rules: one record of what the shell needs.
# `(use "ray")` is textual inclusion, so this compiles to the library
# plus this expression, with every definition it does not reach dropped.
SOURCE = """\
(use "ray")
(rec new new-game step step frame frame level level orbs orbs-live)
"""

TICK_MS = 120                 # one tick of the world
BUDGET = 2_000_000            # steps a tick may cost; a frame costs ~35 000
COLS = 80                     # rays cast, one a column
VIEW_W, VIEW_H = 720, 420     # the picture, in pixels
CW = VIEW_W // COLS
BAR_H = 26
MAP_CELL = 5                  # the plan in the corner

ONE = 1024                    # the language's fixed point, for reading px/py

# What `step` takes.
WAIT, FWD, BACK, LEFT, RIGHT, SL, SR = 0, 1, 2, 3, 4, 5, 6
MOVE_KEYS = {"w": FWD, "Up": FWD, "s": BACK, "Down": BACK, "q": SL, "e": SR}
TURN_KEYS = {"a": LEFT, "Left": LEFT, "d": RIGHT, "Right": RIGHT}

# Wall glyph -> colour.  The quarters of the maze are built of
# different stuff; `5` is the outer shell and `6` is the door out.
WALLS = {ord("1"): (176, 82, 54),     ord("2"): (92, 118, 160),
         ord("3"): (94, 140, 92),     ord("4"): (188, 160, 106),
         ord("5"): (110, 110, 118),   ord("6"): (232, 196, 92)}
ORB = (250, 232, 140)


def shade(rgb, k):
    """`rgb` dimmed to k/1000, clamped."""
    k = max(90, min(1000, k))
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * k // 1000)) for c in rgb)


class Rules:
    """The LOVA program, loaded once; every tick is a call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.fn = {name: api.entries[_map_key(name, "rec")][1]
                   for name in ("new", "step", "frame", "level", "orbs")}
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))
        self.level = [row for row in list_to_python(self.fn["level"])]

    def call(self, name, *args):
        """Apply a curried LOVA function, under the per-tick budget."""
        self.rt.steps = 0
        fn = self.fn[name]
        for arg in args:
            fn = _call(fn, arg, self.rt)
        return fn

    @staticmethod
    def field(value, name: str):
        """A field of a LOVA record, read from Python."""
        return value.entries[_map_key(name, "get")][1]

    def fields(self, value, *names):
        return [self.field(value, n) for n in names]


class Maze(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules, facing: int) -> None:
        super().__init__(master, bg="#0b0d10")
        self.rules = rules
        self.facing = facing
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H,
                                bg="#0b0d10", highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(self, anchor="w", bg="#0b0d10", fg="#c8d0da",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.held: set = set()
        self.anomaly = None
        self.frame_steps = 0
        self.tick_steps = 0
        master.bind("<KeyPress>", self.on_press)
        master.bind("<KeyRelease>", self.on_release)
        self.restart()
        self.after(TICK_MS, self.tick)

    # --- input ---------------------------------------------------------

    def on_press(self, event: tk.Event) -> None:
        key = event.keysym
        if key in ("r", "R"):
            self.facing += 2
            self.restart()
        elif key == "Escape":
            self.master.destroy()
        else:
            self.held.add(key)

    def on_release(self, event: tk.Event) -> None:
        self.held.discard(event.keysym)

    def commands(self) -> list:
        """Every command the held keys ask for: you may walk and turn at once."""
        out = [cmd for key, cmd in TURN_KEYS.items() if key in self.held]
        out += [cmd for key, cmd in MOVE_KEYS.items() if key in self.held]
        return out[:2]

    # --- the loop ------------------------------------------------------

    def restart(self) -> None:
        self.anomaly = None
        self.world = self.rules.call("new", self.facing)
        self.paint()

    def tick(self) -> None:
        if not self.rules.field(self.world, "status") and self.anomaly is None:
            try:
                spent = 0
                for cmd in self.commands() or [WAIT]:
                    self.world = self.rules.call("step", self.world, cmd)
                    spent += self.rules.rt.steps
                self.tick_steps = spent
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                # A rule that broke: the anomaly says what and where.
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": "error",
                                                                 "message": str(exc)}
        self.paint()
        self.after(TICK_MS, self.tick)

    # --- the picture ---------------------------------------------------

    def paint(self) -> None:
        c = self.canvas
        c.delete("all")
        self.sky()
        if self.anomaly is None:
            f = self.rules.call("frame", self.world, COLS, VIEW_H)
            self.frame_steps = self.rules.rt.steps
            self.walls(list_to_python(self.rules.field(f, "cols")))
            self.orbs(list_to_python(self.rules.field(f, "spr")))
            left, turn, msg, status = self.rules.fields(f, "left", "turn", "msg", "status")
        else:
            left = turn = status = 0
            msg = str(self.anomaly.get("repair") or self.anomaly.get("kind"))
        self.plan()
        self.bar.config(
            text=f"orbs left {left}   ticks {turn}   "
                 f"LOVA steps: {self.tick_steps:,} the tick, {self.frame_steps:,} the picture"
                 f"   {msg}")
        if self.anomaly is not None:
            self.banner("the rules faulted", msg)
        elif status:
            self.banner("you are out", f"{turn} ticks -- R for another way round")

    def sky(self) -> None:
        """Ceiling and floor: bands, darkest at the horizon, where the
        floor is furthest away."""
        c = self.canvas
        mid = VIEW_H // 2
        bands = 16
        for i in range(bands):
            k = 200 + 800 * i // bands
            y0, y1 = mid * i // bands, mid * (i + 1) // bands
            c.create_rectangle(0, y0, VIEW_W, y1, fill=shade((66, 72, 86), k), outline="")
            c.create_rectangle(0, VIEW_H - y1, VIEW_W, VIEW_H - y0,
                               fill=shade((104, 92, 78), k), outline="")

    def walls(self, cols) -> None:
        c = self.canvas
        mid = VIEW_H // 2
        for x, col in enumerate(cols):
            h, kind, side, dist = self.rules.fields(col, "h", "k", "s", "d")
            rgb = WALLS.get(kind, (120, 120, 120))
            # dimmer with distance, and dimmer again on the face you see
            # edge-on: two multiplications are the whole lighting model
            k = 3000 * ONE // (dist + 2 * ONE)
            if side:
                k = k * 70 // 100
            h = min(h, VIEW_H * 3)
            c.create_rectangle(x * CW, mid - h // 2, x * CW + CW, mid + h // 2,
                               fill=shade(rgb, k), outline="")

    def orbs(self, spr) -> None:
        c = self.canvas
        for s in spr:
            x, top, bot, dist = self.rules.fields(s, "c", "t", "u", "d")
            k = max(560, 1000 - 60 * dist // ONE)
            c.create_rectangle(x * CW, top, x * CW + CW, bot,
                               fill=shade(ORB, k), outline="")

    def plan(self) -> None:
        """The maze from above, in the corner: where you are, and the orbs
        you have not found."""
        c = self.canvas
        rows = self.rules.level
        n = len(rows)
        x0, y0 = VIEW_W - n * MAP_CELL - 10, 10
        c.create_rectangle(x0 - 3, y0 - 3, x0 + n * MAP_CELL + 3, y0 + n * MAP_CELL + 3,
                           fill="#0b0d10", outline="#2c3440")
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != ".":
                    col = "#e8c45c" if ch == "6" else "#39404c"
                    c.create_rectangle(x0 + x * MAP_CELL, y0 + y * MAP_CELL,
                                       x0 + (x + 1) * MAP_CELL, y0 + (y + 1) * MAP_CELL,
                                       fill=col, outline="")
        for orb in list_to_python(self.rules.call("orbs", self.world)):
            ox, oy = self.rules.fields(orb, "x", "y")
            c.create_oval(x0 + ox * MAP_CELL, y0 + oy * MAP_CELL,
                          x0 + (ox + 1) * MAP_CELL, y0 + (oy + 1) * MAP_CELL,
                          fill="#faE88c", outline="")
        px, py = self.rules.fields(self.world, "px", "py")
        mx, my = x0 + px * MAP_CELL / ONE, y0 + py * MAP_CELL / ONE
        c.create_oval(mx - 3, my - 3, mx + 3, my + 3, fill="#7ad0ff", outline="")

    def banner(self, line1: str, line2: str) -> None:
        c = self.canvas
        c.create_rectangle(0, VIEW_H / 2 - 44, VIEW_W, VIEW_H / 2 + 44,
                           fill="#0b0d10", outline="#39404c")
        c.create_text(VIEW_W / 2, VIEW_H / 2 - 14, text=line1, fill="#eceff4",
                      font=("Consolas", 16, "bold"))
        c.create_text(VIEW_W / 2, VIEW_H / 2 + 18, text=line2, fill="#a3acbb",
                      font=("Consolas", 11))


def main() -> int:
    facing = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rules = Rules()
    root = tk.Tk()
    root.title("maze -- the window is Python, the 3D is LOVA")
    root.configure(bg="#0b0d10")
    root.resizable(False, False)
    game = Maze(root, rules, facing)
    game.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
