"""Experiment 21 -- the repair leg of the yardstick (Q88).

    python experiments/experiment_21_repair.py tasks [--lang python]
    python experiments/experiment_21_repair.py given  --session r1 --lang lova --task h01
    python experiments/experiment_21_repair.py patch  --session r1 --lang lova --task h01 --find "(lt a b)" --replacement "(le a b)" [--dry-run]
    python experiments/experiment_21_repair.py patch  --session r1 --lang lova --task h01 --span 12 30 --replacement "..."
    python experiments/experiment_21_repair.py submit --session r1 --lang lova --task h01 --file h01.lova
    python experiments/experiment_21_repair.py check  --session r1 --lang lova --task h01 --file h01.lova
    python experiments/experiment_21_repair.py report [--lang lova] [--session r1]
    python experiments/experiment_21_repair.py dry-run

The yardstick's fourth number is the cost of repairing code already
written.  Exp 18-20 measured writing from nothing; here each of Exp
19's eight tasks comes with a program that was written for it -- the
LOVA one by a session of Exp 20, the Python one the harness's own
reference -- with one semantic fault planted, the same fault at the
analogous place in both languages: unary minus dropped, a punctuation
mark not stripped, a sort key's sign, a winning line replaced by a
duplicate, a count where a sum was meant, `<` for `<=` on a touching
interval, an undirected edge relaxed one way, `<` for `<=` on a
withdrawal.  Every planted fault fails at least one hidden test (two
tests were added so that this holds; `dry-run` checks it), and every
program compiles and runs, so what the session reads is a wrong value
or a run-time fault -- the structured anomaly against the traceback.

A session reads the program with `given` (the characters are logged as
context read), then gets it green with `patch` (one span of the
current program, the given one or its last submission; counted as the
size of the replacement) or `submit` (a whole file), in either
language.  `report` adds up attempts, characters emitted and read, and
how many fixes were patches.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import experiment_18_agent_loop as loop  # noqa: E402
from experiments import experiment_19_agent_loop_apps as e19  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_21"

# Two tests added to Exp 19's so that every planted fault is visible:
# O's only win is the anti-diagonal (found by searching the legal
# boards for one where the planted fault changes the answer), and the
# path needs an edge read backwards.
EXTRA_TESTS = {
    "h04": [({"board": "XXOXOO.X.", "side": "O"}, 6)],
    "h07": [({"edges": "b-a:3 c-b:4", "start": "a", "goal": "c"}, 7)],
}
TASKS = [loop.Task(t.id, t.prompt, t.inputs,
                   t.tests + [{"inputs": i, "expected": x} for i, x in EXTRA_TESTS.get(t.id, [])])
         for t in e19.TASKS]
BY_ID = {t.id: t for t in TASKS}


# --- the programs as written -----------------------------------------------

# Session o5 of Exp 20 (journal/experiment_20.md), its passing program
# for each task, unchanged.
REFERENCE_LOVA = {
    "h01": """(def skip [cs] (if (nil? cs) cs (if (eq (head cs) 32) (skip (tail cs)) cs)))
(def digit? [c] (and (ge c 48) (le c 57)))
(def num [cs acc]
  (if (nil? cs) (rec v acc r cs)
    (if (digit? (head cs))
        (num (tail cs) (merge (mul acc 10) (sub (head cs) 48)))
        (rec v acc r cs))))
(def factor [cs0]
  (let cs (skip cs0)
    (if (eq (head cs) 45)
        (let f (factor (tail cs)) (rec v (neg (get f v)) r (get f r)))
        (if (eq (head cs) 40)
            (let e (expr (tail cs)) (rec v (get e v) r (tail (skip (get e r)))))
            (num cs 0)))))
(def term-loop [acc cs0]
  (let cs (skip cs0)
    (if (nil? cs) (rec v acc r cs)
      (if (eq (head cs) 42)
          (let f (factor (tail cs)) (term-loop (mul acc (get f v)) (get f r)))
      (if (eq (head cs) 47)
          (let f (factor (tail cs)) (term-loop (div acc (get f v)) (get f r)))
          (rec v acc r cs))))))
(def term [cs0] (let f (factor cs0) (term-loop (get f v) (get f r))))
(def expr-loop [acc cs0]
  (let cs (skip cs0)
    (if (nil? cs) (rec v acc r cs)
      (if (eq (head cs) 43)
          (let t (term (tail cs)) (expr-loop (merge acc (get t v)) (get t r)))
      (if (eq (head cs) 45)
          (let t (term (tail cs)) (expr-loop (sub acc (get t v)) (get t r)))
          (rec v acc r cs))))))
