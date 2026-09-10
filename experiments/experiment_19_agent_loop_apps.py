"""Experiment 19 -- the agent loop at a size where first attempts fail (Q87).

    python experiments/experiment_19_agent_loop_apps.py tasks [--lang python]
    python experiments/experiment_19_agent_loop_apps.py submit --session s1 --lang lova --task h01 --file h01.lova
    python experiments/experiment_19_agent_loop_apps.py patch  --session s1 --task h01 --span 12 30 --replacement "..."
    python experiments/experiment_19_agent_loop_apps.py show   --session s1 --lang lova --task h01
    python experiments/experiment_19_agent_loop_apps.py report [--lang lova] [--session s1]
    python experiments/experiment_19_agent_loop_apps.py dry-run

Exp 18 ran the loop on ten small tasks and both languages went green
at the first attempt on nine or ten of them, so the yardstick's
second number -- what an agent reads to understand a failure -- had
one side.  These eight tasks are bigger: a calculator with precedence,
a word-frequency report, a log summary, the best tic-tac-toe move, a
department ledger, interval merging, shortest paths, a bank ledger.
Each has edge cases a first attempt tends to miss, and each answer is
an integer or a text.  Several sessions per language, named with
``--session``, so the report can say how often a first attempt failed
and what a failure cost to read on each side.

The harness is Exp 18's (``experiment_18_agent_loop``): the same
``submit`` / ``patch`` / ``show`` / ``report``, a log per session and
language under ``experiments/results_19/<session>/<lang>/log.jsonl``.
"""

from __future__ import annotations

import argparse
import heapq
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import experiment_18_agent_loop as loop  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_19"


# --- oracles ---------------------------------------------------------------------

def _calc(s: str) -> int:
    toks = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            toks.append(int(s[i:j])); i = j
        else:
            toks.append(c); i += 1
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def atom():
        t = take()
        if t == "(":
            v = expr(); take(); return v
        if t == "-":
            return -atom()
        return t

    def term():
        v = atom()
        while peek() in ("*", "/"):
            if take() == "*":
                v = v * atom()
            else:
                v = v // atom()
        return v

    def expr():
        v = term()
        while peek() in ("+", "-"):
            if take() == "+":
                v = v + term()
            else:
                v = v - term()
        return v
    return expr()


