"""A reference server for `spec/native-runtime-protocol.md`.

    python tools/conformance.py --runtime "python tools/mock_runtime.py"

It is the Python runtime behind the protocol a native runtime must
speak: one JSON object per line in, one out.  Its job is to make the
protocol executable -- a port can be developed against it, and the
conformance harness's native path is exercised by something before the
binary exists.  It is not a port, and it proves nothing about a port.

Two shapes: `run`, which evaluates a program and forgets it, and a
**session** (`session` / `get` / `call` / `release` / `close`, protocol
0.3.0), which keeps the program's value alive and hands out handles on
what is not data -- the shape `apps/war`, `apps/platformer` and
`apps/citybuilder` have, where the world is a LOVA value that lives
between calls.  `core.native.NativeSession` is the other end.

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
from core.conservation import (                        # noqa: E402
    BudgetTrap, DeltaTrap, DepthTrap,
)
from core.observability import suggest_alternatives    # noqa: E402
from core.runtime import (                             # noqa: E402
    Cons, NIL_VALUE, Runtime, _as_map, _call, _map_key, evaluate, list_from,
)
from core.tokens import Node, decode                         # noqa: E402

VERSION = "mock-runtime 1.0.0 (core.runtime behind the protocol)"

# The protocol's own boundary between a JSON number and `{"int": "..."}`.
SAFE_INT = 1 << 53


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
        anomaly = _anomaly_of(exc, tree)
        if anomaly is None:
            return {"id": request.get("id"), "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        reply.update(ok=False, anomaly=anomaly)
    reply["steps"] = rt.steps
    reply["stdout"] = rt.written()
    return reply


def _anomaly_of(exc, tree):
    """The anomaly a trap reports over the wire, or None if it has none.

    Everything the protocol says is the runtime's, and nothing the
    driver adds: no span, no valid_alternatives, no names.
    """
    anomaly = getattr(exc, "anomaly", None)
    if anomaly is None:
        return None
    return {
        "kind": anomaly.get("kind"),
        "offending_op": anomaly.get("offending_op"),
        "offending_op_name": anomaly.get("offending_op_name", ""),
        "position_path": list(anomaly.get("position_path") or ()),
        "position_nodes": _position_nodes(tree, getattr(exc, "path_nodes", ())),
        "detail": _jsonable(anomaly.get("detail") or {}),
        "repair_hint": anomaly.get("repair_hint", ""),
    }


def _position_nodes(tree, path_nodes):
    """Each frame's node as its ordinal in the decoded program.

    Preorder over every node, literals included -- the order the bytes
    hold them -- and ``None`` for a node that is not in the program's
    own tree (one made by `quote` / `clone` / `mutate` and then run).
    """
    ordinal = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        if not isinstance(node, Node):
            continue
        ordinal[id(node)] = len(ordinal)
        stack.extend(reversed(node.args))
    return [ordinal.get(id(n)) for n in path_nodes]


# --- sessions (0.3.0, Q126) --------------------------------------------------
#
# `run` evaluates a program and forgets it; a session keeps the value it
# produced and hands out handles.  Everything below is the protocol's
# "Sessions" section over `core.runtime`: the same `evaluate` for the
# open, the same `_call` per argument for a call, and `_as_map` /
# `_map_key` for a get -- so what the reference server answers is what
# the three drivers compute when they run the program in this process.


class ProtocolError(Exception):
    """A malformed request: answered as `error`, never as an anomaly.

    An anomaly is the language's answer to a fault in a *program*; a
    handle that was released is a fault in the conversation.
    """


class Session:
    """One kept program: its tree, its runtime, and the values it made."""

    def __init__(self, ident, tree, rt, feed, max_steps):
        self.id = ident
        self.tree = tree
        self.rt = rt
        self.feed = feed                  # the rest of stdin, read by calls
        self.max_steps = max_steps
        self.refs = {}                    # id -> the held value
        self.by_value = {}                # id(value) -> ref, so one value is one handle
        self.next_ref = 0

    # -- handles ---------------------------------------------------------

    def ref_for(self, value):
        """The handle for a value, the same one each time it is seen.

        Ids are never reused: a handle released and then used again is
        an error, not a silent hit on somebody else's value.
        """
        hit = self.by_value.get(id(value))
        if hit is not None:
            return hit
        self.next_ref += 1
        ident = self.next_ref
        self.refs[ident] = value
        self.by_value[id(value)] = ident
        return ident

    def release(self, idents):
        for ident in idents:
            value = self.refs.pop(ident, None)
            if value is not None and self.by_value.get(id(value)) == ident:
                del self.by_value[id(value)]

    # -- the encoding ----------------------------------------------------

    def encode(self, value):
        """A LOVA value as the protocol carries it: data, or a handle."""
        if value is None or value is NIL_VALUE:
            return None
        if isinstance(value, bool):                 # not a LOVA value; be exact
            return int(value)
        if isinstance(value, int):
            if -SAFE_INT < value < SAFE_INT:
                return value
            return {"int": str(value)}
        if isinstance(value, str):
            return value
        if isinstance(value, Cons):
            out = []
            rest = value
            while isinstance(rest, Cons):
                out.append(self.encode(rest.head))
                rest = rest.tail
            return out
        return {"ref": self.ref_for(value)}

    def decode(self, data, where="argument"):
        """What the protocol carries, as a LOVA value."""
        if data is None:
            return NIL_VALUE
        if isinstance(data, bool):
            return int(data)
        if isinstance(data, int):
            return data
        if isinstance(data, float):
            if data.is_integer():
                return int(data)
            raise ProtocolError(f"{where}: LOVA has no floating point: {data!r}")
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            return list_from([self.decode(item, where) for item in data])
        if isinstance(data, dict):
            if "ref" in data:
                ident = data["ref"]
                if ident not in self.refs:
                    raise ProtocolError(f"no such ref: {ident}")
                return self.refs[ident]
            if "int" in data:
                try:
                    return int(str(data["int"]))
                except ValueError:
                    raise ProtocolError(
                        f"{where}: not an integer: {data['int']!r}") from None
        raise ProtocolError(f"{where}: cannot read {data!r}")


SESSIONS = {}
_NEXT_SESSION = [0]


def _room_for(max_depth):
    """The Python recursion limit a call of this depth needs.

    `evaluate` raises it for the duration of a run and puts it back; a
    session's calls happen outside any `evaluate`, so the room is made
    once, when the session opens -- which is what the three drivers do
    for themselves with `sys.setrecursionlimit` after they build.
    """
    from core.runtime import _PY_FRAMES_PER_CALL, _PY_RECURSION_HEADROOM
    needed = int(max_depth) * _PY_FRAMES_PER_CALL + _PY_RECURSION_HEADROOM
    if needed > sys.getrecursionlimit():
        sys.setrecursionlimit(needed)


def session_open(request):
    """`session`: a `run` that keeps what it made."""
    try:
        tree = decode(bytes.fromhex(request["bytes"]))
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "error": f"decode: {type(exc).__name__}: {exc}"}
    max_steps = int(request.get("max_steps", 1_000_000))
    max_depth = int(request.get("max_depth", 10_000))
    feed = io.StringIO(request.get("stdin", ""))
    rt = Runtime(max_steps=max_steps, max_call_depth=max_depth,
                 granted=request.get("allow", 0), input_source=feed.readline)
    reply = {"id": request.get("id")}
    try:
        value = evaluate(tree, rt)
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        anomaly = _anomaly_of(exc, tree)
        if anomaly is None:
            return {"id": request.get("id"), "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        # A trap during evaluation is a `run` failure, and no session
        # is opened.
        reply.update(ok=False, anomaly=anomaly,
                     steps=rt.steps, stdout=rt.written())
        return reply
    _NEXT_SESSION[0] += 1
    ident = _NEXT_SESSION[0]
    session = Session(ident, tree, rt, feed, max_steps)
    SESSIONS[ident] = session
    _room_for(max_depth)
    reply.update(ok=True, session=ident, value=session.encode(value),
                 steps=rt.steps, stdout=rt.written())
    return reply


def _session_of(request):
    ident = request.get("session")
    session = SESSIONS.get(ident)
    if session is None:
        raise ProtocolError(f"no such session: {ident}")
    return session


def session_get(request):
    """`get`: `map-get` on a held map, charging nothing."""
    session = _session_of(request)
    # `ref` is the handle's own id, not an encoded value -- the map is
    # always something the session holds.
    ref = request.get("ref")
    if not isinstance(ref, int) or isinstance(ref, bool):
        raise ProtocolError(f"no such ref: {ref!r}")
    target = session.decode({"ref": ref}, "ref")
    key = session.decode(request.get("key"), "key")
    reply = {"id": request.get("id")}
    try:
        table = _as_map(target, "map-get")
        hashed = _map_key(key, "map-get")
    except (BudgetTrap, DeltaTrap, ValueError) as exc:
        anomaly = _anomaly_of(exc, session.tree)
        if anomaly is None:
            return {"id": request.get("id"), "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        reply.update(ok=False, anomaly=anomaly, steps=0, stdout="")
        return reply
    hit = table.entries.get(hashed)
    reply.update(ok=True, value=None if hit is None else session.encode(hit[1]),
                 steps=0, stdout="")
    return reply


def session_call(request):
    """`call`: `_call` per argument, with the steps starting at zero."""
    session = _session_of(request)
    rt = session.rt
    value = session.decode(request.get("fn"), "fn")
    args = [session.decode(item, "args") for item in request.get("args") or ()]
    rt.max_steps = int(request.get("max_steps", session.max_steps))
    # A fresh run's accounting: this call's steps, this call's output,
    # and no function in flight from the call before it.
    rt.steps = 0
    rt.mark = 0
    rt.current = None
    del rt.output[:]
    reply = {"id": request.get("id")}
    try:
        try:
            for arg in args:
                value = _call(value, arg, rt)
        except RecursionError:
            # What `evaluate` does with one: exhausting the host's stack
            # is still a LOVA depth overrun.
            raise DepthTrap(depth=rt.call_depth,
                            limit=rt.max_call_depth) from None
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        anomaly = _anomaly_of(exc, session.tree)
        if anomaly is None:
            return {"id": request.get("id"), "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        # The session stays open: the drivers catch a trap per tick and
        # go on.
        reply.update(ok=False, anomaly=anomaly,
                     steps=rt.steps, stdout=rt.written())
        return reply
    reply.update(ok=True, value=session.encode(value),
                 steps=rt.steps, stdout=rt.written())
    return reply


def session_release(request):
    session = _session_of(request)
    session.release([r for r in request.get("refs") or () if isinstance(r, int)])
    return {"id": request.get("id"), "ok": True}


def session_close(request):
    session = _session_of(request)
    del SESSIONS[session.id]
    session.refs.clear()
    session.by_value.clear()
    return {"id": request.get("id"), "ok": True}


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
            handler = {"run": run, "session": session_open, "get": session_get,
                       "call": session_call, "release": session_release,
                       "close": session_close}.get(op)
            if op == "ping":
                reply = {"ok": True, "version": VERSION, "unsupported": []}
            elif handler is not None:
                try:
                    reply = handler(request)
                except ProtocolError as exc:
                    reply = {"id": request.get("id"), "ok": False,
                             "error": str(exc)}
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
