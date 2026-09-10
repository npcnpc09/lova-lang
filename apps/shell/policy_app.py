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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Policy Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root {
  --bg: #F3F5F9; --panel: #FFFFFF; --panel-2: #EBEEF4; --line: #D6DBE5;
  --ink: #17202E; --ink-2: #55617A; --ink-3: #8A94A8;
  --accent: #2456E6; --accent-ink: #FFFFFF;
  --ok: #1E8E5A; --ok-bg: #E3F5EB; --fault: #C7382C; --fault-bg: #FBE7E4;
  --warn: #B76E00; --int: #6B4BD6; --int-bg: #EEE9FB;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0E1219; --panel: #151B26; --panel-2: #1C2432; --line: #2A3444;
    --ink: #E8ECF4; --ink-2: #A5AFC2; --ink-3: #6F7A90;
    --accent: #6C8CFF; --accent-ink: #0B1020;
    --ok: #4CC98A; --ok-bg: #12301F; --fault: #FF7A6E; --fault-bg: #3A1A16;
    --warn: #F0B54A; --int: #B39CFF; --int-bg: #241E3D;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0E1219; --panel: #151B26; --panel-2: #1C2432; --line: #2A3444;
  --ink: #E8ECF4; --ink-2: #A5AFC2; --ink-3: #6F7A90;
  --accent: #6C8CFF; --accent-ink: #0B1020;
  --ok: #4CC98A; --ok-bg: #12301F; --fault: #FF7A6E; --fault-bg: #3A1A16;
  --warn: #F0B54A; --int: #B39CFF; --int-bg: #241E3D;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 var(--sans); }
a { color: var(--accent); }
.top { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: 1.1rem 1.6rem; border-bottom: 1px solid var(--line); background: var(--panel); }
.brand { display: flex; align-items: baseline; gap: .8rem; }
.brand h1 { margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: -.01em; }
.brand .sub { color: var(--ink-2); font-size: .9rem; }
.meta { color: var(--ink-3); font-size: .8rem; font-family: var(--mono); }
main { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); gap: 1.2rem; padding: 1.2rem 1.6rem 2rem; max-width: 84rem; margin: 0 auto; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; display: flex; flex-direction: column; min-width: 0; }
.panel > header { display: flex; align-items: center; justify-content: space-between; gap: .8rem; padding: .7rem 1rem; border-bottom: 1px solid var(--line); }
.eyebrow { font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); font-weight: 600; }
.editor { position: relative; }
.editor textarea { display: block; width: 100%; min-height: 17rem; resize: vertical; border: 0; outline: none; padding: 1rem 1rem 1rem 1rem; background: transparent; color: var(--ink); font: 13.5px/1.55 var(--mono); tab-size: 2; }
.editor textarea:focus-visible { box-shadow: inset 0 0 0 2px var(--accent); }
.inputs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; gap: .8rem; align-items: end; padding: .9rem 1rem; border-top: 1px solid var(--line); }
.inputs label { display: flex; flex-direction: column; gap: .3rem; font-size: .78rem; color: var(--ink-2); }
.inputs input { font: 15px var(--mono); padding: .45rem .6rem; border: 1px solid var(--line); border-radius: 6px; background: var(--panel-2); color: var(--ink); font-variant-numeric: tabular-nums; }
.inputs input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
button { font: 500 .9rem var(--sans); border: 1px solid var(--line); background: var(--panel-2); color: var(--ink); padding: .5rem .9rem; border-radius: 7px; cursor: pointer; }
button:hover { border-color: var(--ink-3); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button.primary { background: var(--accent); color: var(--accent-ink); border-color: transparent; }
.chaos { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; padding: .8rem 1rem; border-top: 1px solid var(--line); }
.chaos .eyebrow { margin-right: .3rem; }
.chaos button { font-size: .82rem; padding: .35rem .7rem; border-radius: 999px; }
.chaos button.restore { margin-left: auto; }
.result { border-left: 5px solid var(--line); }
.result.ok { border-left-color: var(--ok); }
.result.fault { border-left-color: var(--fault); }
.status { display: flex; align-items: center; gap: .6rem; }
.pill { font: 600 .72rem/1 var(--sans); letter-spacing: .06em; text-transform: uppercase; padding: .35rem .6rem; border-radius: 999px; background: var(--panel-2); color: var(--ink-2); }
.ok .pill { background: var(--ok-bg); color: var(--ok); }
.fault .pill { background: var(--fault-bg); color: var(--fault); }
.big { padding: 1rem 1rem .4rem; }
.big .num { font: 500 2.6rem/1.1 var(--mono); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.big .what { color: var(--ink-2); font-size: .85rem; margin-top: .2rem; }
.fault .big .num { color: var(--fault); font-size: 1.5rem; }
dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: .35rem 1rem; margin: 0; padding: .6rem 1rem 1rem; font-size: .86rem; }
dt { color: var(--ink-3); } dd { margin: 0; font-family: var(--mono); font-size: .82rem; overflow-wrap: anywhere; }
dd.hint { font-family: var(--sans); font-size: .86rem; color: var(--ink); }
.identity dd.proj { color: var(--int); }
.identity .badge { display: inline-block; padding: .15rem .45rem; border-radius: 5px; background: var(--int-bg); color: var(--int); font: 500 .78rem var(--mono); }
.history { padding: 0; margin: 0; list-style: none; }
.history li { display: grid; grid-template-columns: 6px minmax(0, 1fr) auto; gap: .8rem; align-items: center; padding: .55rem 1rem; border-top: 1px solid var(--line); font-size: .82rem; }
.history li .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3); }
.history li.ok .dot { background: var(--ok); } .history li.fault .dot { background: var(--fault); }
.history .d { font-family: var(--mono); color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history .v { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.history .empty { color: var(--ink-3); padding: .8rem 1rem; font-size: .85rem; }
.foot { grid-column: 1 / -1; color: var(--ink-3); font-size: .8rem; }
kbd { font: .75rem var(--mono); padding: .1rem .35rem; border: 1px solid var(--line); border-radius: 4px; background: var(--panel-2); }
.right { display: flex; flex-direction: column; gap: 1.2rem; }
@media (prefers-reduced-motion: no-preference) { .result { transition: border-color .2s ease; } }
</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <h1>Policy Console</h1>
    <span class="sub">the shell is Python, the rule is LOVA</span>
  </div>
  <span class="meta" id="meta">budget 50 000 nodes · no capability granted · via tool_execute</span>
</header>
<main>
  <section class="panel">
    <header>
      <span class="eyebrow">Rule · loyalty points</span>
      <span class="meta">edit freely · <kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs</span>
    </header>
    <div class="editor"><textarea id="rule" spellcheck="false" aria-label="the rule"></textarea></div>
    <div class="inputs">
      <label>amount, cents <input id="amount" value="12345"></label>
      <label>tier (1 silver · 2 gold) <input id="tier" value="2"></label>
      <label>items <input id="items" value="6"></label>
      <button id="run" class="primary">Run rule</button>
    </div>
    <div class="chaos">
      <span class="eyebrow">Break it</span>
      <button data-s="divide">divide by zero</button>
      <button data-s="loop">loop for ever</button>
      <button data-s="file">read a file</button>
      <button data-s="unbound">unknown name</button>
      <button id="restore" class="restore">Restore rule</button>
    </div>
  </section>

  <div class="right">
    <section class="panel result" id="result">
      <header>
        <span class="eyebrow">Result</span>
        <span class="status"><span class="pill" id="pill">idle</span></span>
      </header>
      <div class="big"><div class="num" id="num">–</div><div class="what" id="what">run the rule to see its value</div></div>
      <dl id="fields"></dl>
    </section>

    <section class="panel identity">
      <header><span class="eyebrow">The rule as an integer</span><span class="badge" id="digest">–</span></header>
      <dl>
        <dt>bytes</dt><dd id="bytes">–</dd>
        <dt>stage-2</dt><dd class="proj" id="proj">–</dd>
      </dl>
    </section>

    <section class="panel">
      <header><span class="eyebrow">Runs</span><span class="meta" id="count">0</span></header>
      <ul class="history" id="history"><li class="empty">Every run is recorded by the digest of the rule that produced it.</li></ul>
    </section>
  </div>
  <p class="foot">The page, the server and the form are ordinary Python. The only thing that decides anything is the rule, which runs through the same call the MCP server exposes. A shell in another language would call <code>lova mcp</code> and get the same JSON.</p>
</main>
<script>
const DEFAULT = __DEFAULT__;
const SAB = __SABOTAGE__;
const $ = (id) => document.getElementById(id);
const rule = $('rule');
rule.value = DEFAULT;
const history = [];
$('restore').onclick = () => { rule.value = DEFAULT; run(); };
for (const b of document.querySelectorAll('.chaos button[data-s]')) b.onclick = () => { rule.value = SAB[b.dataset.s]; run(); };
$('run').onclick = run;
document.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run(); });

