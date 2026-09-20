"""LOVA as a tool for agents — an MCP server over stdio (M7).

An AI that writes LOVA needs four things from the substrate, and this
module serves them as Model Context Protocol tools:

- ``lova_execute``        run a program (text or Stage-2), with the
                          host's capability grants, and get the value,
                          the output and the structured anomaly if any;
- ``lova_static_analyze`` compile a program and report what it would
                          do without running it (effects, bounds,
                          passes, the compiled form, its bytes);
- ``lova_valid_next``     the type-constrained next-token set for a
                          partial program -- Axiom 3 as a service -- with
                          per-token metadata and telemetry priors;
- ``lova_emit``           project a program into Stage 2, s-expression,
                          bytes or one integer.

The server speaks JSON-RPC 2.0, one message per line, on stdin/stdout
(the MCP stdio transport), and depends on nothing outside the standard
library -- Axiom 8's "small core" applied to dependencies, as
``pyproject.toml`` already says.  ``python -m core.cli mcp`` starts it;
``handle`` answers one request in-process, which is how the tests and
any embedding host use it.
"""

from __future__ import annotations

import io
import json
import re
import os
import sys
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from core.cli import (
    CLI_MAX_DEPTH, CLI_MAX_STEPS, build, format_value, name_anomaly,
    parse_allow, parse_net_allow, substitute,
)
from core.compiler import CompileError
from core.conservation import BudgetTrap, DeltaTrap
from core.generator import GenState, cheapest_to_finish, pending
from core.observability import static_analyze, valid_next_with_stats
from core.runtime import Runtime, evaluate, is_list_value, list_to_python
from core.surface import pretty
from core import surface2
from core.tokens import END, LIT_INT, SIGNATURES, Node, encode
from core.types import FN, INT, LIST, POPULATION, PROGRAM, VALUE, Type

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "lova", "version": "1.0.0"}

_TOP_TYPES: Dict[str, Type] = {
    "Value": VALUE, "Int": INT, "List": LIST, "Fn": FN,
    "Program": PROGRAM, "Population": POPULATION,
}

TELEMETRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "corpus", "token_telemetry.json",
)
_telemetry: Any = None
_telemetry_loaded = False


def _load_telemetry():
    """The pass-rate telemetry DB, if the corpus ships one; loaded once."""
    global _telemetry, _telemetry_loaded
    if not _telemetry_loaded:
        _telemetry_loaded = True
        if os.path.isfile(TELEMETRY_PATH):
            from core.telemetry import TelemetryDB
            try:
                _telemetry = TelemetryDB.load(TELEMETRY_PATH)
            except (OSError, ValueError):
                _telemetry = None
    return _telemetry


# --- the tools ---------------------------------------------------------------

