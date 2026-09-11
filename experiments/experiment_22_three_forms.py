"""Experiment 22 -- the three-form experiment (Q100).

    python experiments/experiment_22_three_forms.py tasks
    python experiments/experiment_22_three_forms.py card  --form s1|s2|tok
    python experiments/experiment_22_three_forms.py submit --session g1 --form s2 --task c01 --file c01.txt
    python experiments/experiment_22_three_forms.py report [--form s2] [--session g1]
    python experiments/experiment_22_three_forms.py cost
    python experiments/experiment_22_three_forms.py dry-run

The ruling of 2026-09-11 (`CLAUDE.md`, "The design method"): the model's
behaviour decides between representations by measured experiment, not
the designer's taste, and a decision made on the s-expression is a
decision made with human-language intuition in the room.  So this is
the first experiment that puts the three forms of a LOVA program
against each other as the thing the model must EMIT:

  s1   the Stage-1 s-expression text  -- parentheses, operator names
  s2   the Stage-2 surface            -- one symbol per byte, no parens,
                                          integer references (`core.surface2`)
  tok  the raw token bytes            -- the substrate itself, written as
                                          space-separated decimal byte values
                                          (`core.tokens.encode`)

Ten CLOSED programs (no inputs, one known answer each), expressible in
the core operators plus the list and text families and NOTHING from the
prelude -- because the prelude is a Stage-1 text construct (its names
are integers in the substrate, and s2/tok have no include mechanism),
so operator-only is the only footing on which the same program exists
in all three forms.  Each card lists exactly the operators available;
the three cards differ only in how a call is written.

A session is given ONE form's card and writes the ten programs in that
form.  `submit` assembles the form back into a tree, compiles, runs,
and checks the answer.  `report` gives pass@1 and the LLM-token cost of
what was emitted (tiktoken cl100k_base).  `cost` is the form-intrinsic
half, needing no model: one canonical solution per task, rendered three
ways, measured in LLM tokens and bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.compiler import CompileError, compile as lova_compile          # noqa: E402
from core.runtime import evaluate, Runtime, list_to_python, NIL_VALUE    # noqa: E402
from core.surface import parse as parse1                                 # noqa: E402
from core import surface2                                                # noqa: E402
from core.tokens import decode, encode, SIGNATURES                        # noqa: E402
from core.surface2 import SYMBOLS                                          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_22"

# (canonical solution, expected answer).  Operator-only, no prelude, no
# inputs.  `tests`/`dry-run` check every one against its answer in all
# three forms.
TASKS: Dict[str, Tuple[str, Any]] = {
    "c01": ("(fold (lambda a (lambda x (merge a x))) 0 (map (lambda n (mul n n)) (range 1 6)))", 55),
    "c02": ("(text-len (filter (lambda n (eq (mod n 2) 0)) (range 0 20)))", 10),
    "c03": ("(head (reverse (list 5 3 8 1)))", 1),
    "c04": ("(fold (lambda a (lambda x (if (gt x a) x a))) 0 (list 4 9 2 9 5))", 9),
    "c05": ("(gcd 48 36)", 12),
    "c06": ("(fold (lambda a (lambda x (merge a x))) 0 (range 1 7))", 21),
    "c07": ('(text-len (text-cat "foo" "barbaz"))', 9),
    "c08": ("(head (sort-by (lambda a (lambda b (lt a b))) (list 5 3 8 1)))", 1),
    "c09": ("(any (lambda x (eq x 7)) (range 0 10))", 1),
    "c10": ("(sigma 12)", 28),
}

PROMPTS: Dict[str, str] = {
    "c01": "Sum of the squares of 1..5.  (55)",
    "c02": "How many even numbers in 0..19.  (10)",
    "c03": "The first element of the list 5 3 8 1 reversed.  (1)",
    "c04": "The largest of 4 9 2 9 5.  (9)",
    "c05": "The greatest common divisor of 48 and 36.  (12)",
    "c06": "Sum of 1..6.  (21)",
    "c07": 'The number of characters in "foo" and "barbaz" joined.  (9)',
    "c08": "The smallest of the list 5 3 8 1.  (1)",
    "c09": "1 if 7 is among 0..9, else 0.  (1)",
    "c10": "The sum of the divisors of 12.  (28)",
}


# --- scoring: assemble a form back into a tree, run, check -------------------

def _answer(tree) -> Any:
    compiled, _ = lova_compile(tree)
    value = evaluate(compiled, Runtime(max_steps=2_000_000))
    if value is NIL_VALUE:
        return []
    if isinstance(value, str) or isinstance(value, int):
        return value
    try:
        return list_to_python(value)
    except Exception:
        return value


def _tree_from(form: str, text: str):
    text = text.strip()
    if form == "s1":
        return parse1(text)
    if form == "s2":
        return surface2.parse(text)
    if form == "tok":
        parts = text.replace(",", " ").split()
        data = bytes(int(p, 16) if p.lower().startswith("0x") else int(p) for p in parts)
        return decode(data)
    raise ValueError(f"unknown form {form!r}")


def score(form: str, text: str, task_id: str) -> Dict[str, Any]:
    want = TASKS[task_id][1]
    try:
        tree = _tree_from(form, text)
    except Exception as exc:
        return {"passed": False, "stage": "parse", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        tree, _ = lova_compile(tree)
    except CompileError as exc:
        a = getattr(exc, "anomaly", {})
        return {"passed": False, "stage": "compile",
                "detail": a.get("repair_hint") or a.get("kind") or str(exc)}
    try:
        got = _answer(tree)
    except Exception as exc:
        a = getattr(exc, "anomaly", None)
        return {"passed": False, "stage": "run",
                "detail": (a or {}).get("repair_hint") or f"{type(exc).__name__}: {exc}"}
    return {"passed": got == want, "stage": "run", "got": got, "want": want}


# --- the cost axis (no model) -----------------------------------------------

def _tiktoken():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def cost_row(task_id: str) -> Dict[str, Any]:
    src = TASKS[task_id][0]
    tree = parse1(src)
    s2 = surface2.render(tree)
    data = encode(tree)
    tok = " ".join(str(b) for b in data)
    enc = _tiktoken()
    return {
        "s1_chars": len(src), "s2_chars": len(s2), "bytes": len(data),
        "s1_llm": len(enc.encode(src)),
        "s2_llm": len(enc.encode(s2)),
        "tok_llm": len(enc.encode(tok)),
    }


# --- cards ------------------------------------------------------------------

_OPERATORS = """The operators you may use (nothing else exists; there is no standard library):

  arithmetic   (merge a b)=a+b  (sub a b)=a-b  (mul a b)=a*b  (div a b)=a//b
               (mod a b)  (neg a)  (gcd a b)  (p n)=partitions  (tau n)=divisor count
               (sigma n)=divisor sum  (mobius n)
  compare      (eq a b) (ne a b) (lt a b) (gt a b) (le a b) (ge a b) -> 1 or 0
  control      (if c then else)   c is an integer, non-zero is true
  functions    (lambda x body)  a function of ONE parameter; curry for two:
               (lambda a (lambda b ...)) and call (f a b)
  lists        (list 1 2 3)  (cons x xs)  (head xs)  (tail xs)  (nil)  (nil? xs)
  list ops     (map f xs) (filter f xs) (fold f acc xs) [f called (f acc x)]
               (reverse xs) (range a b)=a..b-1 (any f xs) (sort-by less xs)
               (zip xs ys)
  text         "abc" is a text; (text-len v)=length of a text OR a list;
               (text-cat a b) (text-slice t i j) (text-int t) (int-text n)

