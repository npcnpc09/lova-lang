"""``lova`` -- run, inspect and explore LOVA programs.

Until M11 there was no way to run a ``.lova`` file. Every program in
``apps/`` shipped with a hand-written Python driver whose job was to
read the file, substitute an input, call the compiler, call the
evaluator and format the result — five programs, five drivers, the same
forty lines each. A language you cannot invoke is a library.

    python -m core.cli run apps/palindrome.lova racecar
    python -m core.cli repl
    python -m core.cli emit apps/is_prime.lova --stage2
    python -m core.cli analyze apps/collatz.lova

The result of a program goes to **stderr** as ``=> value``, so what the
program itself writes with ``stdout`` is the only thing on stdout and
can be piped. Traps and compile errors print their structured anomaly —
the same ``kind`` / ``detail`` / ``repair_hint`` an agent would read —
and exit non-zero.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, Any, List, Optional

from core import surface2
from core.compiler import CompileError, compile as lova_compile
from core.conservation import BudgetTrap, DeltaTrap
from core.observability import static_analyze
from core.runtime import (
    Cons, NIL_VALUE, Runtime, evaluate, is_list_value, is_map_value,
    is_population_value, is_program_value, list_to_python,
)
from core.surface import parse, parse_with_prelude, pretty
from core.tokens import ALL_CAPABILITIES, CAPABILITY_BITS, encode


CLI_MAX_STEPS = 20_000_000
CLI_MAX_DEPTH = 10_000

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_TRAP = 2


# --- reading -----------------------------------------------------------------

def read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def substitute(source: str, args: List[str]) -> str:
    """Fill ``{name}`` placeholders from the command line.

    ``apps/`` programs carry placeholders their drivers used to fill.
    An argument that is not an integer is quoted as a string literal,
    which is how ``palindrome.lova racecar`` works.

    An argument ``name=value`` fills the placeholder it names (M23,
    Q81); the rest fill the remaining placeholders in the order of
    their first appearance in the code -- which a reader cannot see,
    so a program that takes more than one is best read with its
    arguments declared first, or run with them named.
    """
    import re

    # Names are collected from code only: a comment that mentions
    # `{n}` must not decide the argument order (M22).
    code = re.sub(r";[^\n]*", "", source)
    names: List[str] = []
    for match in re.finditer(r"\{(\w+)\}", code):
        if match.group(1) not in names:
            names.append(match.group(1))
    if not names:
        return source
    named: Dict[str, str] = {}
    positional: List[str] = []
    for arg in args:
        key, sep, value = arg.partition("=")
        if sep and key in names and key not in named:
            named[key] = value
        else:
            positional.append(arg)
    unnamed = [n for n in names if n not in named]
    if len(positional) < len(unnamed):
        raise SystemExit(
            f"program expects {len(names)} input(s) {names}, got "
            f"{len(named) + len(positional)}; missing "
            f"{unnamed[len(positional):]} (give them as name=value)"
        )
    filled = list(named.items()) + list(zip(unnamed, positional))
    out = source
    for name, value in filled:
        try:
            int(value, 0)
            literal = value
        except ValueError:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            literal = f'"{escaped}"'
        out = out.replace("{" + name + "}", literal)
    return out


def build(source: str, *, prelude: bool = True, stage2: bool = False,
          do_compile: bool = True):
    """Source text -> (tree, report or None)."""
    if stage2:
        tree = surface2.parse(source.strip())
    elif prelude:
        tree = parse_with_prelude(source)
    else:
        tree = parse(source)
    if not do_compile:
        return tree, None
    symbols = getattr(tree, "symbols", None)
    try:
        compiled, report = lova_compile(tree)
    except CompileError as exc:
        name_anomaly(exc.anomaly, symbols)
        raise
    compiled.symbols = symbols
    return compiled, report


def name_anomaly(anomaly: Any, symbols: Any) -> None:
    """Add the surface spelling of a name the anomaly mentions (Q79).

    The anomaly names an integer, because the integer is the name; a
    person reading the report wants the word they wrote.
    """
    if symbols is None or not isinstance(anomaly, dict):
        return
    detail = anomaly.get("detail")
    if not isinstance(detail, dict) or "name_id" not in detail:
        return
    name = symbols.name_of(detail["name_id"])
    if name is not None:
        detail["name"] = name


# --- printing ----------------------------------------------------------------

def format_value(value: Any) -> str:
    """A value as a human would want it in a terminal.

    Lists print as lists, and as text too when every element is a
    plausible codepoint — a string is a list of codepoints, so the
    reader deserves to be told which one they are looking at.
    """
    if isinstance(value, str):
        from core.surface import quote_text
        return quote_text(value)
    if is_population_value(value):
        return (f"#<population n={len(value.variants)} "
                f"gen={value.generation}>")
    if is_map_value(value):
        shown = " ".join(
            f"{format_value(k)}: {format_value(v)}"
            for k, v in list(value.entries.values())[:8])
        more = "" if len(value.entries) <= 8 else " ..."
        return f"#<map n={len(value.entries)} {{{shown}{more}}}>"
    if is_program_value(value):
        uid = getattr(value, "uid", None)
        tag = f" uid={uid}" if uid else ""
        return f"#<program{tag} {pretty(value)}>"
    if is_list_value(value):
        items = list_to_python(value)
        shown = "(" + " ".join(
            format_value(i) if not isinstance(i, int) else str(i) for i in items
        ) + ")"
        if items and all(isinstance(i, int) and 32 <= i <= 0x10FFFF
                         for i in items):
            try:
                return f'{shown}  "{"".join(chr(i) for i in items)}"'
            except ValueError:
                return shown
        return shown
    return repr(value) if not isinstance(value, int) else str(value)


def parse_allow(values: Optional[List[str]]) -> int:
    """``--allow fs-read,clock`` (repeatable; ``all``) to a capability mask.

    What the host grants this run.  A program still has to declare what
    it uses in a `boundary`; the grant is the other half of the
    contract, and nothing is granted unless asked (M19).  The network
    is granted by place -- ``net=host:port`` to send there, ``net=:port``
    to listen there (M21) -- and ``all`` does not include it, because a
    network grant without a place is not a grant.
    """
    mask = 0
    for value in values or ():
        for name in value.replace(",", " ").split():
            if name == "all":
                mask |= ALL_CAPABILITIES
            elif name == "net":
                raise ValueError(
                    "--allow: the network is granted by place: "
                    "net=host:port to send there, net=:port to listen")
            elif name in CAPABILITY_BITS:
                mask |= CAPABILITY_BITS[name]
            elif name.startswith("net="):
                mask |= CAPABILITY_BITS["net"]
            else:
                raise ValueError(
                    f"--allow: unknown capability {name!r}; known: "
                    + ", ".join(CAPABILITY_BITS) + ", all, net=host:port, net=:port"
                )
    return mask


def parse_net_allow(values: Optional[List[str]]):
    """The places ``--allow net=...`` named: (send-to set, listen-on set)."""
    send_to, listen_on = set(), set()
    for value in values or ():
        for name in value.replace(",", " ").split():
            if not name.startswith("net="):
                continue
            place = name[len("net="):]
            if place == "*":
                send_to.add("*")
                continue
            host, sep, port = place.rpartition(":")
            if not sep or not port.isdigit():
                raise ValueError(
                    f"--allow: {name!r} is not net=host:port or net=:port")
            if host:
                send_to.add(f"{host}:{int(port)}")
            else:
                listen_on.add(int(port))
    return send_to, listen_on


def describe_span(source: str, span) -> str:
    """``line:col-line:col`` and the text of the span (M24)."""
    from core.surface import line_col
    start, end = span
    l1, c1 = line_col(source, start)
    l2, c2 = line_col(source, max(start, end - 1))
    excerpt = source[start:end]
    if len(excerpt) > 80:
        excerpt = excerpt[:77] + "..."
    where = f"{l1}:{c1}" if l1 == l2 else f"{l1}:{c1}-{l2}:{c2}"
    return f"{where}  {excerpt}"


def report_error(exc: Exception, source: Optional[str] = None) -> int:
    """Print a structured anomaly, or a plain message, and pick an exit code."""
    anomaly = getattr(exc, "anomaly", None)
    if anomaly is None:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"{anomaly['kind']}:", file=sys.stderr)
    if source is not None and anomaly.get("span"):
        print(f"  at: {describe_span(source, anomaly['span'])}", file=sys.stderr)
    for key in ("detail", "offending_op_name", "position_path",
                "valid_alternatives", "body_offender"):
        value = anomaly.get(key)
        if not value:
            continue
        if key == "position_path" and len(value) > 12:
            # A deep recursion trap carries a path per frame; printing
            # two hundred of them buries the repair hint underneath.
            head = ", ".join(str(v) for v in value[:6])
            tail = ", ".join(str(v) for v in value[-3:])
            value = f"({head}, ... {len(value) - 9} more ..., {tail})"
        print(f"  {key}: {value}", file=sys.stderr)
    if anomaly.get("repair_hint"):
        print(f"  repair: {anomaly['repair_hint']}", file=sys.stderr)
    return EXIT_TRAP


# --- commands ----------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    source = substitute(read_source(args.file), args.args)
    try:
        tree, _report = build(source, prelude=not args.no_prelude,
                              stage2=args.stage2,
                              do_compile=not args.no_compile)
    except (CompileError, ValueError) as exc:
        return report_error(exc, source)

    try:
        granted = parse_allow(args.allow)
        send_to, listen_on = parse_net_allow(args.allow)
    except ValueError as exc:
        return report_error(exc, source)
    runtime = Runtime(out_stream=sys.stdout,
                      input_source=sys.stdin.readline,
                      max_steps=args.max_steps,
                      max_call_depth=args.max_depth,
                      granted=granted,
                      net_send_to=send_to, net_listen_on=listen_on)
    try:
        value = evaluate(tree, runtime)
    except (BudgetTrap, DeltaTrap) as trap:
        sys.stdout.flush()
        return report_error(trap, source)
    except (ValueError, NotImplementedError) as exc:
        sys.stdout.flush()
        name_anomaly(getattr(exc, "anomaly", None), getattr(tree, "symbols", None))
        return report_error(exc, source)

    sys.stdout.flush()
    if not args.quiet:
        print(f"=> {format_value(value)}", file=sys.stderr)
        if args.stats:
            print(f"   [{runtime.steps} steps, "
                  f"{len(runtime.surprise.events)} surprise events]",
                  file=sys.stderr)
    return EXIT_OK


def cmd_emit(args: argparse.Namespace) -> int:
    source = substitute(read_source(args.file), args.args)
    try:
        tree, report = build(source, prelude=not args.no_prelude,
                             stage2=args.stage2,
                             do_compile=not args.no_compile)
    except (CompileError, ValueError) as exc:
        return report_error(exc, source)

    data = encode(tree)
    if args.form == "stage2":
        print(surface2.render(tree))
    elif args.form == "sexp":
        print(pretty(tree))
    elif args.form == "bytes":
        print(data.hex(" "))
    elif args.form == "int":
        print(int.from_bytes(data, "big"))
    if report is not None and args.stats:
        print(f"[{report.original_nodes} -> {report.compiled_nodes} nodes, "
              f"{len(data)} bytes, passes {', '.join(report.passes)}, "
              f"{report.dropped_bindings} bindings dropped]", file=sys.stderr)
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    """Run the program's own examples (M26)."""
    from core.examples import check, summary
    source = substitute(read_source(args.file), args.args)
    try:
        granted = parse_allow(args.allow)
    except ValueError as exc:
        return report_error(exc)
    try:
        results = check(source, prelude=not args.no_prelude, granted=granted,
                        max_steps=args.max_steps, max_call_depth=args.max_depth)
    except (CompileError, ValueError) as exc:
        return report_error(exc, source)
    if not results:
        print("  no examples: write (example expr expected) beside the defs", file=sys.stderr)
        return EXIT_OK
    print(summary(results))
    return EXIT_OK if all(r["passed"] for r in results) else EXIT_TRAP


