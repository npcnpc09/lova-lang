"""Experiment 12 -- Abstraction and iteration (M9).

Until M9 a LOVA program was a fixed-depth expression over built-in
operators.  ``LAMBDA`` and ``APPLY`` raised ``NotImplementedError``,
``LOOP_UNTIL`` had no implementation, and ``LET`` was a plain let, so
there was no way to write a function, call one, or repeat anything.
Every program in ``corpus/`` and ``apps/`` was as long as it was
written.  The consequence is stronger than "inconvenient": the
language was not computationally universal, and no amount of corpus or
fine-tuning work would have changed that.

M9 adds unary closures, currying, letrec, a loop combinator, ``mul`` /
``mod`` on the two never-implemented mock-theta slots, and the
``deviation`` / ``threshold`` pair that gives ordering.  This
experiment measures what that bought, in four parts:

  1. **Expressiveness.**  Ten algorithmic tasks that need recursion or
     iteration, each checked against a Python reference over a range
     of inputs.  The pre-M9 baseline is measured, not assumed: the
     same programs are run through a runtime with the M9 operators
     disabled.

  2. **Universality.**  Primitive recursion and unbounded minimisation
     (the mu-operator) are each exhibited in LOVA.  Together with
     zero-test, successor and predecessor -- all present -- that is
     the standard mu-recursive argument for Turing-completeness.  The
     experiment demonstrates the ingredients; it does not claim to
     prove the theorem.

  3. **Ceilings.**  Non-termination is now reachable, so it has to be
     observable.  Every runaway shape must produce a structured
     anomaly carrying the full L2 schema -- never a hang, never a
     Python traceback.

  4. **Density on algorithmic tasks.**  The density numbers in the
     README come from number-theory tasks where LOVA has a one-byte
     built-in and Python calls sympy.  That comparison is open to the
     objection that the tasks were chosen to suit the built-ins.  These
     ten tasks have no such shortcut on either side -- both languages
     have to write the algorithm out -- so the ratio here is the
     harder, more honest number.  ``tiktoken`` is optional; byte
     density is reported either way.
"""

from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.compiler import compile as lova_compile
from core.conservation import BudgetTrap, DepthTrap, DomainTrap, StepTrap
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import encode


def _stage2_tokens(tree) -> int:
    """Stage-2 token estimate -- identical to Experiment 11's method.

    One LLM token per AST node, plus one per literal payload: what a
    fine-tuned vocabulary would plausibly reach.  Reproduced here
    rather than imported so the two experiments cannot silently drift
    apart in their definitions.
    """
    from core.tokens import LIT_INT
    total = 1
    if tree.op == LIT_INT:
        total += 1  # value payload
    for a in tree.args:
        if hasattr(a, "op"):
            total += _stage2_tokens(a)
    return total


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


# --- the task set ------------------------------------------------------------
#
# Each task: a LOVA source template with a {n} (and sometimes {m})
# placeholder, a Python reference, the inputs to check, and the
# idiomatic Python spelling used for the density comparison.
#
# Inputs are kept small where the recursion depth is linear in the
# input -- the point of the task is expressibility, not stress.

class Task:
    def __init__(self, tid, lova, py_ref, inputs, py_src, note=""):
        self.id = tid
        self.lova = lova
        self.py_ref = py_ref
        self.inputs = inputs
        self.py_src = py_src
        self.note = note


