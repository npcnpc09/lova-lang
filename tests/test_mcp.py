"""Tests for M7 — LOVA as a tool for agents.

``core/mcp_server.py`` serves four tools over the Model Context
Protocol's stdio transport (JSON-RPC 2.0, one message per line) with
no dependency outside the standard library.  Most tests drive
``handle`` in-process; one spawns ``python -m core.cli mcp`` and does
the real round trip through pipes.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest

from core.mcp_server import HANDLERS, TOOLS, handle, serve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(name: str, **arguments):
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}})
    result = json.loads(response["result"]["content"][0]["text"])
    return result, response["result"]["isError"]


class TestProtocol(unittest.TestCase):

    def test_initialize(self):
        response = handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05"}})
        result = response["result"]
        self.assertEqual(result["serverInfo"]["name"], "lova")
        self.assertIn("tools", result["capabilities"])

    def test_tools_are_listed_with_schemas(self):
        response = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in response["result"]["tools"]]
        self.assertEqual(names, ["lova_execute", "lova_patch", "lova_check",
                                 "lova_static_analyze", "lova_valid_next", "lova_emit"])
        for tool in TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertIn(tool["name"], HANDLERS)

    def test_a_notification_gets_no_answer(self):
        self.assertIsNone(handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_and_tool(self):
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"], -32601)
        response = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "lova_teleport", "arguments": {}}})
        self.assertEqual(response["error"]["code"], -32602)

    def test_serve_answers_line_by_line(self):
        requests = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            "not json",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "lova_execute",
                                   "arguments": {"source": "(mul 6 7)"}}}),
        ]) + "\n"
        out = io.StringIO()
        serve(io.StringIO(requests), out)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([l.get("id") for l in lines], [1, None, 2])
        self.assertEqual(lines[1]["error"]["code"], -32700)
        self.assertEqual(json.loads(lines[2]["result"]["content"][0]["text"])["value_int"], 42)


class TestExecute(unittest.TestCase):

    def test_runs_and_returns_the_value(self):
        result, is_error = call("lova_execute", source="(sum (list 1 2 3))")
        self.assertFalse(is_error)
        self.assertEqual(result["value_int"], 6)
        self.assertEqual(result["output"], "")
        self.assertGreater(result["steps"], 0)

    def test_output_and_text_values(self):
        result, _ = call("lova_execute", source='(seq (println "hi") "ok")')
        self.assertEqual(result["output"], "hi\n")
        self.assertEqual(result["value_text"], "ok")
        self.assertEqual(result["value_list"], [111, 107])

    def test_placeholders_and_stdin(self):
        result, _ = call("lova_execute", source="(merge {n} 1)", args=["41"])
        self.assertEqual(result["value_int"], 42)
        result, _ = call("lova_execute", source="(len (stdin))", stdin="abcd\n")
        self.assertEqual(result["value_int"], 5)          # the newline is kept (Q78)

    def test_a_trap_is_a_structured_error(self):
        result, is_error = call("lova_execute", source="(div 1 0)")
        self.assertTrue(is_error)
        self.assertEqual(result["stage"], "run")
        self.assertEqual(result["anomaly"]["kind"], "domain-error")
        self.assertIn("repair_hint", result["anomaly"])

    def test_a_compile_error_is_a_structured_error(self):
        result, is_error = call("lova_execute", source="(merge (nil) 1)", prelude=False)
        self.assertTrue(is_error)
        self.assertEqual(result["stage"], "compile")
        self.assertEqual(result["anomaly"]["kind"], "type-mismatch")

    def test_capabilities_are_granted_explicitly(self):
        result, is_error = call("lova_execute", source='(boundary "clock" (gt (clock) 0))')
        self.assertTrue(is_error)
        self.assertEqual(result["anomaly"]["kind"], "capability-denied")
        result, is_error = call("lova_execute", source='(boundary "clock" (gt (clock) 0))',
                                allow=["clock"])
        self.assertFalse(is_error)
        self.assertEqual(result["value_int"], 1)

    def test_a_bad_grant_is_reported(self):
        result, is_error = call("lova_execute", source="1", allow=["teleport"])
        self.assertTrue(is_error)
        self.assertEqual(result["stage"], "grant")

    def test_stage2_source(self):
        result, _ = call("lova_emit", source="(mul 6 7)", form="stage2")
        back, is_error = call("lova_execute", source=result["text"], stage2=True, prelude=False)
        self.assertFalse(is_error)
        self.assertEqual(back["value_int"], 42)


class TestAnalyze(unittest.TestCase):

    def test_reports_effects_passes_and_bytes(self):
        result, is_error = call("lova_static_analyze", source='(boundary "fs-read" (fs-read "x"))')
        self.assertFalse(is_error)
        self.assertIn("read-fs", result["analysis"]["effects"])
        self.assertFalse(result["analysis"]["is_deterministic"])
        self.assertIn("capability-check", result["report"]["passes"])
        self.assertEqual(bytes.fromhex(result["bytes"]).__len__(), result["byte_count"])
        self.assertTrue(result["stage2"])

    def test_the_prelude_is_free(self):
        result, _ = call("lova_static_analyze", source="1")
        self.assertEqual(result["report"]["compiled_nodes"], 1)

    def test_emit_forms(self):
        for form in ("stage2", "sexp", "bytes", "int"):
            result, is_error = call("lova_emit", source="(merge 1 2)", form=form)
            self.assertFalse(is_error, form)
            self.assertTrue(result["text"])
        self.assertEqual(call("lova_emit", source="(merge 1 2)", form="sexp")[0]["text"], "3")


class TestValidNext(unittest.TestCase):

    def test_an_empty_prefix_offers_everything_typed(self):
        result, is_error = call("lova_valid_next")
        self.assertFalse(is_error)
        self.assertFalse(result["complete"])
        self.assertEqual(result["expects"], "Value")
        names = {c["name"] for c in result["choices"]}
        self.assertIn("lit", names)
        self.assertIn("merge", names)
        self.assertNotIn("clock", names)          # not declared here
        self.assertIn("lit", result["finish_soonest"])

    def test_a_byte_prefix_is_walked(self):
        # merge, lit 5: one Int slot left.
        result, _ = call("lova_valid_next", bytes="03 01 01 05", top_type="Int")
        self.assertEqual(result["expects"], "Int")
        self.assertEqual(result["parent_op"], "merge")
        self.assertEqual(result["depth"], 1)

    def test_a_token_prefix_keeps_scope(self):
        # (let 0 5 ...) -- the body slot; a ref would name 0.
        result, _ = call("lova_valid_next", tokens=[0x2E, [1, 0], [1, 5], 0x2F],
                         top_type="Int")
        self.assertEqual(result["literal_role"], "ref-name")
        self.assertEqual(result["names_in_scope"], [0])

    def test_a_complete_program_says_so(self):
        result, _ = call("lova_valid_next", tokens=[[1, 7]])
        self.assertTrue(result["complete"])

    def test_an_invalid_prefix_is_an_error(self):
        result, is_error = call("lova_valid_next", tokens=[0x37])   # clock at the root
        self.assertTrue(is_error)

    def test_choices_carry_metadata(self):
        result, _ = call("lova_valid_next", top_type="Int")
        merge = next(c for c in result["choices"] if c["name"] == "merge")
        self.assertEqual(merge["out_type"], "Int")
        self.assertIn("terminating", merge)
        self.assertIn("prior_pass_rate", merge)


class TestSubprocess(unittest.TestCase):

    def test_the_cli_serves_over_pipes(self):
        requests = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "lova_execute",
                                   "arguments": {"source": "(product (list 2 3 7))"}}}),
        ]) + "\n"
        env = dict(os.environ, PYTHONPATH=ROOT)
        proc = subprocess.run([sys.executable, "-m", "core.cli", "mcp"], input=requests,
                              capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "lova")
        self.assertEqual(json.loads(lines[1]["result"]["content"][0]["text"])["value_int"], 42)


if __name__ == "__main__":
    unittest.main()
