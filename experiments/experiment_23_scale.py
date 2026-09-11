"""Experiment 23 -- does the Stage-2 surface hold at program size? (Q104)

    python experiments/experiment_23_scale.py tasks
    python experiments/experiment_23_scale.py card  --form s1|s2|tok
    python experiments/experiment_23_scale.py submit --session b1 --form s2 --task b01 --file b01.txt
    python experiments/experiment_23_scale.py report [--form s2] [--session b1]
    python experiments/experiment_23_scale.py cost
    python experiments/experiment_23_scale.py dry-run

Experiment 22 put the three forms of a LOVA program against each other
on ten CLOSED one-expression tasks, and Q101 -- once the substrate
cards were rebuilt from the substrate's own operators -- found that the
forms do not separate on reliability at that size: s1, s2 and tok were
all written first-try, and they separated only on cost (s2 ~145 emitted
LLM tokens, s1 ~190, tok 528).

Both Stage-2 sessions then named the thing that size hid.  A reference
in s2/tok is by the NAME's number, tracked across the whole program (a
lambda parameter called `n` in two different lambdas is one number; a
`let`-bound helper is another), and adjacent literals need a separating
space.  Both failures are silent: a wrong number or a missing space
yields a different VALUE, not a parse error.  On a one-line program
there is nothing to track.  This experiment asks what happens when
there is.

Six tasks, the same rules as Exp 22 -- closed, operator-only, no
prelude, one known answer -- but 2x to 5x the size, each needing
recursion through a `let`-bound self-referencing lambda, and the last
carrying eight distinct names at once:

    b01 111 bytes of Collatz     b04 a digit sum by recursion
    b02 naive Fibonacci          b05 primes composed with a fold
    b03 a primality helper       b06 longest run: 8 names, nested lets

The cards are Experiment 22's, unchanged apart from the task list, so
the only variable between the two experiments is program size.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import experiment_22_three_forms as e22  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_23"

TASKS: Dict[str, Tuple[str, Any]] = {
    "b01": ("(let f (lambda n (if (eq n 1) 0 (merge 1 (f (if (mod n 2) (merge (mul 3 n) 1) (div n 2)))))) (f 27))", 111),
    "b02": ("(let f (lambda n (if (lt n 2) n (merge (f (sub n 1)) (f (sub n 2))))) (f 25))", 75025),
    "b03": ("(let divs (lambda n (lambda d (if (gt (mul d d) n) 1 (if (mod n d) (divs n (merge d 1)) 0)))) (text-len (filter (lambda n (if (lt n 2) 0 (divs n 2))) (range 0 50))))", 15),
    "b04": ("(let f (lambda n (if (eq n 0) 0 (merge (mod n 10) (f (div n 10))))) (f 1048576))", 31),
    "b05": ("(let divs (lambda n (lambda d (if (gt (mul d d) n) 1 (if (mod n d) (divs n (merge d 1)) 0)))) (fold (lambda a (lambda x (merge a x))) 0 (filter (lambda n (if (lt n 2) 0 (divs n 2))) (range 0 100))))", 1060),
    "b06": ('(let go (lambda cs (lambda st (if (nil? cs) (head st) (let c (head cs) (let best (head st) (let cur (head (tail st)) (let prev (head (tail (tail st))) (let run (if (eq c prev) (merge cur 1) 1) (go (tail cs) (cons (if (gt run best) run best) (cons run (cons c (nil))))))))))))) (go (text-chars "aaabbbbcca") (cons 0 (cons 0 (cons -1 (nil))))))', 4),
}

PROMPTS: Dict[str, str] = {
    "b01": ("Start from 27.  Repeatedly: if the number is odd replace it by 3n+1, "
            "if even by n/2.  Count how many steps it takes to reach 1.  (111)"),
    "b02": "The 25th Fibonacci number, with fib(0)=0, fib(1)=1.  (75025)",
    "b03": "How many of the numbers 0..49 are prime.  (15)",
    "b04": "The sum of the decimal digits of 1048576.  (31)",
    "b05": "The sum of all primes below 100.  (1060)",
    "b06": ('The length of the longest run of equal characters in the text '
            '"aaabbbbcca".  (4)'),
}


def _bind() -> None:
    """Point Experiment 22's cards and scoring at this task set."""
    e22.TASKS = TASKS
    e22.PROMPTS = PROMPTS
    e22._TASK_LINES = "\n".join(f"  {tid}: {PROMPTS[tid]}" for tid in TASKS)
    e22.RESULTS = RESULTS
    e22.MAX_STEPS = 60_000_000      # b02 is a naive Fibonacci; b05 folds over 100


def main(argv=None) -> int:
    _bind()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.set_defaults(func=e22.cmd_tasks)
    p = sub.add_parser("card"); p.add_argument("--form", required=True, choices=["s1", "s2", "tok"])
    p.set_defaults(func=e22.cmd_card)
    p = sub.add_parser("submit"); p.add_argument("--session", required=True)
    p.add_argument("--form", required=True, choices=["s1", "s2", "tok"])
    p.add_argument("--task", required=True, choices=list(TASKS)); p.add_argument("--file", required=True)
    p.set_defaults(func=e22.cmd_submit)
    p = sub.add_parser("report"); p.add_argument("--form", choices=["s1", "s2", "tok"])
    p.add_argument("--session"); p.set_defaults(func=e22.cmd_report)
    p = sub.add_parser("cost"); p.set_defaults(func=e22.cmd_cost)
    p = sub.add_parser("dry-run"); p.set_defaults(func=e22.cmd_dry_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
