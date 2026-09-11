"""Experiment 24 -- linear authoring: emitting the substrate left to right (Q105).

    python experiments/experiment_24_linear.py tasks
    python experiments/experiment_24_linear.py card
    python experiments/experiment_24_linear.py start --session L1 --task c01 [--frontier off]
    python experiments/experiment_24_linear.py emit  --session L1 --tokens "merge 2 3"
    python experiments/experiment_24_linear.py state --session L1
    python experiments/experiment_24_linear.py finish --session L1
    python experiments/experiment_24_linear.py report

Experiment 23 found the three forms equally reliable at size -- and
then found out why: **neither Stage-2 session composed in Stage-2.**
Both built a parenthesised tree first and flattened it, keeping an
external name-to-letter table.  "The stream was a serialisation step,
not an authoring step ... the form gives you no place to stand: there
is no closing bracket to tell you an argument list is done."  So the
substrate was demonstrated as a storage and transport form and left
untested as an authoring one.

This experiment tests it as an authoring one.  A session emits the
program **left to right, one token at a time**, into LOVA's own
generation state machine (`core.generator.GenState`, Axiom 3): every
token is checked against the set of well-typed successors, an
ill-typed or out-of-scope token is refused, and the stream is finished
only when no slot is open.  There is no program text to revise -- what
is emitted is emitted.

Tokens are written by NAME (`merge`, `fold`, `if-surprise`), not by
the Stage-2 symbol, deliberately: Exp 22 already measured what the
dense symbols cost, and this experiment is about the *structure* of the
substrate -- prefix order, positional arguments, no delimiters -- not
about remembering Greek letters.  A number is a literal, `ref` followed
by a number is a reference to that binding, `"..."` is a text, and `;`
closes a variadic.

Two arms, so that the machine's help can be priced:

  --frontier on   (default) after every token the harness prints the
                  set of tokens that may come next, and how many slots
                  are still open.  This is Axiom 3 offered as an
                  authoring interface.
  --frontier off  the harness accepts or refuses, and says nothing
                  else.  The writer must hold the shape alone.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.compiler import CompileError, compile as lova_compile      # noqa: E402
from core.generator import GenState                                  # noqa: E402
from core.runtime import Runtime, evaluate                           # noqa: E402
from core.surface import NAME_TO_TOKEN                               # noqa: E402
from core.tokens import END, LIT_INT, LIT_TEXT, SIGNATURES, decode   # noqa: E402
from core.types import VALUE as TVALUE                               # noqa: E402
from experiments import experiment_22_three_forms as e22             # noqa: E402
from experiments import experiment_23_scale as e23                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results_24"

# Four graded tasks: two one-expression, two needing recursion through a
# `let`-bound self-referencing lambda.  Answers are Exp 22 / Exp 23's.
TASKS: Dict[str, Tuple[str, Any]] = {
    "c01": e22.TASKS["c01"],
    "c04": e22.TASKS["c04"],
    "b04": e23.TASKS["b04"],
    "b01": e23.TASKS["b01"],
}
PROMPTS: Dict[str, str] = {
    "c01": e22.PROMPTS["c01"],
    "c04": e22.PROMPTS["c04"],
    "b04": e23.PROMPTS["b04"],
    "b01": e23.PROMPTS["b01"],
}
MAX_STEPS = 60_000_000


# --- tokens -----------------------------------------------------------------

def parse_token(word: str) -> Tuple[int, Optional[Any]]:
    """One written token -> (byte, payload)."""
    if word == ";":
        return END, None
    if word.startswith('"') and word.endswith('"') and len(word) >= 2:
        return LIT_TEXT, word[1:-1]
    if word.startswith("&"):
        raise ValueError("a reference is two tokens: `ref` then the number, e.g. `ref 0`")
    try:
        return LIT_INT, int(word)
    except ValueError:
        pass
    tok = NAME_TO_TOKEN.get(word)
    if tok is None:
        raise ValueError(f"{word!r} is not an operator name, a number, a \"text\" or `;`")
    return tok, None


def token_name(tok: int) -> str:
    return SIGNATURES[tok]["name"]


def to_bytes(stream: List[Tuple[int, Optional[Any]]]) -> bytes:
    buf = bytearray()
    for tok, payload in stream:
        buf.append(tok)
        if tok == LIT_INT:
            v = int(payload)
            n = max(1, (v.bit_length() + 1 + 7) // 8)
            buf.append(n)
            buf.extend(v.to_bytes(n, "big", signed=True))
        elif tok == LIT_TEXT:
            data = str(payload).encode("utf-8")
            buf.extend(len(data).to_bytes(2, "big"))
            buf.extend(data)
    return bytes(buf)


def replay(stream: List[Tuple[int, Optional[Any]]]) -> GenState:
    st = GenState.fresh(TVALUE)
    for tok, payload in stream:
        st = st.step(tok, payload) if tok == LIT_INT else st.step(tok)
    return st


LIST_FRONTIER_UPTO = 30


def frontier_names(st: GenState) -> List[str]:
    if st.is_complete():
        return []
    return sorted(token_name(t) for t in st.valid_next(generate=False))


def frontier_line(st: GenState) -> str:
    """What may come next.

    At a Value slot nearly the whole table qualifies, and printing eighty
    names every turn is noise, not help -- so the count is always given
    and the names only when the slot actually narrows the choice.  How
    often it narrows is itself part of what this experiment measures.
    """
    names = frontier_names(st)
    if len(names) <= LIST_FRONTIER_UPTO:
        return f"  may come next ({len(names)}): {', '.join(names)}"
    return (f"  may come next: {len(names)} tokens -- nearly anything that "
            f"yields a value, so the slot is not constraining you here")


# --- session state ----------------------------------------------------------

def _path(session: str) -> Path:
    p = RESULTS / session / "session.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load(session: str) -> Dict[str, Any]:
    p = _path(session)
    if not p.exists():
        raise SystemExit(f"session {session!r} has not started a task; use `start`")
    return json.loads(p.read_text(encoding="utf-8"))


def _save(session: str, data: Dict[str, Any]) -> None:
    _path(session).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _log(session: str, record: Dict[str, Any]) -> None:
    p = RESULTS / session / "log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _stream(data: Dict[str, Any]) -> List[Tuple[int, Optional[Any]]]:
    return [(t, p) for t, p in data["stream"]]


def _written(stream) -> str:
    out = []
    for tok, payload in stream:
        if tok == LIT_INT:
            out.append(str(payload))
        elif tok == LIT_TEXT:
            out.append('"' + str(payload) + '"')
        elif tok == END:
            out.append(";")
        else:
            out.append(token_name(tok))
    return " ".join(out)


# --- commands ---------------------------------------------------------------

def cmd_tasks(args) -> int:
    for tid in TASKS:
        print(f"{tid}: {PROMPTS[tid]}")
    return 0


def cmd_card(args) -> int:
    from core.surface2 import REF_SYMBOLS  # noqa: F401  (not used; names form only)
    rows = []
    for n in e22._SUB_NAMES() + ["let", "apply"]:
        tok = NAME_TO_TOKEN.get(n)
        if tok is None:
            continue
        rows.append(f"  {n:12s} arity {SIGNATURES[tok]['arity']}")
    table = "\n".join(rows)
    print(f"""# LOVA, emitted one token at a time

