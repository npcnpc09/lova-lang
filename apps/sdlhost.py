"""The window the three 3D ports draw in, when SDL is there.

The games -- `apps/fps`, `apps/platformer`, `apps/citybuilder` -- each
own their rules (LOVA), their keys and their clock.  What they share is
the surface the faces go onto, and that is all this module is: a window,
a font, a polygon, a bar along the bottom, and the timings of a frame.

Why it exists.  Every one of the three drew its frame by deleting every
polygon on a Tk canvas and creating them again -- 21 ms on the median
here and a quarter of a second at the worst, against 2 to 8 ms of LOVA
for the tick and the frame behind it.  The stutter was the canvas, not
the language.  The same faces through `pygame.draw.polygon` cost about
2 ms.  So: the same LOVA, the same rules, the same keys, a different
surface.  `--host tk` still opens the old one, and `--shot` never
touched either.

pygame is an app-level dependency and nothing in `core/` knows about
it: `pick_host` falls back to Tk with a one-line notice when the import
fails.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

BAR_H = 26                       # the strip under the view, where the bar's text goes
TICK = 1 / 60

# Consolas by file: `pygame.font.SysFont` walks the font registry and
# raises TypeError on this machine (pygame 2.6, a registry value that is
# not a string), so the fonts are opened by path and the default font is
# the fallback.
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono"
_FONTS = {False: (r"C:\Windows\Fonts\consola.ttf", _DEJAVU + ".ttf"),
          True: (r"C:\Windows\Fonts\consolab.ttf", _DEJAVU + "-Bold.ttf")}


def have_pygame() -> bool:
    """Whether `import pygame` works, without keeping the import."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        import pygame  # noqa: F401
    except Exception:
        return False
    return True


def pick_host(requested: str) -> str:
    """`sdl` or `tk`: what was asked for, or what is installed."""
    if requested == "tk":
        return "tk"
    if have_pygame():
        return "sdl"
    if requested == "sdl":
        print("no pygame: `pip install pygame` for the smooth window; "
              "opening the Tk one instead", file=sys.stderr)
    return "tk"


