"""Neon Alley (`lib/neon.lova`, `apps/web/neon`) and the runtime in a page
(`native/lova-wasm`).

1. the program the page opens builds and its examples -- the rules'
   relations: mirror symmetry, the kerb, the jump that comes down, the
   gate that holds -- pass;
2. the page's own calls, made in Python: `layout` and `scene` answer in
   the shape `rules.js` reads;
3. the same ticks through the WebAssembly module under node, when node
   and a built module are there: what the page would be shown is what
   Python computes, tick for tick.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.examples import check  # noqa: E402
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python  # noqa: E402
from core.tokens import encode  # noqa: E402

APP = ROOT / "apps" / "web" / "neon"
SOURCE = (APP / "neon_web.lova").read_text(encoding="utf-8")
WASM = ROOT / "native" / "lova-wasm" / "target" / "wasm32-unknown-unknown" / "release" / "lova_wasm.wasm"


def _api():
    tree, _report = build(SOURCE)
    rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
    api = evaluate(tree, rt)
    fn = {n: api.entries[_map_key(n, "rec")][1] for n in ("new", "tick", "input", "scene", "layout")}
    return rt, fn


def _call_all(rt, f, *args):
    rt.steps = 0
    rt.mark = 0
    rt.current = None
    for a in args:
        f = _call(f, a, rt)
    return f


def _deep(value):
    if value is None:
        return []
    out = list_to_python(value)
    return [_deep(x) if not isinstance(x, int) else x for x in out]


def _python_ticks(inputs):
    rt, fn = _api()
    w = fn["new"]
    for mx, mz, j in inputs:
        w = _call_all(rt, fn["tick"], w, _call_all(rt, fn["input"], mx, mz, j))
    return _deep(_call_all(rt, fn["scene"], w))


# A walk that turns, jumps, floats and runs into the first drone.
INPUTS = [(0, 1, 0)] * 40 + [(1, 1, 1)] * 25 + [(-1, 0, 0)] * 30 + [(0, 1, 0)] * 60


def test_examples_pass():
    results = check(SOURCE, runtime="native", max_steps=20_000_000)
    assert len(results) >= 16
    missed = [r for r in results if not r["passed"]]
    assert not missed, missed


def test_layout_and_scene_shape():
    rt, fn = _api()
    lay = fn["layout"]
    get = lambda k: lay.entries[_map_key(k, "rec")][1]
    assert get("half-w") == 4 * 65536 and get("length") == 60 * 65536
    sparks = _deep(get("sparks"))
    assert len(sparks) == 15 and all(len(s) == 3 for s in sparks)
    assert len(_deep(get("drones"))) == 6
    ghost, drones, taken = _python_ticks(INPUTS[:10])
    assert len(ghost) == 14 and ghost[11] == 10          # t
    assert len(drones) == 6 and len(taken) == 15


def test_the_page_sees_what_python_computes():
    node = shutil.which("node")
    if node is None or not WASM.exists():
        pytest.skip("no node, or native/lova-wasm not built")
    tree, _report = build(SOURCE)
    hexed = encode(tree).hex()
    script = """
      import { readFileSync } from "node:fs";
      import { LovaRuntime } from %s;
      const rt = await LovaRuntime.load(readFileSync(%s));
      const s = rt.open(%s, { maxSteps: 50000000 });
      const [tick, input, scene] = ["tick", "input", "scene"].map(k => s.get(k));
      let w = s.get("new");
      for (const [mx, mz, j] of %s) {
        const held = s.call(input, [mx, mz, j]);
        const next = s.call(tick, [w, held]);
        s.release([w, held]);
        w = next;
      }
      console.log(JSON.stringify(s.call(scene, [w])));
    """ % (json.dumps((ROOT / "native" / "lova-wasm" / "web" / "lova.js").as_uri()),
           json.dumps(str(WASM)), json.dumps(hexed), json.dumps(INPUTS))
    out = subprocess.run([node, "--input-type=module", "-e", script],
                         capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == _python_ticks(INPUTS)
