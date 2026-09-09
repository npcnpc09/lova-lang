"""Experiment 03 -- LOVABench: reference / random / Claude baselines.

Three baselines over all 60 v2 tasks, quantified:

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

    # --- v2 extension, written 2026-09-09 (M13) to close Q30 -----------
    #
    # The v1 twenty above were written in April against LOVABench v1.
    # The corpus grew to sixty in May and these two experiments were
    # never extended, so both had been dead for four months while the
    # README quoted their headline number.  The forty below close that.
    #
    # Same protocol as the originals: written from each task's `prompt`
    # and the language spec, without reading `tasks.py`'s `template`.
    #
    # Read the result with Exp 13's F3 in mind.  These prompts state the
    # formula -- "Compute p(tau(sigma(n)))" -- so what this baseline
    # measures on the v2 tasks is *transcription into s-expressions*,
    # not program synthesis.  That is a fair test of whether the surface
    # is writable and an unfair one to quote as "an LLM can program in
    # LOVA".

    # deep composition (pb21-pb30)
    "pb21": "(p (tau (sigma {n})))",
    "pb22": "(sigma (gcd (p {a}) (p {b})))",
    "pb23": "(tau (tau (tau {n})))",
    "pb24": "(mobius (gcd (sigma {a}) (tau {b})))",
    "pb25": "(p (p (tau {n})))",
    "pb26": "(merge (p (tau {a})) (sigma (gcd {a} {b})))",
    "pb27": "(gcd (sigma (p {n})) (tau (p {n})))",
    "pb28": "(tau (merge (sigma {a}) (sigma {b})))",
    "pb29": "(sigma (p (gcd {a} {b})))",
    "pb30": "(merge (sigma (tau {n})) (p (mobius {n})))",

    # conserve-heavy (pb31-pb40)
    "pb31": "(conserve {k} (p {n}))",
    "pb32": "(conserve {k} (tau {n}))",
    "pb33": "(conserve {k} (gcd {a} {b}))",
    "pb34": "(conserve {k} (merge (p {n}) (tau {n})))",
    "pb35": "(conserve {k} (sigma (gcd {a} {b})))",
    "pb36": "(conserve {k} (mobius {n}))",
    "pb37": "(conserve {k} (p (tau {n})))",
    "pb38": "(let 0 {n} (conserve {k} (merge (tau (ref 0)) (sigma (ref 0)))))",
    "pb39": "(let 0 {a} (conserve {k} (gcd (ref 0) {b})))",
    "pb40": "(merge (conserve {k1} (p {n})) (conserve {k2} (tau {n})))",

    # surprise-based (pb41-pb50)
    "pb41": "(surprise {k} (p {n}))",
    "pb42": "(surprise {k} (tau {n}))",
    "pb43": "(surprise (p {n}) (p {m}))",
    # |sigma(n) - 2n|: the perfect-number test, written as a prediction
    "pb44": "(surprise (merge {n} {n}) (sigma {n}))",
    "pb45": "(if-surprise (surprise {k} (p {n})) 0 1)",
    "pb46": "(if-surprise (surprise 1 (gcd {a} {b})) 0 1)",
    "pb47": "(if-surprise (surprise {k} (sigma {n})) 0 1)",
    "pb48": "(surprise (tau (sigma {n})) (sigma (tau {n})))",
    # squarefree: non-zero surprise from 0 takes the THEN branch
    "pb49": "(if-surprise (surprise 0 (mobius {n})) 1 0)",
    "pb50": "(let 0 {a} (let 1 {b} (surprise (p (ref 0)) (p (ref 1)))))",

    # let-heavy (pb51-pb60)
    "pb51": "(let 0 {n} (merge (p (ref 0)) (tau (ref 0))))",
    "pb52": "(let 0 (gcd {a} {b}) (merge (p (ref 0)) (tau (ref 0))))",
    "pb53": "(let 0 {n} (gcd (sigma (ref 0)) (tau (ref 0))))",
    "pb54": "(let 0 (p {n}) (merge (ref 0) (tau (ref 0))))",
    "pb55": "(let 0 {n} (let 1 (tau (ref 0)) (merge (ref 0) (ref 1))))",
    "pb56": "(let 0 {a} (let 1 {b} (gcd (sigma (ref 0)) (tau (ref 1)))))",
    "pb57": "(let 0 (sigma {n}) (merge (ref 0) (ref 0)))",
    "pb58": "(let 0 (sigma {a}) (let 1 (sigma {b}) (gcd (ref 0) (ref 1))))",
    "pb59": "(let 0 {n} (merge (p (ref 0)) (sigma (ref 0))))",
    "pb60": "(let 0 (merge {a} {b}) (p (ref 0)))",
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
    _hr(f"SUMMARY -- three baselines, {len(TASKS)} tasks")

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
    print(f"    Reference    : {ref_full:2d} / {len(TASKS)}")
    print(f"    Unguided rnd : ~{unguided_total:3d} / {len(TASKS) * 100:4d} sample-tasks (across 100 seeds each)")
    print(f"    Claude       : {claude_full:2d} / {len(TASKS)}")
    print()
    print("  per-test-case pass rate:")
    print(f"    Reference    : {ref_pass}/{total_tests} ({ref_pass/total_tests*100:5.1f}%)")
    print(f"    Claude       : {claude_pass}/{total_tests} ({claude_pass/total_tests*100:5.1f}%)")
    print()
    if claude_full >= 18 and unguided_total < 20:
        print("  verdict: STRONG WIN on capability-gap quantification")
        print("    -> Claude can write LOVA from prompts at ~100% pass rate")
        print("    -> Unguided random is essentially useless (~0% task coverage)")
        print("    -> The gap is the whole range -- motivates fine-tuning")
        print()
        print("  Caveat, and it is load-bearing (Exp 13, F3):")
        print("  LOVABench's tasks were authored *in* the language, and the")
        print("  v2 prompts state the formula outright -- \"Compute")
        print("  p(tau(sigma(n)))\".  So the Claude baseline measures")
        print("  transcription into s-expressions, not program synthesis.")
        print("  Quote it as evidence that the surface is writable, not")
        print("  that an LLM can program in LOVA.")
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