An operator is not a value: to pass one to map/fold, wrap it in a lambda."""

_TASK_LINES = "\n".join(f"  {tid}: {PROMPTS[tid]}" for tid in TASKS)


def card_s1() -> str:
    return f"""# LOVA, Stage-1 form

A program is one s-expression.  A call is `(operator arg arg ...)`,
parenthesised, the operator named.  Examples:

  (merge 2 3)                      -> 5
  (map (lambda n (mul n n)) (range 1 4))   -> (1 4 9)
  (fold (lambda a (lambda x (merge a x))) 0 (list 1 2 3))   -> 6

{_OPERATORS}

Write each of these ten programs as one Stage-1 s-expression.  The
answer is in parentheses after each; your program must produce it.

{_TASK_LINES}
"""


def _s2_examples() -> str:
    rows = []
    for src in ["(merge 2 3)",
                "(map (lambda n (mul n n)) (range 1 4))",
                "(fold (lambda a (lambda x (merge a x))) 0 (list 1 2 3))",
                '(text-len "abc")']:
        rows.append(f"  {src:<52s} ->  {surface2.render(parse1(src))}")
    return "\n".join(rows)


def _symbol_table() -> str:
    # Only the operators the tasks need, plus the structural ones.
    from core.surface import NAME_TO_TOKEN
    names = ["merge", "sub", "mul", "div", "mod", "neg", "gcd", "p", "tau", "sigma", "mobius",
             "eq", "ne", "lt", "gt", "le", "ge", "if", "lambda", "apply", "let", "ref",
             "cons", "head", "tail", "nil", "nil?",
             "map", "filter", "fold", "reverse", "range", "any", "sort-by", "zip",
             "text-len", "text-cat", "text-slice", "text-int", "int-text"]
    rows = []
    for n in names:
        tok = NAME_TO_TOKEN.get(n)
        if tok is None:
            continue
        rows.append(f"  {SYMBOLS[tok]}  {n}")
    return "\n".join(rows)


def card_s2() -> str:
    return f"""# LOVA, Stage-2 form