_SOURCE_PROPS = {
    "source": {"type": "string",
               "description": "LOVA program text (Stage-1 s-expressions, "
                              "or the Stage-2 surface when stage2 is true)"},
    "args": {"type": "array", "items": {"type": "string"},
             "description": "values for the program's {placeholders}, in order"},
    "prelude": {"type": "boolean", "default": True,
                "description": "load lib/prelude.lova (len, map, filter, ...)"},
    "stage2": {"type": "boolean", "default": False,
               "description": "read source as the Stage-2 surface"},
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "lova_execute",
        "description": (
            "Run a LOVA program. Returns its value, what it wrote to stdout, "
            "the step count, and -- if it trapped or failed to compile -- the "
            "structured anomaly (kind, detail, position_path, repair_hint). "
            "Capabilities are granted with `allow`, e.g. [\"fs-read\", \"clock\", "
            "\"net=127.0.0.1:9000\"]; nothing is granted by default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_SOURCE_PROPS,
                "allow": {"type": "array", "items": {"type": "string"},
                          "description": "capabilities to grant: fs-read, fs-write, "
                                         "clock, all, net=host:port, net=:port"},
                "stdin": {"type": "string",
                          "description": "lines the program may read with (stdin)"},
                "max_steps": {"type": "integer", "default": 20000000},
                "max_depth": {"type": "integer", "default": 10000},
                "native": {"type": "string", "enum": ["auto", "on", "off"],
                           "default": "auto",
                           "description": "run on the native runtime when "
                                          "there is one and the program stays "
                                          "inside what it implements (`auto`), "
                                          "require it (`on`), or use the "
                                          "Python runtime (`off`).  The result "
                                          "says which ran, in `runtime`"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "lova_patch",
        "description": (
            "Replace one span of a LOVA source and report whether the result "
            "compiles. An anomaly from lova_execute carries `span` as [start, "
            "end] character offsets and `excerpt`, the text there: patch that "
            "span with the fix and run again. Or name a `def` and the `find` "
            "text to replace inside it, which must occur once in that def "
            "(it may occur elsewhere). Returns the patched source."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_SOURCE_PROPS,
                "span": {"type": "array", "items": {"type": "integer"},
                         "description": "[start, end] offsets into `source`, as an anomaly reports them"},
                "def": {"type": "string", "description": "the def to patch inside, with `find`"},
                "find": {"type": "string", "description": "the text to replace, occurring once in `def`"},
                "replacement": {"type": "string", "description": "the text to put there"},
            },
            "required": ["source", "replacement"],
        },
    },
    {
        "name": "lova_show",
        "description": (
            "The program's own defs -- name, span, parameters, size -- or, with "
            "`def`, one def's text and span. Read the def you need, not the file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {**_SOURCE_PROPS,
                           "def": {"type": "string", "description": "a def's name; omit for the list"}},
            "required": ["source"],
        },
    },
    {
        "name": "lova_scope",
        "description": (
            "What is bound at a character offset: the program's defs, and the "
            "parameters and lets of every enclosing form, innermost last, with "
            "the smallest form containing the offset."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {**_SOURCE_PROPS, "offset": {"type": "integer"}},
            "required": ["source", "offset"],
        },
    },
    {
        "name": "lova_callers",
        "description": "The defs whose bodies mention a name, and the defs that name's body mentions.",
        "inputSchema": {
            "type": "object",
            "properties": {**_SOURCE_PROPS, "name": {"type": "string"}},
            "required": ["source", "name"],
        },
    },
    {
        "name": "lova_check",
        "description": (
            "Run the examples a LOVA program declares about itself -- "
            "`(example expr expected)` forms beside its defs. Each is run as "
            "a conservation contract; a miss reports expected, got, the "
            "example's span and the sub-expression at fault when one is found. "
            "With `strength` true and every example passing, also tries every "
            "single-node edit of every def and reports, def by def, the edits "
            "no example would notice and the defs no example reaches -- where "
            "to write the relation that would (M40)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_SOURCE_PROPS,
                "allow": {"type": "array", "items": {"type": "string"}},
                "max_steps": {"type": "integer", "default": 20000000},
                "max_depth": {"type": "integer", "default": 10000},
                "strength": {"type": "boolean", "default": False},
                "strength_budget": {"type": "number", "default": 20.0,
                                    "description": "seconds to spend probing"},
                "only": {"type": "array", "items": {"type": "string"},
                         "description": "probe these defs only"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "lova_static_analyze",
        "description": (
            "Compile a LOVA program without running it. Returns the static "
            "analysis (effects, budget bound, determinism, cost-boundedness), "
            "the compiler report (passes, node counts, dropped bindings), the "
            "compiled form as text, its bytes, and its Stage-2 projection. A "
            "program that does not compile returns the structured anomaly."
        ),
        "inputSchema": {"type": "object", "properties": dict(_SOURCE_PROPS),
                        "required": ["source"]},
    },
    {
        "name": "lova_valid_next",
        "description": (
            "The set of tokens that may validly follow a partial LOVA program "
            "(Axiom 3: type-constrained generation). Give the prefix as `bytes` "
            "(hex, the byte encoding) or as `tokens` (a list of token bytes, a "
            "literal as [1, value]). Returns each valid token with its name, "
            "types, effects, termination flag and telemetry priors, which "
            "tokens finish soonest, and -- in a reference slot -- which names "
            "are in scope."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bytes": {"type": "string", "description": "hex of the byte prefix"},
                "tokens": {"type": "array",
                           "items": {"anyOf": [{"type": "integer"},
                                               {"type": "array", "items": {"type": "integer"},
                                                "minItems": 2, "maxItems": 2}]},
                           "description": "token bytes; a literal as [1, value]"},
                "top_type": {"type": "string", "enum": list(_TOP_TYPES),
                             "default": "Value"},
            },
        },
    },
    {
        "name": "lova_emit",
        "description": (
            "Project a LOVA program into another form: `stage2` (the "
            "delimiter-free surface), `sexp` (Stage-1 text of the compiled "
            "tree), `bytes` (hex) or `int` (the program as one integer)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_SOURCE_PROPS,
                "form": {"type": "string", "enum": ["stage2", "sexp", "bytes", "int"],
                         "default": "stage2"},
            },
            "required": ["source"],
        },
    },
]


