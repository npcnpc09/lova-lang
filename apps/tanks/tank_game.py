"""A window in Python, the game in LOVA.

    python apps/tanks/tank_game.py            # arrows move, space fires, R restarts

Tank battle, in real time: eight enemies arrive along the top of the
grid, up to three at once, and you hold the base beside you.  Every
rule of the game -- who moves where, what a bullet breaks, when an
enemy shoots, who has won -- is `lib/tanks.lova`, the same file that
`apps/tanks.lova` plays turn by turn in a terminal.  This shell owns
the window, the clock and the keyboard, and nothing else: ten times a
second it hands the LOVA program the world and the key you are
holding, gets the next world back, asks for it as text, and paints
the text.

The point is the division of labour.  The world is a LOVA value that
Python never looks inside; a turn is a pure function of it, run under
a step budget, and a rule that misbehaved -- a loop, an out-of-range
index -- would arrive here as a structured anomaly, not a crash.  The
steps each turn cost are shown in the corner, because with LOVA that
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
from core.runtime import Runtime, _call, _map_key, evaluate

# The interface to the rules: one record of the four functions the
# shell needs.  `(use "tanks")` is textual inclusion, so this compiles
# to the library plus this expression, unused defs dropped.
SOURCE = """\
(use "tanks")
(rec new new-game step step render render left enemies-left)
"""

TICK_MS = 150             # one turn of the game
BUDGET = 200_000          # steps a turn may cost; a typical one costs ~5 000
CELL = 40
ROWS, COLS = 11, 15

# Commands, as `step` takes them.
WAIT, UP, RIGHT, DOWN, LEFT, FIRE = 0, 1, 2, 3, 4, 5
KEYS = {"Up": UP, "Right": RIGHT, "Down": DOWN, "Left": LEFT,
        "w": UP, "d": RIGHT, "s": DOWN, "a": LEFT}

STATUS = {1: "you win -- the last enemy is gone",
          2: "you were hit",
          3: "the base fell"}


class Rules:
    """The LOVA program, loaded once; every turn is a call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.fn = {name: api.entries[_map_key(name, "rec")][1]
                   for name in ("new", "step", "render", "left")}
        # A turn's nested closures need more Python stack than the
        # default; `evaluate` raises the limit for a run, and a call made
        # outside one raises it here.
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

    def call(self, name: str, *args):
        """Apply a curried LOVA function, under the per-turn budget."""
        self.rt.steps = 0
        fn = self.fn[name]
        for arg in args:
            fn = _call(fn, arg, self.rt)
        return fn

    @staticmethod
    def field(world, name: str):
        """A field of the world record, read from Python."""
        return world.entries[_map_key(name, "get")][1]


