"""Generate the one-page language card from the language itself.

    python -m corpus.make_card            # rewrites corpus/language_card.md
    python -m corpus.make_card --check    # exit 1 if the card is stale

The card is what a model gets before it writes LOVA (Exp 17, the
fine-tuning corpus, the MCP host's prompt), so it must not drift from
the library.  The narrative lives in ``corpus/language_card.tmpl.md``;
the library index is read from ``lib/prelude.lova`` -- every `def`,
grouped by the prelude's own section headers, with the one-line
comment written just above it when there is one -- and the text
family's operator names come from the token table.  `tests/test_card.py`
fails when the checked-in card differs from this output.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRELUDE = ROOT / "lib" / "prelude.lova"
TEMPLATE = ROOT / "corpus" / "language_card.tmpl.md"
CARD = ROOT / "corpus" / "language_card.md"

# Helpers the prelude keeps for its own use; a program has no reason to
# call them, so the card does not list them.
INTERNAL = {"le2", "ge2", "iterate", "parse-digits", "space", "digit"}

_SECTION = re.compile(r"^;; --- (.+?) -+\s*$")
_DEF = re.compile(r"^\(def ([^\s\[]+) \[([^\]]*)\]")
_NOTE = re.compile(r"^;; (.+)$")


def prelude_index() -> list:
    """[(section, [(signature, note), ...]), ...] in prelude order."""
    sections: list = []
    current = None
    last_note: list = []
    for line in PRELUDE.read_text(encoding="utf-8").splitlines():
        m = _SECTION.match(line)
        if m:
            current = (m.group(1).strip(), [])
            sections.append(current)
            last_note = []
            continue
        m = _NOTE.match(line)
        if m and current is not None:
            last_note.append(m.group(1).strip())
            continue
        m = _DEF.match(line)
        if m and current is not None:
            name, params = m.group(1), m.group(2).split()
            note = last_note[0] if len(last_note) == 1 else ""
            if name not in INTERNAL:
                current[1].append(("(" + " ".join([name] + params) + ")", note))
            last_note = []
            continue
        if line.strip() == "" or not line.startswith(";;"):
            last_note = []
    return [s for s in sections if s[1]]


def library_block() -> str:
    lines = ["```"]
    for section, defs in prelude_index():
        sigs = [sig for sig, _ in defs]
        row = ""
        rows = []
        for sig in sigs:
            if row and len(row) + 1 + len(sig) > 76:
                rows.append(row)
                row = sig
            else:
                row = (row + " " + sig).strip()
        if row:
            rows.append(row)
        lines.append(f"; {section}")
        lines.extend(rows)
    lines.append("```")
    notes = [(sig, note) for _, defs in prelude_index() for sig, note in defs if note]
    if notes:
        lines.append("")
        lines.append("Notes: " + "  ".join(f"`{sig}` {note.rstrip('.')}." for sig, note in notes))
    return "\n".join(lines)


def text_ops_line() -> str:
    from core.tokens import SIGNATURES, TEXT_FAMILY
    names = [SIGNATURES[t]["name"] for t in sorted(TEXT_FAMILY)]
    return "Text operators: " + " ".join(f"`{n}`" for n in names) + "."


def list_ops_line() -> str:
    from core.tokens import SIGNATURES, LIST_FAMILY
    names = [SIGNATURES[t]["name"] for t in sorted(LIST_FAMILY)]
    return "List operators: " + " ".join(f"`{n}`" for n in names) + "."


# Q113 (Exp 24 run 2, 2026-09-18): every session's one real uncertainty
# was an operator's exact semantics -- is `text-slice` half-open, what
# is `(mod -7 3)`, which way round does `text-join` go -- and a wrong
# guess is a well-typed wrong value with no diagnostic.  The card now
# carries one worked example per operator whose semantics can be bet
# on, and the VALUE IS COMPUTED HERE, by the runtime, when the card is
# generated: the card cannot state a semantics the language does not
# have, and `tests/test_card.py` re-evaluates every line.
OPERATOR_EXAMPLES = [
    ";; integers",
    "(div 7 2)", "(div -7 2)", "(mod -7 3)", "(sub 3 5)", "(if 0 1 2)", "(or 0 5)",
    ";; lists (0-based; `range` stops before b)",
    "(range 1 5)", "(nth (list 5 6 7) 1)", "(take 2 (list 5 6 7))", "(drop 2 (list 5 6 7))",
    "(fold (lambda a (lambda x (sub a x))) 10 (list 1 2))",
    "(sort-by (lambda a (lambda b (gt a b))) (list 3 1 2))",
    "(zip (list 1 2 3) (list 4 5))", "(digits 1048576)", "(head \"abc\")",
    "(text-slice (list 1 2 3 4) 1 3)",
    ";; texts (half-open slices, clamped; -1 for not found)",
    "(text-slice \"hello\" 1 3)", "(text-slice \"hello\" 3 99)",
    "(text-find \"hello\" \"ll\")", "(text-find \"hello\" \"z\")",
    "(text-split \"a,b,,c\" \",\")", "(text-split \" a  b \" \"\")",
    "(text-join (list \"a\" \"b\") \", \")", "(text-trim \"  a \")",
    "(text-chars \"ab\")", "(text-of-chars (list 104 105))", "(text-int \"-7\")", "(int-text 42)",
    "(text-cmp \"a\" \"b\")", "(words \"a b  c\")", "(lines \"a\\nb\")",
    ";; maps and records",
    "(map-get (map-put (nil) \"k\" 1) \"k\" 0)", "(map-get (map-of (nil)) \"k\" 0)",
    "(map-pairs (map-put (map-put (nil) \"a\" 1) \"b\" 2))",
    "(get (rec x 1 y 2) y)", "(get (put (rec x 1) x 9) x)",
]


def operator_examples_block() -> str:
    """Each example with the value the runtime gives it, `expr ; value`."""
    import sys
    sys.path.insert(0, str(ROOT))
    from core.cli import build, format_value
    from core.runtime import Runtime, evaluate
    lines = []
    for expr in OPERATOR_EXAMPLES:
        if expr.startswith(";;"):
            lines.append(expr)
            continue
        tree, _ = build(expr)
        value = format_value(evaluate(tree, Runtime(max_steps=200_000)))
        lines.append(f"{expr:52s} ; {value}")
    return chr(10).join(lines)


def render() -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    return (template.replace("{{LIBRARY}}", library_block())
                    .replace("{{TEXT_OPS}}", text_ops_line())
                    .replace("{{LIST_OPS}}", list_ops_line())
                    .replace("{{OPERATOR_EXAMPLES}}", operator_examples_block()))


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    text = render()
    if "--check" in args:
        current = CARD.read_text(encoding="utf-8") if CARD.exists() else ""
        if current != text:
            print("corpus/language_card.md is stale; run `python -m corpus.make_card`")
            return 1
        print("corpus/language_card.md is current")
        return 0
    CARD.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {CARD} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