def _jsonable(value: Any) -> Any:
    """Make anomalies and reports JSON-safe: trees as text, sets as lists."""
    if isinstance(value, Node):
        return pretty(value)
    if isinstance(value, (frozenset, set)):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _failure(stage: str, exc: Exception, source: Optional[str] = None) -> Dict[str, Any]:
    anomaly = getattr(exc, "anomaly", None)
    if anomaly is None:
        anomaly = {"kind": "error", "message": str(exc)}
    anomaly = _jsonable(anomaly)
    path = anomaly.get("position_path") if isinstance(anomaly, dict) else None
    if isinstance(path, list) and len(path) > 12:
        # A depth trap carries a path per frame -- twenty thousand
        # integers for a ten-thousand-frame recursion, eighty kilobytes
        # the model would read back for nothing, since `span` and
        # `excerpt` say where the fault is.  The CLI has elided it since
        # M23; the server now does the same (audit, 2026-09-18).
        anomaly["position_path"] = path[:6] + [f"... {len(path) - 9} more ..."] + path[-3:]
    # M24: the span as offsets into the source the caller sent, and the
    # text there, so the caller can patch that expression and nothing else.
    if source is not None and isinstance(anomaly, dict) and anomaly.get("span"):
        # Q127: the span indexes the expanded text; `line` and `col`
        # are in the file the offset came from, and `file` names it
        # when that is an included library (absent for the program's
        # own text, where `span` is also a patchable offset).
        from core.surface import expansion
        exp = expansion(source)
        start, end = anomaly["span"]
        anomaly["excerpt"] = exp.text[start:end]
        origin, anomaly["line"], anomaly["col"] = exp.where(start)
        if origin is not None:
            anomaly["file"] = origin
    return {"ok": False, "stage": stage, "anomaly": anomaly}


def _build(params: Dict[str, Any]):
    source = _source(params)
    return build(source, prelude=params.get("prelude", True),
                 stage2=params.get("stage2", False))


def _source(params: Dict[str, Any]) -> str:
    """The source as it will be parsed: placeholders filled.

    Spans in an anomaly are offsets into *this* text, which differs
    from what the caller sent only where a placeholder was longer or
    shorter than its value; ``lova_patch`` takes the same text.
    """
    return substitute(params["source"], [str(a) for a in params.get("args", [])])


def _value_fields(value: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"value": format_value(value)}
    if isinstance(value, str):
        out["value_text"] = value
        out["value_list"] = [ord(ch) for ch in value]
    elif isinstance(value, bool):
        out["value_int"] = int(value)
    elif isinstance(value, int):
        out["value_int"] = value
    elif is_list_value(value):
        items = list_to_python(value)
        if all(isinstance(i, int) for i in items):
            out["value_list"] = items
            if items and all(32 <= i <= 0x10FFFF for i in items):
                out["value_text"] = "".join(chr(i) for i in items)
    return out


