"""ttt_check.py  --  the pair of Exp 29 checked against each other.

(a) The eight cases in ttt_tests.json run through the Python `solve`.
(b) Every legal reachable noughts-and-crosses position is enumerated by
    playing all games from the empty board (5478 of them); a sample of
    300, drawn with a fixed seed, is run through the LOVA program
    in-process and through the Python `solve`, and the two texts must
    agree on every one.

    python experiments/exp29/ttt_check.py [--all]
"""

import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.cli import build, substitute, format_value          # noqa: E402
from core.runtime import Runtime, evaluate                    # noqa: E402

import ttt                                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = open(os.path.join(HERE, "ttt.lova"), encoding="utf-8").read()

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
         (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def run_lova(board):
    tree, _ = build(substitute(SOURCE, ["board=" + board]))
    out = format_value(evaluate(tree, Runtime(max_steps=50_000_000)))
    return out[1:-1] if out.startswith('"') else out


def decided(cells):
    for a, b, c in LINES:
        if cells[a] != "." and cells[a] == cells[b] == cells[c]:
            return True
    return "." not in cells


def reachable():
    """Every position reachable by legal play, terminal ones included."""
    seen = set()

    def walk(cells, turn):
        text = "".join(cells)
        if text in seen:
            return
        seen.add(text)
        if decided(cells):
            return
        for k in range(9):
            if cells[k] == ".":
                walk(cells[:k] + [turn] + cells[k + 1:], "O" if turn == "X" else "X")

    walk(["."] * 9, "X")
    return sorted(seen)


def main():
    cases = json.load(open(os.path.join(HERE, "ttt_tests.json"), encoding="utf-8"))
    for case in cases:
        board = case["inputs"]["board"]
        got = ttt.solve(board)
        assert got == case["expected"], (board, got, case["expected"])
        lova = run_lova(board)
        assert lova == case["expected"], (board, lova, case["expected"])
    print(f"tests: {len(cases)}/{len(cases)} agree in both languages")

    positions = reachable()
    print(f"reachable positions: {len(positions)}")
    if "--all" in sys.argv:
        sample = positions
    else:
        sample = random.Random(29).sample(positions, 300)
    for i, board in enumerate(sample):
        a = run_lova(board)
        b = ttt.solve(board)
        assert a == b, (board, a, b)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(sample)} agree")
    print(f"positions: {len(sample)}/{len(sample)} agree "
          f"(LOVA and Python, identical text)")


if __name__ == "__main__":
    main()