(def expr [cs0] (let t (term cs0) (expr-loop (get t v) (get t r))))
(get (expr (text-chars {s})) v)
""",
    "h02": """(def punct? [c]
  (or (eq c 46) (or (eq c 44) (or (eq c 33) (or (eq c 63) (or (eq c 59) (eq c 58)))))))
(def strip-front [cs] (if (nil? cs) cs (if (punct? (head cs)) (strip-front (tail cs)) cs)))
(def strip-end [cs] (reverse (strip-front (reverse cs))))
(def lower [c] (if (and (ge c 65) (le c 90)) (merge c 32) c))
(def norm [w] (text-of-chars (map lower (strip-end (text-chars w)))))
(def nonempty [w] (gt (text-len w) 0))
(let ws (filter nonempty (map norm (words {text})))
  (let m (fold (lambda mm (lambda w (map-count mm w))) (map-of (nil)) ws)
    (let ks (sort-by (lambda a (lambda b
                 (if (ne (map-get m a 0) (map-get m b 0))
                     (gt (map-get m a 0) (map-get m b 0))
                     (text-lt a b))))
               (map-keys m))
      (join (map (lambda w (text-cat w (text-cat " " (text-of (map-get m w 0)))))
                 (take (min {k} (len ks)) ks))
            10))))
""",
    "h03": """(def strip-colon [t]
  (let n (text-len t)
    (if (eq (text-slice t (sub n 1) n) ":") (text-slice t 0 (sub n 1)) t)))
(def step [m ln]
  (let ws (words ln)
    (if (nil? ws) m
      (let comp (strip-colon (nth ws 1))
        (let cur (map-get m comp (rec e 0 w 0))
          (let lv (nth ws 0)
            (map-put m comp
              (if (eq lv "ERROR") (put cur e (inc (get cur e)))
                (if (eq lv "WARN") (put cur w (inc (get cur w))) cur)))))))))
(let m (fold step (map-of (nil)) (lines {text}))
  (let ks (sort-by (lambda a (lambda b
             (let ra (map-get m a 0) (let rb (map-get m b 0)
               (if (ne (get ra e) (get rb e)) (gt (get ra e) (get rb e))
                 (if (ne (get ra w) (get rb w)) (gt (get ra w) (get rb w))
                   (text-lt a b)))))))
           (map-keys m))
    (join (map (lambda c
                 (let r (map-get m c 0)
                   (text-cat c (text-cat " " (text-cat (text-of (get r e))
                     (text-cat " " (text-of (get r w))))))))
               ks)
          10)))
""",
    "h04": """(def code [c] (if (eq c 88) 1 (if (eq c 79) 2 0)))
(def w3 [a b c q] (and (eq a q) (and (eq b q) (eq c q))))
(def best [p mm kb empt]
  (let kk (merge (mul kb 2) (sub p 1))
    (let hit (map-get mm kk 9)
      (if (ne hit 9) (rec s hit m mm)
        (let res (best2 p mm kb empt)
          (rec s (get res s) m (map-put (get res m) kk (get res s))))))))
(def best2 [p mm kb empt]
  (let c0 (mod (div kb 6561) 3)
  (let c1 (mod (div kb 2187) 3)
  (let c2 (mod (div kb 729) 3)
  (let c3 (mod (div kb 243) 3)
  (let c4 (mod (div kb 81) 3)
  (let c5 (mod (div kb 27) 3)
  (let c6 (mod (div kb 9) 3)
  (let c7 (mod (div kb 3) 3)
  (let c8 (mod kb 3)
  (let q (if (eq p 1) 2 1)
    (if (or (w3 c0 c1 c2 q) (or (w3 c3 c4 c5 q) (or (w3 c6 c7 c8 q)
        (or (w3 c0 c3 c6 q) (or (w3 c1 c4 c7 q) (or (w3 c2 c5 c8 q)
        (or (w3 c0 c4 c8 q) (w3 c2 c4 c6 q))))))))
        (rec s (neg 1) m mm)
        (if (eq empt 0) (rec s 0 m mm)
          (bestloop p 0 6561 (neg 2) mm kb empt))))))))))))))