def tool_execute(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        source = _source(params)
        tree, _report = _build(params)
    except (CompileError, ValueError, SystemExit) as exc:
        return _failure("compile", exc, params.get("source"))
    allow = [str(a) for a in params.get("allow", [])]
    try:
        granted = parse_allow(allow)
        send_to, listen_on = parse_net_allow(allow)
    except ValueError as exc:
        return _failure("grant", exc)
    stdin_text = params.get("stdin") or ""

    mode = str(params.get("native", "auto"))
    if mode != "off":
        answer = _execute_native(params, tree, source, granted, stdin_text, mode)
        if answer is not None:
            return answer

    runtime = Runtime(
        max_steps=int(params.get("max_steps", CLI_MAX_STEPS)),
        max_call_depth=int(params.get("max_depth", CLI_MAX_DEPTH)),
        granted=granted, net_send_to=send_to, net_listen_on=listen_on,
        input_lines=stdin_text.splitlines(keepends=True) if stdin_text else [],
    )
    try:
        value = evaluate(tree, runtime)
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        name_anomaly(getattr(exc, "anomaly", None), getattr(tree, "symbols", None))
        result = _failure("run", exc, source)
        result["output"] = runtime.written()
        result["steps"] = runtime.steps
        result["runtime"] = "python"
        return result
    return {
        "ok": True,
        **_value_fields(value),
        "output": runtime.written(),
        "steps": runtime.steps,
        "surprise_events": len(runtime.surprise.events),
        "caught": _jsonable(runtime.caught),
        "runtime": "python",
    }


def _execute_native(params: Dict[str, Any], tree: Any, source: str,
                    granted: int, stdin_text: str,
                    mode: str) -> Optional[Dict[str, Any]]:
    """`lova_execute` on a native runtime, or ``None`` for "Python's".

    A trap comes back as the trap class the Python runtime would have
    raised, carrying the native anomaly with its span already recovered
    from the tree -- so `_failure` fills `excerpt`, `line` and `col` from
    the source exactly as it does for a Python trap.
    """
    from core.native import NativeUnavailable, NativeUnsupported, choose

    try:
        # Shared: one process for the life of the server, because a host
        # asks this tool once per attempt and starting a binary each
        # time is what the persistent protocol exists to avoid.
        native = choose(tree, mode, shared=True)
    except (NativeUnavailable, NativeUnsupported) as exc:
        return {"ok": False, "stage": "native", "runtime": "native",
                "anomaly": {"kind": "error", "message": str(exc)}}
    if native is None:
        return None
    try:
        result = native.run(
            tree, stdin=stdin_text, allow=granted,
            max_steps=int(params.get("max_steps", CLI_MAX_STEPS)),
            max_call_depth=int(params.get("max_depth", CLI_MAX_DEPTH)))
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        name_anomaly(getattr(exc, "anomaly", None), getattr(tree, "symbols", None))
        failure = _failure("run", exc, source)
        failure["output"] = getattr(exc, "stdout", "")
        failure["steps"] = getattr(exc, "steps", 0)
        failure["runtime"] = "native"
        return failure
    except (NativeUnavailable, NativeUnsupported) as exc:
        if mode == "on":
            return {"ok": False, "stage": "native", "runtime": "native",
                    "anomaly": {"kind": "error", "message": str(exc)}}
        return None
    out = _printed_value_fields(result.value_text)
    out.update({
        "ok": True,
        "output": result.stdout,
        "steps": result.steps,
        "runtime": "native",
    })
    return out


_PRINTED_INT = re.compile(r"-?\d+\Z")
_PRINTED_INT_LIST = re.compile(r"\((-?\d+(?: -?\d+)*)?\)(?:  \".*)?\Z", re.S)
_TEXT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _printed_value_fields(text: str) -> Dict[str, Any]:
    """`_value_fields` read off the printed form the native runtime returns.

    The protocol carries the value as `format_value` prints it, and on
    the three shapes the Python path types -- an integer, a text, a flat
    list of integers -- that printing is one-to-one: a text is
    `quote_text`, whose four escapes are undone here; a list of integers
    is its elements in parentheses, with the text they spell after two
    spaces when they are all codepoints.  Anything else (a nested list,
    a map, a record, a closure) keeps only `value`, as the Python path
    does.  Nothing is guessed: a printed form that does not match one
    of the three exactly is left as it is.
    """
    out: Dict[str, Any] = {"value": text}
    if _PRINTED_INT.match(text):
        out["value_int"] = int(text)
        return out
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        body, chars, i = text[1:-1], [], 0
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body) and body[i + 1] in _TEXT_ESCAPES:
                chars.append(_TEXT_ESCAPES[body[i + 1]])
                i += 2
            else:
                chars.append(ch)
                i += 1
        value = "".join(chars)
        out["value_text"] = value
        out["value_list"] = [ord(ch) for ch in value]
        return out
    m = _PRINTED_INT_LIST.match(text)
    if m:
        items = [int(w) for w in m.group(1).split()] if m.group(1) else []
        out["value_list"] = items
        if items and all(32 <= i <= 0x10FFFF for i in items):
            try:
                out["value_text"] = "".join(chr(i) for i in items)
            except ValueError:
                pass
        return out
    return out