class Game(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules, seed: int) -> None:
        super().__init__(master, bg="#101418")
        self.rules = rules
        self.seed = seed
        self.canvas = tk.Canvas(self, width=COLS * CELL, height=ROWS * CELL,
                                bg="#101418", highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(self, anchor="w", bg="#101418", fg="#d8dee9",
                            font=("Consolas", 11), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.held: list = []           # direction keys down, most recent last
        self.fire_queued = False
        self.anomaly = None
        self.turn_steps = 0            # what the last `step` cost
        master.bind("<KeyPress>", self.on_press)
        master.bind("<KeyRelease>", self.on_release)
        self.restart()
        self.after(TICK_MS, self.tick)

    # --- input ---------------------------------------------------------

    def on_press(self, event: tk.Event) -> None:
        key = event.keysym
        if key in KEYS:
            cmd = KEYS[key]
            if cmd in self.held:
                self.held.remove(cmd)
            self.held.append(cmd)
        elif key == "space":
            self.fire_queued = True
        elif key in ("r", "R"):
            self.seed += 1
            self.restart()
        elif key == "Escape":
            self.master.destroy()

    def on_release(self, event: tk.Event) -> None:
        cmd = KEYS.get(event.keysym)
        if cmd in self.held:
            self.held.remove(cmd)

    def command(self) -> int:
        if self.fire_queued:
            self.fire_queued = False
            return FIRE
        return self.held[-1] if self.held else WAIT

    # --- the loop ------------------------------------------------------

    def restart(self) -> None:
        self.anomaly = None
        self.world = self.rules.call("new", self.seed)
        self.turn_steps = self.rules.rt.steps
        self.paint()

    def tick(self) -> None:
        status = self.rules.field(self.world, "status")
        if status == 0 and self.anomaly is None:
            try:
                self.world = self.rules.call("step", self.world, self.command())
                self.turn_steps = self.rules.rt.steps
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                # A rule that broke: the anomaly says what and where.
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": "error",
                                                                 "message": str(exc)}
        self.paint()
        self.after(TICK_MS, self.tick)

    # --- the picture ---------------------------------------------------

    def paint(self) -> None:
        text = self.rules.call("render", self.world)
        c = self.canvas
        c.delete("all")
        for y, row in enumerate(text.split("\n")):
            for x, ch in enumerate(row):
                self.glyph(x, y, ch)
        status = self.rules.field(self.world, "status")
        score = self.rules.field(self.world, "score")
        turn = self.rules.field(self.world, "turn")
        left = self.rules.call("left", self.world)
        self.bar.config(text=f"score {score}   enemies left {left}   turn {turn}   "
                             f"LOVA steps this turn {self.turn_steps:,} / {BUDGET:,}")
        if self.anomaly is not None:
            self.banner(f"the rules faulted: {self.anomaly.get('kind')}",
                        str(self.anomaly.get("repair") or self.anomaly.get("message") or ""))
        elif status:
            self.banner(STATUS[status], "R for another game")

    def banner(self, line1: str, line2: str) -> None:
        c = self.canvas
        w, h = COLS * CELL, ROWS * CELL
        c.create_rectangle(0, h / 2 - 44, w, h / 2 + 44, fill="#101418", outline="#3b4252")
        c.create_text(w / 2, h / 2 - 14, text=line1, fill="#eceff4", font=("Consolas", 16, "bold"))
        c.create_text(w / 2, h / 2 + 18, text=line2, fill="#a3acbb", font=("Consolas", 11))

    def glyph(self, x: int, y: int, ch: str) -> None:
        c = self.canvas
        x0, y0 = x * CELL, y * CELL
        x1, y1 = x0 + CELL, y0 + CELL
        if ch == "#":
            c.create_rectangle(x0, y0, x1, y1, fill="#b5502a", outline="#101418")
            for k in (1, 3):
                c.create_line(x0, y0 + k * CELL / 4, x1, y0 + k * CELL / 4, fill="#7a3418")
            c.create_line(x0 + CELL / 2, y0, x0 + CELL / 2, y0 + CELL / 4, fill="#7a3418")
            c.create_line(x0 + CELL / 2, y0 + CELL / 2, x0 + CELL / 2, y0 + 3 * CELL / 4, fill="#7a3418")
            c.create_line(x0 + CELL / 4, y0 + CELL / 4, x0 + CELL / 4, y0 + CELL / 2, fill="#7a3418")
            c.create_line(x0 + 3 * CELL / 4, y0 + CELL / 4, x0 + 3 * CELL / 4, y0 + CELL / 2, fill="#7a3418")
            c.create_line(x0 + CELL / 4, y0 + 3 * CELL / 4, x0 + CELL / 4, y1, fill="#7a3418")
            c.create_line(x0 + 3 * CELL / 4, y0 + 3 * CELL / 4, x0 + 3 * CELL / 4, y1, fill="#7a3418")
        elif ch == "%":
            c.create_rectangle(x0, y0, x1, y1, fill="#8a919c", outline="#101418")
            c.create_rectangle(x0 + 8, y0 + 8, x1 - 8, y1 - 8, fill="#c0c6cf", outline="")
        elif ch == "@":
            self.base(x0, y0, "#e5c07b")
        elif ch == "X":
            self.base(x0, y0, "#4c3a3a")
        elif ch in "^>v<":
            self.tank(x0, y0, "^>v<".index(ch), "#88c070", "#5a9a48")
        elif ch in "URDL":
            self.tank(x0, y0, "URDL".index(ch), "#c0c0c0", "#8a8a8a")
        elif ch == "*":
            c.create_oval(x0 + 15, y0 + 15, x1 - 15, y1 - 15, fill="#fff3b0", outline="")
        elif ch == "o":
            c.create_oval(x0 + 15, y0 + 15, x1 - 15, y1 - 15, fill="#ff8a80", outline="")

    def base(self, x0: float, y0: float, colour: str) -> None:
        c = self.canvas
        m = CELL / 2
        pts = [(m, 4), (m + 6, m - 6), (CELL - 4, m - 4), (m + 8, m + 2),
               (m + 12, CELL - 4), (m, m + 8), (m - 12, CELL - 4), (m - 8, m + 2),
               (4, m - 4), (m - 6, m - 6)]
        c.create_polygon([(x0 + px, y0 + py) for px, py in pts], fill=colour, outline="#101418")

    def tank(self, x0: float, y0: float, d: int, body: str, dark: str) -> None:
        c = self.canvas
        x1, y1 = x0 + CELL, y0 + CELL
        m = CELL / 2
        # tracks, hull, turret, barrel toward d (0 up, 1 right, 2 down, 3 left)
        if d in (0, 2):
            c.create_rectangle(x0 + 4, y0 + 4, x0 + 11, y1 - 4, fill=dark, outline="")
            c.create_rectangle(x1 - 11, y0 + 4, x1 - 4, y1 - 4, fill=dark, outline="")
            c.create_rectangle(x0 + 11, y0 + 8, x1 - 11, y1 - 8, fill=body, outline="")
        else:
            c.create_rectangle(x0 + 4, y0 + 4, x1 - 4, y0 + 11, fill=dark, outline="")
            c.create_rectangle(x0 + 4, y1 - 11, x1 - 4, y1 - 4, fill=dark, outline="")
            c.create_rectangle(x0 + 8, y0 + 11, x1 - 8, y1 - 11, fill=body, outline="")
        c.create_oval(x0 + m - 7, y0 + m - 7, x0 + m + 7, y0 + m + 7, fill=dark, outline="")
        dx, dy = [(0, -1), (1, 0), (0, 1), (-1, 0)][d]
        c.create_line(x0 + m, y0 + m, x0 + m + dx * (m - 2), y0 + m + dy * (m - 2),
                      fill=dark, width=5)


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    rules = Rules()
    root = tk.Tk()
    root.title("tanks -- the window is Python, the rules are LOVA")
    root.configure(bg="#101418")
    root.resizable(False, False)
    game = Game(root, rules, seed)
    game.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
