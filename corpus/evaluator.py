"""Run a LOVA template against a task's test cases.

A template is a string with ``{var}`` placeholders (e.g.
``"(gcd {a} {b})"``).  For each test case, the evaluator substitutes
input bindings, parses the resulting surface form, evaluates it, and
compares the integer result to the expected output.

Returns structured per-test-case results so the experiment script can
produce per-task and per-model summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.runtime import Runtime, evaluate
from core.surface import parse
from corpus.tasks import Task


@dataclass
class TestResult:
    """Result of one test case."""
    inputs: dict
    expected: int
    got: object             # int on success, str (error class) on failure
    passed: bool


@dataclass
class TaskResult:
    """Result of one task — list of per-test-case results."""
    task_id: str
    results: List[TestResult]

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def n_total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return self.n_passed == self.n_total


def _fill(template: str, inputs: dict) -> str:
    """Substitute ``{var}`` placeholders with test inputs."""
    return template.format(**inputs)


def evaluate_template(template: str, inputs: dict) -> object:
    """Substitute, parse, and evaluate.  Return the int on success,
    or a string ``"error:<class>:<msg>"`` on any failure."""
    try:
        src = _fill(template, inputs)
        tree = parse(src)
        rt = Runtime()
        return evaluate(tree, rt)
    except Exception as e:
        return f"error:{type(e).__name__}:{e}"


def run_task(template: str, task: Task) -> TaskResult:
    """Run ``template`` against every test case of ``task``."""
    results = []
    for inputs, expected in task.tests:
        got = evaluate_template(template, inputs)
        passed = isinstance(got, int) and got == expected
        results.append(TestResult(
            inputs=inputs, expected=expected, got=got, passed=passed,
        ))
    return TaskResult(task_id=task.id, results=results)
