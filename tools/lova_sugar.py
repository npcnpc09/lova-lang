"""Rewrite LOVA source into the 2026-09-27 surface sugar, mechanically.

    python tools/lova_sugar.py FILE [--write]

Three rewrites, each of which compiles to exactly the bytes it replaces:

- a chain of one-name lets, `(let a x (let b y body))`, becomes one
  multi-binding let, `(let [a x b y] body)`; comment lines inside the
  chain move above it;
- nested puts, `(put (put r a 1) b 2)`, become one, `(put r a 1 b 2)`,
  a field a line when it would be long;
- a chain of one-parameter lambdas, `(lambda a (lambda b body))`,
  becomes `(fn [a b] body)`.

Everything else -- values, bodies, comments -- is kept as written: the
tool splices text by spans and re-indents what it moves, it does not
pretty-print.  Without `--write` it prints the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

NL = "\n"


class Tok:
    __slots__ = ("text", "start", "end")

    def __init__(self, text, start, end):
        self.text, self.start, self.end = text, start, end


def tokenize(src: str):
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif c == ";":
            while i < n and src[i] != NL:
                i += 1
        elif c in "()[]":
            out.append(Tok(c, i, i + 1))
            i += 1
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == chr(92) else 1
            out.append(Tok(src[i:j + 1], i, j + 1))
            i = j + 1
        else:
            j = i
            while j < n and not src[j].isspace() and src[j] not in "()[];\"":
                j += 1
            out.append(Tok(src[i:j], i, j))
            i = j
    return out


class Node:
    """A list or an atom, with its span in the source."""
    __slots__ = ("items", "atom", "start", "end", "bracket")

    def __init__(self, start, end, items=None, atom=None, bracket=False):
        self.start, self.end, self.items, self.atom, self.bracket = start, end, items, atom, bracket


def parse(toks, i=0):
    t = toks[i]
    if t.text in "([":
        close = ")" if t.text == "(" else "]"
        items = []
        i += 1
        while toks[i].text != close:
            node, i = parse(toks, i)
            items.append(node)
        return Node(t.start, toks[i].end, items=items, bracket=t.text == "["), i + 1
    return Node(t.start, t.end, atom=t.text), i + 1


def parse_all(src):
    toks = tokenize(src)
    nodes, i = [], 0
    while i < len(toks):
        node, i = parse(toks, i)
        nodes.append(node)
    return nodes


def head(node):
    return node.items[0].atom if node.items and node.items[0].atom else None


def is_single_let(node):
    return (node.items is not None and not node.bracket and head(node) == "let"
            and len(node.items) == 4 and node.items[1].atom is not None)


def is_lambda(node):
    return (node.items is not None and not node.bracket and head(node) == "lambda"
            and len(node.items) == 3 and node.items[1].atom is not None)


def is_put(node):
    return node.items is not None and not node.bracket and head(node) == "put" and len(node.items) >= 4


def comments_in(src, a, b):
    """Comment lines between offsets a and b, as written."""
    return [line.strip() for line in src[a:b].split(NL) if line.strip().startswith(";")]


def moved(text, old_col, new_col):
    """`text`, first written at column `old_col`, set at `new_col`: every
    line after the first shifted by the difference."""
    d = new_col - old_col
    if d == 0 or NL not in text:
        return text
    lines = text.split(NL)
    out = [lines[0]]
    for line in lines[1:]:
        if d > 0:
            out.append(" " * d + line if line.strip() else line)
        else:
            strip = min(-d, len(line) - len(line.lstrip(" ")))
            out.append(line[strip:])
    return NL.join(out)


def rewrite(src: str, base: int = 0) -> str:
    """One pass: the outermost rewritable forms, innermost text kept.
    `src` begins at column `base` of the file it came from."""
    edits = []   # (start, end, text)

    def cl(offset):
        nl = src.rfind(NL, 0, offset)
        return offset - nl - 1 + (base if nl < 0 else 0)

    def sub(node, at_col):
        """The text of `node`, rewritten, as it will stand at `at_col`."""
        return moved(rewrite(src[node.start:node.end], cl(node.start)), cl(node.start), at_col)

    def visit(node):
        if node.items is None:
            return
        col = cl(node.start)
        if is_single_let(node) and is_single_let(node.items[3]):
            pairs, gaps = [], []
            cur = node
            while is_single_let(cur):
                pairs.append((cur.items[1].atom, cur.items[2]))
                nxt = cur.items[3]
                gaps.append((cur.items[2].end, nxt.start))
                cur = nxt
            notes = []
            for a, b in gaps:
                notes.extend(comments_in(src, a, b))
            binds = []
            for k, (name, value) in enumerate(pairs):
                binds.append(("" if k == 0 else " " * (col + 6)) + name + " " + sub(value, col + 6 + len(name) + 1))
            text = "(let [" + NL.join(binds) + "]" + NL + " " * (col + 2) + sub(cur, col + 2) + ")"
            if notes:
                text = (NL + " " * col).join(notes) + NL + " " * col + text
            edits.append((node.start, node.end, text))
            return
        if is_lambda(node) and is_lambda(node.items[2]):
            params = []
            cur = node
            while is_lambda(cur):
                params.append(cur.items[1].atom)
                cur = cur.items[2]
            head_text = "(fn [" + " ".join(params) + "] "
            if NL in src[node.start:cur.start]:
                text = head_text.rstrip() + NL + " " * (col + 2) + sub(cur, col + 2) + ")"
            else:
                text = head_text + sub(cur, col + len(head_text)) + ")"
            edits.append((node.start, node.end, text))
            return
        if is_put(node) and is_put(node.items[1]) and len(node.items) % 2 == 0:
            chain = []
            cur = node
            while is_put(cur) and len(cur.items) % 2 == 0:
                chain.append(cur.items[2:])
                cur = cur.items[1]
            base_text = sub(cur, col + 5)
            fields = []
            for group in reversed(chain):
                for k in range(0, len(group), 2):
                    fields.append((src[group[k].start:group[k].end], group[k + 1]))
            flat = [(f, rewrite(src[v.start:v.end], cl(v.start))) for f, v in fields]
            one_line = "(put " + base_text + " " + " ".join(f + " " + v for f, v in flat) + ")"
            if NL not in one_line and col + len(one_line) <= 100:
                text = one_line
            else:
                pad = " " * (col + 5)
                lines = ["(put " + base_text]
                for f, v in fields:
                    lines.append(pad + f + " " + sub(v, col + 5 + len(f) + 1))
                text = NL.join(lines) + ")"
            edits.append((node.start, node.end, text))
            return
        for child in node.items:
            visit(child)

    for node in parse_all(src):
        visit(node)
    out = src
    for a, b, text in sorted(edits, reverse=True):
        out = out[:a] + text + out[b:]
    return out


def main(argv):
    write = "--write" in argv
    for a in [x for x in argv if not x.startswith("--")]:
        p = Path(a)
        new = rewrite(p.read_text(encoding="utf-8"))
        if write:
            p.write_text(new, encoding="utf-8")
            print("rewrote", p)
        else:
            sys.stdout.write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