def tool_patch(params: Dict[str, Any]) -> Dict[str, Any]:
    """Replace one span of the source and say whether the result compiles.

    The loop an AI runs: execute, read the anomaly's span, patch that
    span, execute again.  A patch costs the size of the fix, not the
    size of the program (spec/ai-convenience.md, section 4).
    """
    source = str(params["source"])
    span = params.get("span")
    if span is None and params.get("def") is not None and params.get("find") is not None:
        # Exp 28: a correct fault line still cost a whole read when its
        # excerpt occurred four times in the program and once in the def.
        from core.query import find_in_def
        found = find_in_def(_source(params), str(params["def"]), str(params["find"]))
        if not found["ok"]:
            return {"ok": False, "stage": "patch", "anomaly": {"kind": "error", "message": found["message"]}}
        span = found["span"]
        source = _source(params)
    if span is None:
        span = [params.get("start"), params.get("end")]
    try:
        start, end = int(span[0]), int(span[1])
    except (TypeError, ValueError, IndexError):
        return {"ok": False, "stage": "patch",
                "anomaly": {"kind": "error", "message": "span must be [start, end] offsets"}}
    # Q127: a span is an offset into the expanded text.  In the
    # program's own text it maps back to the source the caller sent;
    # inside an included library there is nothing here to patch.
    from core.surface import expansion
    exp = expansion(source)
    if not exp.plain:
        a, b = exp.to_original(start), exp.to_original(max(start, end - 1))
        if a is None or b is None:
            origin = exp.where(start)[0] or exp.where(max(start, end - 1))[0]
            return {"ok": False, "stage": "patch",
                    "anomaly": {"kind": "error",
                                "message": f"span [{start}, {end}] is inside the included "
                                           f"library {origin}; patch that file, not this source"}}
        start, end = a, b + 1 if end > start else a
    if not 0 <= start <= end <= len(source):
        return {"ok": False, "stage": "patch",
                "anomaly": {"kind": "error",
                            "message": f"span [{start}, {end}] is outside the source (length {len(source)})"}}
    replacement = str(params.get("replacement", ""))
    patched = source[:start] + replacement + source[end:]
    result: Dict[str, Any] = {"ok": True, "source": patched,
                              "replaced": source[start:end],
                              "span": [start, start + len(replacement)]}
    try:
        _build({**params, "source": patched})
    except (CompileError, ValueError, SystemExit) as exc:
        failure = _failure("compile", exc, patched)
        failure["source"] = patched
        return failure
    return result


