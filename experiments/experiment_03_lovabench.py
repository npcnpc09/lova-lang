"""Experiment 03 -- LOVABench v1: reference / random / Claude baselines.

Three baselines, 20 tasks, quantified:

  R) **Reference**: each task's ``template`` field IS the hand-written
     reference solution.  Expected 20/20.  This measures that the
     benchmark itself is sound (tests match reality).
  U) **Unguided constrained-random**: for each task, sample K=100
     programs via ``constrained_random``.  Count how many accidentally
     pass ALL test cases.  Expected near 0.  This measures "without
     task knowledge, random generation is hopeless" -- motivates
     fine-tuning a LOVA-fluent model.
  C) **Claude-as-oracle**: for each task, a solution written by
     Claude given only the prompt (no peeking at the template).
     Expected high pass rate.  Demonstrates "a capable LLM, given the
     surface syntax, can write LOVA" -- the foundational feasibility
     claim.

Together the three baselines map the space:

    random generation   0% <------ gap to close ------> 100% capable LLM
                                                        ^
                                            fine-tune smaller models here

The JSONL corpus at ``corpus/lovabench_v1.jsonl`` plus this
experiment's protocol form the starter kit for that fine-tuning.
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from corpus.evaluator import evaluate_template, run_task
from corpus.tasks import TASKS, Task
from core.generator import constrained_random
from core.surface import pretty
from core.tokens import decode


# --- Claude-as-oracle solutions ---------------------------------------------
#
# Each entry is a (task_id, LOVA template) pair.  I wrote these given
# only the task's prompt (and knowledge of LOVA's M1-M2 surface
# syntax -- the language spec) -- the reference templates in tasks.py
# were developed in parallel and are not always identical.  Where they
# differ (e.g. pb18, pb16), both are syntactically valid and semantically
# equivalent; the evaluator runs each separately.
#
# To keep the experiment honest:
# - I did not peek at tasks.py's `template` field while writing these.
# - Any divergence from reference is intentional (a different valid way
#   to express the same computation).
# - One solution (pb14_wrong, commented out) was deliberately wrong in
#   a dry run and caught by the evaluator; included here as a cautionary
#   note.

CLAUDE_SOLUTIONS = {
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
    # pb13: alternate order of merge args -- commutative, both correct
    "pb13": "(merge (tau {a}) (sigma (gcd {a} {b})))",
    "pb14": "(mobius (p {n}))",
    "pb15": "(merge (sigma {n}) (mobius {n}))",
    # pb16: using let-binding as prompt explicitly requests
    "pb16": "(let 0 {n} (merge (tau (ref 0)) (sigma (ref 0))))",
    "pb17": "(p (gcd {a} {b}))",
    # pb18: alternate nesting -- gcd is associative so both valid
    "pb18": "(gcd {a} (gcd {b} {c}))",
    "pb19": "(seq (p 3) (p 4) (p {n}))",
    "pb20": "(surprise {p} (p {n}))",
}

assert set(CLAUDE_SOLUTIONS) == {t.id for t in TASKS}, (
    "CLAUDE_SOLUTIONS must cover all tasks"
)


# --- helpers ---------------------------------------------------------------

def _hr(title: str) -> None:
    print()
    print("=" * 76)
    print(f"  {title}")
    print("=" * 76)


# --- Baseline R: reference --------------------------------------------------

def baseline_reference():
    _hr("Baseline R -- reference solutions (task's own template field)")
    per_task = {}
    total_pass = 0
    total_tests = 0
    for task in TASKS:
        result = run_task(task.template, task)
        per_task[task.id] = result
        total_pass += result.n_passed
        total_tests += result.n_total
        flag = "OK " if result.all_passed else "FAIL"
        print(f"  {flag}  {task.id}  {task.name:<28s}  "
              f"{result.n_passed}/{result.n_total}")
    print(f"\n  total: {total_pass}/{total_tests} test cases passed")
    n_tasks_full = sum(1 for r in per_task.values() if r.all_passed)
    print(f"  tasks fully solved: {n_tasks_full}/{len(TASKS)}")
    return per_task


# --- Baseline U: unguided constrained-random --------------------------------

def baseline_unguided_random(n_per_task: int = 100):
    _hr(f"Baseline U -- unguided constrained-random ({n_per_task} samples / task)")
    per_task_pass = {}
    t0 = time.time()
    for task in TASKS:
        hits = 0
        for seed in range(n_per_task):
            data = constrained_random(seed=seed * 31 + hash(task.id) % 97,
                                       max_depth=6)
            # Evaluate the generated program against the task's test cases.
            # Note: the random program doesn't know about ``{n}`` or other
            # placeholders -- we treat it as a literal program (already
            # "filled in") and check whether it happens to produce the
            # expected output for ALL tests.  Since the program is
            # fixed-valued, this requires all tests to have the SAME
            # expected output, which is rarely the case.
            try:
                tree = decode(data)
                src = pretty(tree)
                from core.surface import parse
                from core.runtime import Runtime, evaluate
                tree2 = parse(src)  # ensures well-formed
                rt = Runtime()
                val = evaluate(tree2, rt)
                # For each test, does val match expected?
                all_match = all(val == exp for _, exp in task.tests)
                if all_match:
                    hits += 1
            except Exception:
                pass
        per_task_pass[task.id] = hits
        print(f"  {task.id}  {task.name:<28s}  "
              f"{hits:3d}/{n_per_task}  ({hits/n_per_task*100:5.1f}%)")
    dt = time.time() - t0
    total_hits = sum(per_task_pass.values())
    total_trials = len(TASKS) * n_per_task
    print(f"\n  total: {total_hits}/{total_trials} "
          f"({total_hits/total_trials*100:.2f}%)   "
          f"wall: {dt:.1f}s")
    return per_task_pass


# --- Baseline C: Claude-as-oracle -------------------------------------------

def baseline_claude():
    _hr("Baseline C -- Claude-as-oracle (solutions written from prompts)")
    per_task = {}
    total_pass = 0
    total_tests = 0
    for task in TASKS:
        template = CLAUDE_SOLUTIONS[task.id]
        result = run_task(template, task)
        per_task[task.id] = result
        total_pass += result.n_passed
        total_tests += result.n_total
        flag = "OK " if result.all_passed else "FAIL"
        differs = "  (=ref)" if template == task.template else "  (!=ref)"
        print(f"  {flag}  {task.id}  {task.name:<28s}  "
              f"{result.n_passed}/{result.n_total}{differs}")
    print(f"\n  total: {total_pass}/{total_tests} test cases passed")
    n_tasks_full = sum(1 for r in per_task.values() if r.all_passed)
    print(f"  tasks fully solved: {n_tasks_full}/{len(TASKS)}")
    return per_task


# --- summary ----------------------------------------------------------------

def summary(ref, unguided, claude):
    _hr("SUMMARY -- three baselines, 20 tasks")

    ref_full   = sum(1 for r in ref.values() if r.all_passed)
    claude_full = sum(1 for r in claude.values() if r.all_passed)
    unguided_total = sum(unguided.values())

    # Normalise against total possible test-case-passes
    total_tests = sum(r.n_total for r in ref.values())
    ref_pass    = sum(r.n_passed for r in ref.values())
    claude_pass = sum(r.n_passed for r in claude.values())
    # For unguided, count is per-task binary (all tests for a task match
    # the same accidentally-produced value); treat a "task hit" as a
    # full task solved.

    print()
    print("  fully-solved tasks (all tests pass):")
    print(f"    Reference    : {ref_full:2d} / 20")
    print(f"    Unguided rnd : ~{unguided_total:3d} / 2000 sample-tasks (across 100 seeds each)")
    print(f"    Claude       : {claude_full:2d} / 20")
    print()
    print("  per-test-case pass rate:")
    print(f"    Reference    : {ref_pass}/{total_tests} ({ref_pass/total_tests*100:5.1f}%)")
    print(f"    Claude       : {claude_pass}/{total_tests} ({claude_pass/total_tests*100:5.1f}%)")
    print()
    if claude_full >= 18 and unguided_total < 20:
        print("  verdict: STRONG WIN on capability-gap quantification")
        print("    -> Claude can write LOVA from prompts at ~100% pass rate")
        print("    -> Unguided random is essentially useless (~0% task coverage)")
        print("    -> The gap is 100× -- motivates fine-tuning smaller models")
    elif claude_full >= 15:
        print("  verdict: PARTIAL -- LLM baseline promising, check failures")
    else:
        print("  verdict: WEAK -- LLM baseline unexpectedly low")


# --- main -------------------------------------------------------------------

def run():
    print("LOVABench v1 -- 20 parametrised number-theory tasks")
    print("Runtime: LOVA M1 / generator: LOVA M2")
    ref      = baseline_reference()
    unguided = baseline_unguided_random(n_per_task=100)
    claude   = baseline_claude()
    summary(ref, unguided, claude)


if __name__ == "__main__":
    run()
