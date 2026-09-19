"""Drive a native LOVA runtime over the line protocol.

`spec/native-runtime-protocol.md` says what a native runtime answers:
one JSON object per line in, one out, the bytes of the compiled program
in and a printed value, a step count, whatever the program wrote, or an
anomaly out.  This module is the other end of that pipe -- the Python
side that starts the binary once, keeps it, and hands the answer back
in the shape the rest of the codebase already handles:

    with NativeRuntime([...]) as rt:
        result = rt.run(tree, max_steps=..., max_call_depth=...)
        print(result.value_text)

A value comes back as `NativeResult`, and the **text** is the value:
nothing is reconstructed on this side, because the protocol already
carries the printed form `core.cli.format_value` would have produced,
and the golden set is what guarantees the two agree.  A trap comes back
as a raised `core.conservation` trap of the right class carrying the
anomaly the native side produced, so `core.cli.report_error`,
`core.cli.name_anomaly` and the MCP server's `_failure` work on it
unchanged.

Two things the native side cannot know are added here, exactly as
`core.runtime._enrich_trap` adds them for a Python trap:
`valid_alternatives` (derived from the offending operator) and `span`
(the place in the source text).  Bytes carry no spans, so the span is
recovered from the tree by `span_for_path` -- see its docstring for
what that costs in honesty.

Stdlib only, and no import of `core.runtime` at module level: a host
that only wants to ask "is there a native runtime?" should not pay for
the interpreter.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.tokens import Node, SIGNATURES, encode

__all__ = [
    "NativeUnavailable", "NativeUnsupported", "NativeResult", "NativeRuntime",
    "UNSUPPORTED_OPS", "default_runtime", "supports", "operators_of",
    "split_command",
    "span_for_path", "trap_from_anomaly",
]


# --- what a phase-2 native runtime does not do -------------------------------

# D7 (`spec/runtime-semantics.md` §0.1): phase 2 is everything except the
# Meta family, the Evolution family, `trace` / `trace-surprise`, `read` /
# `explain` and the network.  Named, not numbered, so a slot that changes
# hands does not silently change the list.
UNSUPPORTED_OP_NAMES = frozenset({
    # Evolution, 0x20-0x27
    "defpop", "variant", "evolve", "select", "mutate", "clone", "fitness",
    "retire",
    # Meta / lineage, 0x38-0x3F (this is where `trace` and `explain` live)
    "lineage-query", "why", "trace", "explain", "hash", "uid", "ancestor-of",
    "generation",
    # named by D7 outside those two families
    "trace-surprise", "read", "net-send", "net-recv",
    # the world: D7 gives these to phase 3, and the phase-2 binary
    # refuses them (`unsupported` in native/lova-rt/src/main.rs).  They
    # must be screened here and not left to the binary's refusal, because
    # `run` has already handed over the whole of stdin by then, and a
    # program that falls back to Python after that has lost its input
    # (apps/guess.lova: `clock` inside a boundary, `stdin` in a def).
    "fs-read", "fs-write", "clock",
})

UNSUPPORTED_OPS = frozenset(
    token for token, sig in SIGNATURES.items()
    if sig.get("name") in UNSUPPORTED_OP_NAMES
)

# The list is the binary's own list, by name.  A runtime that disagrees
# still says so, and `run` turns its `{"ok": false, "error": "unsupported:
# ..."}` into `NativeUnsupported`, which every caller treats as "this
# program is Python's" -- but that is the safety net, not the screen:
# phase 3 removes the world from both lists at once.


def split_command(text: str) -> List[str]:
    """A command string to its words, on Windows as on anything else.

    ``posix=False`` keeps a backslash a backslash, which a Windows path
    needs, but it also keeps the quotes that held a path with a space
    in it together -- so they come off here.
    """
    words = []
    for word in shlex.split(text, posix=False):
        if len(word) >= 2 and word[0] == word[-1] and word[0] in "\"'":
            word = word[1:-1]
        words.append(word)
    return words


class NativeUnavailable(RuntimeError):
    """No native runtime, or the one we had stopped answering."""


class NativeUnsupported(RuntimeError):
    """The native runtime refused the program: not in its phase's scope."""