(def bestloop [p i w acc mm kb empt]
  (if (or (eq i 9) (eq acc 1)) (rec s acc m mm)
    (if (ne (mod (div kb w) 3) 0)
        (bestloop p (inc i) (div w 3) acc mm kb empt)
      (let r (best (if (eq p 1) 2 1) mm (merge kb (mul w p)) (sub empt 1))
        (bestloop p (inc i) (div w 3) (max acc (neg (get r s))) (get r m) kb empt)))))
(def pick [p i w bi bs mm kb empt]
  (if (eq i 9) bi
    (if (ne (mod (div kb w) 3) 0) (pick p (inc i) (div w 3) bi bs mm kb empt)
      (let r (best (if (eq p 1) 2 1) mm (merge kb (mul w p)) (sub empt 1))
        (let sc (neg (get r s))
          (if (eq sc 1) i
            (if (gt sc bs) (pick p (inc i) (div w 3) i sc (get r m) kb empt)
                           (pick p (inc i) (div w 3) bi bs (get r m) kb empt))))))))
(let cs (text-chars {board})
  (let kb (fold (lambda a (lambda c (merge (mul a 3) (code c)))) 0 cs)
    (let empt (len (filter (lambda c (eq c 46)) cs))
      (pick (if (eq (head {side}) 88) 1 2) 0 6561 0 (neg 2) (map-of (nil)) kb empt))))
""",
    "h05": """(def step [m ln]
  (let t (text-trim ln)
    (if (eq (text-len t) 0) m
      (let ps (text-split t ",")
        (let d (text-trim (nth ps 1))
          (map-put m d (merge (map-get m d 0) (parse-int (text-trim (nth ps 2))))))))))
(let m (fold step (map-of (nil)) (lines {text}))
  (let ks (sort-by (lambda a (lambda b
             (if (ne (map-get m a 0) (map-get m b 0))
                 (gt (map-get m a 0) (map-get m b 0))
                 (text-lt a b))))
           (map-keys m))
    (join (map (lambda d (text-cat d (text-cat " " (text-of (map-get m d 0))))) ks) 10)))
""",
    "h06": """(def pairup [ns]
  (if (nil? ns) (nil)
    (let a (head ns)
      (let b (head (tail ns))
        (cons (rec lo (min a b) hi (max a b)) (pairup (tail (tail ns))))))))
(def mrg [acc iv]
  (if (nil? acc) (list iv)
    (let c (head acc)
      (if (le (get iv lo) (get c hi))
          (cons (rec lo (get c lo) hi (max (get c hi) (get iv hi))) (tail acc))
          (cons iv acc)))))
(let ivs (sort-by (lambda a (lambda b
             (if (ne (get a lo) (get b lo)) (lt (get a lo) (get b lo))
                 (lt (get a hi) (get b hi)))))
           (pairup (map parse-int (words {s}))))
  (join (map (lambda iv (text-cat (text-of (get iv lo)) (text-cat "-" (text-of (get iv hi)))))
             (reverse (fold mrg (nil) ivs)))
        32))
""",
    "h07": """(def mkedge [t]
  (let i (text-find t "-")
    (let j (text-find t ":")
      (rec na (text-slice t 0 i)
           nb (text-slice t (inc i) j)
           wt (parse-int (text-slice t (inc j) (text-len t)))))))
(def relax1 [d u v c]
  (let du (map-get d u 1000000000)
    (if (lt (merge du c) (map-get d v 1000000000)) (map-put d v (merge du c)) d)))
(def relax [d e]
  (relax1 (relax1 d (get e na) (get e nb) (get e wt)) (get e nb) (get e na) (get e wt)))
(def rounds [d es n]
  (if (eq n 0) d (rounds (fold relax d es) es (sub n 1))))
(let es (map mkedge (words {edges}))
  (let d (rounds (map-put (map-of (nil)) {start} 0) es (inc (len es)))
    (let r (map-get d {goal} 1000000000)
      (if (eq r 1000000000) (neg 1) r))))
""",
    "h08": """(def digit? [c] (and (ge c 48) (le c 57)))
(def alldig [cs] (and (not (nil? cs)) (all digit? cs)))
(def rej [st] (put st rj (inc (get st rj))))
(def step [st ln]
  (let ws (words ln)
    (if (eq (len ws) 0) st
      (if (ne (len ws) 2) (rej st)
        (let cmd (nth ws 0)
          (let amtt (nth ws 1)
            (if (not (alldig (text-chars amtt))) (rej st)
              (let n (parse-int amtt)
                (if (le n 0) (rej st)
                  (if (eq cmd "deposit") (put st bal (merge (get st bal) n))
                    (if (eq cmd "withdraw")
                        (if (ge (get st bal) n) (put st bal (sub (get st bal) n)) (rej st))
                        (rej st))))))))))))
