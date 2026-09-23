"""The fault in one line: what an agent reads when a program fails.

Exp 19 measured what a session reads per failure: LOVA 594 characters,
Python 71.  The replay of every logged LOVA failure (tools/brief/) found
where they went: the full anomaly is a JSON object whose fields repeat
each other -- `message` restates `repair_hint`, `detail.message`
restates it again, the step trap's `hot` list is printed twice, `span`
and `line`/`col` both locate, `bound` lists what `Nearest:` already
chose -- and the step trap carries a 700-character paragraph of advice
that is the same on every trap and is already in the language card.
A compile fault also carried the test's inputs, which a compile fault
does not depend on.

`brief` keeps what differs from one fault to the next: the stage, the
kind, where (line:col and the span to patch), the text there, and the
one fact that says what is wrong.  Static advice belongs in the card,
read once; the report carries the facts, read every time.  The full
anomaly stays one argument away (`report: "full"`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

EXCERPT_MAX = 48
HINT_MAX = 160


def _excerpt(text: Any) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= EXCERPT_MAX else s[: EXCERPT_MAX - 3] + "..."


def _where(a: Dict[str, Any]) -> str:
    parts = []
    if a.get("file"):
        parts.append(f"{a['file']}:")
    if a.get("line") is not None:
        parts.append(f"{a['line']}:{a.get('col', 0)}")
    out = "".join(parts)
    span = a.get("span")
    if isinstance(span, (list, tuple)) and len(span) == 2:
        out = f"{out} [{span[0]},{span[1]})".strip()
    if a.get("excerpt") not in (None, ""):
        out = f"{out} `{_excerpt(a['excerpt'])}`".strip()
    return out


def _clip(text: str, n: int = HINT_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 3] + "..."


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?\.)(\s|$)", text)
    return _clip(m.group(1) if m else text)


def _num(n: Any) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n // 1000}k"
    return str(n)


def _hot(detail: Dict[str, Any], n: int = 4) -> str:
    rows = detail.get("hot") or detail.get("calls") or []
    shown = []
    for row in rows[:n]:
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            shown.append(f"{row[0]} {_num(row[1])} ({_num(row[2])} calls)")
        elif isinstance(row, (list, tuple)) and len(row) == 2:
            shown.append(f"{row[0]} {row[1]}")
    more = len(rows) - len(shown)
    if more > 0:
        shown.append(f"+{more} more")
    return ", ".join(shown)


def _what(a: Dict[str, Any]) -> str:
    kind = a.get("kind", "error")
    detail = a.get("detail") if isinstance(a.get("detail"), dict) else {}
    hint = str(a.get("repair_hint") or "")

    if kind == "type-mismatch" and {"at_operator", "produces", "expected"} <= detail.keys():
        return f"`{detail['at_operator']}` gives {detail['produces']}; the slot wants {detail['expected']}"

    if kind == "unbound-ref":
        name = detail.get("name")
        m = re.search(r"Nearest:\s*(.+?)\.?$", hint)
        if name and hint.startswith(f"`{name}` is not defined.") and m:
            return f"`{name}` is not defined; nearest: {m.group(1)}"
        if len(hint) <= HINT_MAX:
            return hint

    if kind == "parse-error":
        msg = str(detail.get("message") or hint or a.get("message") or "")
        return re.sub(r"\s+at token \d+", "", msg)

    if kind in ("step-limit-exceeded", "recursion-depth-exceeded"):
        limit = detail.get("limit")
        what = "step budget" if kind == "step-limit-exceeded" else "call-depth limit"
        out = f"{what} of {limit} spent; stopped here, not where the cost is" if limit else f"{what} spent"
        if "needed" in detail and limit:
            # Q141: how far over, measured by running it again uncounted.
            if detail["needed"] is not None:
                out += f"; the run needs {_num(detail['needed'])} steps ({detail['needed'] / limit:.1f}x the budget)"
            else:
                probe = detail.get("probe_limit") or 0
                out += (f"; still running at {_num(probe)} steps ({probe // limit}x the budget): "
                        "non-terminating, or far too costly")
        hot = _hot(detail)
        return f"{out}. steps by function: {hot}" if hot else out

    if kind == "conservation-violated" and "entry" in detail and "exit" in detail:
        out = f"expected {detail['entry']}, got {detail['exit']}"
        return f"{out}; {hint}" if hint and len(hint) <= HINT_MAX else out

    if kind == "signalled" and "code" in detail:
        out = f"signal {detail['code']}"
        return f"{out}; {hint}" if hint else out

    # The general case: the fact (`message`), then the fix (`repair_hint`)
    # when it is short and says something the fact does not.
    msg = str(a.get("message") or "")
    if hint and ";" in msg:
        msg = msg.split(";", 1)[0]          # the fact; the fix is the hint's to give
    parts = [_clip(msg)] if msg else []
    if hint and hint not in msg:
        parts.append(hint if len(hint) <= HINT_MAX else _first_sentence(hint))
    return "; ".join(parts) if parts else kind


def brief(anomaly: Any, stage: Optional[str] = None) -> str:
    """One line: `<stage> <kind> <line:col> [span) `excerpt`: <what>`."""
    if not isinstance(anomaly, dict):
        return f"{stage or 'error'}: {anomaly}"
    stage = stage or anomaly.get("stage")
    head = " ".join(x for x in (stage, anomaly.get("kind", "error"), _where(anomaly)) if x)
    return f"{head}: {_what(anomaly)}"


def brief_examples(examples: List[Dict[str, Any]]) -> List[str]:
    """One line per failing `(example ...)`, with the fault located when found."""
    out = []
    for ex in examples:
        if ex.get("passed"):
            continue
        where = _where({k: ex.get(k) for k in ("line", "col", "span", "excerpt")})
        a = ex.get("anomaly") if isinstance(ex.get("anomaly"), dict) else {}
        if "got" in ex:
            what = f"expected {ex.get('expected')}, got {ex.get('got')}"
        else:
            what = f"{a.get('kind', 'error')}: {_what(a)}" if a else "failed"
        fault = ex.get("fault") if isinstance(ex.get("fault"), dict) else None
        if fault and fault.get("edit"):
            what += f"; {fault['edit']} at {_where(fault)}"
        out.append(f"example {where}: {what}")
    return out


def compact(result: Dict[str, Any]) -> Dict[str, Any]:
    """A tool result as the agent needs it: unchanged on success, one line on failure."""
    if not isinstance(result, dict) or result.get("ok", True):
        return result
    out: Dict[str, Any] = {"ok": False}
    if isinstance(result.get("examples"), list):
        out["passed"] = result.get("passed")
        out["total"] = result.get("total")
        out["faults"] = brief_examples(result["examples"])
        return out
    a = result.get("anomaly")
    out["stage"] = result.get("stage")
    if isinstance(a, dict):
        # Stage and kind as keys, for a host that branches on them; the
        # line carries where and what, and is what a model reads.
        out["kind"] = a.get("kind", "error")
        where = _where(a)
        out["fault"] = f"{where}: {_what(a)}" if where else _what(a)
    else:
        out["fault"] = str(a)
    for key in ("steps", "output", "source"):
        if result.get(key) not in (None, ""):
            out[key] = result[key]
    return out
