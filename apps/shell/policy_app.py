"""A shell in Python, the rules in LOVA.

    python apps/shell/policy_app.py            # http://127.0.0.1:8765

The demonstration of the division of labour LOVA is for: the user
interface, the HTTP server and the page are ordinary Python (standard
library only), and the one piece of the application that decides
anything -- the loyalty-points rule -- is a LOVA program.  The page
lets you edit the rule and run it against inputs; the shell runs it
through the same function the MCP server exposes (`tool_execute`),
under a node budget and with no capability granted, and shows what
comes back: the value, or the structured fault -- kind, position,
repair hint -- when the rule divides by zero, loops for ever, or
tries to read a file it never declared.  The page also shows the rule
as the integer it is: its Stage-2 projection and its digest.

A shell in another language would call `lova mcp` over stdio and get
the same JSON; this one imports the core because it is Python.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import surface2
from core.mcp_server import _build, tool_execute
from core.tokens import encode

PORT = 8765
BUDGET = 50_000            # nodes a rule may spend; a loop meets it in milliseconds

DEFAULT_RULE = """\
;; Loyalty points for a purchase.  Edit freely: the shell runs whatever
;; is here, under a budget of 50 000 nodes and with no effect granted.
;;   amount  the purchase in cents
;;   tier    1 silver, 2 gold
;;   items   how many items
(def base [amount] (div amount 100))              ; one point per whole unit
(def tiered [pts tier] (if (eq tier 2) (mul pts 2) pts))
(def bonus [items] (if (ge items 5) 50 0))
(min 1000 (merge (tiered (base {amount}) {tier}) (bonus {items})))
"""

SABOTAGE = {
    "divide": "(div {amount} (sub {tier} {tier}))",
    "loop": "(def spin [n] (spin (inc n)))(spin {amount})",
    "file": '(boundary "fs-read" (len (fs-read "/etc/passwd")))',
    "unbound": "(merge {amount} (undefined-name {items}))",
}

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Loyalty points -- a Python shell, a LOVA rule</title>
<style>
 body { font: 14px/1.4 system-ui, sans-serif; margin: 2rem auto; max-width: 62rem; color: #222; }
 h1 { font-size: 1.3rem; } h2 { font-size: 1rem; margin: 1.2rem 0 .4rem; }
 textarea { width: 100%; height: 14rem; font: 13px/1.4 ui-monospace, monospace; }
 .row { display: flex; gap: 1rem; align-items: end; flex-wrap: wrap; margin: .6rem 0; }
 label { display: flex; flex-direction: column; font-size: .85rem; }
 input { width: 8rem; font-size: 1rem; }
 button { padding: .4rem .9rem; } .sab button { background: #fbe9e7; }
 pre { background: #f5f5f5; padding: .8rem; overflow-x: auto; white-space: pre-wrap; }
 .ok { color: #1a7f37; } .fault { color: #b3261e; }
 .small { color: #666; font-size: .85rem; }
</style>
<h1>Loyalty points &mdash; the shell is Python, the rule is LOVA</h1>
<p class="small">The page, the server and the form are ordinary Python. The only thing that
<em>decides</em> anything is the program below. It runs under a budget of 50&thinsp;000 nodes,
with no capability granted, through the same call the MCP server exposes.</p>
<h2>The rule</h2>
<textarea id="rule"></textarea>
<div class="row">
 <label>amount (cents) <input id="amount" value="12345"></label>
 <label>tier (1 silver, 2 gold) <input id="tier" value="2"></label>
 <label>items <input id="items" value="6"></label>
 <button id="run">Run the rule</button>
</div>
<div class="row sab">
 <span class="small">Break it on purpose:</span>
 <button data-s="divide">divide by zero</button>
 <button data-s="loop">loop for ever</button>
 <button data-s="file">read a file</button>
 <button data-s="unbound">use a name that does not exist</button>
 <button id="restore">restore the rule</button>
</div>
<h2>What came back</h2>
<pre id="out">(nothing yet)</pre>
<h2>The rule as an integer</h2>
<pre id="int" class="small">(run to see)</pre>
<script>
const rule = document.getElementById('rule');
const DEFAULT = __DEFAULT__;
const SAB = __SABOTAGE__;
rule.value = DEFAULT;
document.getElementById('restore').onclick = () => { rule.value = DEFAULT; };
for (const b of document.querySelectorAll('.sab button[data-s]')) b.onclick = () => { rule.value = SAB[b.dataset.s]; run(); };
document.getElementById('run').onclick = run;
async function run() {
  const body = { source: rule.value, inputs: {
    amount: document.getElementById('amount').value,
    tier: document.getElementById('tier').value,
    items: document.getElementById('items').value } };
  const r = await fetch('/run', { method: 'POST', body: JSON.stringify(body) });
  const j = await r.json();
  const out = document.getElementById('out');
  if (j.ok) {
    out.className = 'ok';
    out.textContent = 'value: ' + j.value + '\\nsteps: ' + j.steps + (j.output ? '\\noutput: ' + j.output : '');
  } else {
    out.className = 'fault';
    const a = j.anomaly || {};
    const lines = ['fault at ' + j.stage + ': ' + (a.kind || 'error')];
    if (a.message) lines.push('message: ' + a.message);
    if (a.detail) lines.push('detail: ' + JSON.stringify(a.detail));
    if (a.offending_op_name) lines.push('offending operator: ' + a.offending_op_name);
    if (a.position_path) lines.push('position path: ' + JSON.stringify(a.position_path).slice(0, 120));
    if (a.repair_hint) lines.push('repair: ' + a.repair_hint);
    if (j.steps !== undefined) lines.push('steps before the trap: ' + j.steps);
    out.textContent = lines.join('\\n');
  }
  document.getElementById('int').textContent = j.projection
    ? 'stage-2 (' + j.projection.length + ' chars): ' + j.projection + '\\nbytes: ' + j.bytes + '\\ndigest: ' + j.digest
    : '(the rule did not compile, so it has no integer)';
}
run();
</script>
"""


def run_rule(source: str, inputs: dict) -> dict:
    """The shell's one call into the language."""
    args = [f"{k}={v}" for k, v in inputs.items()]
    result = tool_execute({"source": source, "args": args, "allow": [],
                           "max_steps": BUDGET, "max_depth": 1000})
    try:
        tree, _ = _build({"source": source, "args": args})
        data = encode(tree)
        result["projection"] = surface2.render(tree)
        result["bytes"] = len(data)
        result["digest"] = int.from_bytes(data, "big") % 2305843009213693951
    except Exception:
        pass
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):     # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        page = (PAGE.replace("__DEFAULT__", json.dumps(DEFAULT_RULE))
                    .replace("__SABOTAGE__", json.dumps(SABOTAGE)))
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/run":
            self._send(404, b"{}", "application/json")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            result = run_rule(str(req.get("source", "")), dict(req.get("inputs", {})))
        except Exception as exc:                 # the shell never dies for a rule
            result = {"ok": False, "stage": "shell", "anomaly": {"kind": "error", "message": str(exc)}}
        self._send(200, json.dumps(result).encode("utf-8"), "application/json")


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"the shell is up at http://127.0.0.1:{PORT}  (Ctrl-C stops it)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
