"""Driver for apps/is_prime.lova.

Usage:
    PYTHONPATH=. python apps/is_prime.py 97        # prime
    PYTHONPATH=. python apps/is_prime.py 91        # 7 x 13
    PYTHONPATH=. python apps/is_prime.py 1 2 3 4 5 # several at once
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from core.compiler import compile as lova_compile
from core.observability import static_analyze
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import encode


PROGRAM_FILE = _HERE / "is_prime.lova"


def run(n: int) -> int:
    source = PROGRAM_FILE.read_text(encoding="utf-8").replace("{n}", str(n))
    compiled, _report = lova_compile(parse(source))
    rt = Runtime()
    result = evaluate(compiled, rt)
    print(f"  is-prime({n:>5d}) = {result}   "
          f"[{rt.steps:>5d} substrate steps, depth <= {rt.max_call_depth}]")
    return result


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(f"usage: python {sys.argv[0]} <n> [<n> ...]")
        raise SystemExit(2)

    # What the program is, before running it: an integer sequence and a
    # static summary.  Both are available to an AI caller ahead of time.
    tree = parse(PROGRAM_FILE.read_text(encoding="utf-8").replace("{n}", "0"))
    data = encode(tree)
    analysis = static_analyze(tree)
    print(f"\n  program: {len(data)} bytes, {analysis.node_count} nodes, "
          f"cost bounded: {analysis.is_cost_bounded}")
    print("  (a program that can call a function has no static cost bound; "
          "the substrate's step ceiling is the real one)\n")

    for arg in args:
        run(int(arg))
    print()


if __name__ == "__main__":
    main()
