"""The step profiler (`native/lova-rt/src/callprof.rs`, `core/profile.py`).

Needs the built runtime (native/lova-rt/target/release/lova-rt); skipped
without it.  What it holds the profiler to: asking for a profile does
not change a call's steps; the self steps add up to the call's steps;
both evaluators put them down to the same closures; the names, the
curried parameters and the folded stacks come out as documented.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cli import build                                     # noqa: E402
from core.native import NativeRuntime, NativeSession           # noqa: E402
from core import profile                                       # noqa: E402

BIN = next((p for p in (ROOT / "native" / "lova-rt" / "target" / "release" / n
                        for n in ("lova-rt.exe", "lova-rt")) if p.is_file()), None)

TOY = """
(def sq [x] (mul x x))
(def fib [n] (if (lt n 2) n (merge (fib (sub n 1)) (fib (sub n 2)))))
(def tick [w k] (merge (fib 8) (sum (map (lambda x (sq x)) (range 0 (merge 3 k))))))
(tick 0 0)
"""


class StripLastForm(unittest.TestCase):
    def test_last_form_goes(self):
        head, last = profile.strip_last_form('(def a [] 1) ; (x)\n(b ")" (c))\n')
        self.assertEqual(last, '(b ")" (c))')
        self.assertEqual(head.strip(), "(def a [] 1) ; (x)")

    def test_range(self):
        self.assertEqual(profile.parse_range("3..9"), (3, 9))
        self.assertEqual(profile.parse_range("7"), (7, 7))


@unittest.skipUnless(BIN, "no native runtime built")
class StepProfile(unittest.TestCase):
    def setUp(self):
        head, _ = profile.strip_last_form(TOY)
        self.tree, _ = build(head + profile.DRIVER.format(init="0", step="(tick w k)"))

    def one(self, mode):
        rt = NativeRuntime([str(BIN), mode], timeout_s=60.0)
        try:
            s = NativeSession(rt, self.tree, max_steps=10 ** 8)
            w = s.call(s.get("init"), 0)
            s.call(s.get("step"), w, 4)
            plain = s.steps
            self.assertIsNone(s.profile)
            s.call(s.get("step"), w, 4, profile=True)
            self.assertEqual(s.steps, plain, "profiling changed the steps")
            rows = s.profile
            s.close()
            return plain, rows
        finally:
            rt.close()

    def test_adds_up_and_evaluators_agree(self):
        steps, rows = self.one("--vm")
        self.assertEqual(rows[0][5], steps)
        self.assertEqual(sum(profile._selfs(rows)), steps)
        tsteps, trows = self.one("--tree")
        self.assertEqual(tsteps, steps)
        self.assertEqual(trows, rows)

    def test_names_and_tables(self):
        steps, rows = self.one("--vm")
        namer = profile.Namer(self.tree)
        p = profile.Profile(namer)
        p.add(rows, steps, 4)
        labels = {k[0] for k in p.self_}
        self.assertTrue({"fib", "sq", "tick/2", "tick/lambda"} <= labels, labels)
        fib = next(k for k in p.self_ if k[0] == "fib")
        self.assertEqual(p.count[fib], 67)                 # fib 8's calls
        # recursion: fib's inclusive is its outermost activation's only
        self.assertEqual(p.incl[fib], p.self_[fib])
        self.assertIn("fib", p.table().splitlines()[1])
        stacks = p.folded_text().splitlines()
        self.assertTrue(any(s.startswith("(call);tick/2;fib;fib ") for s in stacks))
        self.assertEqual(sum(int(s.rsplit(" ", 1)[1]) for s in stacks), steps)


if __name__ == "__main__":
    unittest.main()