(let st (fold step (rec bal 0 rj 0) (lines {text}))
  (text-cat (text-of (get st bal)) (text-cat " " (text-of (get st rj)))))
""",
}
REFERENCE_PY = e19.REFERENCE_PY

# (what was planted, LOVA edit, Python edit) -- one occurrence each.
FAULTS = {
    "h01": ("unary minus dropped",
            ("(rec v (neg (get f v)) r (get f r))", "(rec v (get f v) r (get f r))"),
            ("if t == '-': return -atom()", "if t == '-': return atom()")),
    "h02": ("the period is not stripped",
            ("(eq c 46)", "(eq c 39)"),
            ("strip('.,!?;:')", "strip(',!?;:')")),
    "h03": ("warnings sorted ascending",
            ("(if (ne (get ra w) (get rb w)) (gt (get ra w) (get rb w))",
             "(if (ne (get ra w) (get rb w)) (lt (get ra w) (get rb w))"),
            ("(-kv[1][0], -kv[1][1], kv[0])", "(-kv[1][0], kv[1][1], kv[0])")),
    "h04": ("the anti-diagonal replaced by a duplicate of the diagonal",
            ("(w3 c2 c4 c6 q)", "(w3 c0 c4 c8 q)"),
            ("(2,4,6)", "(0,4,8)")),
    "h05": ("a count where a sum was meant",
            ("(merge (map-get m d 0) (parse-int (text-trim (nth ps 2))))", "(merge (map-get m d 0) 1)"),
            ("t[d] = t.get(d, 0) + int(s)", "t[d] = t.get(d, 0) + 1")),
    "h06": ("touching intervals not merged",
            ("(if (le (get iv lo) (get c hi))", "(if (lt (get iv lo) (get c hi))"),
            ("if out and a <= out[-1][1]", "if out and a < out[-1][1]")),
    "h07": ("an undirected edge relaxed one way",
            ("(relax1 (relax1 d (get e na) (get e nb) (get e wt)) (get e nb) (get e na) (get e wt))",
             "(relax1 d (get e na) (get e nb) (get e wt))"),
            ("adj.setdefault(a, []).append((b, int(w))); adj.setdefault(b, []).append((a, int(w)))",
             "adj.setdefault(a, []).append((b, int(w)))")),
    "h08": ("a withdrawal of the whole balance rejected",
            ("(if (ge (get st bal) n) (put st bal (sub (get st bal) n)) (rej st))",
             "(if (gt (get st bal) n) (put st bal (sub (get st bal) n)) (rej st))"),
            ("elif n <= bal: bal -= n", "elif n < bal: bal -= n")),
}


def _plant(src: str, edit) -> str:
    old, new = edit
    assert src.count(old) == 1, (old, src.count(old))
    return src.replace(old, new)


GIVEN = {tid: {"lova": _plant(REFERENCE_LOVA[tid], FAULTS[tid][1]),
               "python": _plant(REFERENCE_PY[tid], FAULTS[tid][2])}
         for tid in BY_ID}


# --- commands ----------------------------------------------------------------------

def _bind(session: str) -> None:
    loop.TASKS = TASKS
    loop.BY_ID = BY_ID
    loop.RESULTS = RESULTS / session


def cmd_tasks(args) -> int:
    loop.cmd_tasks(args)
    print("each task comes with a program written for it that fails at least one hidden "
          "test; `given` prints it, `patch` or `submit` repairs it.")
    return 0


def cmd_given(args) -> int:
    program = GIVEN[args.task][args.lang]
    loop._append(args.lang, {"task": args.task, "how": "given", "read_chars": len(program),
                             "time": time.time()})
    print(program, end="" if program.endswith("\n") else "\n")
    return 0


def _current(lang: str, task_id: str) -> str:
    last = loop._last_submission(lang, task_id)
    return last if last is not None else GIVEN[task_id][lang]


def cmd_patch(args) -> int:
    """Replace one span -- given as offsets, or as the text to find.

    Exp 21: nine of the ten extra attempts across both languages were
    offset arithmetic (a console that prints CRLF, a hand count off by
    one), none of them the repair; so a patch may name the text it
    replaces, which must occur once, and may be tried without
    submitting.
    """
    base = _current(args.lang, args.task)
    if args.find is not None:
        n = base.count(args.find)
        if n != 1:
            print(f"--find text occurs {n} times in the current program; it must occur exactly once")
            return 2
        start = base.index(args.find)
        end = start + len(args.find)
    elif args.span is not None:
        start, end = args.span
        if not 0 <= start <= end <= len(base):
            print(f"span [{start}, {end}] is outside the current program (length {len(base)})")
            return 2
    else:
        print("give --find <text> or --span START END")
        return 2
    program = base[:start] + args.replacement + base[end:]
    print(f"{'would replace' if args.dry_run else 'patched: replaced'} {base[start:end]!r} at [{start}, {end})")
    if args.out:
        Path(args.out).write_text(program, encoding="utf-8")
    if args.dry_run:
        print(program, end="" if program.endswith("\n") else "\n")
        return 0
    return loop._submit(args.lang, args.task, program, len(args.replacement), "patch")


def cmd_show(args) -> int:
    print(_current(args.lang, args.task))
    return 0


def _sessions() -> List[str]:
    if not RESULTS.exists():
        return []
    return sorted(p.name for p in RESULTS.iterdir() if p.is_dir() and not p.name.startswith("_"))


def cmd_report(args) -> int:
    sessions = [args.session] if args.session else _sessions()
    langs = [args.lang] if args.lang else ["lova", "python"]
    cols = ("tasks", "green", "first", "attempts", "patches", "emitted", "read", "fails", "checks")
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
            green = sum(any(r["passed"] for r in recs if r["task"] == t) for t in tasks)
            first = sum(1 for t in tasks if next(r for r in recs if r["task"] == t)["passed"])
            fails = [r for r in recs if not r["passed"]]
            row = {"tasks": len(tasks), "green": green, "first": first, "attempts": len(recs),
                   "patches": sum(1 for r in recs if r["how"] == "patch"),
                   "emitted": sum(r["emitted_chars"] for r in recs),
                   "read": sum(r.get("read_chars", 0) for r in allrecs) + sum(r["feedback_chars"] for r in fails),
                   "fails": len(fails),
                   "checks": sum(1 for r in allrecs if r.get("how") == "check")}
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
        for lang, run, ref in (("lova", loop.run_lova, REFERENCE_LOVA), ("python", loop.run_python, REFERENCE_PY)):
            good = run(ref[t.id], t)
            bad = run(GIVEN[t.id][lang], t)
            caught = bad["failures"][0]["inputs"] if bad["failures"] else None
            print(f"  {t.id} {lang:6s} reference {'passes' if good['passed'] else 'FAILS ' + json.dumps(good['failures'][0])[:120]}; "
                  f"planted fault {'caught by ' + json.dumps(caught) if caught else 'NOT CAUGHT'}")
            ok = ok and good["passed"] and bool(caught)
    print("  all references pass and every fault is caught" if ok else "  PROBLEM above")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.add_argument("--lang", default="lova"); p.set_defaults(func=cmd_tasks)
    for name, func in (("given", cmd_given), ("show", cmd_show)):
        p = sub.add_parser(name); p.add_argument("--session", required=True)
        p.add_argument("--lang", required=True, choices=["lova", "python"])
        p.add_argument("--task", required=True, choices=list(BY_ID)); p.set_defaults(func=func)
    for name, func in (("submit", loop.cmd_submit), ("check", loop.cmd_check)):
        p = sub.add_parser(name); p.add_argument("--session", required=True)
        p.add_argument("--lang", required=True, choices=["lova", "python"])
        p.add_argument("--task", required=True, choices=list(BY_ID)); p.add_argument("--file", required=True)
        p.set_defaults(func=func)
    p = sub.add_parser("patch"); p.add_argument("--session", required=True)
    p.add_argument("--lang", required=True, choices=["lova", "python"])
    p.add_argument("--task", required=True, choices=list(BY_ID))
    p.add_argument("--span", nargs=2, type=int); p.add_argument("--find", help="the text to replace; must occur once")
    p.add_argument("--replacement", required=True)
    p.add_argument("--out", help="also write the patched source to this file")
    p.add_argument("--dry-run", action="store_true", help="print the result; do not submit")
    p.set_defaults(func=cmd_patch)
    p = sub.add_parser("report"); p.add_argument("--lang"); p.add_argument("--session"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    _bind(getattr(args, "session", None) or "_")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
