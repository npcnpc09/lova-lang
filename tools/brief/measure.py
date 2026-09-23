"""Characters per failure, full report against brief, on the replayed faults."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from experiments import experiment_18_agent_loop as loop
rows = [r for r in json.loads((ROOT / "tools/brief/replay.json").read_text()) if not r["result"]["passed"]]
def text(r, mode):
    os.environ["LOVA_REPORT"] = mode
    return loop.feedback_text("lova", r["result"])
full = [len(text(r, "full")) for r in rows]; short = [len(text(r, "brief")) for r in rows]
logged = [r["logged_chars"] for r in rows]
by = {}
for r, a, b in zip(rows, full, short):
    f = r["result"]["failures"][0]; k = f.get("anomaly", {}).get("kind", "wrong-value")
    by.setdefault(k, [0, 0, 0]); by[k][0] += 1; by[k][1] += a; by[k][2] += b
print(f"faults: {len(rows)}")
print(f"as logged then     : {sum(logged)/len(rows):7.0f} chars/fault")
print(f"full report today  : {sum(full)/len(rows):7.0f} chars/fault")
print(f"brief report today : {sum(short)/len(rows):7.0f} chars/fault  ({sum(full)/sum(short):.1f}x smaller)")
for k, (n, a, b) in sorted(by.items(), key=lambda kv: -kv[1][0]):
    print(f"  {k:22s} n={n:2d}  full {a/n:6.0f}  brief {b/n:5.0f}")
if "-v" in sys.argv:
    for r in rows:
        print("\n" + r["id"], r["task"]); print(text(r, "brief"))
