"""Experiment 17 -- a real LLM writes LOVA and Python for LOVABench v3.

    python experiments/experiment_17_llm_benchmark.py --dry-run
    python experiments/experiment_17_llm_benchmark.py --model gpt-4o-mini
    python experiments/experiment_17_llm_benchmark.py --model ft:gpt-4o-mini:...:lova --tasks algorithmic

M8's measurement.  For every task the model is asked twice, once for
a LOVA program (the one-page language card as the system prompt --
the same prompt the fine-tuning corpus uses, so a fine-tuned model
sees what it trained on) and once for a Python function.  Each answer
is run against the task's tests; pass@1 is one attempt, no retries,
no feedback.  The number the project has waited for is the delta:
the same model's LOVA pass@1 against its Python pass@1, on the same
tasks -- and, for a fine-tuned model, against its own base.

Exp 07 measured this with Claude transcribing formulas by hand (60/60
vs 59/60); Exp 13 F3 said that measured transcription, not synthesis.
The algorithmic category (Q33) is where the two come apart: its
prompts say what to compute and not how.

``--dry-run`` runs the reference solutions through the same pipeline,
which is how the pipeline itself is tested without a model.  Any
OpenAI-compatible endpoint works (``--base-url``, ``OPENAI_API_KEY``);
results go to ``experiments/results_17/<model>.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus.evaluator import run_task
from corpus.finetune import INPUT_NOTE, SYSTEM_PROMPT
from corpus.python_solutions import PYTHON_ALGORITHMIC, PYTHON_PURE
from corpus.tasks import TASKS_V3, Task

ROOT = Path(__file__).resolve().parent.parent
CARD = (ROOT / "corpus" / "language_card.md").read_text(encoding="utf-8")
RESULTS = ROOT / "experiments" / "results_17"

PYTHON_SYSTEM = (
    "You write Python. Reply with code only: no prose, no code fence. "
    "Define a function `solve` taking the named integer inputs as keyword "
    "arguments and returning an integer. Use only the standard library.")


def category(task: Task) -> str:
    n = int(task.id[2:])
    if n <= 20:
        return "v1-core"
    if n <= 30:
        return "deep-compose"
    if n <= 40:
        return "conserve"
    if n <= 50:
        return "surprise"
    if n <= 60:
        return "let-heavy"
    return "algorithmic"


def variables(task: Task) -> List[str]:
    return sorted(task.tests[0][0].keys())


# --- prompts -----------------------------------------------------------------------

def lova_messages(task: Task, card: bool = True) -> List[dict]:
    names = ", ".join("{" + v + "}" for v in variables(task))
    system = SYSTEM_PROMPT + "\n\n" + CARD if card else SYSTEM_PROMPT
    return [{"role": "system", "content": system},
            {"role": "user", "content": task.prompt + "\n\n" + INPUT_NOTE.format(names=names)}]


def python_messages(task: Task) -> List[dict]:
    names = ", ".join(variables(task))
    return [{"role": "system", "content": PYTHON_SYSTEM},
            {"role": "user", "content": f"{task.prompt}\n\nThe inputs are: {names}."}]


# --- the model ----------------------------------------------------------------------

class Model:
    def __init__(self, name: str, base_url: Optional[str], temperature: float = 0.0):
        from openai import OpenAI      # the only non-stdlib import, and only here
        self.name = name
        self.temperature = temperature
        self.client = OpenAI(base_url=base_url) if base_url else OpenAI()

    def ask(self, messages: List[dict]) -> str:
        for attempt in range(4):
            try:
                reply = self.client.chat.completions.create(
                    model=self.name, messages=messages,
                    temperature=self.temperature, max_tokens=600)
                return reply.choices[0].message.content or ""
            except Exception as exc:          # rate limit, transient
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return ""


def strip_fence(text: str) -> str:
    m = re.search(r"```(?:\w+)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def extract_lova(text: str) -> str:
    text = strip_fence(text)
    i = text.find("(")
    return text[i:] if i >= 0 else text


# --- running the answers ------------------------------------------------------------

def run_python(code: str, task: Task, timeout: float = 10.0) -> dict:
    """Run ``solve`` on every test in a subprocess; a hang is a failure."""
    harness = (
        code + "\n\nimport json, sys\n"
        f"tests = {json.dumps([{'inputs': i, 'expected': e} for i, e in task.tests])}\n"
        "out = []\n"
        "for t in tests:\n"
        "    try:\n"
        "        got = solve(**t['inputs'])\n"
        "        out.append({'passed': got == t['expected'], 'got': repr(got)})\n"
        "    except Exception as exc:\n"
        "        out.append({'passed': False, 'got': 'error:' + type(exc).__name__})\n"
        "print(json.dumps(out))\n")
    try:
        proc = subprocess.run([sys.executable, "-c", harness], capture_output=True,
                              text=True, timeout=timeout)
        rows = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        rows = [{"passed": False, "got": "error:" + type(exc).__name__} for _ in task.tests]
    return {"passed": all(r["passed"] for r in rows), "n_passed": sum(r["passed"] for r in rows),
            "n_total": len(rows), "results": rows}


def run_lova(program: str, task: Task) -> dict:
    result = run_task(program, task)
    return {"passed": result.all_passed, "n_passed": result.n_passed, "n_total": result.n_total,
            "results": [{"passed": r.passed, "got": str(r.got)[:80]} for r in result.results]}


# --- references, for the dry run -------------------------------------------------------

def reference_python(task: Task) -> Optional[str]:
    if task.id in PYTHON_ALGORITHMIC:
        return PYTHON_ALGORITHMIC[task.id]
    if task.id in PYTHON_PURE:
        return PYTHON_PURE[task.id]
    try:
        from experiments.experiment_07_claude_vs_claude import PYTHON_SOLUTIONS
        return PYTHON_SOLUTIONS.get(task.id)
    except Exception:
        return None


# --- the experiment ---------------------------------------------------------------------

def select(tasks, spec: Optional[str]):
    if not spec:
        return list(tasks)
    wanted = {s.strip() for s in spec.split(",")}
    return [t for t in tasks if t.id in wanted or category(t) in wanted]


def run(model: Optional[Model], tasks: List[Task], languages: List[str], verbose: bool,
        card: bool = True, answers: Optional[Dict[str, dict]] = None) -> dict:
    """``answers`` (task id -> {"lova": text, "python": text}) scores
    answers produced elsewhere -- a model asked by hand, a session with
    no tools -- through the same pipeline."""
    rows = []
    for task in tasks:
        row = {"id": task.id, "category": category(task)}
        given = (answers or {}).get(task.id, {})
        if "lova" in languages:
            if answers is not None:
                program = extract_lova(given.get("lova", ""))
            elif model is None:
                program = task.template
            else:
                program = extract_lova(model.ask(lova_messages(task, card)))
            row["lova"] = {"program": program, **run_lova(program, task)}
        if "python" in languages:
            if answers is not None:
                code = strip_fence(given.get("python", "")) or None
            elif model is None:
                code = reference_python(task)
            else:
                code = strip_fence(model.ask(python_messages(task)))
            if code is None:
                row["python"] = {"program": None, "passed": None, "n_passed": 0, "n_total": len(task.tests)}
            else:
                row["python"] = {"program": code, **run_python(code, task)}
        rows.append(row)
        if verbose:
            marks = " ".join(f"{lang}={'ok' if row[lang]['passed'] else 'x' if row[lang]['passed'] is not None else '-'}"
                             for lang in languages)
            print(f"  {task.id}  {category(task):13s}  {marks}", flush=True)
    return {"model": model.name if model else "reference", "rows": rows}


def summarise(result: dict, languages: List[str]) -> str:
    rows = result["rows"]
    cats = []
    for r in rows:
        if r["category"] not in cats:
            cats.append(r["category"])
    lines = [f"  {'category':13s} {'n':>3s}  " + "  ".join(f"{lang:>8s}" for lang in languages)]
    for cat in cats + ["all"]:
        subset = [r for r in rows if cat == "all" or r["category"] == cat]
        cells = []
        for lang in languages:
            scored = [r for r in subset if r.get(lang, {}).get("passed") is not None]
            passed = sum(1 for r in scored if r[lang]["passed"])
            cells.append(f"{passed:3d}/{len(scored):<3d}")
        lines.append(f"  {cat:13s} {len(subset):3d}  " + "  ".join(f"{c:>8s}" for c in cells))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="an OpenAI-compatible chat model id")
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"))
    ap.add_argument("--dry-run", action="store_true", help="run the reference solutions instead of a model")
    ap.add_argument("--tasks", help="comma-separated task ids or categories (e.g. algorithmic)")
    ap.add_argument("--languages", default="lova,python")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-card", action="store_true",
                    help="a one-sentence system prompt, as a fine-tuned model was trained with")
    ap.add_argument("--answers", help="a JSON file of answers to score: {task id: {lova, python}}")
    ap.add_argument("--label", help="a name for the results file (default: the model)")
    args = ap.parse_args(argv)
    if not args.dry_run and not args.model and not args.answers:
        ap.error("give --model, --answers, or --dry-run")
    languages = [x.strip() for x in args.languages.split(",")]
    tasks = select(TASKS_V3, args.tasks)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else None
    model = None if (args.dry_run or answers is not None) else Model(args.model, args.base_url, args.temperature)
    label = args.label or ("reference" if args.dry_run else args.model or Path(args.answers).stem)
    print(f"Experiment 17 -- {label} on {len(tasks)} LOVABench v3 tasks, pass@1, {', '.join(languages)}")
    result = run(model, tasks, languages, verbose=not args.quiet, card=not args.no_card,
                 answers=answers)
    print(summarise(result, languages))
    RESULTS.mkdir(parents=True, exist_ok=True)
    result["model"] = label
    out = RESULTS / (re.sub(r"[^\w.-]+", "_", label) + ".json")
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"  results -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
