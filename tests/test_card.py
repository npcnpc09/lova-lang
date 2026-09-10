"""The one-page card is generated from the language, and does not drift.

`corpus/language_card.md` is what a model gets before it writes LOVA
(Exp 17, the fine-tuning corpus, an MCP host's prompt).  Its library
index comes from `lib/prelude.lova` and its text operators from the
token table; the checked-in file must equal the generator's output,
every public prelude function must be on it, and every example on it
must run.
"""

from __future__ import annotations

import re
import unittest

from corpus.evaluator import evaluate_template
from corpus.make_card import CARD, INTERNAL, prelude_index, render


class Card(unittest.TestCase):

    def test_the_checked_in_card_is_the_generated_one(self):
        self.assertEqual(CARD.read_text(encoding="utf-8"), render(),
                         "run `python -m corpus.make_card`")

    def test_every_public_prelude_function_is_on_the_card(self):
        card = CARD.read_text(encoding="utf-8")
        for _section, defs in prelude_index():
            for sig, _note in defs:
                name = sig[1:].split()[0]
                with self.subTest(name=name):
                    self.assertIn("(" + name, card)

    def test_internal_helpers_are_not(self):
        card = CARD.read_text(encoding="utf-8")
        for name in ("rev-onto", "merge-by", "le2"):
            self.assertNotIn("(" + name + " ", card)
        self.assertTrue(INTERNAL)

    def test_every_text_operator_is_named(self):
        from core.tokens import SIGNATURES, TEXT_FAMILY
        card = CARD.read_text(encoding="utf-8")
        for tok in TEXT_FAMILY:
            with self.subTest(op=SIGNATURES[tok]["name"]):
                self.assertIn(SIGNATURES[tok]["name"], card)

    def test_every_example_runs(self):
        card = CARD.read_text(encoding="utf-8")
        block = card.split("## Examples")[1].split("```")[1]
        programs = []
        buf = ""
        for line in block.splitlines():
            code = line.split(";")[0].rstrip()
            if not code:
                continue
            buf += code
            # A line whose last top-level form is a `def` continues into
            # the next line; anything else ends a program.
            depth, last_start = 0, 0
            for i, ch in enumerate(buf):
                if ch == "(":
                    if depth == 0:
                        last_start = i
                    depth += 1
                elif ch == ")":
                    depth -= 1
            if depth == 0 and not buf[last_start:].startswith("(def"):
                programs.append(buf)
                buf = ""
        self.assertGreaterEqual(len(programs), 5)
        for program in programs:
            with self.subTest(program=program[:50]):
                got = evaluate_template(program, {"n": 12})
                self.assertIsInstance(got, int, got)


if __name__ == "__main__":
    unittest.main()