A program is a stream of one character per operator, no parentheses.
An operator's arguments follow it in order; a variadic operator (list,
lambda's group) is closed by `;`.  A reference to the k-th enclosing
`\\`-bound parameter is a single character (`0`..`9` for the innermost
ten).  An integer is written in decimal; a text is `"..."`.  Two
digits that would run together are separated by one space.

The symbol for each operator you may use:

{_symbol_table()}

Structure of a call: the operator's symbol, then each argument written
the same way.  `\\` (lambda) is followed by a parameter and a body;
inside the body the parameter is referenced by its depth digit.

Examples (the Stage-1 form on the left is only to show the meaning):

{_s2_examples()}

{_OPERATORS}

Write each of these ten programs as a Stage-2 stream.

{_TASK_LINES}
"""


def _tok_examples() -> str:
    rows = []
    for src in ["(merge 2 3)", "(gcd 48 36)", "(range 1 4)"]:
        data = encode(parse1(src))
        rows.append(f"  {src:<20s} ->  {' '.join(str(b) for b in data)}")
    return "\n".join(rows)


def card_tok() -> str:
    from core.surface import NAME_TO_TOKEN
    names = ["merge", "sub", "mul", "div", "mod", "neg", "gcd", "p", "tau", "sigma", "mobius",
             "eq", "ne", "lt", "gt", "le", "ge", "if", "lambda", "apply", "let", "ref",
             "cons", "head", "tail", "nil", "nil?",
             "map", "filter", "fold", "reverse", "range", "any", "sort-by", "zip",
             "text-len", "text-cat", "text-slice", "text-int", "int-text"]
    rows = []
    for n in names:
        tok = NAME_TO_TOKEN.get(n)
        if tok is not None:
            rows.append(f"  {tok:>3d}  {n}")
    table = "\n".join(rows)
    return f"""# LOVA, raw-token form

A program is the byte stream of its tree, written as space-separated
DECIMAL byte values.  Each node is: the operator's byte, then its
arguments' bytes in order.  A variadic operator (list, and a lambda
group) ends with byte 0 (END).

An integer literal is THREE-or-more bytes: byte 1 (LIT_INT), then a
length byte n, then the value as n bytes, signed, big-endian.  So 5 is
`1 1 5`; 48 is `1 1 48`; 300 is `1 2 1 44`.

The operator bytes you may use:

{table}

Examples:

{_tok_examples()}

Write each of these ten programs as a decimal byte stream.