You write a program as a stream of tokens, left to right, and the
machine checks each one as it arrives.  There are no parentheses.  An
operator is followed by exactly as many arguments as its arity, each of
which is itself a token stream.  You cannot go back: what is accepted
stays.  A token is refused if it would not be well typed there, or if a
reference names nothing in scope; a refusal costs nothing but the turn.

How to write a token:

  merge, fold, if-surprise ...   an operator, by name (table below)
  7   -1   1048576               an integer literal
  ref 0                          a reference: the word `ref`, then the
                                 number of the binding you mean
  "abc"                          a text literal
  ;                              closes a variadic operator (`apply`)

Binding and naming.  `lambda` takes a NUMBER and then a body: `lambda 0
<body>` binds number 0 as that lambda's parameter, referred to inside
the body as `ref 0`.  `let` takes a number, a value and a body: `let 0
<value> <body>` binds number 0 in the body AND in the value, so a
function bound by `let` may call itself -- that is how you write
recursion.  Number each new binding 0, 1, 2, ... as you introduce it.
Call a function with `apply`: `apply <fn> <arg> ;` -- it is variadic, so
it is closed by `;`, and a curried two-argument call is `apply <fn> <a>
<b> ;`.

{e22._OPERATORS_SUB}

The operators, with arity:

{table}

The tasks:

