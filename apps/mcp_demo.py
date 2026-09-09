"""Drive LOVA's MCP server the way an agent host would (M7).

Spawns ``python -m core.cli mcp``, speaks JSON-RPC over its pipes, and
calls each of the four tools once:

    python apps/mcp_demo.py

No MCP client library is needed -- the transport is one JSON object per
line -- which is also why any MCP-capable host (Claude Code, Claude
Desktop, Cursor, ...) can use the server with a configuration like::

    {"mcpServers": {"lova": {"command": "python",
                             "args": ["-m", "core.cli", "mcp"],
                             "cwd": "/path/to/lova-lang"}}}

or, after ``pip install lova-lang``, simply ``{"command": "lova",
"args": ["mcp"]}``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Server:
    def __init__(self) -> None:
        env = dict(os.environ, PYTHONPATH=ROOT)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "core.cli", "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=ROOT, env=env, encoding="utf-8",
        )
        self.next_id = 0

    def request(self, method: str, **params):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, tool: str, **arguments):
        response = self.request("tools/call", name=tool, arguments=arguments)
        return json.loads(response["result"]["content"][0]["text"])

    def close(self) -> None:
        assert self.proc.stdin
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def main() -> int:
    server = Server()
    try:
        hello = server.request("initialize", protocolVersion="2024-11-05")
        print("server:", hello["result"]["serverInfo"])
        tools = server.request("tools/list")["result"]["tools"]
        print("tools: ", ", ".join(t["name"] for t in tools))

        print("\n-- lova_execute")
        result = server.call("lova_execute", source="(sum (map (lambda 9 (mul (ref 9) (ref 9))) (range 1 5)))")
        print("  sum of squares 1..4 =", result["value_int"], f"({result['steps']} steps)")
        result = server.call("lova_execute", source="(div 1 0)")
        print("  (div 1 0) ->", result["anomaly"]["kind"], "-", result["anomaly"]["repair_hint"])
        result = server.call("lova_execute", source='(boundary "clock" (gt (clock) 0))', allow=["clock"])
        print("  clock under a granted boundary ->", result["value_int"])

        print("\n-- lova_static_analyze")
        result = server.call("lova_static_analyze", source='(boundary "fs-read" (len (fs-read "notes.txt")))')
        print("  effects:", result["analysis"]["effects"], "| deterministic:", result["analysis"]["is_deterministic"])
        print("  passes: ", result["report"]["passes"])
        print("  stage2: ", result["stage2"])

        print("\n-- lova_valid_next")
        result = server.call("lova_valid_next", tokens=[0x03, [1, 5]], top_type="Int")
        print("  after (merge 5 _): expects", result["expects"], "| finish soonest:", result["finish_soonest"])
        print("  choices:", ", ".join(c["name"] for c in result["choices"][:12]), "...")

        print("\n-- lova_emit")
        for form in ("stage2", "bytes", "int"):
            result = server.call("lova_emit", source="(def twice [x] (mul x 2)) (twice 21)", form=form)
            print(f"  {form:7}", result["text"])
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