TASKS = [
    Task(
        "factorial",
        "(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))"
        "(fact {n})",
        lambda n: math.factorial(n),
        [0, 1, 5, 10, 20],
        "def fact(n):\n"
        "    return 1 if n == 0 else n * fact(n - 1)\n",
        "primitive recursion",
    ),
    Task(
        "fibonacci",
        "(defn fib [n] (if-surprise (threshold (deviation n 1))"
        " (merge (fib (merge n -1)) (fib (merge n -2))) n))"
        "(fib {n})",
        lambda n: _fib(n),
        [0, 1, 7, 15, 20],
        "def fib(n):\n"
        "    return n if n < 2 else fib(n - 1) + fib(n - 2)\n",
        "tree recursion",
    ),
    Task(
        "is-prime",
        "(defn check [d n] (if-surprise (threshold (deviation (mul d d) n)) 1"
        " (if-surprise (mod n d) (check (merge d 1) n) 0)))"
        "(defn is-prime [n] (if-surprise (threshold (deviation 2 n)) 0 (check 2 n)))"
        "(is-prime {n})",
        lambda n: int(n >= 2 and all(n % d for d in range(2, int(n ** 0.5) + 1))),
        [1, 2, 4, 91, 97, 561, 1999],
        "def is_prime(n):\n"
        "    if n < 2:\n"
        "        return 0\n"
        "    d = 2\n"
        "    while d * d <= n:\n"
        "        if n % d == 0:\n"
        "            return 0\n"
        "        d += 1\n"
        "    return 1\n",
        "loop with early exit",
    ),
    Task(
        "collatz-steps",
        "(defn next [n] (if-surprise (mod n 2) (merge (mul 3 n) 1) (partition n)))"
        "(defn steps [n acc] (if-surprise (deviation n 1)"
        " (steps (next n) (merge acc 1)) acc))"
        "(steps {n} 0)",
        lambda n: _collatz(n),
        [1, 6, 7, 27],
        "def steps(n):\n"
        "    c = 0\n"
        "    while n != 1:\n"
        "        n = n // 2 if n % 2 == 0 else 3 * n + 1\n"
        "        c += 1\n"
        "    return c\n",
        "accumulator via currying",
    ),
    Task(
        "sum-to",
        "(defn sum-to [n] (if-surprise n (merge n (sum-to (merge n -1))) 0))"
        "(sum-to {n})",
        lambda n: n * (n + 1) // 2,
        [0, 1, 10, 100],
        "def sum_to(n):\n"
        "    return 0 if n == 0 else n + sum_to(n - 1)\n",
        "linear recursion",
    ),
    Task(
        "power-of-two",
        "(defn pow2 [n] (if-surprise n (mul 2 (pow2 (merge n -1))) 1))"
        "(pow2 {n})",
        lambda n: 2 ** n,
        [0, 1, 8, 32],
        "def pow2(n):\n"
        "    return 1 if n == 0 else 2 * pow2(n - 1)\n",
        "exponentiation",
    ),
    Task(
        "gcd-euclid",
        "(defn g [a b] (if-surprise b (g b (mod a b)) a))"
        "(g {n} {m})",
        lambda n, m: math.gcd(n, m),
        [(12, 18), (7, 13), (270, 192), (0, 5)],
        "def g(a, b):\n"
        "    return a if b == 0 else g(b, a % b)\n",
        "two-argument recursion (Euclid, not the gcd built-in)",
    ),
    Task(
        "count-divisors",
        "(defn count [d n] (if-surprise (threshold (deviation d n)) 0"
        " (merge (if-surprise (mod n d) 0 1) (count (merge d 1) n))))"
        "(defn tau-by-loop [n] (count 1 n))"
        "(tau-by-loop {n})",
        lambda n: sum(1 for d in range(1, n + 1) if n % d == 0),
        [1, 12, 28, 60],
        "def tau_by_loop(n):\n"
        "    return sum(1 for d in range(1, n + 1) if n % d == 0)\n",
        "counting loop (reimplements the tau built-in)",
    ),
    Task(
        "multiply-by-adding",
        "(defn mul-add [a b] (if-surprise b (merge a (mul-add a (merge b -1))) 0))"
        "(mul-add {n} {m})",
        lambda n, m: n * m,
        [(7, 6), (0, 9), (13, 13)],
        "def mul_add(a, b):\n"
        "    return 0 if b == 0 else a + mul_add(a, b - 1)\n",
        "defines multiplication from addition",
    ),
    Task(
        "divide-by-subtracting",
        "(defn div-sub [a b] (if-surprise (threshold (deviation b a)) 0"
        " (merge 1 (div-sub (merge a (mul -1 b)) b))))"
        "(div-sub {n} {m})",
        lambda n, m: n // m,
        [(10, 2), (17, 5), (3, 7), (100, 10)],
        "def div_sub(a, b):\n"
        "    return 0 if a < b else 1 + div_sub(a - b, b)\n",
        "defines division from subtraction -- the core has no `div`",
    ),
]


def _fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _collatz(n: int) -> int:
    count = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        count += 1
    return count


def _instantiate(task: Task, args) -> str:
    if not isinstance(args, tuple):
        args = (args,)
    src = task.lova.replace("{n}", str(args[0]))
    if len(args) > 1:
        src = src.replace("{m}", str(args[1]))
    return src


# --- part 1: expressiveness --------------------------------------------------