{chr(10).join(f"  {tid}: {PROMPTS[tid]}" for tid in TASKS)}
""")
    return 0


def cmd_start(args) -> int:
    data = {"task": args.task, "stream": [], "frontier": args.frontier == "on",
            "emits": 0, "refused": 0, "started": time.time()}
    _save(args.session, data)
    st = replay([])
    print(f"[{args.task}] {PROMPTS[args.task]}")
    print(f"  open slots: {len(st.stack)}")
    if data["frontier"]:
        print(frontier_line(st))
    return 0


def cmd_emit(args) -> int:
    data = _load(args.session)
    stream = _stream(data)
    st = replay(stream)
    words = args.tokens.split()
    accepted = 0
    refusal = None
    for word in words:
        try:
            tok, payload = parse_token(word)
        except ValueError as exc:
            refusal = (word, str(exc))
            break
        if st.is_complete():
            refusal = (word, "the program is already complete; use `finish`")
            break
        try:
            st = st.step(tok, payload) if tok == LIT_INT else st.step(tok)
        except ValueError as exc:
            msg = str(exc)
            if "not in valid_next" in msg:
                msg = "not well typed here"
            refusal = (word, msg)
            break
        stream.append((tok, payload))
        accepted += 1
    data["stream"] = [[t, p] for t, p in stream]
    data["emits"] += len(words)
    if refusal:
        data["refused"] += 1
    _save(args.session, data)
    _log(args.session, {"task": data["task"], "tokens": args.tokens, "accepted": accepted,
                        "refused": bool(refusal), "reason": refusal[1] if refusal else None,
                        "time": time.time()})
    print(f"  accepted {accepted} of {len(words)}")
    if refusal:
        print(f"  REFUSED at {refusal[0]!r}: {refusal[1]}")
    print(f"  stream: {_written(stream)}")
    if data["frontier"]:
        if st.is_complete():
            print("  the program is complete; use `finish`")
        else:
            print(f"  open slots: {len(st.stack)}")
            print(frontier_line(st))
    return 0 if not refusal else 1


def cmd_state(args) -> int:
    data = _load(args.session)
    st = replay(_stream(data))
    print(f"  task: {data['task']}")
    print(f"  stream: {_written(_stream(data))}")
    if data["frontier"]:
        if st.is_complete():
            print("  complete")
        else:
            print(f"  open slots: {len(st.stack)}")
            print(frontier_line(st))
    return 0


def cmd_finish(args) -> int:
    data = _load(args.session)
    stream = _stream(data)
    st = replay(stream)
    if not st.is_complete():
        print(f"  not complete: {len(st.stack)} slot(s) still open")
        return 2
    want = TASKS[data["task"]][1]
    try:
        tree = decode(to_bytes(stream))
        compiled, _ = lova_compile(tree)
        got = evaluate(compiled, Runtime(max_steps=MAX_STEPS))
    except (CompileError, ValueError, NotImplementedError) as exc:
        print(f"  FAIL at run: {type(exc).__name__}: {exc}")
        _log(args.session, {"task": data["task"], "final": True, "passed": False,
                            "detail": str(exc)[:200], "time": time.time()})
        return 1
    ok = got == want
    n = len(stream)
    print(f"  {'PASS' if ok else 'FAIL'}: got {got}, want {want}  "
          f"({n} tokens, {data['emits']} written, {data['refused']} refusals)")
    _log(args.session, {"task": data["task"], "final": True, "passed": ok, "got": str(got),
                        "tokens": n, "written": data["emits"], "refusals": data["refused"],
                        "frontier": data["frontier"], "time": time.time()})
    return 0 if ok else 1


def cmd_report(args) -> int:
    if not RESULTS.exists():
        print("no sessions"); return 0
    print(f"  {'session':8s} {'arm':8s} {'task':5s} {'pass':5s} {'tokens':>6s} {'written':>7s} {'refusals':>8s}")
    for sess in sorted(p.name for p in RESULTS.iterdir() if p.is_dir()):
        log = RESULTS / sess / "log.jsonl"
        if not log.exists():
            continue
        for line in log.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not r.get("final"):
                continue
            arm = "frontier" if r.get("frontier") else "blind"
            print(f"  {sess:8s} {arm:8s} {r['task']:5s} {'yes' if r['passed'] else 'no':5s} "
                  f"{r.get('tokens',0):6d} {r.get('written',0):7d} {r.get('refusals',0):8d}")
    return 0


def cmd_dry_run(args) -> int:
    """Emit each canonical solution token by token; every one must be accepted."""
    from core.surface import parse
    from core.tokens import encode
    ok = True
    for tid, (src, want) in TASKS.items():
        data = encode(parse(src))
        tree = decode(data)
        # walk the byte stream into (token, payload) pairs via decode/encode round trip
        stream: List[Tuple[int, Optional[Any]]] = []
        i = 0
        while i < len(data):
            b = data[i]
            if b == LIT_INT:
                n = data[i + 1]
                stream.append((b, int.from_bytes(data[i + 2:i + 2 + n], "big", signed=True)))
                i += 2 + n
            elif b == LIT_TEXT:
                n = int.from_bytes(data[i + 1:i + 3], "big")
                stream.append((b, data[i + 3:i + 3 + n].decode("utf-8")))
                i += 3 + n
            else:
                stream.append((b, None)); i += 1
        try:
            st = replay(stream)
            complete = st.is_complete()
        except ValueError as exc:
            print(f"  {tid}: REFUSED -- {exc}"); ok = False; continue
        got = evaluate(lova_compile(decode(to_bytes(stream)))[0], Runtime(max_steps=MAX_STEPS))
        good = complete and got == want
        ok = ok and good
        print(f"  {tid}: {'ok' if good else 'FAIL'}  {len(stream)} tokens, value {got}")
    print("  every canonical solution is accepted token by token" if ok else "  PROBLEM above")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tasks"); p.set_defaults(func=cmd_tasks)
    p = sub.add_parser("card"); p.set_defaults(func=cmd_card)
    p = sub.add_parser("start"); p.add_argument("--session", required=True)
    p.add_argument("--task", required=True, choices=list(TASKS))
    p.add_argument("--frontier", default="on", choices=["on", "off"]); p.set_defaults(func=cmd_start)
    p = sub.add_parser("emit"); p.add_argument("--session", required=True)
    p.add_argument("--tokens", required=True); p.set_defaults(func=cmd_emit)
    p = sub.add_parser("state"); p.add_argument("--session", required=True); p.set_defaults(func=cmd_state)
    p = sub.add_parser("finish"); p.add_argument("--session", required=True); p.set_defaults(func=cmd_finish)
    p = sub.add_parser("report"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
