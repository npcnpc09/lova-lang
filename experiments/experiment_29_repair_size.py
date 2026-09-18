"""Experiment 29 -- the repair leg at the size where reading fails (Q95).

    python experiments/experiment_29_repair_size.py tasks
    python experiments/experiment_29_repair_size.py dry-run
    python experiments/experiment_29_repair_size.py given  --session L1 --lang lova --task g2048-a
    python experiments/experiment_29_repair_size.py show   --session L1 --lang lova --task g2048-a [--defs | --def name]
    python experiments/experiment_29_repair_size.py fault  --session L1 --lang lova --task g2048-a
    python experiments/experiment_29_repair_size.py patch  --session L1 --lang lova --task g2048-a --def sweep --find "..." --replacement "..."
    python experiments/experiment_29_repair_size.py submit --session L1 --lang lova --task g2048-a --file x.lova
    python experiments/experiment_29_repair_size.py report [--lang lova] [--session L1]

Exp 21 measured repair at 20-40 lines and found it was reading; Exp 28
gave the fault an address and a def-scoped read and won at that size.
Both sessions' rule was the same: reading a program of that size
costs less than deciding whether a hint is safe.  This experiment is
the same measurement where reading is not cheap: two programs of
110-160 lines, each with a Python transliteration of the same
structure (experiments/exp29/, built and checked to agree on hundreds
of random inputs), two faults planted in each at the analogous place
in both languages, with run-time symptoms -- a wrong value on some
inputs, a trap or an exception on others.

A LOVA session has the program with its tests as `(example ...)`
forms and the tools of Exp 28 run 2: `fault` (the check report with
the located edit), `show --defs` (free), `show --def name`, `patch
--def name --find text`.  A Python session has the program, the
traceback or the expected/got of the failing test on `submit`, and
`patch --find`.  Three sessions a language.  The numbers are Exp 21's:
attempts, characters read, characters written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from experiments import experiment_18_agent_loop as loop  # noqa: E402

loop.BUDGET = 20_000_000       # the search on an early position is a few million steps
loop.PY_TIMEOUT = 30.0

HERE = Path(__file__).resolve().parent
PAIRS = HERE / "exp29"
RESULTS = HERE / "results_29"

PROGRAMS = ("g2048", "ttt")
PROMPTS = {
    "g2048": ("The 2048 engine: `main(board, moves)` takes sixteen cells (space-separated, "
              "cell order as `board-of` takes them) and a text of moves from `u r d l`, applies "
              "each move with the original game's rules (a tile merged this move cannot merge "
              "again; the traversal order decides which pair merges), and returns "
              "'<score> <moves that moved> <sixteen cells>'."),
    "ttt": ("Noughts and crosses: `main(board)` takes nine characters from `.XO` (square 0 "
            "first, row by row), the side to move being X when the counts are equal, else O; "
            "it returns the memoised negamax's chosen square and the score for the side to move "
            "('4 0'), or '-1 <winner>' when the board is already decided."),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tests(name: str) -> List[Dict[str, Any]]:
    return json.loads(_read(PAIRS / f"{name}_tests.json"))


# --- the faults ---------------------------------------------------------------------
#
# Each fault: (what, (lova old, lova new), (python old, python new)).  The
# `old` text must occur exactly once in the reference; `new` is what the
# session is given.  Filled in after the pairs were built and read.

FAULTS: Dict[str, Any] = {
    "g2048": {
        "a": ("a merged tile is not flagged, so it can merge again in the same move",
              ("m (map-put (get st m) k 1))", "m (get st m))"),
              ('"m", map_put(get(st, "m"), k, 1)),', '"m", get(st, "m")),')),
        "b": ("the letter for left names a direction that does not exist",
              ("        3))", "        4))"),
              ("    return 3" + chr(10), "    return 4" + chr(10))),
    },
    "ttt": {
        "a": ("among equally good squares the last is chosen instead of the first",
              ("              (if (gt sc (get st score))", "              (if (ge sc (get st score))"),
              ("        if sc > st[\"score\"]:", "        if sc >= st[\"score\"]:")),
        "b": ("the empty squares are counted one past the board",
              ("(def empties [b] (filter (lambda k (not (cell b k))) (range 0 9)))",
               "(def empties [b] (filter (lambda k (not (cell b k))) (range 0 10)))"),
              ("    return [k for k in range(0, 9) if not cell(b, k)]",
               "    return [k for k in range(0, 10) if not cell(b, k)]")),
    },
}


def _plant(src: str, edit) -> str:
    old, new = edit
    assert src.count(old) == 1, (old[:60], src.count(old))
    return src.replace(old, new)


def _lit(v) -> str:
    if isinstance(v, str):
        return '"' + v.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"') \
                      .replace(chr(10), chr(92) + "n").replace(chr(9), chr(92) + "t") + '"'
    return str(v)


def with_examples(program: str, tests: List[Dict[str, Any]], names: List[str]) -> str:
    """The program with its tests as `(example (main ...) expected)` forms
    before the final `(main {..})` expression."""
    body_at = program.rindex("(main {")
    forms = ["(example (main " + " ".join(_lit(t["inputs"][k]) for k in names) + ") "
             + _lit(t["expected"]) + ")" for t in tests]
    return program[:body_at] + chr(10).join(forms) + chr(10) + program[body_at:]


def _build_tasks():
    tasks, given = [], {}
    for name in PROGRAMS:
        if not (PAIRS / f"{name}.lova").exists() or name not in FAULTS:
            continue
        tests = _tests(name)
        names = list(tests[0]["inputs"])
        ref_lova = _read(PAIRS / f"{name}.lova")
        ref_py = _read(PAIRS / f"{name}.py")
        for tag, (what, lova_edit, py_edit) in FAULTS.get(name, {}).items():
            tid = f"{name}-{tag}"
            tasks.append(loop.Task(tid, PROMPTS[name] + f"  ({what})", tuple(names),
                                   [{"inputs": t["inputs"], "expected": t["expected"]} for t in tests]))
            given[tid] = {"lova": with_examples(_plant(ref_lova, lova_edit), tests, names),
                          "python": _plant(ref_py, py_edit),
                          "ref_lova": with_examples(ref_lova, tests, names), "ref_python": ref_py}
    return tasks, given


TASKS, GIVEN = _build_tasks()
BY_ID = {t.id: t for t in TASKS}


# --- commands ---------------------------------------------------------------------

def _bind(session: str) -> None:
    loop.TASKS = TASKS
    loop.BY_ID = BY_ID
    loop.RESULTS = RESULTS / session


def cmd_tasks(args) -> int:
    for t in TASKS:
        print(f"{t.id}: {t.prompt}")
    print("each task is a program written for it with one fault planted; `given` prints it, "
          "`fault` locates, `patch` or `submit` repairs.")
    return 0


def cmd_given(args) -> int:
    program = GIVEN[args.task][args.lang]
    loop._append(args.lang, {"task": args.task, "how": "given", "read_chars": len(program), "time": time.time()})
    print(program, end="" if program.endswith(chr(10)) else chr(10))
    return 0


def _current(lang: str, task_id: str) -> str:
    last = loop._last_submission(lang, task_id)
    return last if last is not None else GIVEN[task_id][lang]


def cmd_show(args) -> int:
    program = _current(args.lang, args.task)
    if getattr(args, "def_name", None):
        if args.lang == "lova":
            from core.query import def_text, defs
            d = def_text(program, args.def_name)
            if d is None:
                print(f"no def named {args.def_name!r}; the defs are " + ", ".join(x["name"] for x in defs(program)))
                return 2
            loop._append(args.lang, {"task": args.task, "how": "given", "read_chars": len(d["text"]),
                                     "def": args.def_name, "time": time.time()})
            print(f"{d['name']}  [{d['span'][0]}, {d['span'][1]})  {d['line']}:{d['col']}  ({' '.join(d['params'])})")
            print(d["text"])
            return 0
        # Python: one top-level function by name, logged as its size.
        m = re.search(rf"^def {re.escape(args.def_name)}\b.*?(?=^def |^[A-Za-z_]|\Z)", program, re.S | re.M)
        if not m:
            print(f"no function named {args.def_name!r}"); return 2
        loop._append(args.lang, {"task": args.task, "how": "given", "read_chars": len(m.group(0)),
                                 "def": args.def_name, "time": time.time()})
        print(m.group(0).rstrip()); return 0
    if getattr(args, "defs", False):
        if args.lang == "lova":
            from core.query import defs
            for x in defs(program):
                print(f"  {x['name']:20s} [{x['span'][0]:5d}, {x['span'][1]:5d})  {x['line']:3d}:{x['col']:<3d} {x['chars']:5d} chars  ({' '.join(x['params'])})")
        else:
            for m in re.finditer(r"^def (\w+)\(([^)]*)\):", program, re.M):
                line = program[:m.start()].count(chr(10)) + 1
                print(f"  {m.group(1):20s} line {line:3d}  ({m.group(2)})")
        return 0
    print(program)
    return 0


def cmd_fault(args) -> int:
    if args.lang != "lova":
        print("fault: for LOVA programs; a Python session sees the traceback on submit"); return 2
    from core.examples import check, summary
    program = _current(args.lang, args.task)
    try:
        results = check(program, locate_budget_s=15.0, max_steps=20_000_000)
        report = summary(results)
    except Exception as exc:          # noqa: BLE001
        a = getattr(exc, "anomaly", None)
        report = "does not compile: " + (json.dumps({k: a[k] for k in ("kind", "repair_hint", "excerpt", "line", "col") if k in a})
                                         if isinstance(a, dict) else str(exc))
    loop._append(args.lang, {"task": args.task, "how": "fault", "read_chars": len(report), "time": time.time()})
    print(report)
    return 0


def cmd_patch(args) -> int:
    base = _current(args.lang, args.task)
    if args.find is not None and getattr(args, "def_name", None) and args.lang == "lova":
        from core.query import find_in_def
        found = find_in_def(base, args.def_name, args.find)
        if not found["ok"]:
            print(found["message"]); return 2
        start, end = found["span"]
    elif args.find is not None:
        n = base.count(args.find)
        if n != 1:
            print(f"--find text occurs {n} times in the current program; it must occur exactly once")
            return 2
        start = base.index(args.find); end = start + len(args.find)
    elif args.span is not None:
        start, end = args.span
        if not 0 <= start <= end <= len(base):
            print(f"span [{start}, {end}] is outside the current program (length {len(base)})"); return 2
    else:
        print("give --find <text> (with --def for LOVA) or --span START END"); return 2
    program = base[:start] + args.replacement + base[end:]
    print(f"{'would replace' if args.dry_run else 'patched: replaced'} {base[start:end]!r} at [{start}, {end})")
    if args.dry_run:
        print(program, end="" if program.endswith(chr(10)) else chr(10)); return 0
    return loop._submit(args.lang, args.task, program, len(args.replacement), "patch")


def _sessions() -> List[str]:
    if not RESULTS.exists():
        return []
    return sorted(p.name for p in RESULTS.iterdir() if p.is_dir() and not p.name.startswith("_"))


def cmd_report(args) -> int:
    sessions = [args.session] if args.session else _sessions()
    langs = [args.lang] if args.lang else ["lova", "python"]
    cols = ("tasks", "green", "first", "attempts", "patches", "emitted", "read", "fails", "faults", "givens", "defreads")
    print(f"  {'lang':7s} {'session':8s} " + " ".join(f"{c:>8s}" for c in cols))
    grand: Dict[str, Dict[str, int]] = {}
    for lang in langs:
        for session in sessions:
            loop.RESULTS = RESULTS / session
            allrecs = loop._records(lang, checks=True)
            recs = [r for r in allrecs if r.get("how") in ("submit", "patch")]
            if not recs:
                continue
            tasks = sorted({r["task"] for r in recs})
            fails = [r for r in recs if not r["passed"]]
            row = {"tasks": len(tasks),
                   "green": sum(any(r["passed"] for r in recs if r["task"] == t) for t in tasks),
                   "first": sum(1 for t in tasks if next(r for r in recs if r["task"] == t)["passed"]),
                   "attempts": len(recs), "patches": sum(1 for r in recs if r["how"] == "patch"),
                   "emitted": sum(r["emitted_chars"] for r in recs),
                   "read": sum(r.get("read_chars", 0) for r in allrecs) + sum(r["feedback_chars"] for r in fails),
                   "fails": len(fails),
                   "faults": sum(1 for r in allrecs if r.get("how") == "fault"),
                   "givens": sum(1 for r in allrecs if r.get("how") == "given" and not r.get("def")),
                   "defreads": sum(1 for r in allrecs if r.get("how") == "given" and r.get("def"))}
            print(f"  {lang:7s} {session:8s} " + " ".join(f"{row[c]:8d}" for c in cols))
            g = grand.setdefault(lang, {c: 0 for c in cols})
            for c in cols:
                g[c] += row[c]
    for lang, g in grand.items():
        print(f"  {lang:7s} {'all':8s} " + " ".join(f"{g[c]:8d}" for c in cols))
    return 0


def cmd_dry_run(args) -> int:
    ok = True
    for t in TASKS:
        for lang, run in (("lova", loop.run_lova), ("python", loop.run_python)):
            good = run(GIVEN[t.id]["ref_" + lang], t)
            bad = run(GIVEN[t.id][lang], t)
            caught = bad["failures"][0] if bad["failures"] else None
            kind = ("traceback" if caught and "traceback" in caught else
                    "trap" if caught and "error" in json.dumps(caught).lower() else "value") if caught else "NOT CAUGHT"
            print(f"  {t.id:10s} {lang:6s} reference {'passes' if good['passed'] else 'FAILS ' + json.dumps(good['failures'][0])[:160]}; "
                  f"planted fault {kind}: {json.dumps(caught)[:140] if caught else ''}")
            ok = ok and good["passed"] and bool(caught)
    print("  all references pass and every fault is caught" if ok else "  PROBLEM above")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.set_defaults(func=cmd_tasks)
    for name, func in (("given", cmd_given), ("show", cmd_show), ("fault", cmd_fault)):
        p = sub.add_parser(name); p.add_argument("--session", required=True)
        p.add_argument("--lang", required=True, choices=["lova", "python"])
        p.add_argument("--task", required=True, choices=list(BY_ID)); p.set_defaults(func=func)
        if name == "show":
            p.add_argument("--def", dest="def_name"); p.add_argument("--defs", action="store_true")
    for name, func in (("submit", loop.cmd_submit), ("check", loop.cmd_check)):
        p = sub.add_parser(name); p.add_argument("--session", required=True)
        p.add_argument("--lang", required=True, choices=["lova", "python"])
        p.add_argument("--task", required=True, choices=list(BY_ID)); p.add_argument("--file", required=True)
        p.set_defaults(func=func)
    p = sub.add_parser("patch"); p.add_argument("--session", required=True)
    p.add_argument("--lang", required=True, choices=["lova", "python"])
    p.add_argument("--task", required=True, choices=list(BY_ID))
    p.add_argument("--span", nargs=2, type=int); p.add_argument("--find"); p.add_argument("--def", dest="def_name")
    p.add_argument("--replacement", required=True); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_patch)
    p = sub.add_parser("report"); p.add_argument("--lang"); p.add_argument("--session"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    _bind(getattr(args, "session", None) or "_")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
