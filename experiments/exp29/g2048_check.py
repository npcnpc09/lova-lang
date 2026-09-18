"""Check the pair: the LOVA 2048 engine and its Python transliteration.

Two halves.  First the eight stated tests in `g2048_tests.json` are run
through the Python `solve` and compared with the `expected` the LOVA
program printed.  Then a hundred and fifty random boards and random
move texts are run through both programs and compared to each other --
the whole point of the pair being that the two agree everywhere, so
that a fault planted at one place in one of them shows up as a
disagreement and nowhere else.

    python experiments/exp29/g2048_check.py

Exits non-zero on the first disagreement, naming the inputs.
"""

from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core.cli import build, format_value, substitute            # noqa: E402
from core.runtime import Runtime, evaluate                      # noqa: E402

from g2048 import solve                                         # noqa: E402

LOVA_PATH = os.path.join(HERE, "g2048.lova")
TESTS_PATH = os.path.join(HERE, "g2048_tests.json")

VALUES = [0, 0, 0, 2, 2, 4, 4, 8, 16, 32, 64, 128, 256, 512]
LETTERS = "urdl"


def run_lova(source: str, board: str, moves: str) -> str:
    """The text the LOVA program prints, quotes off."""
    tree, _report = build(substitute(source, [f"board={board}", f"moves={moves}"]))
    out = format_value(evaluate(tree, Runtime(max_steps=20_000_000)))
    return out[1:-1] if out.startswith('"') and out.endswith('"') else out


def main() -> int:
    with open(LOVA_PATH, encoding="utf-8") as handle:
        source = handle.read()
    with open(TESTS_PATH, encoding="utf-8") as handle:
        tests = json.load(handle)

    for i, case in enumerate(tests):
        board, moves = case["inputs"]["board"], case["inputs"]["moves"]
        got = solve(board, moves)
        assert got == case["expected"], (
            f"test {i}: board={board!r} moves={moves!r}\n"
            f"  python   {got!r}\n  expected {case['expected']!r}")
    print(f"the {len(tests)} stated tests pass against the Python solve")

    random.seed(2048)
    agreed = 0
    for _ in range(150):
        board = " ".join(str(random.choice(VALUES)) for _ in range(16))
        moves = "".join(random.choice(LETTERS)
                        for _ in range(random.randint(1, 5)))
        want = run_lova(source, board, moves)
        got = solve(board, moves)
        assert got == want, (
            f"board={board!r} moves={moves!r}\n"
            f"  lova   {want!r}\n  python {got!r}")
        agreed += 1
    print(f"{agreed} random cases: LOVA and Python agree on every one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
