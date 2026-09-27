"""What a tick of the duel costs, on the native runtime.

    python apps/godot/danmaku/bench.py [--ticks N] [--every K]

Plays the duel with a scripted hand -- circling the witch, shooting,
rising and falling, focused for a few seconds at a time -- and prints,
every K ticks, the bullets in the air and the steps and milliseconds
the `tick` and `scene` calls took.  The milliseconds here include the
stdio crossing to the runtime process; inside Godot the crossing is a
function call on a thread, so these are an upper bound.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.native import open_session  # noqa: E402


def hand(t: int):
    """(mx mz my focus shoot bomb retry) at tick t."""
    mx = 1 if (t // 240) % 2 == 0 else -1
    my = 1 if (t // 90) % 4 == 0 else (-1 if (t // 90) % 4 == 2 else 0)
    focus = 1 if (t // 300) % 3 == 1 else 0
    return (mx, 0, my, focus, 1, 0, 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=7200)
    ap.add_argument("--every", type=int, default=600)
    args = ap.parse_args()

    tree, _ = build((HERE / "danmaku_godot.lova").read_text(encoding="utf-8"))
    s = open_session(tree, "on", max_steps=200_000_000)
    fn = {n: s.get(n) for n in ("new", "tick", "input", "scene")}
    w = fn["new"]
    rows = []
    for t in range(args.ticks):
        held = s.call(fn["input"], *hand(t))
        t0 = time.perf_counter()
        nxt = s.call(fn["tick"], w, held)
        t1 = time.perf_counter()
        tick_steps = s.steps
        s.release(w, held)
        w = nxt
        scene = s.call(fn["scene"], w)
        t2 = time.perf_counter()
        hud = scene[0]
        rows.append((len(scene[1] or []) // 4, tick_steps, s.steps, (t1 - t0) * 1e3, (t2 - t1) * 1e3, hud))
        if (t + 1) % args.every == 0:
            r = rows[-1]
            print(f"t={t+1:5d} phase={hud[10]} hp={hud[11]:4d} lives={hud[6]} bombs={hud[7]} graze={hud[8]:4d} "
                  f"bullets={r[0]:5d} tick {r[1]:7d} steps {r[3]:6.2f} ms  scene {r[2]:7d} steps {r[4]:6.2f} ms")
        if hud[16] or hud[17]:
            print(f"ended at t={t+1}: over={hud[16]} won={hud[17]}")
            break
    busy = [r for r in rows if r[0] > 0]
    top = max(rows, key=lambda r: r[0])
    print(f"\nmost bullets: {top[0]}  (tick {top[1]} steps {top[3]:.2f} ms, scene {top[2]} steps {top[4]:.2f} ms)")
    if busy:
        per = [r[1] / r[0] for r in busy if r[0] >= 100]
        if per:
            print(f"tick steps per bullet (>=100 in the air): median {statistics.median(per):.1f}")
        print(f"tick ms: median {statistics.median(r[3] for r in busy):.2f}  max {max(r[3] for r in busy):.2f}")
        print(f"scene ms: median {statistics.median(r[4] for r in busy):.2f}  max {max(r[4] for r in busy):.2f}")
    s.close()


if __name__ == "__main__":
    main()
