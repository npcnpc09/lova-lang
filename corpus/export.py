"""Export LOVABench as JSONL for downstream LLM fine-tuning.

One line per task.  Format:

    {
      "id": "pb01",
      "name": "partition_number",
      "prompt": "Given an integer n, return the n-th partition ...",
      "template": "(p {n})",
      "tests": [ {"inputs": {"n": 12}, "expected": 77}, ... ],
      "tags": ["nt", "recall", "single-op"]
    }

The ``template`` is the reference LOVA solution.  For fine-tuning,
one would train a (prompt, template) completion where the model learns
to emit a well-formed LOVA program given the natural-language task
description.  Combining this with the ``valid_next`` constraint
(``core.generator``) during generation means the fine-tuned model is
**physically unable** to emit syntactically invalid LOVA.

This JSONL format is stable: downstream pipelines can read it without
importing LOVA Python modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from corpus.tasks import TASKS, Task


def task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "prompt": task.prompt,
        "template": task.template,
        "tests": [
            {"inputs": dict(inputs), "expected": expected}
            for inputs, expected in task.tests
        ],
        "tags": list(task.tags),
    }


def export_jsonl(tasks: Iterable[Task], path: str | Path) -> int:
    """Write ``tasks`` as JSONL to ``path``.  Return the number of lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fp:
        for t in tasks:
            fp.write(json.dumps(task_to_dict(t), ensure_ascii=False))
            fp.write("\n")
            count += 1
    return count


if __name__ == "__main__":
    import os
    here = Path(__file__).resolve().parent
    out = here / "lovabench_v2.jsonl"
    n = export_jsonl(TASKS, out)
    print(f"wrote {n} tasks to {out}")