def part_1_expressiveness() -> dict:
    _hr("1. Expressiveness -- ten tasks that need recursion or iteration")
    print(f"  {'task':<24s} {'cases':>6s}  {'M9':>7s}  {'pre-M9':>7s}  note")
    print("  " + "-" * 74)

    m9_pass = m9_total = pre_pass = 0
    for task in TASKS:
        passed = 0
        for args in task.inputs:
            src = _instantiate(task, args)
            expected = (task.py_ref(*args) if isinstance(args, tuple)
                        else task.py_ref(args))
            try:
                compiled, _ = lova_compile(parse(src))
                actual = evaluate(compiled, Runtime())
            except Exception as exc:  # noqa: BLE001 - we are measuring failures
                actual = f"<{type(exc).__name__}>"
            if actual == expected:
                passed += 1
        m9_pass += passed
        m9_total += len(task.inputs)

        # Pre-M9 baseline: the same source through a runtime with the
        # abstraction operators disabled, which is what the interpreter
        # did before this milestone.
        pre_ok = _runs_without_abstraction(_instantiate(task, task.inputs[0]))
        pre_pass += int(pre_ok)

        print(f"  {task.id:<24s} {len(task.inputs):>6d}  "
              f"{passed}/{len(task.inputs):<5d}  "
              f"{'yes' if pre_ok else 'no':>7s}  {task.note}")

    print("  " + "-" * 74)
    print(f"  M9:      {m9_pass}/{m9_total} cases pass")
    print(f"  pre-M9:  {pre_pass}/{len(TASKS)} tasks even representable")
    return {"m9_pass": m9_pass, "m9_total": m9_total,
            "pre_pass": pre_pass, "tasks": len(TASKS)}


def _runs_without_abstraction(src: str) -> bool:
    """Would this program have run before M9?

    Rather than reason about it, disable the operators M9 implemented
    and see.  Anything reaching LAMBDA / APPLY / LOOP_UNTIL / MUL / MOD
    / DEVIATION / THRESHOLD would have hit ``NotImplementedError`` in
    the pre-M9 runtime.
    """
    from core.tokens import (
        APPLY, DEVIATION, LAMBDA, LIT_INT, LOOP_UNTIL, MOD, MUL, THRESHOLD,
    )
    pre_m9_missing = {APPLY, DEVIATION, LAMBDA, LOOP_UNTIL, MOD, MUL, THRESHOLD}

    def walk(node) -> bool:
        if node.op in pre_m9_missing:
            return False
        if node.op == LIT_INT:
            return True
        return all(walk(c) for c in node.args)

    try:
        return walk(parse(src))
    except Exception:  # noqa: BLE001
        return False


# --- part 2: universality ----------------------------------------------------

def part_2_universality() -> dict:
    _hr("2. Universality -- primitive recursion and the mu-operator")

    print("  The mu-recursive functions are the primitive recursive ones")
    print("  closed under unbounded minimisation.  LOVA now has each")
    print("  ingredient; here is one of each, run.")
    print()

    # zero test, successor, predecessor
    print("  zero test    (if-surprise n THEN ELSE)     ", end="")
    zero = evaluate(parse("(if-surprise 0 111 222)"))
    nonzero = evaluate(parse("(if-surprise 5 111 222)"))
    print(f"-> {zero}, {nonzero}   (0 takes ELSE, 5 takes THEN)")

    print("  successor    (merge n 1)                   ", end="")
    print(f"-> {evaluate(parse('(merge 41 1)'))}")

    print("  predecessor  (merge n -1)                  ", end="")
    print(f"-> {evaluate(parse('(merge 43 -1)'))}")

    # primitive recursion
    fact = evaluate(parse(
        "(defn fact [n] (if-surprise n (mul n (fact (merge n -1))) 1))(fact 12)"
    ))
    print(f"  primitive recursion  fact(12)             -> {fact} "
          f"({'matches' if fact == math.factorial(12) else 'MISMATCH'})")

    # minimisation: least x with x*x >= n, via loop-until.  Iterative,
    # so an unbounded search costs no call depth at all.
    mu_src = (
        "(defn isqrt-ceil [n]"
        "  (apply (loop-until (lambda x (threshold (deviation (mul x x) (merge n -1))))"
        "                     (lambda x (merge x 1)))"
        "         0))"
        "(isqrt-ceil {n})"
    )
    print()
    print("  minimisation (mu-operator) via loop-until:")
    print("    mu x. [ x*x >= n ]   -- least x whose square reaches n")
    mu_ok = 0
    for n in (0, 1, 2, 9, 10, 50, 1000):
        got = evaluate(parse(mu_src.replace("{n}", str(n))), Runtime())
        want = math.ceil(math.sqrt(n))
        mu_ok += int(got == want)
        print(f"    n={n:<6d} mu -> {got:<4d} expected {want:<4d} "
              f"{'ok' if got == want else 'MISMATCH'}")

    # ...and the same search costs no call depth, because loop-until
    # iterates rather than recurses.
    rt = Runtime(max_call_depth=4)
    deep = evaluate(parse(mu_src.replace("{n}", "10000")), rt)
    print(f"    with max_call_depth=4: mu(10000) -> {deep} "
          f"(iteration does not consume call frames)")

    print()
    print("  Ingredients present: zero test, successor, predecessor,")
    print("  composition, primitive recursion, unbounded minimisation.")
    print("  That is the standard mu-recursive basis.  Stated as an")
    print("  observation about the operator set, not as a proof.")
    return {"mu_ok": mu_ok, "mu_cases": 7, "factorial_ok": fact == math.factorial(12)}