# --- scanning a tree ---------------------------------------------------------

def operators_of(tree: Node) -> frozenset:
    """Every token byte that occurs in the tree."""
    seen: set = set()
    stack: List[Any] = [tree]
    while stack:
        node = stack.pop()
        if not isinstance(node, Node):
            continue
        seen.add(node.op)
        stack.extend(node.args)
    return frozenset(seen)


def supports(tree: Node) -> bool:
    """Can a phase-2 native runtime run this program?"""
    return not (operators_of(tree) & UNSUPPORTED_OPS)


def unsupported_in(tree: Node) -> List[str]:
    """The names of the operators that keep this program in Python."""
    found = sorted(operators_of(tree) & UNSUPPORTED_OPS)
    return [SIGNATURES.get(t, {}).get("name", hex(t)) for t in found]


# --- the span of a trap, recovered from the tree -----------------------------

_MAX_OUTWARD = 8        # how far out of a call a span is looked for


def _index(tree: Node):
    """The tree's nodes in preorder, and each one's parent.

    Parents rather than chains: a depth trap's path is one entry per
    frame, and holding a chain per node would cost the tree's size times
    its depth to answer a question that walks upward anyway.
    """
    order: List[Node] = []
    parent: Dict[int, Optional[Node]] = {}
    stack: List[Tuple[Any, Optional[Node]]] = [(tree, None)]
    while stack:
        node, above = stack.pop()
        if not isinstance(node, Node):
            continue
        order.append(node)
        parent[id(node)] = above
        for arg in reversed(node.args):
            stack.append((arg, node))
    return order, parent


def _chain(node: Node, parent: Dict[int, Optional[Node]]) -> List[Node]:
    chain = [node]
    above = parent.get(id(node))
    while above is not None:
        chain.append(above)
        above = parent.get(id(above))
    chain.reverse()
    return chain


def span_for_path(tree: Node, position_path: Sequence[int]):
    """The source span a native trap's ``position_path`` points at.

    `core.runtime._enrich_trap` takes the innermost node **with a span**
    off the live Python stack: the chain of nodes actually being
    evaluated, so a fault inside the prelude reports the call in the
    author's own text.  A native runtime reports token bytes, not nodes,
    and that chain is dynamic -- `seq -> apply -> div` crosses a call
    boundary, so it is not a path through the tree.

    What is recoverable is the longest **suffix** of the chain that is a
    real ancestor line in the tree: a call boundary breaks the chain, but
    everything after the last boundary is ordinary nesting, and that is
    the part that names the expression.  So: among the nodes whose op is
    the last of the path, take the one whose ancestor ops match the most
    of the path's tail, and walk up from it to the innermost node
    carrying a span -- the same last step as the Python path.

    The innermost node of the path may be library code, which carries no
    span -- `(nth (list 1 2) 9)` traps on a `tail` inside the prelude --
    so when nothing on its line has a span the path is truncated by one
    and asked again, outward through the call, which is what the Python
    path does by walking up its own stack.

    It is a best effort, and it says so: two identical expressions in one
    def are indistinguishable by op alone, and the deepest match wins
    arbitrarily.  ``None`` when the path is empty or nothing matches.
    """
    path = [p for p in (position_path or ()) if isinstance(p, int)]
    if not path:
        return None
    order, parent = _index(tree)
    for drop in range(min(_MAX_OUTWARD, len(path))):
        want = path[:len(path) - drop]
        target = want[-1]
        ranked: List[Tuple[int, int, Node]] = []
        for index, node in enumerate(order):
            if node.op != target:
                continue
            ops = [n.op for n in _chain(node, parent)]
            k = 0
            while k < len(ops) and k < len(want) and ops[-1 - k] == want[-1 - k]:
                k += 1
            ranked.append((-k, index, node))
        if not ranked:
            continue
        ranked.sort(key=lambda item: (item[0], item[1]))
        # Only the best matches: a node that matched less of the path is
        # a worse answer than looking one call further out.
        best_k = ranked[0][0]
        for _, _, node in [r for r in ranked if r[0] == best_k]:
            for above in reversed(_chain(node, parent)):
                span = getattr(above, "span", None)
                if span is not None:
                    return span
    return None