def cmd_analyze(args: argparse.Namespace) -> int:
    source = substitute(read_source(args.file), args.args)
    try:
        tree, _ = build(source, prelude=not args.no_prelude,
                        stage2=args.stage2, do_compile=not args.no_compile)
    except (CompileError, ValueError) as exc:
        return report_error(exc, source)
    print(static_analyze(tree).summary())
    print(f"  bytes:           {len(encode(tree))}")
    print(f"  stage-2:         {surface2.render(tree)[:60]}")
    return EXIT_OK


REPL_BANNER = """LOVA {stage} REPL.  The prelude is loaded.
  :q quit    :d show definitions    :s stage-2 of the last expression
  :b bytes of the last expression   :a static analysis of it
Definitions entered with `def` persist; anything else is evaluated."""


def cmd_repl(args: argparse.Namespace) -> int:
    definitions: List[str] = []
    last: Optional[str] = None
    print(REPL_BANNER.format(stage="stage-2" if args.stage2 else "stage-1"))

    while True:
        try:
            line = input("lova> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return EXIT_OK
        if not line:
            continue
        if line in (":q", ":quit"):
            return EXIT_OK
        if line == ":d":
            print("\n".join(definitions) or "(no definitions yet)")
            continue
        if line in (":s", ":b", ":a") and last is not None:
            try:
                tree, _ = build("\n".join(definitions + [last]),
                                prelude=not args.no_prelude)
            except (CompileError, ValueError) as exc:
                report_error(exc)
                continue
            if line == ":s":
                print(surface2.render(tree))
            elif line == ":b":
                print(encode(tree).hex(" "))
            else:
                print(static_analyze(tree).summary())
            continue

        if line.startswith("(def ") or line.startswith("(defn "):
            # Keep it only if the whole program still compiles with it.
            candidate = definitions + [line]
            try:
                build("\n".join(candidate + ["0"]),
                      prelude=not args.no_prelude)
            except (CompileError, ValueError) as exc:
                report_error(exc)
                continue
            definitions.append(line)
            print("ok")
            continue

        last = line
        try:
            tree, _ = build("\n".join(definitions + [line]),
                            prelude=not args.no_prelude)
        except (CompileError, ValueError) as exc:
            report_error(exc)
            continue
        send_to, listen_on = parse_net_allow(args.allow)
        runtime = Runtime(out_stream=sys.stdout,
                          max_steps=args.max_steps,
                          max_call_depth=args.max_depth,
                          granted=parse_allow(args.allow),
                          net_send_to=send_to, net_listen_on=listen_on)
        try:
            value = evaluate(tree, runtime)
        except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
            report_error(exc)
            continue
        print(format_value(value))
    return EXIT_OK


# --- argument parsing --------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lova", description="Run and inspect LOVA programs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(sub, with_file=True):
        if with_file:
            sub.add_argument("file", help="a .lova file, or - for stdin")
            sub.add_argument("args", nargs="*",
                             help="values for the program's {placeholders}")
        sub.add_argument("--no-prelude", action="store_true",
                         help="do not load lib/prelude.lova")
        sub.add_argument("--no-compile", action="store_true",
                         help="skip the compiler passes")
        sub.add_argument("--stage2", action="store_true",
                         help="read the source as the Stage-2 surface")
        # M22: the CLI runs real programs, so its ceilings are wide; the
        # library defaults (core/runtime.py) stay tight because the
        # generation experiments run thousands of random programs.
        sub.add_argument("--max-steps", type=int, default=CLI_MAX_STEPS)
        sub.add_argument("--max-depth", type=int, default=CLI_MAX_DEPTH)
        sub.add_argument("--allow", action="append", metavar="CAPS",
                         help="grant capabilities: fs-read, fs-write, clock, "
                              "all, net=host:port, net=:port "
                              "(comma-separated, repeatable)")
        return sub

    run = common(subparsers.add_parser("run", help="evaluate a program"))
    run.add_argument("--quiet", action="store_true",
                     help="do not print the result value")
    run.add_argument("--stats", action="store_true",
                     help="report steps and surprise events")
    run.set_defaults(func=cmd_run)

    emit = common(subparsers.add_parser(
        "emit", help="print the program in another form"))
    emit.add_argument("--form", choices=("stage2", "sexp", "bytes", "int"),
                      default="stage2")
    emit.add_argument("--stats", action="store_true")
    emit.set_defaults(func=cmd_emit)

    analyze = common(subparsers.add_parser(
        "analyze", help="what will this program do, without running it"))
    analyze.set_defaults(func=cmd_analyze)

    check = common(subparsers.add_parser(
        "check", help="run the program's own (example expr expected) forms"))
    check.set_defaults(func=cmd_check)

    repl = common(subparsers.add_parser("repl", help="interactive session"),
                  with_file=False)
    repl.set_defaults(func=cmd_repl)

    mcp = subparsers.add_parser(
        "mcp", help="serve LOVA as MCP tools over stdio (for agents)")
    mcp.set_defaults(func=cmd_mcp)

    return parser


def cmd_mcp(args: argparse.Namespace) -> int:
    """Speak the Model Context Protocol on stdin/stdout until EOF (M7)."""
    from core.mcp_server import serve
    serve()
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
