"""Driver for apps/collatz.lova.

Usage:
    PYTHONPATH=. python apps/collatz.py 27         # 111 steps
    PYTHONPATH=. python apps/collatz.py 2463       # exceeds MAX_CALL_DEPTH

A trajectory longer than the substrate's call-depth ceiling is not a
crash: it is a ``DepthTrap`` carrying the same L2 anomaly schema as
every other LOVA trap, so the caller reads ``kind`` / ``detail`` /
``repair_hint`` instead of parsing a stack trace.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from core.compiler import compile as lova_compile
from core.conservation import BudgetTrap
from core.runtime import Runtime, evaluate
from core.surface import parse


PROGRAM_FILE = _HERE / "collatz.lova"


def run(n: int) -> None:
    source = PROGRAM_FILE.read_text(encoding="utf-8").replace("{n}", str(n))
    compiled, _report = lova_compile(parse(source))
    rt = Runtime()
    try:
        result = evaluate(compiled, rt)
    except BudgetTrap as trap:
        anomaly = trap.anomaly
        print(f"  collatz({n}) -> trap")
        print(f"    kind:        {anomaly['kind']}")
        print(f"    detail:      {anomaly['detail']}")
        print(f"    repair hint: {anomaly['repair_hint']}")
        return
    print(f"  collatz({n:>6d}) = {result:>4d} steps   "
          f"[{rt.steps} substrate steps]")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(f"usage: python {sys.argv[0]} <n> [<n> ...]")
        raise SystemExit(2)
    print()
    for arg in args:
        run(int(arg))
    print()


if __name__ == "__main__":
    main()