{_TASK_LINES}
"""


CARDS = {"s1": card_s1, "s2": card_s2, "tok": card_tok}


# --- log --------------------------------------------------------------------

def _log_path(session: str, form: str) -> Path:
    p = RESULTS / session / form / "log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append(session: str, form: str, record: Dict[str, Any]) -> None:
    with _log_path(session, form).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _records(session: str, form: str) -> List[Dict[str, Any]]:
    p = _log_path(session, form)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# --- commands ---------------------------------------------------------------

def cmd_tasks(args) -> int:
    for tid in TASKS:
        print(f"{tid}: {PROMPTS[tid]}")
    return 0


def cmd_card(args) -> int:
    print(CARDS[args.form]())
    return 0


def cmd_submit(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8").strip()
    enc = _tiktoken()
    result = score(args.form, text, args.task)
    attempt = 1 + sum(1 for r in _records(args.session, args.form) if r["task"] == args.task)
    _append(args.session, args.form, {
        "task": args.task, "attempt": attempt, "passed": result["passed"],
        "emitted_chars": len(text), "emitted_llm": len(enc.encode(text)),
        "program": text, "result": result, "time": time.time()})
    if result["passed"]:
        print(f"[{args.task} attempt {attempt}] PASS ({len(enc.encode(text))} LLM tokens emitted)")
    else:
        print(f"[{args.task} attempt {attempt}] FAIL at {result['stage']}: "
              f"{result.get('detail', result.get('got'))}")
    return 0 if result["passed"] else 1


def _sessions() -> List[str]:
    if not RESULTS.exists():
        return []
    return sorted(p.name for p in RESULTS.iterdir() if p.is_dir() and not p.name.startswith("_"))


def cmd_report(args) -> int:
    forms = [args.form] if args.form else ["s1", "s2", "tok"]
    sessions = [args.session] if args.session else _sessions()
    print(f"  {'form':4s} {'session':8s} {'tasks':>5s} {'green':>5s} {'first':>5s} "
          f"{'attempts':>8s} {'emit_llm':>8s}")
    grand: Dict[str, Dict[str, int]] = {}
    for form in forms:
        for session in sessions:
            recs = _records(session, form)
            if not recs:
                continue
            tasks = sorted({r["task"] for r in recs})
            green = sum(any(r["passed"] for r in recs if r["task"] == t) for t in tasks)
            first = sum(1 for t in tasks if next(r for r in recs if r["task"] == t)["passed"])
            emit = sum(r["emitted_llm"] for r in recs)
            print(f"  {form:4s} {session:8s} {len(tasks):5d} {green:5d} {first:5d} "
                  f"{len(recs):8d} {emit:8d}")
            g = grand.setdefault(form, {"tasks": 0, "green": 0, "first": 0, "attempts": 0, "emit": 0})
            for k, v in (("tasks", len(tasks)), ("green", green), ("first", first),
                         ("attempts", len(recs)), ("emit", emit)):
                g[k] += v
    for form, g in grand.items():
        print(f"  {form:4s} {'all':8s} {g['tasks']:5d} {g['green']:5d} {g['first']:5d} "
              f"{g['attempts']:8d} {g['emit']:8d}")
    return 0


def cmd_cost(args) -> int:
    enc = _tiktoken()
    print(f"  {'task':5s} {'s1_llm':>7s} {'s2_llm':>7s} {'tok_llm':>8s} "
          f"{'s1_ch':>6s} {'s2_ch':>6s} {'bytes':>6s}")
    tot = {"s1_llm": 0, "s2_llm": 0, "tok_llm": 0, "s1_chars": 0, "s2_chars": 0, "bytes": 0}
    for tid in TASKS:
        r = cost_row(tid)
        for k in tot:
            tot[k] += r[k]
        print(f"  {tid:5s} {r['s1_llm']:7d} {r['s2_llm']:7d} {r['tok_llm']:8d} "
              f"{r['s1_chars']:6d} {r['s2_chars']:6d} {r['bytes']:6d}")
    print(f"  {'all':5s} {tot['s1_llm']:7d} {tot['s2_llm']:7d} {tot['tok_llm']:8d} "
          f"{tot['s1_chars']:6d} {tot['s2_chars']:6d} {tot['bytes']:6d}")
    s1, s2, tk = tot["s1_llm"], tot["s2_llm"], tot["tok_llm"]
    print(f"\n  LLM tokens: s2 is {s1 / s2:.2f}x cheaper than s1; "
          f"tok is {tk / s1:.2f}x s1 ({'more' if tk > s1 else 'fewer'}).")
    return 0


def cmd_dry_run(args) -> int:
    ok = True
    from core.surface import parse
    for tid, (src, want) in TASKS.items():
        tree = parse(src)
        forms = {"s1": src, "s2": surface2.render(tree),
                 "tok": " ".join(str(b) for b in encode(tree))}
        line = [tid]
        for form, text in forms.items():
            r = score(form, text, tid)
            line.append(f"{form}={'ok' if r['passed'] else 'FAIL ' + str(r.get('detail', r.get('got')))}")
            ok = ok and r["passed"]
        print("  " + "  ".join(line))
    print("  all ten tasks round-trip and evaluate in all three forms" if ok else "  PROBLEM above")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.set_defaults(func=cmd_tasks)
    p = sub.add_parser("card"); p.add_argument("--form", required=True, choices=["s1", "s2", "tok"])
    p.set_defaults(func=cmd_card)
    p = sub.add_parser("submit"); p.add_argument("--session", required=True)
    p.add_argument("--form", required=True, choices=["s1", "s2", "tok"])
    p.add_argument("--task", required=True, choices=list(TASKS)); p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_submit)
    p = sub.add_parser("report"); p.add_argument("--form", choices=["s1", "s2", "tok"])
    p.add_argument("--session"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("cost"); p.set_defaults(func=cmd_cost)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
