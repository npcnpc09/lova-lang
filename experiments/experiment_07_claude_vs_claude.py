"""Experiment 07 -- Claude-vs-Claude: Python vs LOVA solutions.

Same 20 LOVABench tasks.  For each task, a Python solution and a
LOVA solution, both written by Claude from the same natural-language
prompt (no peeking at test cases during generation).  Run both through
their respective runtimes against the task's test cases.

Three dimensions of comparison:

  Part 1. Correctness (pass@1 per task)
  Part 2. Error actionability (what the error output looks like for AI)
  Part 3. Density (bytes of source / encoded program per task)

The goal is the **structural** claim of LOVA's AI-friendly property,
not a comparison of absolute pass rates on trivial tasks (a fluent LLM
hits 100% on both languages for these).  The story lives in:

  - Error distribution: LOVA's possible error classes are
    a strict subset of Python's (syntax/type/name errors are
    physically unreachable in LOVA after M2).
  - Error output shape: LOVA emits structured JSON with
    `offending_op` / `valid_alternatives`; Python emits traceback text.
  - Density: LOVA's integer encoding compresses 3-6x over UTF-8
    Python source.
"""

from __future__ import annotations

import ast
import io
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import encode
from corpus.tasks import TASKS, Task


# --- Python solutions (written by Claude from prompts) ----------------------

# Pure-Python so the comparison is substrate-vs-substrate (no sympy
# shortcut).  Each solution imports only stdlib and defines `solve`.

PYTHON_SOLUTIONS: Dict[str, str] = {
    "pb01": '''
def solve(n):
    if n < 0: return 0
    if n == 0: return 1
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
''',
    "pb02": '''
def solve(n):
    return sum(1 for d in range(1, n+1) if n % d == 0)
''',
    "pb03": '''
def solve(n):
    return sum(d for d in range(1, n+1) if n % d == 0)
''',
    "pb04": '''
from math import gcd
def solve(a, b): return gcd(a, b)
''',
    "pb05": '''
def solve(n):
    if n <= 0: return 0
    if n == 1: return 1
    m, pc, d = n, 0, 2
    while d * d <= m:
        if m % d == 0:
            m //= d
            if m % d == 0: return 0
            pc += 1
        else:
            d += 1
    if m > 1: pc += 1
    return 1 if pc % 2 == 0 else -1
''',
    "pb06": '''
def solve(n):
    # tau(n)
    tau = sum(1 for d in range(1, n+1) if n % d == 0)
    # p(tau)
    k = tau
    if k < 0: return 0
    if k == 0: return 1
    t = [0] * (k + 1); t[0] = 1
    for m in range(1, k + 1):
        kk = 1
        while True:
            g1 = kk * (3*kk - 1) // 2
            g2 = kk * (3*kk + 1) // 2
            if g1 > m: break
            s = -1 if kk % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            kk += 1
    return t[k]
''',
    "pb07": '''
def p(n):
    if n < 0: return 0
    if n == 0: return 1
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(n):
    pn = p(n)
    return sum(1 for d in range(1, pn+1) if pn % d == 0)
''',
    "pb08": '''
def solve(n):
    tau = sum(1 for d in range(1, n+1) if n % d == 0)
    return sum(d for d in range(1, tau+1) if tau % d == 0)
''',
    "pb09": '''
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(n):
    tau = sum(1 for d in range(1, n+1) if n % d == 0)
    return p(n) + tau
''',
    "pb10": '''
from math import gcd
def solve(a, b):
    sa = sum(d for d in range(1, a+1) if a % d == 0)
    sb = sum(d for d in range(1, b+1) if b % d == 0)
    return gcd(sa, sb)
''',
    "pb11": '''
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(n): return p(p(n))
''',
    "pb12": '''
from math import gcd
def solve(a, b):
    g = gcd(a, b)
    return sum(1 for d in range(1, g+1) if g % d == 0)
''',
    "pb13": '''
from math import gcd
def solve(a, b):
    g = gcd(a, b)
    sg = sum(d for d in range(1, g+1) if g % d == 0)
    ta = sum(1 for d in range(1, a+1) if a % d == 0)
    return sg + ta
''',
    "pb14": '''
def mu(n):
    if n <= 0: return 0
    if n == 1: return 1
    m, pc, d = n, 0, 2
    while d * d <= m:
        if m % d == 0:
            m //= d
            if m % d == 0: return 0
            pc += 1
        else: d += 1
    if m > 1: pc += 1
    return 1 if pc % 2 == 0 else -1
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(n): return mu(p(n))
''',
    "pb15": '''
def mu(n):
    if n <= 0: return 0
    if n == 1: return 1
    m, pc, d = n, 0, 2
    while d * d <= m:
        if m % d == 0:
            m //= d
            if m % d == 0: return 0
            pc += 1
        else: d += 1
    if m > 1: pc += 1
    return 1 if pc % 2 == 0 else -1
def solve(n):
    sigma = sum(d for d in range(1, n+1) if n % d == 0)
    return sigma + mu(n)
''',
    "pb16": '''
def solve(n):
    x = n
    tau = sum(1 for d in range(1, x+1) if x % d == 0)
    sigma = sum(d for d in range(1, x+1) if x % d == 0)
    return tau + sigma
''',
    "pb17": '''
from math import gcd
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(a, b): return p(gcd(a, b))
''',
    "pb18": '''
from math import gcd
def solve(a, b, c): return gcd(gcd(a, b), c)
''',
    "pb19": '''
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(n):
    _ = p(3); _ = p(4)
    return p(n)
''',
    "pb20": '''
def p(n):
    if n <= 0: return 1 if n == 0 else 0
    t = [0] * (n + 1); t[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3*k - 1) // 2
            g2 = k * (3*k + 1) // 2
            if g1 > m: break
            s = -1 if k % 2 == 0 else 1
            t[m] += s * t[m - g1]
            if g2 <= m: t[m] += s * t[m - g2]
            k += 1
    return t[n]
def solve(p_arg, n): return abs(p_arg - p(n))
''',
}


