"""Driver for apps/coprime.lova.

Usage:
    PYTHONPATH=. python apps/coprime.py 12 18      # gcd=6, not coprime
    PYTHONPATH=. python apps/coprime.py 7 13       # gcd=1, coprime
    PYTHONPATH=. python apps/coprime.py 100 101    # consecutive, coprime
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from core.compiler import compile as lova_compile
from core.runtime import Runtime, evaluate
from core.surface import parse, pretty


PROGRAM_FILE = _HERE / "coprime.lova"


def run(a: int, b: int) -> None:
    source = PROGRAM_FILE.read_text(encoding="utf-8")
    concrete = source.replace("{a}", str(a)).replace("{b}", str(b))
    tree = parse(concrete)
    compiled, report = lova_compile(tree)
    rt = Runtime()
    result = evaluate(compiled, rt)

    print(f"\n  coprime({a}, {b}):  {pretty(compiled)}")
    if rt.surprise.events:
        ev = rt.surprise.events[0]
        print(f"  surprise: predicted={ev['predicted']} actual={ev['actual']} "
              f"deviation={ev['deviation']}")
    verdict = "COPRIME" if result == 1 else f"NOT coprime (shares gcd with {a},{b})"
    print(f"  -> {verdict}")


def main() -> None:
    if len(sys.argv) < 3:
        print(f"usage: python {sys.argv[0]} <a> <b>")
        sys.exit(2)
    run(int(sys.argv[1]), int(sys.argv[2]))


if __name__ == "__main__":
    main()
