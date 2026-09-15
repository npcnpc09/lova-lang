"""A window in Python, the 3D in LOVA: a low-poly model viewer.

    python apps/model/model.py [1-5]

Five meshes, turning in real time.  Every number behind the picture is
`lib/mesh3d.lova`: the two rotations, the move away from the camera,
the divide by depth, the signed area that says whether a face has its
back to you, the sun against each face's own normal, and the sort that
puts the far triangles first -- because a host painting polygons has no
depth buffer, and the order it is given is the whole of the depth
sorting.  This shell owns the window, the mouse, and the colour a
material is.

LOVA has no floating point.  A vertex is three integers in 1024ths of a
model unit, a normal is three more, and the perspective is one `div`.
Each face carries the normal it was born with, so a frame needs no
square root at all: a rotation does not change a length.

Drag to turn it, the wheel or +/- to come closer, 1-5 to change the
model, W for wireframe, space to stop it spinning, R to reset, Escape
to leave.
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.cli import build
from core.conservation import BudgetTrap, DeltaTrap
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

SOURCE = """\
(use "models")
(rec shot shot faces face-count verts vertex-count
     sphere sphere tree tree house house gem gem ship ship)
"""

VIEW_W, VIEW_H = 880, 620
BUDGET = 20_000_000
TICK_MS = 50

MODELS = ("sphere", "tree", "house", "gem", "ship")

# Materials, by the number `make_models.py` gives them.
MATERIAL = {0: (108, 158, 74),     # grass
            1: (104, 74, 46),      # bark
            2: (62, 122, 66),      # leaf
            3: (150, 152, 160),    # stone
            4: (168, 74, 58),      # roof
            5: (216, 206, 182),    # wall
            6: (158, 166, 178),    # metal
            7: (96, 190, 214),     # glass
            8: (226, 182, 80)}     # gold


def lit(rgb, l):
    """`rgb` under light `l`, where 1024 is the sun straight on."""
    return "#%02x%02x%02x" % tuple(max(0, min(255, c * l // 1024)) for c in rgb)


class Rules:
    """The LOVA program, loaded once; every frame is one call into it."""

    def __init__(self) -> None:
        tree, _report = build(SOURCE)
        self.rt = Runtime(max_steps=BUDGET, max_call_depth=10_000)
        api = evaluate(tree, self.rt)
        self.fn = {n: api.entries[_map_key(n, "rec")][1]
                   for n in ("shot", "faces", "verts") + MODELS}
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


class Viewer(tk.Frame):
    def __init__(self, master: tk.Tk, rules: Rules, which: int) -> None:
        super().__init__(master, bg="#0e1116")
        self.rules = rules
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H, bg="#0e1116",
                                highlightthickness=0)
        self.canvas.pack()
        self.bar = tk.Label(self, anchor="w", bg="#0e1116", fg="#c8d2de",
                            font=("Consolas", 10), padx=8, pady=4)
        self.bar.pack(fill="x")
        self.which = which
        self.yaw, self.pitch, self.dist = 28, 22, 3400
        self.spin = True
        self.wire = False
        self.anomaly = None
        self.steps = self.drawn = 0
        self.ms = 0.0
        self.drag = None
        master.bind("<KeyPress>", self.on_key)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.after(TICK_MS, self.tick)

    # --- the loop --------------------------------------------------------

    def tick(self) -> None:
        if self.spin and self.anomaly is None:
            self.yaw = (self.yaw + 2) % 256
        self.paint()
        self.after(TICK_MS, self.tick)

    def paint(self) -> None:
        c = self.canvas
        c.delete("all")
        name = MODELS[self.which]
        if self.anomaly is None:
            start = time.perf_counter()
            try:
                picture = list_to_python(self.rules.call(
                    "shot", self.rules.fn[name], self.yaw, self.pitch,
                    self.dist, VIEW_W, VIEW_H))
                self.steps = self.rules.rt.steps
            except (BudgetTrap, DeltaTrap, ValueError) as exc:
                self.anomaly = getattr(exc, "anomaly", None) or {"kind": str(exc)}
                return
            self.ms = (time.perf_counter() - start) * 1000
            self.drawn = len(picture)
            for f in picture:
                u0, v0, u1, v1, u2, v2, k, l = self.rules.fields(
                    f, "u0", "v0", "u1", "v1", "u2", "v2", "k", "l")
                fill = lit(MATERIAL.get(k, (160, 160, 160)), l)
                c.create_polygon(u0, v0, u1, v1, u2, v2,
                                 fill="" if self.wire else fill,
                                 outline="#7f8c9b" if self.wire else fill)
            faces = self.rules.call("faces", self.rules.fn[name])
            verts = self.rules.call("verts", self.rules.fn[name])
            self.bar.config(
                text=f"{name}   {verts} vertices, {faces} triangles, "
                     f"{self.drawn} facing you   {self.steps:,} LOVA steps "
                     f"in {self.ms:.0f} ms ({1000 / max(self.ms, 1):.0f} fps)   "
                     f"[drag to turn, wheel to zoom, 1-5 model, W wire, space stop]")
        else:
            self.bar.config(text=f"the rules faulted: {self.anomaly.get('kind')}")

    # --- input -----------------------------------------------------------

    def on_press(self, event: tk.Event) -> None:
        self.drag = (event.x, event.y, self.yaw, self.pitch)

    def on_drag(self, event: tk.Event) -> None:
        if self.drag is None:
            return
        x0, y0, yaw, pitch = self.drag
        self.yaw = (yaw - (event.x - x0) // 3) % 256
        self.pitch = max(-60, min(60, pitch + (event.y - y0) // 3))
        self.paint()

    def on_wheel(self, event: tk.Event) -> None:
        self.dist = max(1600, min(9000, self.dist - event.delta // 2))
        self.paint()

    def on_key(self, event: tk.Event) -> None:
        key = event.keysym
        if key == "Escape":
            self.master.destroy()
        elif key in "12345":
            self.which = int(key) - 1
            self.anomaly = None
        elif key in ("w", "W"):
            self.wire = not self.wire
        elif key == "space":
            self.spin = not self.spin
        elif key in ("r", "R"):
            self.yaw, self.pitch, self.dist = 28, 22, 3400
        elif key in ("plus", "equal"):
            self.dist = max(1600, self.dist - 300)
        elif key == "minus":
            self.dist = min(9000, self.dist + 300)
        self.paint()


def main() -> int:
    which = int(sys.argv[1]) - 1 if len(sys.argv) > 1 else 0
    rules = Rules()
    root = tk.Tk()
    root.title("model -- the window is Python, the 3D is LOVA")
    root.configure(bg="#0e1116")
    root.resizable(False, False)
    viewer = Viewer(root, rules, max(0, min(len(MODELS) - 1, which)))
    viewer.pack()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