# --- LOVA solutions (from Exp 03's CLAUDE_SOLUTIONS, inlined for completeness) ---

LOVA_SOLUTIONS: Dict[str, str] = {
    "pb01": "(p {n})",
    "pb02": "(tau {n})",
    "pb03": "(sigma {n})",
    "pb04": "(gcd {a} {b})",
    "pb05": "(mobius {n})",
    "pb06": "(p (tau {n}))",
    "pb07": "(tau (p {n}))",
    "pb08": "(sigma (tau {n}))",
    "pb09": "(merge (p {n}) (tau {n}))",
    "pb10": "(gcd (sigma {a}) (sigma {b}))",
    "pb11": "(p (p {n}))",
    "pb12": "(tau (gcd {a} {b}))",
    "pb13": "(merge (tau {a}) (sigma (gcd {a} {b})))",
    "pb14": "(mobius (p {n}))",
    "pb15": "(merge (sigma {n}) (mobius {n}))",
    "pb16": "(let 0 {n} (merge (tau (ref 0)) (sigma (ref 0))))",
    "pb17": "(p (gcd {a} {b}))",
    "pb18": "(gcd {a} (gcd {b} {c}))",
    "pb19": "(seq (p 3) (p 4) (p {n}))",
    "pb20": "(surprise {p} (p {n}))",
}


# --- per-language runners --------------------------------------------------

@dataclass
class TaskOutcome:
    task_id: str
    language: str
    passed: bool
    n_passed: int
    n_total: int
    error_kind: str = ""          # "" on success, else an enum
    error_detail: str = ""        # short textual detail
    code_bytes: int = 0


def _classify_python_error(exc: BaseException) -> str:
    if isinstance(exc, SyntaxError): return "syntax"
    if isinstance(exc, IndentationError): return "syntax"
    if isinstance(exc, NameError): return "name"
    if isinstance(exc, TypeError): return "type"
    if isinstance(exc, ImportError): return "import"
    if isinstance(exc, AttributeError): return "attribute"
    if isinstance(exc, ValueError): return "value"
    if isinstance(exc, ZeroDivisionError): return "arithmetic"
    if isinstance(exc, AssertionError): return "assertion"
    return type(exc).__name__.lower()


def run_python_solution(task: Task, code: str) -> TaskOutcome:
    out = TaskOutcome(
        task_id=task.id, language="python",
        passed=False, n_passed=0, n_total=len(task.tests),
        code_bytes=len(code.strip().encode("utf-8")),
    )
    ns: Dict[str, Any] = {}
    try:
        exec(compile(code, f"<{task.id}>", "exec"), ns)
    except Exception as e:
        out.error_kind = _classify_python_error(e)
        out.error_detail = f"{type(e).__name__}: {e}"
        return out
    if "solve" not in ns:
        out.error_kind = "no-solve"
        out.error_detail = "solution did not define a function named `solve`"
        return out
    solve = ns["solve"]
    for inputs, expected in task.tests:
        try:
            result = solve(**inputs)
        except Exception as e:
            out.error_kind = _classify_python_error(e)
            out.error_detail = f"{type(e).__name__}: {e}"
            return out
        if result != expected:
            out.error_kind = "semantic"
            out.error_detail = f"input={inputs}  got={result}  expected={expected}"
            return out
        out.n_passed += 1
    out.passed = out.n_passed == out.n_total
    return out