def enrich(anomaly: Dict[str, Any], tree: Optional[Node]) -> Dict[str, Any]:
    """Add what the protocol says is the driver's: alternatives and a span."""
    from core.observability import suggest_alternatives

    op = anomaly.get("offending_op")
    if op is not None and not anomaly.get("valid_alternatives"):
        anomaly["valid_alternatives"] = tuple(suggest_alternatives(op))
    if not anomaly.get("offending_op_name") and op is not None:
        anomaly["offending_op_name"] = SIGNATURES.get(op, {}).get("name", "?")
    if tree is not None and not anomaly.get("span"):
        span = span_for_path(tree, anomaly.get("position_path") or ())
        if span is not None:
            anomaly["span"] = span
    return anomaly


def trap_from_anomaly(anomaly: Dict[str, Any], message: str = ""):
    """The `core.conservation` exception a Python run would have raised.

    The class is picked from ``kind`` as `core/conservation.py` maps
    them, and the anomaly is the native side's own -- constructed
    without the class's ``__init__``, because those build an anomaly of
    their own out of arguments a native runtime does not send.
    """
    from core.conservation import (
        BudgetTrap, DeltaTrap, DepthTrap, DomainTrap, StepTrap,
    )

    kind = anomaly.get("kind")
    cls: Any = {
        "budget-exceeded": BudgetTrap,
        "recursion-depth-exceeded": DepthTrap,
        "step-limit-exceeded": StepTrap,
        "conservation-violated": DeltaTrap,
    }.get(kind, DomainTrap)
    exc = cls.__new__(cls)
    detail = anomaly.get("detail") or {}
    if not message:
        message = f"{kind}: " + (anomaly.get("repair_hint") or "")
        if isinstance(detail, dict) and "limit" in detail:
            message = (f"{kind}: spent {detail.get('spent')} > "
                       f"limit {detail.get('limit')}")
    Exception.__init__(exc, message.strip() or str(kind))
    exc.anomaly = anomaly
    return exc


# --- the result of a run -----------------------------------------------------

class NativeResult:
    """What a native run produced: the printed value, steps, stdout.

    ``value_text`` is *the* value: the native side already printed it
    with the same rules `core.cli.format_value` uses, and reconstructing
    a Python object from it would be inventing a second answer.
    """

    __slots__ = ("value_text", "steps", "stdout")

    def __init__(self, value_text: str, steps: int, stdout: str = "") -> None:
        self.value_text = value_text
        self.steps = steps
        self.stdout = stdout

    # `value` reads better at a call site than `value_text`.
    @property
    def value(self) -> str:
        return self.value_text

    def __repr__(self) -> str:
        return (f"NativeResult(value_text={self.value_text!r}, "
                f"steps={self.steps})")


# --- the client --------------------------------------------------------------

DEFAULT_TIMEOUT_S = 300.0


