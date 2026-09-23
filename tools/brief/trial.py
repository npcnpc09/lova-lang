"""A repair trial: a session starts from a logged failing submission and its
feedback, and submits until the hidden tests pass.  Two arms differ only in
the report a failure prints: `full` (the JSON the sessions of Exp 19-29
read) or `brief` (core/brief.py).

    python tools/brief/trial.py setup CASE ARM DIR
    python tools/brief/trial.py try DIR FILE        # one attempt
    python tools/brief/trial.py score ROOT          # the table
"""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from experiments import experiment_18_agent_loop as loop
from experiments import experiment_19_agent_loop_apps as e19
from experiments import experiment_21_repair as e21

CASES = json.loads((ROOT / "tools/brief/replay.json").read_text())
BY = {c["id"]: c for c in CASES}
MAX_ATTEMPTS = 5


def _task(case):
    return (e19 if case["id"].startswith("results_19") else e21).BY_ID[case["task"]]


# Arms: `full` and `brief` (Exp 30: the step trap does not say how far
# over; the Q141 probe is off), `needed` (Exp 31: brief, and the probe on).
import copy
from core import mcp_server


def _strip_probe(result):
    result = copy.deepcopy(result)
    for f in result.get("failures", []):
        d = (f.get("anomaly") or {}).get("detail")
        if isinstance(d, dict):
            for k in ("needed", "probe_limit", "hot_at_probe"):
                d.pop(k, None)
    return result


def _feedback(arm, result):
    os.environ["LOVA_REPORT"] = "full" if arm == "full" else "brief"
    if arm != "needed":
        result = _strip_probe(result)
    return loop.feedback_text("lova", result)


def _run(arm, program, task):
    mcp_server.PROBE_FACTOR = 4 if arm == "needed" else 0
    return loop.run_lova(program, task)


def setup(case_id, arm, d):
    d = Path(d); d.mkdir(parents=True, exist_ok=True)
    case = BY[case_id]; task = _task(case)
    fb = _feedback(arm, case["result"])
    names = ", ".join("{" + n + "}" for n in task.inputs)
    brief = (f"# Task {task.id}\n\n{task.prompt}  [inputs: {names}]\n\n"
             f"Each test runs under {loop.BUDGET} steps.\n\n"
             "## Your last submission (program.lova)\n\n```lova\n" + case["program"] + "\n```\n\n"
             "## What the test run said\n\n```\n" + fb + "\n```\n")
    (d / "TASK.md").write_text(brief, encoding="utf-8")
    (d / "program.lova").write_text(case["program"], encoding="utf-8")
    (d / "card.md").write_text((ROOT / "corpus/language_card.md").read_text(encoding="utf-8"), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"case": case_id, "arm": arm, "start_feedback_chars": len(fb)}))


def attempt(d, f):
    d = Path(d); meta = json.loads((d / "meta.json").read_text())
    log = d / "log.jsonl"
    n = 1 + (sum(1 for _ in log.open()) if log.exists() else 0)
    if n > MAX_ATTEMPTS:
        print(f"no attempts left ({MAX_ATTEMPTS} used)"); return 2
    program = Path(f).read_text(encoding="utf-8")
    result = _run(meta["arm"], program, _task(BY[meta["case"]]))
    fb = _feedback(meta["arm"], result)
    with log.open("a") as fp:
        fp.write(json.dumps({"attempt": n, "passed": result["passed"], "feedback_chars": len(fb),
                             "emitted_chars": len(program), "time": time.time()}) + "\n")
    print(f"[attempt {n} of {MAX_ATTEMPTS}] {fb}")
    return 0 if result["passed"] else 1


def score(root):
    rows = []
    for m in sorted(Path(root).glob("*/meta.json")):
        meta = json.loads(m.read_text()); log = m.parent / "log.jsonl"
        recs = [json.loads(l) for l in log.open()] if log.exists() else []
        passed = any(r["passed"] for r in recs)
        att = next((r["attempt"] for r in recs if r["passed"]), len(recs))
        read = meta["start_feedback_chars"] + sum(r["feedback_chars"] for r in recs if not r["passed"])
        rows.append((meta["arm"], meta["case"], passed, att, read, sum(r["emitted_chars"] for r in recs)))
    for arm in ("full", "brief", "needed"):
        rs = [r for r in rows if r[0] == arm]
        if not rs: continue
        print(f"{arm:5s}  cases {len(rs)}  fixed {sum(r[2] for r in rs)}  attempts {sum(r[3] for r in rs)}"
              f"  first-try {sum(1 for r in rs if r[2] and r[3] == 1)}  feedback read {sum(r[4] for r in rs)}"
              f"  emitted {sum(r[5] for r in rs)}")
    for r in sorted(rows, key=lambda r: (r[1], r[0])):
        print("  ", *r)


if __name__ == "__main__":
    cmd = sys.argv[1]
    sys.exit({"setup": lambda: setup(*sys.argv[2:5]), "try": lambda: attempt(*sys.argv[2:4]),
              "score": lambda: score(sys.argv[2])}[cmd]() or 0)