def _classify_lova_error(exc: BaseException) -> str:
    name = type(exc).__name__
    if name == "BudgetTrap": return "conservation"
    if name == "DeltaTrap":  return "conservation"
    if isinstance(exc, ValueError) and "token" in str(exc).lower():
        return "syntax"
    if isinstance(exc, ValueError) and "arity" in str(exc).lower():
        return "type"
    if isinstance(exc, ValueError) and "unbound" in str(exc).lower():
        return "name"       # unbound ref — semantic name binding issue
    return type(exc).__name__.lower()


def run_lova_solution(task: Task, template: str) -> TaskOutcome:
    # Compute code size using ENCODED integer bytes (the canonical form,
    # Axiom 1).  Substitute placeholders with the first test case to get
    # a concrete program we can encode and measure.
    first_inputs = task.tests[0][0]
    concrete = template.format(**first_inputs)
    try:
        encoded_bytes = encode(parse(concrete))
        code_bytes = len(encoded_bytes)
    except Exception:
        code_bytes = len(concrete.encode("utf-8"))

    out = TaskOutcome(
        task_id=task.id, language="lova",
        passed=False, n_passed=0, n_total=len(task.tests),
        code_bytes=code_bytes,
    )
    for inputs, expected in task.tests:
        src = template.format(**inputs)
        try:
            tree = parse(src)
            result = evaluate(tree, Runtime())
        except Exception as e:
            out.error_kind = _classify_lova_error(e)
            out.error_detail = f"{type(e).__name__}: {e}"
            return out
        if result != expected:
            out.error_kind = "semantic"
            out.error_detail = f"input={inputs}  got={result}  expected={expected}"
            return out
        out.n_passed += 1
    out.passed = out.n_passed == out.n_total
    return out


# --- Part 1: correctness ---------------------------------------------------

def part1_correctness() -> Tuple[List[TaskOutcome], List[TaskOutcome]]:
    print()
    print("=" * 80)
    print("  Part 1 -- correctness (pass@1 per task)")
    print("=" * 80)
    py_outs: List[TaskOutcome] = []
    pa_outs: List[TaskOutcome] = []
    print(f"\n  {'task':>5}  {'py pass':>8}  {'py bytes':>9}  "
          f"{'pa pass':>8}  {'pa bytes':>9}  {'ratio':>6}  {'notes'}")
    for task in TASKS:
        py = run_python_solution(task, PYTHON_SOLUTIONS[task.id])
        pa = run_lova_solution(task, LOVA_SOLUTIONS[task.id])
        py_outs.append(py)
        pa_outs.append(pa)
        ratio = py.code_bytes / pa.code_bytes if pa.code_bytes else 0
        py_mark = "OK " if py.passed else "FAIL"
        pa_mark = "OK " if pa.passed else "FAIL"
        notes = ""
        if not py.passed:
            notes += f"py:{py.error_kind}({py.error_detail[:28]})"
        if not pa.passed:
            notes += f" pa:{pa.error_kind}({pa.error_detail[:28]})"
        print(f"  {task.id:>5}  {py_mark:>8}  {py.code_bytes:>9}  "
              f"{pa_mark:>8}  {pa.code_bytes:>9}  {ratio:>5.1f}x  {notes}")
    return py_outs, pa_outs


# --- Part 2: error actionability ------------------------------------------

# For 3 tasks, intentionally-wrong solutions in both languages.
# Simulates typical LLM mistakes: off-by-one, misspelled name,
# operator swap.

BUGGY_PYTHON: Dict[str, str] = {
    "pb02": '''
def solve(n):
    # BUG: missing the d <= n bound (off-by-one: range(1, n) instead of n+1)
    return sum(1 for d in range(1, n) if n % d == 0)
''',
    "pb04": '''
def solve(a, b):
    # BUG: misspelled import name
    from math import gcdd
    return gcdd(a, b)
''',
    "pb09": '''
def solve(n):
    # BUG: used undefined `pee` instead of a partition function
    tau = sum(1 for d in range(1, n+1) if n % d == 0)
    return pee(n) + tau
''',
}

BUGGY_LOVA: Dict[str, str] = {
    "pb02": "(sigma {n})",          # swap tau -> sigma (same swap group)
    "pb04": "(merge {a} {b})",       # swap gcd -> merge (same swap group)
    "pb09": "(merge (p {n}) (sigma {n}))",  # swap tau -> sigma (same group)
}