def _wordfreq(text: str, k: int) -> str:
    counts: Dict[str, int] = {}
    for raw in text.split():
        w = raw.lower().strip(".,!?;:")
        if w:
            counts[w] = counts.get(w, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return "\n".join(f"{w} {c}" for w, c in top)


def _logsum(text: str) -> str:
    stats: Dict[str, List[int]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        level, rest = line.split(" ", 1)
        comp = rest.split(":", 1)[0]
        e, w = stats.setdefault(comp, [0, 0])
        if level == "ERROR":
            stats[comp][0] += 1
        elif level == "WARN":
            stats[comp][1] += 1
    rows = sorted(stats.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    return "\n".join(f"{c} {e} {w}" for c, (e, w) in rows)


_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _winner(b: str) -> str:
    for a, c, d in _LINES:
        if b[a] != "." and b[a] == b[c] == b[d]:
            return b[a]
    return ""


def _negamax(b: str, side: str) -> int:
    w = _winner(b)
    if w:
        return 1 if w == side else -1
    if "." not in b:
        return 0
    other = "O" if side == "X" else "X"
    best = -2
    for i, c in enumerate(b):
        if c == ".":
            best = max(best, -_negamax(b[:i] + side + b[i + 1:], other))
    return best


def _bestmove(board: str, side: str) -> int:
    other = "O" if side == "X" else "X"
    best, move = -2, -1
    for i, c in enumerate(board):
        if c == ".":
            v = -_negamax(board[:i] + side + board[i + 1:], other)
            if v > best:
                best, move = v, i
    return move


def _depts(text: str) -> str:
    totals: Dict[str, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        _name, dept, salary = line.split(",")
        totals[dept.strip()] = totals.get(dept.strip(), 0) + int(salary)
    rows = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return "\n".join(f"{d} {t}" for d, t in rows)


def _intervals(s: str) -> str:
    xs = [int(t) for t in s.split()]
    pairs = sorted((min(a, b), max(a, b)) for a, b in zip(xs[::2], xs[1::2]))
    out: List[List[int]] = []
    for a, b in pairs:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return " ".join(f"{a}-{b}" for a, b in out)


def _shortest(edges: str, start: str, goal: str) -> int:
    adj: Dict[str, List] = {}
    for e in edges.split():
        ab, w = e.split(":")
        a, b = ab.split("-")
        adj.setdefault(a, []).append((b, int(w)))
        adj.setdefault(b, []).append((a, int(w)))
    dist = {start: 0}
    heap = [(0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == goal:
            return d
        if d > dist.get(u, 1 << 60):
            continue
        for v, w in adj.get(u, []):
            if d + w < dist.get(v, 1 << 60):
                dist[v] = d + w
                heapq.heappush(heap, (d + w, v))
    return -1


def _bank(text: str) -> str:
    balance = rejected = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] not in ("deposit", "withdraw") or not parts[1].isdigit() or int(parts[1]) <= 0:
            rejected += 1
            continue
        amount = int(parts[1])
        if parts[0] == "deposit":
            balance += amount
        elif amount <= balance:
            balance -= amount
        else:
            rejected += 1
    return f"{balance} {rejected}"


T = loop._task
TASKS: List[loop.Task] = [
    T("h01", "Given a text s holding an arithmetic expression over non-negative integer literals with the operators + - * / (division is floor division), parentheses, unary minus, and spaces anywhere between tokens, evaluate it with the usual precedence (* and / before + and -, left to right within a level) and return the integer result.",
      ("s",), _calc, [("3 + 4 * (2 - 1)",), ("10 / 3 - -2",), ("(1+2)*(3+4)",), ("2 * (3 + 4) * 5 - 100",), ("7",)]),
    T("h02", "Given a text `text` of several lines of words and an integer k, return a text: the k most frequent words, one per line as `word count`, most frequent first and alphabetical among equal counts. Words are separated by whitespace, compared case-insensitively (report them in lower case), and the characters . , ! ? ; : are stripped from their ends. If there are fewer than k distinct words, report all of them.",
      ("text", "k"), _wordfreq, [("The cat. The dog!\nA cat, a CAT", 2), ("one two two three three three", 5), ("x", 1)]),
    T("h03", "Given a text `text` of log lines, each `LEVEL component: message` where LEVEL is one of INFO, WARN, ERROR, return a text with one line per component, `component errors warnings` (the counts of its ERROR and WARN lines), ordered by errors descending, then warnings descending, then component name ascending. Components with only INFO lines still appear with 0 0. Blank lines in the input are skipped.",
      ("text",), _logsum, [("INFO db: up\nERROR api: timeout\nWARN db: slow\nERROR api: 500\n\nWARN cache: miss", ), ("INFO a: x\nINFO b: y",), ("ERROR z: a\nERROR y: b\nWARN y: c",)]),
    T("h04", "Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.",
      ("board", "side"), _bestmove, [("XX.OO....", "X"), ("X...O....", "X"), (".........", "O"), ("XOX.O..X.", "X")]),
    T("h05", "Given a text `text` of lines `name,department,salary` (salary a positive integer, names unique), return a text with one line per department, `department total` (the sum of its salaries), ordered by total descending then department name ascending. Blank lines are skipped.",
      ("text",), _depts, [("ann,eng,100\nbob,ops,80\ncy,eng,50\n\ndee,hr,130",), ("a,x,1\nb,y,1",), ("solo,q,7",)]),
    T("h06", "Given a text s of an even number of space-separated integers, read as consecutive pairs each describing a closed interval (either endpoint may come first), merge every overlapping or touching interval, and return a text of the merged intervals in ascending order, each as `low-high`, separated by single spaces.",
      ("s",), _intervals, [("1 3 2 6 8 10 15 18",), ("5 1 6 8 20 12",), ("1 4 4 5",), ("3 3",)]),
    T("h07", "Given a text edges of space-separated undirected weighted edges `a-b:w` (node names are single letters, w a positive integer), a text `start` and a text `goal`, return the length of the shortest path from start to goal, or -1 if goal is unreachable. start may equal goal (then the answer is 0).",
      ("edges", "start", "goal"), _shortest, [("a-b:3 b-c:4 a-c:9", "a", "c"), ("a-b:1 c-d:1", "a", "d"), ("a-b:2 b-c:2 a-c:5 c-d:1", "a", "d"), ("a-b:1", "b", "b")]),
    T("h08", "Given a text `text` of lines, each meant to be `deposit N` or `withdraw N` with N a positive integer, process them in order from a balance of 0: a deposit adds N; a withdraw subtracts N if the balance covers it and is otherwise rejected; any line that is not exactly one of these two forms (wrong word, missing or non-numeric or non-positive amount, extra words) is rejected and ignored. Return a text `balance rejected` with the final balance and the number of rejected lines.",
      ("text",), _bank, [("deposit 100\nwithdraw 50\nwithdraw 200\ndeposit 0\nrefund 5\nwithdraw 50",), ("withdraw 1",), ("deposit 10\ndeposit x\nwithdraw 10 now\nwithdraw 10",)]),
]
BY_ID = {t.id: t for t in TASKS}


REFERENCE_PY = {
    "h01": "import re\ndef solve(s):\n    toks = re.findall(r'\\d+|[-+*/()]', s)\n    pos = [0]\n    def peek(): return toks[pos[0]] if pos[0] < len(toks) else None\n    def take():\n        pos[0] += 1; return toks[pos[0]-1]\n    def atom():\n        t = take()\n        if t == '(':\n            v = expr(); take(); return v\n        if t == '-': return -atom()\n        return int(t)\n    def term():\n        v = atom()\n        while peek() in ('*', '/'):\n            v = v * atom() if take() == '*' else v // atom()\n        return v\n    def expr():\n        v = term()\n        while peek() in ('+', '-'):\n            v = v + term() if take() == '+' else v - term()\n        return v\n    return expr()",
    "h02": "def solve(text, k):\n    c = {}\n    for raw in text.split():\n        w = raw.lower().strip('.,!?;:')\n        if w: c[w] = c.get(w, 0) + 1\n    top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]\n    return '\\n'.join(f'{w} {n}' for w, n in top)",
    "h03": "def solve(text):\n    st = {}\n    for line in text.splitlines():\n        if not line.strip(): continue\n        level, rest = line.split(' ', 1)\n        comp = rest.split(':', 1)[0]\n        st.setdefault(comp, [0, 0])\n        if level == 'ERROR': st[comp][0] += 1\n        elif level == 'WARN': st[comp][1] += 1\n    rows = sorted(st.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))\n    return '\\n'.join(f'{c} {e} {w}' for c, (e, w) in rows)",
    "h04": "L = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]\ndef win(b):\n    for a, c, d in L:\n        if b[a] != '.' and b[a] == b[c] == b[d]: return b[a]\n    return ''\ndef nm(b, side):\n    w = win(b)\n    if w: return 1 if w == side else -1\n    if '.' not in b: return 0\n    o = 'O' if side == 'X' else 'X'\n    return max(-nm(b[:i] + side + b[i+1:], o) for i, c in enumerate(b) if c == '.')\ndef solve(board, side):\n    o = 'O' if side == 'X' else 'X'\n    best, move = -2, -1\n    for i, c in enumerate(board):\n        if c == '.':\n            v = -nm(board[:i] + side + board[i+1:], o)\n            if v > best: best, move = v, i\n    return move",
    "h05": "def solve(text):\n    t = {}\n    for line in text.splitlines():\n        if not line.strip(): continue\n        _n, d, s = line.split(',')\n        t[d] = t.get(d, 0) + int(s)\n    return '\\n'.join(f'{d} {v}' for d, v in sorted(t.items(), key=lambda kv: (-kv[1], kv[0])))",
    "h06": "def solve(s):\n    xs = [int(t) for t in s.split()]\n    ps = sorted((min(a, b), max(a, b)) for a, b in zip(xs[::2], xs[1::2]))\n    out = []\n    for a, b in ps:\n        if out and a <= out[-1][1]: out[-1][1] = max(out[-1][1], b)\n        else: out.append([a, b])\n    return ' '.join(f'{a}-{b}' for a, b in out)",
    "h07": "import heapq\ndef solve(edges, start, goal):\n    adj = {}\n    for e in edges.split():\n        ab, w = e.split(':'); a, b = ab.split('-')\n        adj.setdefault(a, []).append((b, int(w))); adj.setdefault(b, []).append((a, int(w)))\n    dist = {start: 0}; h = [(0, start)]\n    while h:\n        d, u = heapq.heappop(h)\n        if u == goal: return d\n        if d > dist.get(u, 1 << 60): continue\n        for v, w in adj.get(u, []):\n            if d + w < dist.get(v, 1 << 60):\n                dist[v] = d + w; heapq.heappush(h, (d + w, v))\n    return -1",
    "h08": "def solve(text):\n    bal = rej = 0\n    for line in text.splitlines():\n        p = line.split()\n        if len(p) != 2 or p[0] not in ('deposit', 'withdraw') or not p[1].isdigit() or int(p[1]) <= 0:\n            rej += 1; continue\n        n = int(p[1])\n        if p[0] == 'deposit': bal += n\n        elif n <= bal: bal -= n\n        else: rej += 1\n    return f'{bal} {rej}'",
}


# --- commands: Exp 18's, pointed at these tasks and a session directory ------------

def _bind(session: str) -> None:
    loop.TASKS = TASKS
    loop.BY_ID = BY_ID
    loop.RESULTS = RESULTS / session
    loop.REFERENCE_PY = REFERENCE_PY


def cmd_report(args) -> int:
    sessions = sorted(p.name for p in RESULTS.iterdir() if p.is_dir()) if RESULTS.exists() else []
    if args.session:
        sessions = [args.session]
    langs = [args.lang] if args.lang else ["lova", "python"]
    print(f"  {'lang':7s} {'session':8s} {'tasks':>5s} {'green':>5s} {'first':>5s} {'attempts':>8s} {'emitted':>8s} {'feedback':>9s} {'fails':>5s}")
    grand: Dict[str, Dict[str, int]] = {}
    for lang in langs:
        for session in sessions:
            loop.RESULTS = RESULTS / session
            recs = loop._records(lang)
            if not recs:
                continue
            tasks = sorted({r["task"] for r in recs})
            green = sum(any(r["passed"] for r in recs if r["task"] == t) for t in tasks)
            first = sum(1 for t in tasks if next(r for r in recs if r["task"] == t)["passed"])
            emitted = sum(r["emitted_chars"] for r in recs)
            fails = [r for r in recs if not r["passed"]]
            feedback = sum(r["feedback_chars"] for r in fails)
            print(f"  {lang:7s} {session:8s} {len(tasks):5d} {green:5d} {first:5d} {len(recs):8d} {emitted:8d} {feedback:9d} {len(fails):5d}")
            g = grand.setdefault(lang, {"tasks": 0, "green": 0, "first": 0, "attempts": 0, "emitted": 0, "feedback": 0, "fails": 0})
            for k, v in (("tasks", len(tasks)), ("green", green), ("first", first), ("attempts", len(recs)),
                         ("emitted", emitted), ("feedback", feedback), ("fails", len(fails))):
                g[k] += v
    for lang, g in grand.items():
        per_fail = g["feedback"] // g["fails"] if g["fails"] else 0
        print(f"  {lang:7s} {'all':8s} {g['tasks']:5d} {g['green']:5d} {g['first']:5d} {g['attempts']:8d} {g['emitted']:8d} {g['feedback']:9d} {g['fails']:5d}   feedback/failure {per_fail}")
    return 0


def cmd_dry_run(args) -> int:
    ok = 0
    for t in TASKS:
        r = loop.run_python(REFERENCE_PY[t.id], t)
        ok += r["passed"]
        print(f"  {t.id} python {'ok' if r['passed'] else 'FAIL ' + json.dumps(r['failures'][0])[:160]}")
    print(f"  {ok}/{len(TASKS)} python references pass")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.add_argument("--lang", default="lova"); p.set_defaults(func=loop.cmd_tasks)
    p = sub.add_parser("submit"); p.add_argument("--session", required=True)
    p.add_argument("--lang", required=True, choices=["lova", "python"])
    p.add_argument("--task", required=True, choices=list(BY_ID)); p.add_argument("--file", required=True)
    p.set_defaults(func=loop.cmd_submit)
    p = sub.add_parser("patch"); p.add_argument("--session", required=True)
    p.add_argument("--task", required=True, choices=list(BY_ID))
    p.add_argument("--span", nargs=2, type=int, required=True); p.add_argument("--replacement", required=True)
    p.set_defaults(func=loop.cmd_patch)
    p = sub.add_parser("show"); p.add_argument("--session", required=True)
    p.add_argument("--lang", required=True); p.add_argument("--task", required=True)
    p.set_defaults(func=loop.cmd_show)
    p = sub.add_parser("report"); p.add_argument("--lang"); p.add_argument("--session"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    _bind(getattr(args, "session", None) or "_")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
