"""A window in Python, 2048 in LOVA.

    python apps/g2048/game2048.py [seed]

A port of gabrielecirulli/2048 (MIT).  Every rule is `lib/g2048.lova`,
written against the original's `js/game_manager.js` and checked against
a transliteration of it in `tests/test_2048.py`: the same traversal
order, the same farthest-position walk, the same rule that a tile made
this move cannot merge again, the same score, the same nine-in-ten
chance of a two.  This shell owns the window, the keys and the colours
-- which are the original's own, down to the hex -- and nothing else.

One difference on purpose: the original's chance comes from
`Math.random`, so a game cannot be replayed.  Here the generator is
threaded through the world, so a seed is a game: `python
apps/g2048/game2048.py 42` twice is the same 42 twice.

Arrows or WASD move, R starts again, space keeps playing after 2048,
Escape quits.
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
(use "g2048")
(rec new new-game move move rows rows keep keep-playing big biggest)
"""

BUDGET = 5_000_000

# The original's palette, from its style/main.css.
PAGE = "#faf8ef"
GRID = "#bbada0"
EMPTY = "#cdc1b4"
DARK_TEXT = "#776e65"
LIGHT_TEXT = "#f9f6f2"
TILES = {2: "#eee4da", 4: "#ede0c8", 8: "#f2b179", 16: "#f59563",
         32: "#f67c5f", 64: "#f65e3b", 128: "#edcf72", 256: "#edcc61",
         512: "#edc850", 1024: "#edc53f", 2048: "#edc22e"}
BEYOND = "#3c3a32"

CELL = 106
GAP = 12
GRID_PX = 4 * CELL + 5 * GAP
PAD = 24
HEAD = 150

KEYS = {"Up": 0, "w": 0, "k": 0, "Right": 1, "d": 1, "l": 1,
        "Down": 2, "s": 2, "j": 2, "Left": 3, "a": 3, "h": 3}


class Rules:
    """The LOVA program, loaded once; every key press is a call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.fn = {n: api.entries[_map_key(n, "rec")][1]
                   for n in ("new", "move", "rows", "keep", "big")}
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


class Game(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules, seed: int) -> None:
        super().__init__(master, bg=PAGE)
        self.rules = rules
        self.seed = seed
        self.best = 0
        self.anomaly = None
        self.steps = 0
        self.canvas = tk.Canvas(self, width=GRID_PX + 2 * PAD, height=HEAD + GRID_PX + PAD + 42,
                                bg=PAGE, highlightthickness=0)
        self.canvas.pack()
        master.bind("<KeyPress>", self.on_key)
        self.restart()

    # --- the drawing -----------------------------------------------------

    def round_rect(self, x0, y0, x1, y1, r, fill):
        c = self.canvas
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline="")
        c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline="")
        for cx, cy, start in ((x0 + r, y0 + r, 90), (x1 - r, y0 + r, 0),
                              (x1 - r, y1 - r, 270), (x0 + r, y1 - r, 180)):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=90,
                         fill=fill, outline="", style=tk.PIESLICE)

    def font_for(self, value: int):
        size = 44 if value < 100 else 36 if value < 1000 else 28
        return ("Helvetica", size, "bold")

    def paint(self) -> None:
        c = self.canvas
        c.delete("all")
        score = self.rules.field(self.world, "score")
        self.best = max(self.best, score)

        # the head: the name, the two boxes, the line the original carries
        c.create_text(PAD, 34, text="2048", anchor="w", fill=DARK_TEXT,
                      font=("Helvetica", 46, "bold"))
        for i, (label, value) in enumerate((("BEST", self.best), ("SCORE", score))):
            x1 = PAD + GRID_PX - i * 108
            self.round_rect(x1 - 96, 12, x1, 68, 4, GRID)
            c.create_text((x1 - 48), 26, text=label, fill="#eee4da",
                          font=("Helvetica", 11, "bold"))
            c.create_text((x1 - 48), 48, text=str(value), fill="white",
                          font=("Helvetica", 20, "bold"))
        c.create_text(PAD, 96, text="Join the numbers and get to the 2048 tile!",
                      anchor="w", fill=DARK_TEXT, font=("Helvetica", 12))
        c.create_text(PAD, 120, text="arrows or WASD move   R starts again   "
                                     "space keeps playing after 2048",
                      anchor="w", fill="#8f8677", font=("Helvetica", 10))

        # the grid
        self.round_rect(PAD, HEAD, PAD + GRID_PX, HEAD + GRID_PX, 6, GRID)
        rows = [list_to_python(r) for r in list_to_python(self.rules.call("rows", self.world))]
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                x0 = PAD + GAP + x * (CELL + GAP)
                y0 = HEAD + GAP + y * (CELL + GAP)
                self.round_rect(x0, y0, x0 + CELL, y0 + CELL, 4,
                                TILES.get(value, BEYOND) if value else EMPTY)
                if value:
                    c.create_text(x0 + CELL / 2, y0 + CELL / 2, text=str(value),
                                  fill=DARK_TEXT if value < 8 else LIGHT_TEXT,
                                  font=self.font_for(value))

        won = self.rules.field(self.world, "won")
        keep = self.rules.field(self.world, "keep")
        if self.anomaly is not None:
            self.overlay("the rules faulted", str(self.anomaly.get("kind")), "#edeae0")
        elif self.rules.field(self.world, "over"):
            self.overlay("Game over!", f"{score} points in "
                                       f"{self.rules.field(self.world, 'turn')} moves -- R", "#edeae0")
        elif won and not keep:
            self.overlay("You win!", "space to keep going, R to start again", "#f2e8c4")

        c.create_text(PAD, HEAD + GRID_PX + 16, anchor="w", fill="#a29a8e",
                      font=("Consolas", 9),
                      text=f"seed {self.seed}   {self.steps:,} LOVA steps this move")
        c.create_text(PAD, HEAD + GRID_PX + 32, anchor="w", fill="#a29a8e",
                      font=("Consolas", 9),
                      text="rules: lib/g2048.lova, after gabrielecirulli/2048 (MIT)")

    def overlay(self, line1: str, line2: str, colour: str) -> None:
        c = self.canvas
        self.round_rect(PAD, HEAD, PAD + GRID_PX, HEAD + GRID_PX, 6, colour)
        c.create_text(PAD + GRID_PX / 2, HEAD + GRID_PX / 2 - 18, text=line1,
                      fill=DARK_TEXT, font=("Helvetica", 40, "bold"))
        c.create_text(PAD + GRID_PX / 2, HEAD + GRID_PX / 2 + 30, text=line2,
                      fill=DARK_TEXT, font=("Helvetica", 13))

    # --- the keys --------------------------------------------------------

    def restart(self) -> None:
        self.anomaly = None
        self.world = self.rules.call("new", self.seed)
        self.steps = self.rules.rt.steps
        self.paint()

    def on_key(self, event: tk.Event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
            return
        if key in ("r", "R"):
            self.seed += 1
            self.restart()
            return
        if key == "space":
            self.world = self.rules.call("keep", self.world)
            self.paint()
            return
        if key not in KEYS or self.anomaly is not None:
            return
        try:
            self.world = self.rules.call("move", self.world, KEYS[key])
            self.steps = self.rules.rt.steps
        except (BudgetTrap, DeltaTrap, ValueError) as exc:
            self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
        self.paint()


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    rules = Rules()
    root = tk.Tk()
    root.title("2048 -- the window is Python, the rules are LOVA")
    root.configure(bg=PAGE)
    root.resizable(False, False)
    game = Game(root, rules, seed)
    game.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