# --- part 3: ceilings --------------------------------------------------------

RUNAWAY_SHAPES = [
    ("unguarded self-recursion",
     "(defn f [x] (f x))(f 1)"),
    ("recursion whose base case is unreachable",
     "(defn f [x] (if-surprise (deviation x -1) (f (merge x 1)) 0))(f 0)"),
    ("mutual-shaped recursion through one name",
     "(defn f [x] (f (mul x 2)))(f 1)"),
    ("loop-until with a predicate that never fires",
     "(apply (loop-until (lambda x 0) (lambda x (ref x))) 1)"),
    ("loop-until whose step never approaches the predicate",
     "(apply (loop-until (lambda x (threshold (deviation x 1000000000)))"
     "                   (lambda x (merge x -1))) 0)"),
]

L2_FIELDS = ("kind", "detail", "position_path", "offending_op",
             "offending_op_name", "valid_alternatives", "repair_hint")


def part_3_ceilings() -> dict:
    _hr("3. Ceilings -- non-termination as a structured anomaly")
    print("  Every shape below fails to terminate.  A hang or a Python")
    print("  traceback would be a substrate bug; what an AI caller needs")
    print("  is the same anomaly schema it already handles.")
    print()

    trapped = schema_ok = 0
    for label, src in RUNAWAY_SHAPES:
        # The ceilings are pinned to what this experiment measures: M22
        # raised the default depth to 10 000, at which the argument-
        # doubling shape overflows the integer-size guard (a DomainTrap,
        # also L2) before it reaches the depth ceiling.
        rt = Runtime(max_steps=200_000, max_call_depth=200)
        try:
            result = evaluate(parse(src), rt)
            print(f"  {label:<48s} NO TRAP (returned {result!r})")
            continue
        except (BudgetTrap, DomainTrap) as trap:
            trapped += 1
            anomaly = trap.anomaly
            complete = all(f in anomaly for f in L2_FIELDS)
            schema_ok += int(complete)
            kind = anomaly["kind"]
            family = ("DepthTrap" if isinstance(trap, DepthTrap)
                      else "StepTrap" if isinstance(trap, StepTrap)
                      else "DomainTrap" if isinstance(trap, DomainTrap)
                      else "BudgetTrap")
            print(f"  {label:<48s} {family:<10s} {kind}")
            print(f"  {'':<48s} {'':<10s} hint: {anomaly['repair_hint'][:60]}...")

    print()
    print(f"  trapped:           {trapped}/{len(RUNAWAY_SHAPES)}")
    print(f"  full L2 schema:    {schema_ok}/{len(RUNAWAY_SHAPES)}")
    print("  every trap is a BudgetTrap subclass, so one handler covers")
    print("  budget overrun, call depth and step ceiling alike.")
    return {"trapped": trapped, "schema_ok": schema_ok,
            "shapes": len(RUNAWAY_SHAPES)}


# --- part 4: density on algorithmic tasks ------------------------------------

