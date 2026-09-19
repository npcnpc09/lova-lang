"""Time the apps on the Python runtime and on the native one.

    python tools/bench_native.py            # every row, best of 3
    python tools/bench_native.py 5 war      # 5 runs, rows whose name has "war"

Each row is a program run through the CLI (``python -m core.cli run
... --stats``) with ``--native off`` and ``--native on``, N times each;
the best wall-clock is kept, the step count is read off ``--stats``,
and stdout, the value and the steps must be identical between the two
runtimes or the row is flagged ``DIFF``.

Wall-clock includes what is the same on both sides -- the Python
start, and the parse and compile of the program, which for the 3D
libraries is one to two seconds -- so every program is also run under
``analyze`` (parse and compile, no run) and that floor is subtracted:
the ``eval`` columns are the two evaluators alone, and ``steps/s`` is
the native evaluator's rate.  The 3D apps are driven from Python by
closures called every tick, which the run-once protocol cannot serve,
so ``tools/bench/*.lova`` stand in for them: the world built, N ticks,
one frame, through the CLI.  Stdlib only; needs the built binary
(``native/lova-rt/target/release/lova-rt``) or ``LOVA_NATIVE``.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tools" / "bench"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ONLY = sys.argv[2:]


def notes_10k() -> str:
    """A 10 000-line input for wordfreq, made from the golden fixture."""
    path = BENCH / "notes10k.txt"
    if not path.exists():
        src = (ROOT / "corpus" / "golden" / "fixtures" / "notes.txt").read_text(
            encoding="utf-8").splitlines()
        out = []
        while len(out) < 10000:
            out.extend(src)
        path.write_text("\n".join(out[:10000]) + "\n", encoding="utf-8")
    return str(path)


APPS = [
    # name, args, stdin, allow
    ("coprime 14 15",        ["apps/coprime.lova", "14", "15"], "", None),
    ("is_prime 104729",      ["apps/is_prime.lova", "104729"], "", None),
    ("tictactoe 163",        ["apps/tictactoe.lova", "163"], "3\n", None),
    ("tictactoe 0 (full)",   ["apps/tictactoe.lova", "0"], "5\n", None),
    ("g2048 7",              ["apps/g2048.lova", "7"], "", None),
    ("tanks 7",              ["apps/tanks.lova", "7"], "f\nw\nd\n\nq\n", None),
    ("cube",                 ["apps/cube.lova"], "", None),
    ("maze 0",               ["apps/maze.lova", "0"], "", None),
    ("batch 300 2000",       ["apps/batch.lova", "300", "2000"], "", None),
    ("wordfreq notes 10",    ["apps/wordfreq.lova", "corpus/golden/fixtures/notes.txt", "10"], "", "fs-read"),
    ("wordfreq 10k lines",   ["apps/wordfreq.lova", notes_10k(), "10"], "", "fs-read"),
    ("war terrain",          ["tools/bench/war.lova", "n=0"], "", None),
    ("war terrain+60 ticks", ["tools/bench/war.lova", "n=60"], "", None),
    ("platformer frame",     ["tools/bench/platformer.lova", "n=0"], "", None),
    ("platformer 60t+frame", ["tools/bench/platformer.lova", "n=60"], "", None),
    ("citybuilder frame",    ["tools/bench/citybuilder.lova", "n=0"], "", None),
    ("citybuilder 60t+frame", ["tools/bench/citybuilder.lova", "n=60"], "", None),
]

STATS = re.compile(r"\[(\d+) steps")


def cli(*args, stdin=""):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    t = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "core.cli", *args], cwd=ROOT, input=stdin,
                       capture_output=True, text=True, env=env)
    return time.perf_counter() - t, p


def run(args, stdin, allow, mode):
    cmd = ["run", *args, "--stats", "--native", mode]
    if allow:
        cmd += ["--allow", allow]
    dt, p = cli(*cmd, stdin=stdin)
    m = STATS.search(p.stderr)
    value = [l for l in p.stderr.splitlines() if l.startswith("=>")]
    return dt, int(m.group(1)) if m else None, p.stdout, (value[-1] if value else p.stderr[-200:])


def best(fn):
    out = None
    for _ in range(N):
        r = fn()
        if out is None or r[0] < out[0]:
            out = r
    return out


rows = []
for name, args, stdin, allow in APPS:
    if ONLY and not any(o in name for o in ONLY):
        continue
    floor = best(lambda: cli("analyze", *args))[0]
    off = best(lambda: run(args, stdin, allow, "off"))
    on = best(lambda: run(args, stdin, allow, "on"))
    same = off[1:] == on[1:]
    rows.append({"app": name, "steps": off[1], "floor": floor, "python": off[0], "native": on[0],
                 "same": same})
    print(f"{name:24s} steps={off[1]!s:>9} floor={floor:5.2f}s python={off[0]:6.2f}s "
          f"native={on[0]:6.2f}s {'same' if same else 'DIFF'}", flush=True)

print()
print(f"{'app':24s} {'steps':>9} {'py eval':>8} {'nat eval':>9} {'ratio':>6} {'nat steps/s':>12}")
for r in rows:
    py = max(r["python"] - r["floor"], 0.0)
    nat = max(r["native"] - r["floor"], 0.0)
    ratio = py / nat if nat > 0.02 else float("nan")
    rate = r["steps"] / nat if nat > 0.02 and r["steps"] else float("nan")
    print(f"{r['app']:24s} {r['steps']!s:>9} {py:8.2f} {nat:9.2f} {ratio:6.1f} {rate:12.0f}"
          f"  {'' if r['same'] else 'DIFF'}")
(BENCH / "last_run.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
