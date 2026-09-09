"""Driver for apps/palindrome.lova.

Usage:
    PYTHONPATH=. python apps/palindrome.py racecar level abc
    PYTHONPATH=. python apps/palindrome.py                  # a default set
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from core.compiler import compile as lova_compile
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import encode


PROGRAM_FILE = _HERE / "palindrome.lova"
DEFAULTS = ["racecar", "level", "a", "", "abc", "LOVA"]


def run(word: str) -> int:
    source = PROGRAM_FILE.read_text(encoding="utf-8")
    # The program takes a string literal; the driver quotes it.  Escapes
    # matter here in a way they did not for integers.
    literal = '"' + word.replace("\\", "\\\\").replace('"', '\\"') + '"'
    compiled, _report = lova_compile(parse(source.replace("{s}", literal)))
    rt = Runtime()
    result = evaluate(compiled, rt)
    verdict = "palindrome" if result == 1 else "not a palindrome"
    print(f"  {word!r:<12s} -> {result}  {verdict:<18s} "
          f"[{rt.steps:>5d} steps]")
    return result


def main() -> None:
    words = sys.argv[1:] or DEFAULTS

    # A string is a list of codepoints, so the program's size does not
    # depend on the input -- the input is not part of the program until
    # the driver substitutes it.
    skeleton = PROGRAM_FILE.read_text(encoding="utf-8").replace("{s}", '"ab"')
    print(f"\n  program: {len(encode(parse(skeleton)))} bytes with a "
          "2-character input")
    print("  (strings cost the token table nothing: \"ab\" is sugar for "
          "(cons 97 (cons 98 (nil))))\n")

    for word in words:
        run(word)
    print()


if __name__ == "__main__":
    main()
