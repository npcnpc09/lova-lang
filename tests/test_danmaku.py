"""The danmaku duel (`lib/danmaku.lova`, `apps/godot/danmaku`).

1. the program Godot opens builds, and its examples -- the rules'
   relations: the shell is a sphere, left and right mirror, focus is
   slower, the arena holds, a bullet on the maiden hits and one a metre
   off does not, a bomb clears the air once, a passing bullet grazes
   once -- pass;
2. `scene` answers in the shape `main.gd` reads, and a scripted minute
   of play keeps it: a HUD of 24 integers, bullets four integers
   apiece, amulets three;
3. the cost stays where the Godot tick can afford it: the densest
   moment of the first card under 80 000 steps for tick and scene.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.examples import check  # noqa: E402
from core.native import NativeUnavailable, open_session  # noqa: E402

SOURCE = (ROOT / "apps" / "godot" / "danmaku" / "danmaku_godot.lova").read_text(encoding="utf-8")


def _session():
    tree, _ = build(SOURCE)
    try:
        s = open_session(tree, "auto", max_steps=200_000_000)
    except NativeUnavailable:
        s = None
    if s is None:
        pytest.skip("no native runtime")
    return s


def test_examples_pass():
    results = check(SOURCE, runtime="native", max_steps=200_000_000)
    assert len(results) >= 20
    missed = [r for r in results if not r["passed"]]
    assert not missed, missed


def test_scene_shape_and_cost():
    s = _session()
    fn = {n: s.get(n) for n in ("new", "tick", "input", "scene")}
    w = fn["new"]
    worst = 0
    most = 0
    for t in range(900):
        held = s.call(fn["input"], 1 if (t // 240) % 2 == 0 else -1, 0, 0, 0, 1, 0, 0)
        nxt = s.call(fn["tick"], w, held)
        steps = s.steps
        s.release(w, held)
        w = nxt
        hud, bullets, shots = s.call(fn["scene"], w)
        steps += s.steps
        bullets = bullets or []
        shots = shots or []
        assert len(hud) == 24
        assert len(bullets) % 4 == 0 and len(shots) % 3 == 0
        assert len(bullets) // 4 == hud[23]
        assert all(k in (0, 1, 2) for k in bullets[3::4])
        worst = max(worst, steps)
        most = max(most, hud[23])
    s.close()
    assert most > 200            # the first card is under way
    assert worst < 80_000, worst
