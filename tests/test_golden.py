"""The golden set a native runtime is checked against.

`tools/golden.py` writes `corpus/golden/*.jsonl`; `tools/conformance.py`
replays a file against a runtime.  Two things are worth a test: that
the set is there and big enough to mean something, and that the Python
runtime reproduces it *from the bytes alone* -- which is the property
the port depends on, because a port never sees the source text.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

GOLDEN = ROOT / "corpus" / "golden"

FIELDS = {"id", "source", "args", "prelude", "bytes", "bytes_uncompiled",
          "stdin", "allow", "max_steps", "max_depth", "expect", "steps",
          "max_depth_seen", "hot", "stdout", "deterministic", "reason"}


def records(name: str):
    path = GOLDEN / f"{name}.jsonl"
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class TheSet(unittest.TestCase):

    def test_the_files_are_there_with_enough_records(self):
        files = sorted(GOLDEN.glob("*.jsonl"))
        self.assertTrue(files, f"no golden files in {GOLDEN}; run tools/golden.py")
        deterministic = 0
        for path in files:
            rows = records(path.stem)
            self.assertTrue(rows, f"{path.name} is empty")
            for row in rows:
                self.assertEqual(set(row), FIELDS, f"{row.get('id')}: wrong fields")
                self.assertIn(("value" in row["expect"]) or ("anomaly" in row["expect"]),
                              (True,), f"{row['id']}: expect has neither value nor anomaly")
                bytes.fromhex(row["bytes"])          # decodes as hex
            deterministic += sum(1 for r in rows if r["deterministic"])
        self.assertGreaterEqual(deterministic, 300,
                                "the golden set should carry at least 300 "
                                "deterministic records")

    def test_every_anomaly_kind_is_covered(self):
        kinds = {r["expect"]["anomaly"]["kind"] for r in records("traps")
                 if "anomaly" in r["expect"]}
        from core.conservation import ANOMALY_CODES
        self.assertEqual(kinds, set(ANOMALY_CODES))


class Conformance(unittest.TestCase):
    """`conformance --runtime python` on the two hand-made groups."""

    def _run(self, name: str) -> None:
        import conformance
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = conformance.main([str(GOLDEN / f"{name}.jsonl"),
                                     "--runtime", "python"])
        self.assertEqual(code, 0, out.getvalue())

    def test_the_card_examples_replay_from_their_bytes(self):
        self._run("card")

    def test_the_fault_programs_replay_from_their_bytes(self):
        self._run("traps")


if __name__ == "__main__":
    unittest.main()
