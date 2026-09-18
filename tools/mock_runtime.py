"""A reference server for `spec/native-runtime-protocol.md`.

    python tools/conformance.py --runtime "python tools/mock_runtime.py"

It is the Python runtime behind the protocol a native runtime must
speak: one JSON object per line in, one out.  Its job is to make the
protocol executable -- a port can be developed against it, and the
conformance harness's native path is exercised by something before the
binary exists.  It is not a port, and it proves nothing about a port.

Stdlib only.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cli import format_value                      # noqa: E402
from core.conservation import BudgetTrap, DeltaTrap    # noqa: E402
from core.observability import suggest_alternatives    # noqa: E402
from core.runtime import Runtime, evaluate             # noqa: E402
from core.tokens import decode                         # noqa: E402

VERSION = "mock-runtime 1.0.0 (core.runtime behind the protocol)"


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)


def run(request):
    try:
        tree = decode(bytes.fromhex(request["bytes"]))
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "error": f"decode: {type(exc).__name__}: {exc}"}
    feed = io.StringIO(request.get("stdin", ""))
    rt = Runtime(max_steps=request.get("max_steps", 1_000_000),
                 max_call_depth=request.get("max_depth", 10_000),
                 granted=request.get("allow", 0),
                 input_source=feed.readline)
    reply = {"id": request.get("id")}
    try:
        value = evaluate(tree, rt)
        reply.update(ok=True, value=format_value(value))
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        anomaly = getattr(exc, "anomaly", None)
        if anomaly is None:
            return {"id": request.get("id"), "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        # Everything the protocol says is the runtime's, and nothing
        # the driver adds: no span, no valid_alternatives, no names.
        reply.update(ok=False, anomaly={
            "kind": anomaly.get("kind"),
            "offending_op": anomaly.get("offending_op"),
            "offending_op_name": anomaly.get("offending_op_name", ""),
            "position_path": list(anomaly.get("position_path") or ()),
            "detail": _jsonable(anomaly.get("detail") or {}),
            "repair_hint": anomaly.get("repair_hint", ""),
        })
    reply["steps"] = rt.steps
    reply["stdout"] = rt.written()
    return reply


def main() -> int:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            reply = {"ok": False, "error": f"bad request: {exc}"}
        else:
            op = request.get("op")
            if op == "ping":
                reply = {"ok": True, "version": VERSION}
            elif op == "run":
                reply = run(request)
            else:
                reply = {"id": request.get("id"), "ok": False,
                         "error": f"unknown op {op!r}"}
        out.write(json.dumps(reply, ensure_ascii=False) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    # `suggest_alternatives` is imported to say, in one line of code,
    # what the protocol says in prose: the driver derives that field,
    # this side never sends it.
    assert suggest_alternatives is not None
    raise SystemExit(main())