class NativeRuntime:
    """A native runtime kept alive across runs.

    The process is started once and every `run` is one request on its
    pipes, because starting a binary per example costs more than the
    example.  It never hangs: a read runs under a timeout, and a timeout
    kills the process and raises `NativeUnavailable`, as does a process
    that died or answered something that is not a reply.  A client whose
    process has died stays dead -- make a new one.
    """

    def __init__(self, command: Sequence[str],
                 *, cwd: Optional[str] = None,
                 timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        if isinstance(command, str):
            command = split_command(command)
        self.command: List[str] = [str(c) for c in command]
        if not self.command:
            raise NativeUnavailable("no native runtime command")
        self.timeout_s = timeout_s
        self.version = "?"
        self._id = 0
        self._lock = threading.Lock()
        self._dead: Optional[str] = None
        root = cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            self.proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=None, text=True, encoding="utf-8", bufsize=1,
                cwd=root)
        except OSError as exc:
            raise NativeUnavailable(
                f"cannot start {self.command[0]!r}: {exc}") from exc

    # -- protocol ------------------------------------------------------------

    def _fail(self, message: str) -> "NativeUnavailable":
        self._dead = message
        self.kill()
        return NativeUnavailable(message)

    def _call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self._dead is not None:
            raise NativeUnavailable(self._dead)
        proc = self.proc
        if proc.poll() is not None:
            raise self._fail(
                f"the native runtime exited with code {proc.returncode}")
        line_text = json.dumps(request, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                assert proc.stdin is not None
                proc.stdin.write(line_text)
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise self._fail(f"the native runtime closed its input: {exc}")
            line = self._read_line()
        if not line:
            raise self._fail("the native runtime closed its output")
        try:
            reply = json.loads(line)
        except ValueError as exc:
            raise self._fail(f"the native runtime answered non-JSON: {exc}")
        if not isinstance(reply, dict):
            raise self._fail("the native runtime answered a non-object")
        return reply

    def _read_line(self) -> str:
        """One reply line, under a timeout; a timeout kills the process.

        A read on a pipe cannot be interrupted, so it happens on a
        thread: if the runtime is wedged, the process is killed, which
        ends the read and the client with it.
        """
        proc = self.proc
        assert proc.stdout is not None
        box: List[Any] = [None]

        def pull() -> None:
            try:
                box[0] = proc.stdout.readline()
            except Exception as exc:                       # noqa: BLE001
                box[0] = exc

        reader = threading.Thread(target=pull, daemon=True)
        reader.start()
        reader.join(self.timeout_s)
        if reader.is_alive():
            self.kill()
            reader.join(1.0)
            raise self._fail(
                f"the native runtime did not answer within {self.timeout_s:g}s")
        if isinstance(box[0], Exception):
            raise self._fail(f"reading from the native runtime: {box[0]}")
        return box[0] or ""

    # -- the two requests ----------------------------------------------------

    def ping(self) -> str:
        reply = self._call({"op": "ping"})
        if not reply.get("ok"):
            raise self._fail(f"ping: {reply.get('error', 'not ok')}")
        self.version = str(reply.get("version", "?"))
        return self.version

    def run(self, program: Any, *, stdin: str = "", allow: int = 0,
            max_steps: int = 1_000_000, max_call_depth: int = 10_000,
            tree: Optional[Node] = None) -> NativeResult:
        """Run a compiled tree (or its bytes) and answer like the runtime.

        Returns a `NativeResult` on a value; **raises** the trap the
        program raised, of the class `core/conservation.py` gives that
        kind, with the native anomaly enriched the way a Python trap's
        is (`valid_alternatives`, and `span` when the tree is at hand).
        """
        if isinstance(program, Node):
            tree = program if tree is None else tree
            data = encode(program)
        elif isinstance(program, (bytes, bytearray)):
            data = bytes(program)
        else:
            raise TypeError("run: a Node tree or its bytes")
        self._id += 1
        reply = self._call({
            "id": self._id, "op": "run", "bytes": data.hex(),
            "stdin": stdin, "allow": int(allow),
            "max_steps": int(max_steps), "max_depth": int(max_call_depth),
        })
        steps = int(reply.get("steps") or 0)
        out = reply.get("stdout") or ""
        if reply.get("ok"):
            return NativeResult(str(reply.get("value", "")), steps, out)
        anomaly = reply.get("anomaly")
        if not anomaly:
            error = str(reply.get("error", "the native runtime said not ok"))
            if error.startswith("unsupported"):
                raise NativeUnsupported(error)
            raise NativeUnavailable(error)
        anomaly = dict(anomaly)
        anomaly["position_path"] = tuple(anomaly.get("position_path") or ())
        enrich(anomaly, tree)
        trap = trap_from_anomaly(anomaly)
        # Beside the trap, not inside the anomaly: what the run cost and
        # what it managed to write before it stopped, which every caller
        # of the Python runtime reads off the `Runtime` object.
        trap.steps = steps
        trap.stdout = out
        raise trap

    # -- lifetime ------------------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._dead is None and self.proc.poll() is None

    def kill(self) -> None:
        try:
            self.proc.kill()
        except Exception:                                  # noqa: BLE001
            pass

    def close(self) -> None:
        proc = getattr(self, "proc", None)
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:                                  # noqa: BLE001
            self.kill()
        finally:
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:                          # noqa: BLE001
                    pass

    def __enter__(self) -> "NativeRuntime":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        self.close()
        return False


# --- finding one -------------------------------------------------------------

_DEFAULT: List[Any] = []        # [] not looked yet, [None] or [command]


def default_command() -> Optional[List[str]]:
    """The native runtime this machine has, or None.  Cached.

    ``LOVA_NATIVE`` is a command string and wins, so a port under
    development, or the reference server (`python tools/mock_runtime.py`),
    can be pointed at without moving a binary.
    """
    if _DEFAULT:
        return _DEFAULT[0]
    command: Optional[List[str]] = None
    env = os.environ.get("LOVA_NATIVE", "").strip()
    if env:
        command = split_command(env)
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("lova-rt.exe", "lova-rt"):
            path = os.path.join(root, "native", "lova-rt", "target", "release", name)
            if os.path.isfile(path):
                command = [path]
                break
    _DEFAULT.append(command)
    return command


def forget_default() -> None:
    """Drop the cached lookup and the shared process (the tests move
    ``LOVA_NATIVE`` about, and the next look should start again)."""
    _DEFAULT.clear()
    while _SHARED:
        _SHARED.pop().close()


def default_runtime(*, timeout_s: float = DEFAULT_TIMEOUT_S) -> Optional[NativeRuntime]:
    """A started, pinged native runtime, or None if this machine has none."""
    command = default_command()
    if not command:
        return None
    try:
        runtime = NativeRuntime(command, timeout_s=timeout_s)
        runtime.ping()
    except NativeUnavailable:
        return None
    return runtime


_SHARED: List[NativeRuntime] = []


def shared_runtime(*, timeout_s: float = DEFAULT_TIMEOUT_S) -> Optional[NativeRuntime]:
    """One native runtime for the life of this process, restarted if it dies.

    For a server answering one request after another -- the MCP host's
    `lova_execute` -- where starting a binary per request is the cost the
    persistent protocol exists to avoid.  The caller does not close it.
    """
    if _SHARED and _SHARED[0].alive:
        return _SHARED[0]
    del _SHARED[:]
    runtime = default_runtime(timeout_s=timeout_s)
    if runtime is not None:
        _SHARED.append(runtime)
        import atexit
        atexit.register(runtime.close)
    return runtime


def choose(tree: Node, mode: str = "auto", *, shared: bool = False,
           timeout_s: float = DEFAULT_TIMEOUT_S) -> Optional[NativeRuntime]:
    """The runtime for this program under ``--native auto|on|off``.

    ``None`` means "run it in Python".  ``on`` raises `NativeUnavailable`
    or `NativeUnsupported` rather than falling back, because a host that
    asked for the native runtime wants to be told it did not get it.
    """
    if mode not in ("auto", "on", "off"):
        raise ValueError(f"--native: expected auto, on or off, got {mode!r}")
    if mode == "off":
        return None
    if not supports(tree):
        missing = ", ".join(unsupported_in(tree))
        if mode == "on":
            raise NativeUnsupported(
                f"the native runtime does not implement: {missing}")
        return None
    runtime = (shared_runtime(timeout_s=timeout_s) if shared
               else default_runtime(timeout_s=timeout_s))
    if runtime is None and mode == "on":
        raise NativeUnavailable(
            "no native runtime: set LOVA_NATIVE to a command, or build "
            "native/lova-rt (cargo build --release)")
    return runtime


if __name__ == "__main__":        # a one-line smoke test, not a tool
    rt = default_runtime()
    print(rt.ping() if rt is not None else "no native runtime", file=sys.stderr)
    if rt is not None:
        rt.close()
