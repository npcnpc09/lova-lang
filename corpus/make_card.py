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
INTERNAL = {"rev-onto", "merge-by", "le2", "ge2", "iterate", "parse-digits", "space", "digit"}

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


def render() -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    return (template.replace("{{LIBRARY}}", library_block())
                    .replace("{{TEXT_OPS}}", text_ops_line()))


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