function field(dl, k, v, cls) {
  const dt = document.createElement('dt'); dt.textContent = k;
  const dd = document.createElement('dd'); dd.textContent = v; if (cls) dd.className = cls;
  dl.append(dt, dd);
}

async function run() {
  const inputs = { amount: $('amount').value, tier: $('tier').value, items: $('items').value };
  $('pill').textContent = 'running';
  const r = await fetch('/run', { method: 'POST', body: JSON.stringify({ source: rule.value, inputs }) });
  const j = await r.json();
  const box = $('result'), dl = $('fields');
  dl.replaceChildren();
  if (j.ok) {
    box.className = 'panel result ok';
    $('pill').textContent = 'value';
    $('num').textContent = j.value;
    $('what').textContent = 'points for amount ' + inputs.amount + ', tier ' + inputs.tier + ', ' + inputs.items + ' items';
    field(dl, 'steps', String(j.steps));
    if (j.output) field(dl, 'output', j.output);
  } else {
    const a = j.anomaly || {};
    box.className = 'panel result fault';
    $('pill').textContent = 'fault · ' + j.stage;
    $('num').textContent = a.kind || 'error';
    $('what').textContent = j.stage === 'compile' ? 'refused before it ran' : 'stopped while running';
    if (a.message) field(dl, 'message', a.message);
    if (a.offending_op_name) field(dl, 'operator', a.offending_op_name);
    if (a.detail) field(dl, 'detail', JSON.stringify(a.detail));
    if (a.position_path && a.position_path.length) field(dl, 'path', JSON.stringify(a.position_path).slice(0, 100));
    if (a.repair_hint) field(dl, 'repair', a.repair_hint, 'hint');
    if (j.steps !== undefined) field(dl, 'steps before trap', String(j.steps));
  }
  if (j.projection) {
    $('digest').textContent = String(j.digest);
    $('bytes').textContent = j.bytes + ' bytes · ' + j.projection.length + ' chars of stage-2';
    $('proj').textContent = j.projection;
  } else {
    $('digest').textContent = 'no integer';
    $('bytes').textContent = '–';
    $('proj').textContent = 'the rule did not compile, so it has no integer';
  }
  history.unshift({ ok: j.ok, digest: j.digest, label: j.ok ? j.value : (j.anomaly || {}).kind });
  const ul = $('history');
  ul.replaceChildren(...history.slice(0, 8).map(h => {
    const li = document.createElement('li'); li.className = h.ok ? 'ok' : 'fault';
    const dot = document.createElement('span'); dot.className = 'dot';
    const d = document.createElement('span'); d.className = 'd'; d.textContent = h.digest !== undefined ? 'digest ' + h.digest : 'no integer';
    const v = document.createElement('span'); v.className = 'v'; v.textContent = String(h.label);
    li.append(dot, d, v); return li;
  }));
  $('count').textContent = String(history.length);
}
run();
</script>
</body>
</html>
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