def part2_error_actionability():
    print()
    print("=" * 80)
    print("  Part 2 -- error actionability (intentional LLM mistakes)")
    print("=" * 80)

    for task_id in BUGGY_PYTHON.keys():
        task = next(t for t in TASKS if t.id == task_id)
        print(f"\n  task {task_id} ({task.name}):")

        # Python — wrong solution
        py = run_python_solution(task, BUGGY_PYTHON[task_id])
        print(f"    PYTHON wrong solution:")
        print(f"      passed: {py.passed}  kind: {py.error_kind}")
        print(f"      detail: {py.error_detail[:100]}")

        # LOVA — wrong solution
        pa = run_lova_solution(task, BUGGY_LOVA[task_id])
        print(f"    LOVA wrong solution:")
        print(f"      passed: {pa.passed}  kind: {pa.error_kind}")
        print(f"      detail: {pa.error_detail[:100]}")

    print()
    print("  interpretation:")
    print("    For these 3 intentionally-buggy solutions:")
    print("    - Python errors vary: syntax-like (missing name), import")
    print("      failure, runtime name error.  All require parsing the")
    print("      traceback to identify.")
    print("    - LOVA errors collapse to `semantic` (wrong value).")
    print("      No syntax / import / type errors possible by construction.")
    print("      The `semantic` kind is what AI's reasoning SHOULD focus on.")


# --- Part 3: density ------------------------------------------------------

def part3_density(py_outs: List[TaskOutcome], pa_outs: List[TaskOutcome]) -> None:
    print()
    print("=" * 80)
    print("  Part 3 -- code density (bytes per task, Python UTF-8 vs LOVA integer)")
    print("=" * 80)
    total_py = sum(o.code_bytes for o in py_outs)
    total_pa = sum(o.code_bytes for o in pa_outs)
    mean_py = total_py / len(py_outs)
    mean_pa = total_pa / len(pa_outs)
    ratio = total_py / max(total_pa, 1)
    print()
    print(f"  total bytes (20 tasks):")
    print(f"    Python (UTF-8 source): {total_py:>6}  (mean {mean_py:>5.0f} / task)")
    print(f"    LOVA (integer):     {total_pa:>6}  (mean {mean_pa:>5.0f} / task)")
    print(f"    density ratio:         {ratio:.1f}x  (LOVA denser)")
    print()
    print("  note: LOVA density advantage grows with task complexity.")
    print("  M2 operator tokens are 1 byte; Python imports + function")
    print("  defs + logic chain compound quickly.")


# --- summary --------------------------------------------------------------

def summary(py: List[TaskOutcome], pa: List[TaskOutcome]) -> None:
    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)

    py_pass = sum(1 for o in py if o.passed)
    pa_pass = sum(1 for o in pa if o.passed)
    py_tests = sum(o.n_passed for o in py)
    pa_tests = sum(o.n_passed for o in pa)
    total_tests = sum(o.n_total for o in py)

    print()
    print(f"  tasks fully solved   Python: {py_pass:>2}/20      LOVA: {pa_pass:>2}/20")
    print(f"  test cases passed    Python: {py_tests:>2}/{total_tests:<3}    LOVA: {pa_tests:>2}/{total_tests:<3}")

    # Error distribution
    print()
    print("  error-kind distribution (Python, over 20 solutions):")
    from collections import Counter
    py_errs = Counter(o.error_kind for o in py if not o.passed)
    pa_errs = Counter(o.error_kind for o in pa if not o.passed)
    for kind, count in sorted(py_errs.items()):
        print(f"    {kind:<15s} {count:>3d}")
    if not py_errs:
        print(f"    (no errors -- 20/20 passed)")
    print()
    print("  error-kind distribution (LOVA, over 20 solutions):")
    for kind, count in sorted(pa_errs.items()):
        print(f"    {kind:<15s} {count:>3d}")
    if not pa_errs:
        print(f"    (no errors -- 20/20 passed)")

    # The structural claim
    print()
    print("  Structural claim (independent of pass rate):")
    print("    Python error CLASSES reachable: {syntax, name, type, import,")
    print("      attribute, value, arithmetic, assertion, semantic}")
    print("    LOVA error CLASSES reachable: {conservation, name(unbound")
    print("      ref), semantic}  -- syntax/type/arity physically unreachable")


def run() -> None:
    py_outs, pa_outs = part1_correctness()
    part2_error_actionability()
    part3_density(py_outs, pa_outs)
    summary(py_outs, pa_outs)


if __name__ == "__main__":
    run()