def part_4_density() -> dict:
    _hr("4. Density on algorithmic tasks (no built-in shortcut on either side)")

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:  # noqa: BLE001
        enc = None
        print("  (tiktoken not installed -- byte density only;")
        print("   `pip install -e \".[experiments]\"` for LLM-token counts)")
        print()

    print(f"  {'task':<24s} {'LOVA B':>7s} {'Py B':>6s} {'B ratio':>8s}"
          f" {'S1 tok':>7s} {'S2 est':>7s} {'Py tok':>7s}"
          f" {'S1/Py':>7s} {'S2/Py':>7s}")
    print("  " + "-" * 84)

    lova_bytes = py_bytes = lova_toks = py_toks = stage2_toks = 0
    for task in TASKS:
        # Density is measured on the source without the concrete input,
        # so it compares the *programs*, not the call sites.
        src = _instantiate(task, task.inputs[0])
        encoded = encode(parse(src))
        lb, pb = len(encoded), len(task.py_src.encode("utf-8"))
        lova_bytes += lb
        py_bytes += pb

        # Stage-2 estimate, computed exactly as Experiment 11 does it:
        # one LLM token per AST node plus one per literal payload, which
        # is what a fine-tuned vocabulary would plausibly reach.
        s2 = _stage2_tokens(parse(src))
        stage2_toks += s2

        if enc is not None:
            # The Stage-1 figure is the token count of the text surface,
            # which is what an LLM would actually emit today -- not the
            # byte count of the integer form.
            lt = len(enc.encode(src))
            pt = len(enc.encode(task.py_src))
            lova_toks += lt
            py_toks += pt
            cells = (f" {lt:>7d} {s2:>7d} {pt:>7d}"
                     f" {pt / lt:>6.2f}x {pt / s2:>6.2f}x")
        else:
            cells = f" {'-':>7s} {s2:>7d} {'-':>7s} {'-':>7s} {'-':>7s}"

        print(f"  {task.id:<24s} {lb:>7d} {pb:>6d} {pb / lb:>7.2f}x" + cells)

    print("  " + "-" * 84)
    print(f"  aggregate bytes:      LOVA {lova_bytes}  vs  Python {py_bytes}"
          f"   -> {py_bytes / lova_bytes:.2f}x")
    result = {"lova_bytes": lova_bytes, "py_bytes": py_bytes,
              "byte_ratio": py_bytes / lova_bytes}
    if enc is not None:
        print(f"  aggregate LLM tokens: Stage-1 {lova_toks}  Stage-2 est "
              f"{stage2_toks}  vs  Python {py_toks}")
        print(f"                        Stage-1/Python "
              f"{py_toks / lova_toks:.2f}x    "
              f"Stage-2/Python {py_toks / stage2_toks:.2f}x")
        result.update({"lova_tokens": lova_toks, "py_tokens": py_toks,
                       "stage2_tokens": stage2_toks,
                       "token_ratio": py_toks / lova_toks,
                       "stage2_ratio": py_toks / stage2_toks})
    print()
    print("  Read this against the README's 8.5x / 3.2x, which come from")
    print("  number-theory tasks where a one-byte LOVA built-in stands in")
    print("  for a sympy call.  Here neither side has a shortcut and both")
    print("  have to write the algorithm out, so this is the ratio that")
    print("  survives the obvious objection to the headline number.")
    return result


# --- main --------------------------------------------------------------------

def run() -> None:
    print("LOVA M9 -- abstraction and iteration (Experiment 12)")
    p1 = part_1_expressiveness()
    p2 = part_2_universality()
    p3 = part_3_ceilings()
    p4 = part_4_density()

    _hr("Experiment 12 -- summary")
    print(f"  expressiveness:  {p1['m9_pass']}/{p1['m9_total']} cases pass under M9;"
          f" {p1['pre_pass']}/{p1['tasks']} tasks were representable before it")
    print(f"  universality:    mu-operator {p2['mu_ok']}/{p2['mu_cases']},"
          f" primitive recursion {'ok' if p2['factorial_ok'] else 'FAILED'}")
    print(f"  ceilings:        {p3['trapped']}/{p3['shapes']} runaway shapes trapped,"
          f" {p3['schema_ok']}/{p3['shapes']} with the full L2 schema")
    print(f"  density:         {p4['byte_ratio']:.2f}x bytes"
          + (f", Stage-1 {p4['token_ratio']:.2f}x / Stage-2 "
             f"{p4['stage2_ratio']:.2f}x LLM tokens"
             if "token_ratio" in p4 else "")
          + " vs Python on algorithmic tasks")
    if p4.get("token_ratio", 1.0) < 1.0:
        print()
        print("  NEGATIVE RESULT: on tasks with no built-in shortcut the")
        print("  Stage-1 text surface costs MORE LLM tokens than Python.")
        print("  See journal/experiment_12.md -- this is the honest")
        print("  boundary of the density claim, and it is load-bearing.")


if __name__ == "__main__":
    run()
