"""fleet_check.py -- the pair kept honest.

(a) The eight stated tests through the Python `solve`.
(b) 120 random sweeps through both the LOVA program and the Python
    one, asserting they agree on every character.

    cd /d/SSH/lova-lang && export PYTHONPATH="$PWD" && \
      python experiments/exp29/fleet_check.py
"""

from __future__ import annotations

import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from core.cli import build, format_value, substitute          # noqa: E402
from core.runtime import Runtime, evaluate                    # noqa: E402

import fleet as py_fleet                                      # noqa: E402

SOURCE = io.open(os.path.join(HERE, "fleet.lova"), encoding="utf-8").read()
NL = chr(10)


def lova(sweep: str) -> str:
    """Run `fleet.lova` on one sweep and give back the text it produced.

    `substitute` keeps a multi-line value: `argument_literal` escapes a
    backslash and a quote, and the lexer reads a raw newline inside a
    literal, so the text arrives whole.
    """
    tree, _report = build(substitute(SOURCE, ["sweep=" + sweep]))
    shown = format_value(evaluate(tree, Runtime(max_steps=20_000_000)))
    assert shown.startswith('"') and shown.endswith('"'), shown
    body = shown[1:-1]
    out = []
    i = 0
    while i < len(body):
        if body[i] == chr(92) and i + 1 < len(body):
            out.append({"n": NL, "t": chr(9), "r": chr(13),
                        '"': '"', chr(92): chr(92)}.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


# --- (a) the stated tests ---------------------------------------------

def stated() -> int:
    cases = json.load(io.open(os.path.join(HERE, "fleet_tests.json"),
                              encoding="utf-8"))
    for n, case in enumerate(cases, 1):
        got = py_fleet.solve(case["inputs"]["sweep"])
        assert got == case["expected"], (
            "test %d: expected %r, got %r" % (n, case["expected"], got))
    return len(cases)


# --- (b) 120 random sweeps --------------------------------------------

NAMES = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
         "hotel", "india", "juliet", "kilo", "lima", "srv001", "srv002",
         "a", "zzz"]


def reading(rng: random.Random, kind: str) -> str:
    """A reading around its threshold, so the levels land on the edges."""
    if kind == "cpu":
        whole = rng.choice([0, 3, 12, 40, 62, 84, 85, 86, 94, 95, 96, 99, 100])
        return "%d.%d" % (whole, rng.randint(0, 9))
    if kind == "mem":
        total = rng.choice([7823, 1024, 16000, 1, 0])
        used = rng.randint(0, max(total, 1))
        pct = 0 if total == 0 else (1000 * used) // total
        return "%d/%dMB (%d.%d%%)" % (used, total, pct // 10, pct % 10)
    if kind == "disk":
        return "%dG/40G (%d%%)" % (rng.randint(0, 40),
                                   rng.choice([3, 12, 31, 55, 79, 80, 81, 89, 90, 91, 100]))
    if kind == "load":
        return "%d.%02d %d.%02d %d.%02d" % (
            rng.choice([0, 0, 1, 3, 5, 7, 8, 9, 15, 16, 17]), rng.randint(0, 99),
            rng.randint(0, 20), rng.randint(0, 99),
            rng.randint(0, 20), rng.randint(0, 99))
    return rng.choice(["up 3 weeks, 2 days, 4 hours", "up 1 min",
                       "up 200 days, 11:04"])


def block(rng: random.Random, name: str) -> str:
    """A machine's block: its name, then its health output -- sometimes
    with a marker missing, sometimes with nothing at all after it."""
    if rng.random() < 0.10:
        return name                                   # never answered
    kinds = ["cpu", "mem", "disk", "load", "uptime"]
    if rng.random() < 0.15:
        kinds.remove(rng.choice(kinds))               # a marker missing
    lines = [name]
    for kind in kinds:
        lines.append("___" + kind + "___")
        if rng.random() < 0.03:
            continue                                  # an empty value
        lines.append(reading(rng, kind))
    return NL.join(lines)


def sweep_of(rng: random.Random) -> str:
    n = rng.randint(1, 6)
    names = rng.sample(NAMES, n)
    blocks = [block(rng, name) for name in names]
    if rng.random() < 0.2:
        blocks.append("")                             # a trailing `---`
    return (NL + "---" + NL).join(blocks)


def random_agreement(n: int = 120) -> int:
    rng = random.Random(29)
    for i in range(n):
        sweep = sweep_of(rng)
        want = lova(sweep)
        got = py_fleet.solve(sweep)
        assert got == want, (
            "sweep %d disagrees:%s--- LOVA ---%s%s%s--- Python ---%s%s%s"
            "--- input ---%s%s" % (i, NL, NL, want, NL, NL, got, NL, NL, sweep))
    return n


if __name__ == "__main__":
    a = stated()
    b = random_agreement()
    print("%d stated tests pass through the Python solve" % a)
    print("%d random sweeps: LOVA and Python agree on every one" % b)