def tool_check(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run the program's own examples (M26)."""
    from core.examples import check
    try:
        source = _source(params)
        allow = [str(a) for a in params.get("allow", [])]
        results = check(source, prelude=params.get("prelude", True),
                        granted=parse_allow(allow),
                        max_steps=int(params.get("max_steps", CLI_MAX_STEPS)),
                        max_call_depth=int(params.get("max_depth", CLI_MAX_DEPTH)))
    except (CompileError, ValueError, SystemExit) as exc:
        return _failure("compile", exc, params.get("source"))
    passed = sum(1 for r in results if r["passed"])
    out = {"ok": passed == len(results), "passed": passed, "total": len(results),
           "examples": _jsonable(results)}
    if params.get("strength") and passed == len(results):
        from core.strength import strength, summary
        try:
            report = strength(source, prelude=params.get("prelude", True),
                              granted=parse_allow(allow),
                              max_steps=int(params.get("max_steps", CLI_MAX_STEPS)),
                              max_call_depth=int(params.get("max_depth", CLI_MAX_DEPTH)),
                              budget_s=float(params.get("strength_budget", 20.0)),
                              only=params.get("only") or None)
        except (CompileError, ValueError, SystemExit) as exc:
            return _failure("compile", exc, params.get("source"))
        out["strength"] = _jsonable(report)
        out["strength_text"] = summary(report)
    return out


def tool_static_analyze(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        tree, report = _build(params)
    except (CompileError, ValueError, SystemExit) as exc:
        return _failure("compile", exc, params.get("source"))
    analysis = static_analyze(tree)
    data = encode(tree)
    return {
        "ok": True,
        "analysis": _jsonable(asdict(analysis)),
        "report": None if report is None else {
            "passes": list(report.passes),
            "original_nodes": report.original_nodes,
            "compiled_nodes": report.compiled_nodes,
            "dropped_bindings": report.dropped_bindings,
            "warnings": _warnings(report, tree, params.get("source")),
        },
        "compiled": pretty(tree),
        "stage2": surface2.render(tree),
        "bytes": data.hex(),
        "byte_count": len(data),
    }


def _warnings(report: Any, tree: Any, source: Any) -> List[str]:
    """The lint pass's lines (M32), spelled as the CLI spells them."""
    from core.cli import name_warnings
    return name_warnings(getattr(report, "warnings", ()), getattr(tree, "symbols", None),
                         source if isinstance(source, str) else None)


def _walk_prefix(params: Dict[str, Any]) -> GenState:
    """The generation state after a partial program's bytes or tokens."""
    top = _TOP_TYPES[params.get("top_type", "Value")]
    state = GenState.fresh(top)
    if "bytes" in params and params["bytes"] is not None:
        data = bytes.fromhex(str(params["bytes"]).replace(" ", ""))
        pos = 0
        while pos < len(data):
            op = data[pos]
            if op == LIT_INT:
                if pos + 1 >= len(data):
                    raise ValueError("literal: missing length byte")
                length = data[pos + 1]
                if pos + 2 + length > len(data):
                    raise ValueError("literal: truncated payload")
                payload = int.from_bytes(data[pos + 2:pos + 2 + length], "big", signed=True)
                state = state.step(LIT_INT, payload)
                pos += 2 + length
            else:
                state = state.step(op)
                pos += 1
        return state
    for item in params.get("tokens", []) or []:
        if isinstance(item, list):
            state = state.step(int(item[0]), int(item[1]))
        else:
            state = state.step(int(item))
    return state


def tool_valid_next(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        state = _walk_prefix(params)
    except (ValueError, KeyError) as exc:
        return {"ok": False, "stage": "prefix", "anomaly": {"kind": "error", "message": str(exc)}}
    if state.is_complete():
        return {"ok": True, "complete": True, "choices": [], "depth": 0,
                "pending": pending(state)}
    slot = state.stack[-1]
    choices = valid_next_with_stats(state, telemetry=_load_telemetry())
    valid = state.valid_next()
    soonest = cheapest_to_finish(state, valid)
    out: Dict[str, Any] = {
        "ok": True,
        "complete": False,
        "depth": len(state.stack),
        "expects": str(slot.expected_type),
        "parent_op": SIGNATURES[slot.parent_op]["name"] if slot.parent_op is not None else None,
        "literal_role": slot.role,
        "choices": [_jsonable(asdict(c)) for c in choices],
        "finish_soonest": [SIGNATURES[t]["name"] if t != END else "end" for t in sorted(soonest)],
        # Q108.  Four sessions in Exp 24 ignored the alphabet and asked
        # for this instead: which forms are open, what each still owes,
        # and whether the variadic may be closed here.
        "pending": pending(state),
    }
    if slot.role == "ref-name":
        out["names_in_scope"] = state.valid_names()
    if slot.role == "binder":
        out["fresh_name"] = state.fresh_name()
    return out


def tool_emit(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        tree, _report = _build(params)
    except (CompileError, ValueError, SystemExit) as exc:
        return _failure("compile", exc)
    form = params.get("form", "stage2")
    data = encode(tree)
    if form == "stage2":
        text = surface2.render(tree)
    elif form == "sexp":
        text = pretty(tree)
    elif form == "bytes":
        text = data.hex(" ")
    elif form == "int":
        text = str(int.from_bytes(data, "big"))
    else:
        return {"ok": False, "stage": "form",
                "anomaly": {"kind": "error", "message": f"unknown form {form!r}"}}
    return {"ok": True, "form": form, "text": text, "byte_count": len(data)}


def tool_show(params: Dict[str, Any]) -> Dict[str, Any]:
    from core.query import def_text, defs
    source = _source(params)
    try:
        if params.get("def"):
            d = def_text(source, str(params["def"]))
            if d is None:
                return {"ok": False, "anomaly": {"kind": "error",
                        "message": f"no def named {params['def']!r}; the defs are "
                                   + ", ".join(x["name"] for x in defs(source))}}
            return {"ok": True, **d}
        return {"ok": True, "defs": defs(source)}
    except (ValueError, SystemExit) as exc:
        return _failure("parse", exc, source)


def tool_scope(params: Dict[str, Any]) -> Dict[str, Any]:
    from core.query import scope_at
    source = _source(params)
    try:
        return {"ok": True, **scope_at(source, int(params["offset"]))}
    except (ValueError, SystemExit) as exc:
        return _failure("parse", exc, source)


def tool_callers(params: Dict[str, Any]) -> Dict[str, Any]:
    from core.query import callees, callers
    source = _source(params)
    try:
        name = str(params["name"])
        return {"ok": True, "name": name, "callers": callers(source, name), "callees": callees(source, name)}
    except (ValueError, SystemExit) as exc:
        return _failure("parse", exc, source)


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "lova_show": tool_show,
    "lova_scope": tool_scope,
    "lova_callers": tool_callers,
    "lova_patch": tool_patch,
    "lova_check": tool_check,
    "lova_execute": tool_execute,
    "lova_static_analyze": tool_static_analyze,
    "lova_valid_next": tool_valid_next,
    "lova_emit": tool_emit,
}


# --- JSON-RPC ---------------------------------------------------------------

def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def handle(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Answer one JSON-RPC request; None for a notification."""
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if request_id is None:
        return None                     # a notification: nothing to say
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return _error(request_id, -32602, f"unknown tool {name!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "arguments must be an object")
        try:
            result = handler(arguments)
        except Exception as exc:          # a tool must answer, not crash the server
            result = {"ok": False, "stage": "tool",
                      "anomaly": {"kind": "error", "message": f"{type(exc).__name__}: {exc}"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=1)}],
            "isError": not result.get("ok", True),
        }}
    return _error(request_id, -32601, f"unknown method {method!r}")


def serve(stdin: Any = None, stdout: Any = None) -> None:
    """Read requests line by line until end of input; answer each."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response: Optional[Dict[str, Any]] = _error(None, -32700, "parse error")
        else:
            response = handle(request) if isinstance(request, dict) else _error(
                None, -32600, "a request is an object")
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main() -> int:
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
