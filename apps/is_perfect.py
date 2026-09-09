"""Driver for apps/is_perfect.lova  --  the first real LOVA program.

Usage:
    PYTHONPATH=. python apps/is_perfect.py 6       # perfect
    PYTHONPATH=. python apps/is_perfect.py 12      # not perfect
    PYTHONPATH=. python apps/is_perfect.py 28      # perfect
    PYTHONPATH=. python apps/is_perfect.py 496     # perfect

The driver does the full LOVA compile + analyse + evaluate pipeline
and prints a trace that shows every step of the substrate at work:

    1. Read the .lova source
    2. Substitute the input placeholder
    3. Parse (surface -> Node tree)
    4. Static analyse (what will it do?)
    5. Compile (scope + type + fold)
    6. Encode (Node tree -> integer bytes)
    7. Evaluate (return integer + any surprise events)
    8. Report result
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from core.compiler import compile as lova_compile
from core.observability import static_analyze
from core.runtime import Runtime, evaluate
from core.surface import parse, pretty
from core.tokens import decode, encode


PROGRAM_FILE = _HERE / "is_perfect.lova"


def _hr(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run(n: int) -> None:
    print(f"\nLOVA first program: is_perfect(n)   with n = {n}")

    # --- 1. read the source ----------------------------------------------
    source = PROGRAM_FILE.read_text(encoding="utf-8")
    _hr("1. Source  (apps/is_perfect.lova)")
    for line in source.splitlines():
        print(f"  {line}")

    # --- 2. substitute -----------------------------------------------------
    concrete = source.replace("{n}", str(n))

    # --- 3. parse ----------------------------------------------------------
    tree = parse(concrete)
    _hr("2. Parsed (Node tree)")
    print(f"  {pretty(tree)}")

    # --- 4. static analyse -------------------------------------------------
    analysis = static_analyze(tree)
    _hr("3. Static analysis (what will it do?)")
    print(analysis.summary())

    # --- 5. compile --------------------------------------------------------
    compiled, report = lova_compile(tree)
    _hr("4. Compile (scope + type + fold)")
    print(f"  passes run:   {', '.join(report.passes)}")
    print(f"  node count:   {report.original_nodes} -> {report.compiled_nodes}")
    print(f"  compiled:     {pretty(compiled)}")

    # --- 6. encode to canonical integer form --------------------------------
    raw_bytes = encode(tree)
    folded_bytes = encode(compiled)
    _hr("5. Encoded (integer bytes  --  Axiom 1: program IS an integer)")
    print(f"  raw    ({len(raw_bytes):>3} B):  {raw_bytes.hex(' ')}")
    print(f"  folded ({len(folded_bytes):>3} B):  {folded_bytes.hex(' ')}")
    print(f"  folded as integer: {int.from_bytes(folded_bytes, 'big')}")

    # --- 7. evaluate ------------------------------------------------------
    rt = Runtime()
    result = evaluate(compiled, rt)
    _hr("6. Execute")
    if rt.surprise.events:
        print(f"  surprise trace ({len(rt.surprise.events)} event(s)):")
        for ev in rt.surprise.events:
            print(f"    predicted={ev['predicted']}  actual={ev['actual']}  "
                  f"deviation={ev['deviation']}  ctx={ev['ctx']!r}")
    else:
        print(f"  (no surprise events  --  likely the folded program is pure)")
    print(f"  returned value: {result}")

    # --- 8. interpret ----------------------------------------------------
    _hr("7. Result")
    if result == 1:
        print(f"  {n} IS a perfect number  (sigma({n}) = 2 x {n})")
    else:
        # Compute the actual deviation for the human-readable explanation
        from core.runtime import sigma
        sig = sigma(n)
        dev = abs(2 * n - sig)
        print(f"  {n} is NOT perfect.")
        print(f"  sigma({n}) = {sig};  2 x {n} = {2 * n};  deviation = {dev}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"usage: python {sys.argv[0]} <n>")
        print(f"examples: 6, 12, 28, 496")
        sys.exit(2)
    run(int(sys.argv[1]))


if __name__ == "__main__":
    main()
