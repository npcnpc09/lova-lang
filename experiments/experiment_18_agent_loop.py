"""Experiment 18 -- the agent loop: the four numbers, measured.

    python experiments/experiment_18_agent_loop.py tasks
    python experiments/experiment_18_agent_loop.py submit --lang lova --task t02 --file t02.lova
    python experiments/experiment_18_agent_loop.py patch  --task t02 --span 12 30 --replacement "(merge a b)"
    python experiments/experiment_18_agent_loop.py report --lang lova
    python experiments/experiment_18_agent_loop.py dry-run

`spec/ai-convenience.md` turns the goal into numbers: attempts from the
first emission to green, the feedback context read per failure, the
tokens emitted across attempts (a patch counting as its own size),
the scaffolding the host needed, and reuse.  This is the harness that
produces the first four.

An agent -- a fresh session with no repository access -- gets ten
tasks that need loops, lists and text, and one command: `submit`.  It
runs the answer against the task's tests and prints the feedback the
agent gets to read: for LOVA the structured anomaly (kind, excerpt,
line, repair hint) or the first failing test; for Python the last
lines of the traceback, as a tool would give them.  `patch` lets the
LOVA agent replace one span of its last submission, which counts as
the size of the replacement.  Every call is logged to
``experiments/results_18/<lang>/log.jsonl`` with what was emitted and
what was read back; `report` adds it up.

Scaffolding is recorded, not measured: a LOVA answer runs in-process
under a 200 000-node budget with no capability granted; a Python
answer needs a subprocess and a wall-clock timeout, because nothing in
the language bounds it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_18"
BUDGET = 200_000
PY_TIMEOUT = 10.0


# --- the tasks ---------------------------------------------------------------

@dataclass
class Task:
    id: str
    prompt: str
    inputs: Tuple[str, ...]
    tests: List[Dict[str, Any]]           # {"inputs": {...}, "expected": int}


def _balanced(s):
    d = 0
    for c in s:
        d += 1 if c == "(" else -1
        if d < 0:
            return 0
    return 1 if d == 0 else 0


def _rpn(s):
    st = []
    for t in s.split():
        if t in "+-*":
            b, a = st.pop(), st.pop()
            st.append(a + b if t == "+" else a - b if t == "-" else a * b)
        else:
            st.append(int(t))
    return st[-1]


def _lis(s):
    xs = [int(t) for t in s.split()]
    best = run = 1
    for i in range(1, len(xs)):
        run = run + 1 if xs[i] > xs[i - 1] else 1
        best = max(best, run)
    return best


def _roman(s):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, c in enumerate(s):
        if i + 1 < len(s) and v[c] < v[s[i + 1]]:
            total -= v[c]
        else:
            total += v[c]
    return total


def _kth(a, b, k):
    xs = sorted([int(t) for t in a.split()] + [int(t) for t in b.split()])
    return xs[k - 1]


def _bsearch(s, target):
    xs = [int(t) for t in s.split()]
    lo, hi = 0, len(xs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if xs[mid] == target:
            return mid
        if xs[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def _topword(s):
    counts: Dict[str, int] = {}
    for w in s.split():
        counts[w] = counts.get(w, 0) + 1
    return max(counts.values())


def _trace_sq(s, n):
    a = [int(t) for t in s.split()]
    return sum(sum(a[i * n + k] * a[k * n + i] for k in range(n)) for i in range(n))


def _runs(s):
    return sum(1 for i, c in enumerate(s) if i == 0 or c != s[i - 1])


def _change(coins, amount):
    cs = [int(t) for t in coins.split()]
    best = [0] + [None] * amount
    for a in range(1, amount + 1):
        opts = [best[a - c] for c in cs if c <= a and best[a - c] is not None]
        best[a] = min(opts) + 1 if opts else None
    return -1 if best[amount] is None else best[amount]


def _task(id, prompt, inputs, oracle, cases):
    return Task(id, prompt, inputs,
                [{"inputs": dict(zip(inputs, case)), "expected": oracle(*case)} for case in cases])


TASKS: List[Task] = [
    _task("t01", "Given a text s of only the characters ( and ), return 1 if the parentheses are balanced and 0 otherwise.",
          ("s",), _balanced, [("(()())",), ("(()",), (")(",)]),
    _task("t02", "Given a text s of space-separated tokens, each an integer or one of + - *, evaluate it as reverse Polish notation and return the result.",
          ("s",), _rpn, [("3 4 + 2 *",), ("5 1 2 + 4 * + 3 -",), ("2 3 -",)]),
    _task("t03", "Given a text s of space-separated integers, return the length of the longest strictly increasing run of consecutive elements.",
          ("s",), _lis, [("1 2 3 1 2",), ("5 4 3",), ("1 1 2 3",)]),
    _task("t04", "Given a text s that is a Roman numeral (I V X L C D M, with the subtractive forms), return its value.",
          ("s",), _roman, [("XIV",), ("MCMXCIV",), ("IX",)]),
    _task("t05", "Given two texts a and b, each of space-separated integers in ascending order (possibly empty), and an integer k >= 1, return the k-th smallest integer of the two lists together.",
          ("a", "b", "k"), _kth, [("1 3 5", "2 4", 3), ("1 2", "3 4", 4), ("", "7", 1)]),
    _task("t06", "Given a text s of space-separated integers in ascending order and an integer target, return the 0-based index of target in the list, or -1 if it is absent.",
          ("s", "target"), _bsearch, [("1 3 5 7", 5), ("1 3 5 7", 4), ("", 1)]),
    _task("t07", "Given a text s of space-separated words, return how many times the most frequent word occurs.",
          ("s",), _topword, [("a b a c a b",), ("x",), ("one two two",)]),
    _task("t08", "Given a text s of n*n integers in row-major order and the integer n, let A be that n-by-n matrix; return the sum of the main diagonal of A times A (the matrix product).",
          ("s", "n"), _trace_sq, [("1 2 3 4", 2), ("1 0 0 1", 2), ("2", 1)]),
    _task("t09", "Given a text s, return the number of runs of equal consecutive characters (so aaabbc has 3).",
          ("s",), _runs, [("aaabbc",), ("abc",), ("aaaa",)]),
    _task("t10", "Given a text coins of space-separated positive integers (the coin values) and an integer amount, return the smallest number of coins that sum exactly to amount, or -1 if no combination does.",
          ("coins", "amount"), _change, [("1 5 10", 27), ("2", 3), ("1 3 4", 6)]),
]
BY_ID = {t.id: t for t in TASKS}


# --- running an answer -------------------------------------------------------

def run_lova(program: str, task: Task) -> Dict[str, Any]:
    from core.mcp_server import tool_execute
    failures = []
    for test in task.tests:
        # A text is quoted so that "7" stays a text (Exp 19's first finding).
        args = [f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}" for k, v in test["inputs"].items()]
        r = tool_execute({"source": program, "args": args, "allow": [], "max_steps": BUDGET})
        expected = test["expected"]
        got_key = "value_text" if isinstance(expected, str) else "value_int"
        if r["ok"] and r.get(got_key) == expected:
            continue
        failure: Dict[str, Any] = {"inputs": test["inputs"], "expected": test["expected"]}
        if r["ok"]:
            failure["got"] = r.get("value")
        else:
            a = r["anomaly"]
            failure["anomaly"] = {k: a[k] for k in ("kind", "stage", "excerpt", "line", "col",
                                                    "repair_hint", "detail", "message", "span")
                                  if k in a} | {"stage": r["stage"]}
        failures.append(failure)
        break                       # the first failure is the feedback, as a test runner gives it
    return {"passed": not failures, "failures": failures}


def run_python(code: str, task: Task) -> Dict[str, Any]:
    failures = []
    for test in task.tests:
        harness = (code + "\n\nimport json\n"
                   f"print('__RESULT__' + json.dumps(solve(**{json.dumps(test['inputs'])})))\n")
        try:
            proc = subprocess.run([sys.executable, "-c", harness], capture_output=True,
                                  text=True, timeout=PY_TIMEOUT)
        except subprocess.TimeoutExpired:
            failures.append({"inputs": test["inputs"], "expected": test["expected"],
                             "error": f"timed out after {PY_TIMEOUT} s"})
            break
        got = None
        for line in proc.stdout.splitlines():
            if line.startswith("__RESULT__"):
                got = json.loads(line[len("__RESULT__"):])
        if proc.returncode != 0:
            tb = proc.stderr.strip().splitlines()
            failures.append({"inputs": test["inputs"], "expected": test["expected"],
                             "traceback": "\n".join(tb[-30:])})
            break
        if got != test["expected"]:
            failures.append({"inputs": test["inputs"], "expected": test["expected"], "got": got})
            break
    return {"passed": not failures, "failures": failures}


# --- the log ------------------------------------------------------------------

def _log_path(lang: str) -> Path:
    path = RESULTS / lang / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append(lang: str, record: Dict[str, Any]) -> None:
    with _log_path(lang).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _records(lang: str) -> List[Dict[str, Any]]:
    path = _log_path(lang)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _last_submission(lang: str, task_id: str) -> Optional[str]:
    for rec in reversed(_records(lang)):
        if rec["task"] == task_id and "program" in rec:
            return rec["program"]
    return None


# --- commands --------------------------------------------------------------------

def cmd_tasks(args) -> int:
    for t in TASKS:
        names = ", ".join("{" + n + "}" for n in t.inputs) if args.lang == "lova" else ", ".join(t.inputs)
        print(f"{t.id}: {t.prompt}  [inputs: {names}]")
    return 0


def feedback_text(lang: str, result: Dict[str, Any]) -> str:
    if result["passed"]:
        return "PASS: all tests pass."
    f = result["failures"][0]
    if lang == "lova":
        return "FAIL " + json.dumps(f, ensure_ascii=False)
    lines = [f"FAIL inputs={json.dumps(f['inputs'])} expected={f['expected']}"]
    if "got" in f:
        lines.append(f"got={f['got']}")
    if "traceback" in f:
        lines.append(f["traceback"])
    if "error" in f:
        lines.append(f["error"])
    return "\n".join(lines)


def _submit(lang: str, task_id: str, program: str, emitted: int, how: str) -> int:
    task = BY_ID[task_id]
    started = time.perf_counter()
    result = run_lova(program, task) if lang == "lova" else run_python(program, task)
    text = feedback_text(lang, result)
    attempt = 1 + sum(1 for r in _records(lang) if r["task"] == task_id)
    _append(lang, {"task": task_id, "attempt": attempt, "how": how, "emitted_chars": emitted,
                   "feedback_chars": len(text), "passed": result["passed"], "program": program,
                   "feedback": text, "seconds": round(time.perf_counter() - started, 3),
                   "time": time.time()})
    print(f"[{task_id} attempt {attempt}] {text}")
    return 0 if result["passed"] else 1


def cmd_submit(args) -> int:
    program = Path(args.file).read_text(encoding="utf-8")
    return _submit(args.lang, args.task, program, len(program), "submit")


def cmd_patch(args) -> int:
    last = _last_submission("lova", args.task)
    if last is None:
        print("nothing submitted for this task yet; use submit")
        return 2
    start, end = args.span
    if not 0 <= start <= end <= len(last):
        print(f"span [{start}, {end}] is outside the last submission (length {len(last)})")
        return 2
    program = last[:start] + args.replacement + last[end:]
    print(f"patched: replaced {last[start:end]!r}")
    return _submit("lova", args.task, program, len(args.replacement), "patch")


def cmd_show(args) -> int:
    last = _last_submission(args.lang, args.task)
    print(last if last is not None else "(nothing submitted)")
    return 0


def cmd_report(args) -> int:
    recs = _records(args.lang)
    if not recs:
        print("no log")
        return 1
    print(f"  {'task':5s} {'attempts':>8s} {'green':>6s} {'emitted':>8s} {'feedback':>9s}")
    totals = {"attempts": 0, "emitted": 0, "feedback": 0, "green": 0}
    for t in TASKS:
        rs = [r for r in recs if r["task"] == t.id]
        if not rs:
            continue
        green = any(r["passed"] for r in rs)
        emitted = sum(r["emitted_chars"] for r in rs)
        feedback = sum(r["feedback_chars"] for r in rs if not r["passed"])
        print(f"  {t.id:5s} {len(rs):8d} {'yes' if green else 'no':>6s} {emitted:8d} {feedback:9d}")
        totals["attempts"] += len(rs)
        totals["emitted"] += emitted
        totals["feedback"] += feedback
        totals["green"] += green
    print(f"  {'all':5s} {totals['attempts']:8d} {totals['green']:>6d} {totals['emitted']:8d} {totals['feedback']:9d}")
    print(f"  scaffolding: {'in-process, budget, no grant' if args.lang == 'lova' else 'subprocess + wall-clock timeout'}")
    return 0


def cmd_dry_run(args) -> int:
    """The reference solutions through both runners: the harness works."""
    from corpus.tasks import Task as _T  # noqa: F401  (import check only)
    ok = 0
    for t in TASKS:
        py = REFERENCE_PY[t.id]
        r = run_python(py, t)
        ok += r["passed"]
        print(f"  {t.id} python {'ok' if r['passed'] else 'FAIL ' + json.dumps(r['failures'][0])[:120]}")
    print(f"  {ok}/{len(TASKS)} python references pass")
    return 0


REFERENCE_PY = {
    "t01": "def solve(s):\n    d = 0\n    for c in s:\n        d += 1 if c == '(' else -1\n        if d < 0: return 0\n    return 1 if d == 0 else 0",
    "t02": "def solve(s):\n    st = []\n    for t in s.split():\n        if t in '+-*':\n            b, a = st.pop(), st.pop()\n            st.append(a + b if t == '+' else a - b if t == '-' else a * b)\n        else:\n            st.append(int(t))\n    return st[-1]",
    "t03": "def solve(s):\n    xs = [int(t) for t in s.split()]\n    best = run = 1\n    for i in range(1, len(xs)):\n        run = run + 1 if xs[i] > xs[i-1] else 1\n        best = max(best, run)\n    return best",
    "t04": "def solve(s):\n    v = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n    total = 0\n    for i, c in enumerate(s):\n        total += -v[c] if i + 1 < len(s) and v[c] < v[s[i+1]] else v[c]\n    return total",
    "t05": "def solve(a, b, k):\n    xs = sorted([int(t) for t in a.split()] + [int(t) for t in b.split()])\n    return xs[k-1]",
    "t06": "def solve(s, target):\n    xs = [int(t) for t in s.split()]\n    lo, hi = 0, len(xs) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if xs[mid] == target: return mid\n        if xs[mid] < target: lo = mid + 1\n        else: hi = mid - 1\n    return -1",
    "t07": "def solve(s):\n    c = {}\n    for w in s.split(): c[w] = c.get(w, 0) + 1\n    return max(c.values())",
    "t08": "def solve(s, n):\n    a = [int(t) for t in s.split()]\n    return sum(sum(a[i*n+k]*a[k*n+i] for k in range(n)) for i in range(n))",
    "t09": "def solve(s):\n    return sum(1 for i, c in enumerate(s) if i == 0 or c != s[i-1])",
    "t10": "def solve(coins, amount):\n    cs = [int(t) for t in coins.split()]\n    best = [0] + [None] * amount\n    for a in range(1, amount + 1):\n        opts = [best[a-c] for c in cs if c <= a and best[a-c] is not None]\n        best[a] = min(opts) + 1 if opts else None\n    return -1 if best[amount] is None else best[amount]",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.add_argument("--lang", default="lova"); p.set_defaults(func=cmd_tasks)
    p = sub.add_parser("submit"); p.add_argument("--lang", required=True, choices=["lova", "python"])
    p.add_argument("--task", required=True, choices=list(BY_ID)); p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_submit)
    p = sub.add_parser("patch"); p.add_argument("--task", required=True, choices=list(BY_ID))
    p.add_argument("--span", nargs=2, type=int, required=True); p.add_argument("--replacement", required=True)
    p.set_defaults(func=cmd_patch)
    p = sub.add_parser("show"); p.add_argument("--lang", required=True); p.add_argument("--task", required=True)
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("report"); p.add_argument("--lang", required=True); p.set_defaults(func=cmd_report)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
