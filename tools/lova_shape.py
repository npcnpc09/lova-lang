"""The shape of LOVA source: lines, characters, parentheses, depth, lets.

    python tools/lova_shape.py FILE ...

Code lines are lines with something besides a comment.  Depth is the
deepest parenthesis nesting inside any top-level form, and "deep forms"
the top-level forms nesting past 10.  `let` counts the let forms, and
"let chain" the longest run of lets nested directly in one another --
the thing a multi-binding `let` flattens.  Used to measure what the
surface sugar of 2026-09-27 changed (journal).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        in_str = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                in_str = not in_str
            elif ch == ";" and not in_str:
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def shape(path: Path) -> dict:
    code = strip_comments(path.read_text(encoding="utf-8"))
    lines = [l for l in code.splitlines() if l.strip()]
    depth = best = 0
    deep_forms = 0
    form_max = 0
    for ch in code:
        if ch == "(":
            depth += 1
            form_max = max(form_max, depth)
            best = max(best, depth)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                if form_max > 10:
                    deep_forms += 1
                form_max = 0
    lets = len(re.findall(r"\(let[\s\[]", code))
    # the longest chain of lets whose body is directly another let
    chain = best_chain = 0
    tokens = re.findall(r"\(|\)|\[|\]|[^\s()\[\]]+", code)
    for i, t in enumerate(tokens):
        if t == "(" and i + 1 < len(tokens) and tokens[i + 1] == "let":
            chain += 1
            best_chain = max(best_chain, chain)
        elif t == "(":
            pass
        elif t not in ("let", "[", "]") and not (tokens[i - 1] == "let" if i else False):
            pass
    # a simpler proxy for the chain: consecutive lines opening a let
    run = best_run = 0
    for l in lines:
        if l.strip().startswith("(let"):
            run += 1
            best_run = max(best_run, run)
        else:
            run = 0
    return {"code lines": len(lines), "chars": len("".join(l.strip() for l in lines)),
            "parens": code.count("(") + code.count(")"), "max depth": best,
            "forms > 10 deep": deep_forms, "lets": lets, "let lines in a row": best_run}


def main(argv: list[str]) -> None:
    for a in argv:
        p = Path(a)
        s = shape(p)
        print(p.name, "  ".join(f"{k} {v}" for k, v in s.items()))


if __name__ == "__main__":
    main(sys.argv[1:])