def rgb(k: int, l: int) -> tuple:
    """A 24-bit colour under light `l`, where 1024 is the sun straight on.

    The same arithmetic as each game's `lit`, which makes the same
    colour as a `#rrggbb` string for the Tk canvas.
    """
    return tuple(max(0, min(255, (k >> s & 255) * l // 1024)) for s in (16, 8, 0))


class Window:
    """A pygame window: the view, a bar under it, and the clock."""

    def __init__(self, title: str, view_w: int, view_h: int, sky, bar_h: int = BAR_H) -> None:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        self.pg = pygame
        self.view_w, self.view_h, self.bar_h = view_w, view_h, bar_h
        self.sky = sky
        pygame.init()
        pygame.display.set_caption(title)
        size = (view_w, view_h + bar_h)
        self.vsync_asked = True
        try:
            self.screen = pygame.display.set_mode(size, 0, vsync=1)
        except Exception:                      # the driver refused it
            self.vsync_asked = False
            self.screen = pygame.display.set_mode(size)
        self.clock = pygame.time.Clock()
        self.bar_font = self.font(14)
        self.flips: list = []

    # --- the surface -----------------------------------------------------

    def font(self, size: int, bold: bool = False):
        for path in _FONTS[bold]:
            if Path(path).is_file():
                return self.pg.font.Font(path, size)
        return self.pg.font.Font(None, size + 4)

    def fill_sky(self) -> None:
        self.screen.fill(self.sky, (0, 0, self.view_w, self.view_h))

    def faces(self, faces, unpack=None, surface=None) -> int:
        """The faces in the order `frame` returned them -- painter's order,
        which the renderer sorted -- each one three points and a colour.

        A face whose three points are all off one side of the view is
        dropped here.  It draws nothing either way, but SDL's fill walks
        the polygon's whole vertical span before it clips, and a wall
        four thousand rows tall is as dear as one on the screen: of the
        FPS kit's 160 faces, 38 are outside the view and were more than
        half the milliseconds (5.7 ms -> 2.6 ms).  The clip rect keeps
        the rest off the bar along the bottom.
        """
        poly = self.pg.draw.polygon
        surface = surface if surface is not None else self.screen
        w, h = self.view_w, self.view_h
        drawn = 0
        surface.set_clip((0, 0, w, h))
        for f in faces:
            u0, v0, u1, v1, u2, v2, k, l = unpack(f) if unpack else f
            if u0 < 0 and u1 < 0 and u2 < 0:
                continue
            if u0 > w and u1 > w and u2 > w:
                continue
            if v0 < 0 and v1 < 0 and v2 < 0:
                continue
            if v0 > h and v1 > h and v2 > h:
                continue
            poly(surface, (max(0, min(255, (k >> 16 & 255) * l // 1024)),
                           max(0, min(255, (k >> 8 & 255) * l // 1024)),
                           max(0, min(255, (k & 255) * l // 1024))),
                 ((u0, v0), (u1, v1), (u2, v2)))
            drawn += 1
        surface.set_clip(None)
        return drawn

    def text(self, s: str, x: int, y: int, colour, font=None, anchor: str = "nw") -> None:
        image = (font or self.bar_font).render(s, True, colour)
        w, h = image.get_size()
        if anchor[1:] == "e":
            x -= w
        if anchor[:1] == "s":
            y -= h
        self.screen.blit(image, (x, y))

    def bar(self, s: str) -> None:
        self.screen.fill((0x0e, 0x11, 0x16), (0, self.view_h, self.view_w, self.bar_h))
        self.screen.blit(self.bar_font.render(s, True, (0xc8, 0xd2, 0xde)),
                         (8, self.view_h + (self.bar_h - self.bar_font.get_height()) // 2))

    def flip(self) -> float:
        t0 = time.perf_counter()
        self.pg.display.flip()
        ms = (time.perf_counter() - t0) * 1000
        self.flips.append(ms)
        return ms

    def cap(self, fps: int = 60) -> None:
        """Hold the cadence when the driver does not.

        `set_mode(vsync=1)` is accepted here and the flip returns in half
        a millisecond, so the sixtieth is kept by the clock instead; with
        a driver that does block, this costs nothing.
        """
        self.clock.tick(fps)

    def vsync_note(self) -> str:
        if not self.vsync_asked:
            return "vsync: refused by the driver; the cadence is Clock.tick(60)"
        med = statistics.median(self.flips[-200:]) if self.flips else 0.0
        if med > 8.0:
            return f"vsync: engaged (the flip blocks {med:.1f} ms)"
        return (f"vsync: requested and accepted, but the flip returns in "
                f"{med:.1f} ms, so the driver is not blocking; the cadence "
                f"is Clock.tick(60)")

    def close(self) -> None:
        self.pg.quit()


class Stats:
    """The milliseconds of a run, by name, and what they came to."""

    def __init__(self) -> None:
        self.runs: dict = {}

    def add(self, name: str, ms: float) -> None:
        self.runs.setdefault(name, []).append(ms)

    def quantiles(self, name: str):
        v = sorted(self.runs.get(name) or [0.0])
        return statistics.median(v), v[min(len(v) - 1, int(len(v) * 0.95))]

    def report(self, title: str, order=("total", "lova tick", "lova frame", "draw", "flip"),
               extra: str = "") -> None:
        n = len(self.runs.get("total") or ())
        med, p95 = self.quantiles("total")
        print(f"{title}: {n} frames, {1000 / max(med, 1e-9):.1f} fps "
              f"(median {med:.1f} ms, p95 {p95:.1f} ms)")
        for name in order:
            if name not in self.runs:
                continue
            m, p = self.quantiles(name)
            print(f"  {name:<12} median {m:6.2f} ms   p95 {p:6.2f} ms")
        if "faces" in self.runs:
            print(f"  {'faces':<12} median {statistics.median(self.runs['faces']):6.0f}"
                  "      drawn a frame")
        if "lova tick" in self.runs and "draw" in self.runs:
            work = [sum(x) for x in zip(*(self.runs[k] for k in
                                          ("lova tick", "lova frame", "lova city",
                                           "lova cursor", "draw")
                                          if k in self.runs))]
            work.sort()
            print(f"  {'work':<12} median {statistics.median(work):6.2f} ms   "
                  f"p95 {work[min(len(work) - 1, int(len(work) * 0.95))]:6.2f} ms"
                  "   (tick + frame + draw, what the cadence must fit in)")
        if extra:
            print(f"  {extra}")
