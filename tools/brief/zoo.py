"""One program per fault kind: the full anomaly beside the brief line."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.mcp_server import tool_execute, tool_check
from core.brief import compact
ZOO = {
    "div by zero": "(def f [x] (div x 0))\n(f 3)",
    "head of empty": "(head (nil))",
    "unbound + synonym": "(def f [x] (add x 1))\n(f 1)",
    "unbound typo": "(def total [xs] (fold merge 0 xs))\n(totl (list 1 2))",
    "type mismatch": "(merge (nil) 1)",
    "arity": "(def f [a b] (merge a b))\n(merge (f 1 2 3) 1)",
    "unclosed paren": "(def f [x] (merge x 1)\n(f 2)",
    "extra paren": "(def f [x] (merge x 1)))\n(f 2)",
    "step limit": "(def spin [n] (spin (merge n 1)))\n(spin 0)",
    "depth": "(def d [n] (merge 1 (d n)))\n(d 0)",
    "capability": '(boundary "clock" (gt (clock) 0))',
    "signal": "(signal 17)",
    "nth past end": "(nth (list 1 2) 5)",
    "missing field": "(get (rec x 1) y)",
    "budget": "(budget 10 (fold merge 0 (range 100)))",
    "conserve": "(conserve 5 (merge 2 2))",
    "op name as def": "(def dist [a b] 99)\n(dist 1 2)",
}
tot_full = tot_brief = 0
for name, src in ZOO.items():
    r = tool_execute({"source": src, "native": "off", "max_steps": 200000})
    if r.get("ok"):
        print(f"## {name}: ran ok -> {r.get('value')}\n"); continue
    full = json.dumps(r, ensure_ascii=False, indent=1); short = json.dumps(compact(r), ensure_ascii=False, separators=(",", ":"))
    tot_full += len(full); tot_brief += len(short)
    print(f"## {name}  full(as served before) {len(full)}  brief {len(short)}\n{short}\n")
print(f"total full {tot_full}  brief {tot_brief}  ratio {tot_full/tot_brief:.1f}x")
