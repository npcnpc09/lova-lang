"""What a frame of the three 3D ports costs, as a number.

`tools/bench/<game>.lova` is what `tools/bench_native.py` times: the
world built, N ticks, one frame.  The numbers below are what those
programs spend at N = 0, measured after the renderer was cut down
(Q129: the projection written out inside `placed-in`'s fold rather
than called with twelve arguments, the model's scale folded into the
object's four sines, the face written out inside `object-faces`'s
fold, `stand` and its `turn` written out inside `shot-of`'s map, a
model's vertices numbered and its reach measured once when the module
is read, an object that lies wholly behind a camera standing in the
scene dropped whole, and `lib/fixed.lova`'s sine table read by
`map-get` rather than walked by `nth`).

The point of pinning them is that a frame's cost is what decides
whether a window is smooth, and nothing else in the suite would notice
it doubling.  A change that makes a frame *cheaper* fails this test
too, on purpose: lower the number here and say what bought it.

The bench programs also stand in for the drivers, which the suite
cannot run: what `apps/*/*.py --shot` draws is the same frame.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# game -> (steps at n=0, steps at n=60)
COST = {
    "platformer": (145212, 376232),
    "citybuilder": (839669, 871166),
    "fps": (108534, 495525),
}

# A frame is 300 steps a face and the count moves with the models; the
# margin is there so that a one-line change to a game's rules that
# places one more object does not fail the test, while a renderer
# regression of a few per cent does.
MARGIN = 0.02


def _steps(path, n):
    """One bench program through the CLI, in a process of its own.

    A subprocess rather than `core.cli.main` in this one, because these
    programs are the largest in the repository -- the city's frame is
    eight hundred thousand steps and a compiled closure per node of it
    -- and leaving that behind in the test runner's interpreter pushed
    `core/locate.py`'s two-second probe budget over in a later file.
    """
    p = subprocess.run(
        [sys.executable, "-m", "core.cli", "run", path, f"n={n}", "--stats",
         "--native", "off"],
        cwd=ROOT, input="", capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=str(ROOT)))
    assert p.returncode == 0, p.stderr
    line = [ln for ln in p.stderr.splitlines() if "steps," in ln][-1]
    return int(line.split("[")[1].split(" ")[0])


class FrameCost(unittest.TestCase):

    def test_a_frame_costs_what_it_did(self):
        for game, (at0, _at60) in COST.items():
            with self.subTest(game=game):
                got = _steps(f"tools/bench/{game}.lova", 0)
                self.assertAlmostEqual(got / at0, 1.0, delta=MARGIN,
                                       msg=f"{game}: {got} steps, pinned at {at0}")

    def test_sixty_ticks_and_a_frame_cost_what_they_did(self):
        for game, (_at0, at60) in COST.items():
            with self.subTest(game=game):
                got = _steps(f"tools/bench/{game}.lova", 60)
                self.assertAlmostEqual(got / at60, 1.0, delta=MARGIN,
                                       msg=f"{game}: {got} steps, pinned at {at60}")


if __name__ == "__main__":
    unittest.main()
