"""The Godot host (`apps/godot/fps`, `native/lova-godot`).

Three layers, each skipped when what it needs is not on the machine:

1. the program Godot loads -- `fps_godot.lova`, which is `lib/fps.lova`
   and a `scene` function -- builds, its examples pass, and `scene`
   answers in the shape the player script reads;
2. the same through a native session, so what crosses the protocol is
   what Python computes;
3. the extension inside Godot: `build.py --smoke` assembles the project
   and runs `lova_smoke.gd` under `godot --headless`, and its output
   says three hundred ticks ran, a float was refused and a trap was
   reported by kind.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python  # noqa: E402

APP = ROOT / "apps" / "godot" / "fps"
SOURCE = (APP / "fps_godot.lova").read_text(encoding="utf-8")


def _api():
    tree, _report = build(SOURCE)
    rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
    api = evaluate(tree, rt)
    fn = {n: api.entries[_map_key(n, "rec")][1] for n in ("new", "tick", "input", "scene")}
    return rt, fn


def _call_all(rt, f, *args):
    rt.steps = 0
    rt.mark = 0
    rt.current = None
    for a in args:
        f = _call(f, a, rt)
    return f


def _deep(value):
    """A LOVA list of lists as Python lists, ints kept."""
    if value is None:
        return []
    out = list_to_python(value)
    return [_deep(x) if not isinstance(x, int) else x for x in out]


def test_scene_shape_in_python():
    rt, fn = _api()
    w = fn["new"]
    held = _call_all(rt, fn["input"], 0, -1, 1, 1, 0, 0, 0)
    for _ in range(30):
        w = _call_all(rt, fn["tick"], w, held)
    scene = _deep(_call_all(rt, fn["scene"], w))
    player, enemies, impacts = scene
    assert len(player) == 11
    x, y, z, yaw, pitch, dip, health, weapon, shot, t, restarts = player
    assert t == 30 and restarts == 0 and health == 100 and weapon == 0
    assert z < 0                      # walked forward, along -z
    assert len(enemies) == 4
    for e in enemies:
        assert len(e) == 7 and e[4] == 1 and e[5] == 100
    # holding the trigger for thirty ticks: two blaster shots at 15 apart,
    # and the tick after the second is not a shot
    assert shot == 0
    assert isinstance(impacts, list)


def test_shot_flag_on_the_tick_of_the_shot():
    rt, fn = _api()
    w = fn["new"]
    quiet = _call_all(rt, fn["input"], 0, 0, 0, 0, 0, 0, 0)
    fire = _call_all(rt, fn["input"], 0, 0, 0, 1, 0, 0, 0)
    for _ in range(20):
        w = _call_all(rt, fn["tick"], w, quiet)
    w = _call_all(rt, fn["tick"], w, fire)
    assert _deep(_call_all(rt, fn["scene"], w))[0][8] == 1
    w = _call_all(rt, fn["tick"], w, fire)
    assert _deep(_call_all(rt, fn["scene"], w))[0][8] == 0   # cooling down


def test_scene_through_a_native_session():
    from core.native import open_session
    tree, _report = build(SOURCE)
    session = open_session(tree, "auto", max_steps=50_000_000, max_depth=10_000)
    if session is None:
        pytest.skip("no native runtime built")
    try:
        new = session.get("new")
        tick, held_fn, scene = session.get("tick"), session.get("input"), session.get("scene")
        held = session.call(held_fn, 0, -1, 1, 1, 0, 0, 0)
        w = new
        for _ in range(30):
            w = session.call(tick, w, held)
        got = session.call(scene, w)
        # the Python side, the same thirty ticks
        rt, fn = _api()
        pw = fn["new"]
        pheld = _call_all(rt, fn["input"], 0, -1, 1, 1, 0, 0, 0)
        for _ in range(30):
            pw = _call_all(rt, fn["tick"], pw, pheld)
        want = _deep(_call_all(rt, fn["scene"], pw))
        assert got[0] == want[0]
        assert got[1] == want[1]
    finally:
        session.close()


def _godot():
    env = os.environ.get("GODOT", "").strip()
    if env and Path(env).exists():
        return Path(env)
    for p in (Path(r"D:\game\godot\Godot_v4.7.2-stable_win64_console.exe"),):
        if p.exists():
            return p
    return None


def _kit():
    for p in (Path(r"D:\SSH\Starter-Kit-FPS"),):
        if (p / "project.godot").exists():
            return p
    return None


def test_extension_inside_godot_headless():
    exe, kit = _godot(), _kit()
    dll = ROOT / "native" / "lova-godot" / "target" / "release" / "lova_godot.dll"
    if exe is None or kit is None or not dll.exists():
        pytest.skip("Godot, the FPS kit or the built extension is not on this machine")
    proc = subprocess.run([sys.executable, str(APP / "build.py"), str(kit), "--smoke"],
                          capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    assert "300 ticks:" in out, out
    assert "a float (1.5) cannot enter a LOVA program" in out, out
    assert "a world for an input: <null> -- signalled" in out, out
    assert "SCRIPT ERROR" not in out, out
