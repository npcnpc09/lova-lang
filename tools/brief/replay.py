"""Replay every logged LOVA failure (Exp 19 run 2, Exp 21) through today's
runtime and record today's feedback text, so a change to the report can be
measured on the faults real sessions actually met."""
import json, glob, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from experiments import experiment_18_agent_loop as loop
from experiments import experiment_19_agent_loop_apps as e19
from experiments import experiment_21_repair as e21

def cases():
    for pat, mod in (("results_19/o*/lova/log.jsonl", e19), ("results_21/*/lova/log.jsonl", e21)):
        for f in sorted(glob.glob(str(ROOT / "experiments" / pat))):
            for i, l in enumerate(open(f)):
                r = json.loads(l)
                if r.get("passed") is False and "program" in r:
                    yield {"id": f"{Path(f).parts[-4]}/{Path(f).parts[-3]}#{i}", "task": r["task"],
                           "program": r["program"], "logged_chars": r["feedback_chars"], "mod": mod}

out = []
for c in cases():
    task = c["mod"].BY_ID[c["task"]]
    res = loop.run_lova(c["program"], task)
    fb = loop.feedback_text("lova", res)
    out.append({k: v for k, v in c.items() if k != "mod"} | {"result": res, "feedback": fb})
    print(c["id"], c["task"], "passed" if res["passed"] else "", len(fb), file=sys.stderr)
Path(ROOT / "tools/brief/replay.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
