"""Harvest the golden test set a native LOVA runtime is checked against.

    python tools/golden.py                  # every group
    python tools/golden.py --group traps    # one group

Each group becomes ``corpus/golden/<group>.jsonl``, one JSON object per
line.  A record is a complete, self-contained run: the compiled byte
sequence, the limits, the input, and exactly what the Python runtime
produced -- the value as ``core.cli.format_value`` prints it, or the
anomaly, plus the step count.  A port is conformant when, given the
bytes and the limits alone, it reproduces every field.

The bytes are what `core.cli.build` returns -- after ``drop-unused``
and constant folding, with the prelude already inlined -- because that
is the tree the Python runtime actually runs.  ``bytes_uncompiled`` is
the same program before the compiler passes, for a port that wants to
be checked on the unoptimised tree.

Record schema (the fields the task fixes, plus three the harvest owes
the reader):

    id                 "<group>-<n>[-<slug>]"
    source             the LOVA text as run (placeholders filled)
    args               the arguments that filled them (extra)
    prelude            parsed with `parse_with_prelude`?
    bytes              hex of encode(compiled tree)
    bytes_uncompiled   hex of encode(parsed tree)
    stdin              text fed to stdin ("" if none)
    allow              capability mask granted (0 if none)
    max_steps          the step ceiling used
    max_depth          the call-depth ceiling used
    expect             {"value": "..."} or {"anomaly": {...}}
    steps              rt.steps after the run (also when it trapped)
    max_depth_seen     null (not cheaply available)
    hot                the named cost ranking from a step / depth trap
    stdout             what the program wrote (extra)
    deterministic      false when the run reads the world
    reason             why it is not deterministic (extra, else null)

Paths inside a program (``fs-read``) are relative to the repository
root: a conformance run must start there.

Stdlib only.  Nothing under ``core/`` is modified.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cli import format_value, parse_allow, substitute          # noqa: E402
from core.compiler import CompileError                              # noqa: E402
from core.compiler import compile as lova_compile                   # noqa: E402
from core.conservation import BudgetTrap, DeltaTrap                 # noqa: E402
from core.runtime import Runtime, evaluate                          # noqa: E402
from core.surface import parse, parse_with_prelude                  # noqa: E402
from core.tokens import (CLOCK, NET_RECV, NET_SEND, Node, encode)   # noqa: E402

OUT_DIR = ROOT / "corpus" / "golden"
FIXTURES = OUT_DIR / "fixtures"

# The library defaults (core.runtime.MAX_STEPS / MAX_CALL_DEPTH).
DEF_STEPS = Runtime().max_steps
DEF_DEPTH = Runtime().max_call_depth
# What the CLI gives a real program.
CLI_STEPS = 20_000_000
CLI_DEPTH = 10_000

NONDET_OPS = {CLOCK: "clock", NET_SEND: "net-send", NET_RECV: "net-recv"}

skipped: List[Tuple[str, str]] = []


# --- helpers -----------------------------------------------------------------

def jsonable(value: Any) -> Any:
    """Anything, as something `json.dumps` will take."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    return str(value)


def ops_in(node: Any, found: Optional[set] = None) -> set:
    """Every token byte the tree uses."""
    found = set() if found is None else found
    if not isinstance(node, Node):
        return found
    found.add(node.op)
    for arg in node.args:
        ops_in(arg, found)
    return found


def named_hot(detail: Dict[str, Any], symbols: Any) -> Optional[List[Any]]:
    """The step / depth trap's cost ranking with the names spelled.

    ``core.cli.name_anomaly`` does this for a terminal; here it is kept
    beside the anomaly rather than inside it, because a port decoding
    bytes has the name *ids* and not the words.
    """
    calls = detail.get("calls")
    if not calls:
        return None
    out = []
    for entry in calls:
        name_id, steps, count = entry
        name = (symbols.name_of(name_id) if symbols is not None else None)
        out.append([name or f"#{name_id}", steps, count])
    return out


def run_program(tree: Node, *, stdin: str = "", allow: int = 0,
                max_steps: int = DEF_STEPS, max_depth: int = DEF_DEPTH,
                symbols: Any = None) -> Dict[str, Any]:
    """Evaluate a compiled tree and describe what happened."""
    feed = io.StringIO(stdin)
    rt = Runtime(max_steps=max_steps, max_call_depth=max_depth,
                 granted=allow, input_source=feed.readline)
    out: Dict[str, Any] = {}
    try:
        value = evaluate(tree, rt)
        out["expect"] = {"value": format_value(value)}
        out["hot"] = None
    except (BudgetTrap, DeltaTrap, ValueError, NotImplementedError) as exc:
        anomaly = getattr(exc, "anomaly", None)
        if anomaly is None:
            raise
        detail = jsonable(anomaly.get("detail") or {})
        out["expect"] = {"anomaly": {
            "kind": anomaly.get("kind"),
            "offending_op": anomaly.get("offending_op"),
            "offending_op_name": anomaly.get("offending_op_name", ""),
            "position_path": list(anomaly.get("position_path") or ()),
            "detail": detail,
        }}
        out["hot"] = named_hot(detail, symbols)
    out["steps"] = rt.steps
    out["stdout"] = rt.written()
    return out


def make_record(group: str, index: int, slug: str, source: str, *,
                prelude: bool = True, args: Optional[List[str]] = None,
                stdin: str = "", allow: int = 0,
                max_steps: int = DEF_STEPS, max_depth: int = DEF_DEPTH,
                deterministic: Optional[bool] = None,
                reason: Optional[str] = None,
                tree: Optional[Node] = None) -> Optional[Dict[str, Any]]:
    """Compile, run and describe one program.  None when it will not build.

    ``tree`` is for the handful of trap records whose shape no surface
    text can express: the tree is built by hand and ``source`` is a
    note saying so.
    """
    ident = f"{group}-{index:04d}" + (f"-{slug}" if slug else "")
    try:
        # What `core.cli.build` does, with the pre-compiler tree kept:
        # parse (prelude inlined), compile, carry the symbol table.
        if tree is None:
            raw = parse_with_prelude(source) if prelude else parse(source)
            symbols = getattr(raw, "symbols", None)
            uncompiled = encode(raw)
            compiled, _report = lova_compile(raw)
            compiled.symbols = symbols
        else:
            compiled, symbols = tree, None
            uncompiled = encode(tree)
        data = encode(compiled)
    except (CompileError, ValueError, NotImplementedError, RecursionError,
            KeyError, TypeError) as exc:
        skipped.append((ident, f"{type(exc).__name__}: {str(exc)[:120]}"))
        return None

    ops = ops_in(compiled)
    auto = [name for tok, name in NONDET_OPS.items() if tok in ops]
    if deterministic is None:
        deterministic = not auto
        if auto:
            reason = reason or ("reads the world: " + ", ".join(sorted(auto)))

    started = time.time()
    try:
        result = run_program(compiled, stdin=stdin, allow=allow,
                             max_steps=max_steps, max_depth=max_depth,
                             symbols=symbols)
    except (RecursionError, OSError, KeyError, TypeError,
            AttributeError, IndexError, ZeroDivisionError) as exc:
        skipped.append((ident, f"run {type(exc).__name__}: {str(exc)[:120]}"))
        return None
    spent = time.time() - started
    if spent > 5:
        print(f"    [slow] {ident}: {spent:.1f}s, {result['steps']} steps")

    record = {
        "id": ident,
        "source": source,
        "args": list(args or []),
        "prelude": prelude,
        "bytes": data.hex(),
        "bytes_uncompiled": uncompiled.hex(),
        "stdin": stdin,
        "allow": allow,
        "max_steps": max_steps,
        "max_depth": max_depth,
        "expect": result["expect"],
        "steps": result["steps"],
        "max_depth_seen": None,
        "hot": result["hot"],
        "stdout": result["stdout"],
        "deterministic": bool(deterministic),
        "reason": reason,
    }
    return record


# --- group (a): every LOVA program written in the test suite -----------------

def _string_constants(path: Path) -> List[str]:
    """Every string constant in a Python file, concatenations included."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: List[str] = []

    def folded(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = folded(node.left), folded(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    for node in ast.walk(tree):
        text = folded(node)
        if text is not None:
            out.append(text)
    return out


def _looks_like_lova(text: str) -> bool:
    stripped = text.strip()
    if not stripped or "(" not in stripped or ")" not in stripped:
        return False
    if len(stripped) > 60_000:
        return False
    if "%s" in stripped or "%d" in stripped or "{}" in stripped:
        return False
    # A `{name}` placeholder is an argument the harness would have to
    # invent; those programs are skipped by instruction.
    import re
    if re.search(r"\{[A-Za-z_]\w*\}", stripped):
        return False
    return stripped.startswith("(") or stripped.startswith(";")


def group_tests() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set = set()
    index = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        for text in _string_constants(path):
            if not _looks_like_lova(text) or text in seen:
                continue
            seen.add(text)
            try:
                parse_with_prelude(text)
            except Exception:
                continue
            index += 1
            record = make_record("tests", index, path.stem[5:], text)
            if record is not None:
                records.append(record)
    return records


# --- group (b): LOVABench ----------------------------------------------------

def group_lovabench() -> List[Dict[str, Any]]:
    from corpus.tasks import TASKS_V3
    records: List[Dict[str, Any]] = []
    index = 0
    for task in TASKS_V3:
        for inputs, _expected in task.tests:
            index += 1
            source = task.template.format(**inputs)
            args = [f"{k}={v}" for k, v in inputs.items()]
            record = make_record("lovabench", index, task.id, source, args=args)
            if record is not None:
                records.append(record)
    return records


# --- group (c): the card's operator examples ---------------------------------

def group_card() -> List[Dict[str, Any]]:
    from corpus.make_card import OPERATOR_EXAMPLES
    records: List[Dict[str, Any]] = []
    index = 0
    for expr in OPERATOR_EXAMPLES:
        if expr.startswith(";;"):
            continue
        index += 1
        record = make_record("card", index, "", expr, max_steps=200_000)
        if record is not None:
            records.append(record)
    return records


# --- group (d): the apps -----------------------------------------------------

# How `tests/test_apps.py` and `tests/test_stdlib.py` invoke each app.
# ping / pong want the network and are left out; guess reads the clock
# and is kept, flagged.
APPS: List[Dict[str, Any]] = [
    {"file": "apps/is_prime.lova", "args": ["1999"]},
    {"file": "apps/is_prime.lova", "args": ["104729"]},
    {"file": "apps/is_perfect.lova", "args": ["496"]},
    {"file": "apps/is_perfect.lova", "args": ["500"]},
    {"file": "apps/coprime.lova", "args": ["14", "15"]},
    {"file": "apps/collatz.lova", "args": ["27"]},
    {"file": "apps/palindrome.lova", "args": ["racecar"]},
    {"file": "apps/palindrome.lova", "args": ["hello"]},
    {"file": "apps/tictactoe.lova", "args": ["166"], "stdin": "3\n"},
    {"file": "apps/tictactoe.lova", "args": ["163"], "stdin": "2\n"},
    {"file": "apps/tictactoe.lova", "args": ["163"], "stdin": "x\n\n9\n"},
    {"file": "apps/logstats.lova", "args": ["corpus/golden/fixtures/sample.log"],
     "allow": ["fs-read"]},
    {"file": "apps/wordfreq.lova", "args": ["corpus/golden/fixtures/notes.txt", "10"],
     "allow": ["fs-read"]},
    {"file": "apps/sandbox.lova", "args": ["5000"],
     "stdin": ("(merge 1 2)\n"
               "(div 1 0)\n"
               "(apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1)\n"
               "(merge 1\n"
               '(boundary "fs-read" (fs-read "x"))\n'
               "(def sq [n] (mul n n))(sq 12)\n")},
    {"file": "apps/batch.lova", "args": ["300", "2000"]},
    {"file": "apps/repair.lova", "args": ["42", "30", "200"]},
    {"file": "apps/evolve.lova", "args": ["42", "60"]},
    {"file": "apps/tanks.lova", "args": ["7"], "stdin": "f\nw\nd\n\nq\n"},
    {"file": "apps/maze.lova", "args": ["0"], "stdin": "ww\nq\n"},
    {"file": "apps/cube.lova", "args": []},
    {"file": "apps/g2048.lova", "args": ["7"], "stdin": "a\nd\nw\ns\nq\n"},
    {"file": "apps/fleet.lova", "args": ["apps/fleet/sweep.txt"],
     "allow": ["fs-read"]},
    {"file": "apps/fleet.lova", "args": ["apps/fleet/sweep.txt"]},
    {"file": "apps/guess.lova", "args": ["3"], "allow": ["clock"],
     "stdin": "x\n1\n2\n3\n"},
]


def group_apps() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    index = 0
    for spec in APPS:
        path = ROOT / spec["file"]
        if not path.exists():
            skipped.append((spec["file"], "no such file"))
            continue
        raw = path.read_text(encoding="utf-8")
        try:
            source = substitute(raw, list(spec.get("args", [])))
        except SystemExit as exc:
            skipped.append((spec["file"], f"arguments: {exc}"))
            continue
        index += 1
        slug = Path(spec["file"]).stem
        record = make_record(
            "apps", index, slug, source, args=list(spec.get("args", [])),
            stdin=spec.get("stdin", ""),
            allow=parse_allow(spec.get("allow")),
            max_steps=spec.get("max_steps", CLI_STEPS),
            max_depth=CLI_DEPTH)
        if record is not None:
            records.append(record)
    return records


# --- group (e): the libraries ------------------------------------------------

# One program per thing the lib tests check, written as a whole program
# rather than as a Python caller holding a record of closures.  These
# are the large, slow records and the ones a port learns most from.
LIB_PROGRAMS: List[Tuple[str, str, int]] = [
    # lib/fixed.lova -- the fixed-point arithmetic the 3D stands on.
    ("fixed-isqrt", '(use "fixed")\n(map isqrt (list 0 1 4 100 9999 250000 1048576))', 2_000_000),
    ("fixed-sin", '(use "fixed")\n(map sin (range 0 64))', 2_000_000),
    ("fixed-cos", '(use "fixed")\n(map cos (range 0 33))', 2_000_000),
    ("fixed-atan2", '(use "fixed")\n(map (lambda y (atan2 y 1024)) (list -1024 -512 0 512 1024))', 2_000_000),
    # lib/assoc.lova
    ("assoc", '(use "assoc")\n(let al (assoc-put (assoc-put (nil) "a" 10) "b" 20)\n'
              '  (list (assoc-get al "a" 0) (assoc-get al "b" 0) (assoc-get al "c" -1)\n'
              '        (len (assoc-keys al)) (len (assoc-vals al)) (assoc-count al "a")))', 2_000_000),
    # lib/evolution.lova
    ("evolution", '(use "evolution")\n(let p (defpop (lambda g (sub 42 (eval g))) '
                  '(quote (merge 1 2)) (quote (mul 6 7)) (quote (mul 5 5)))\n'
                  '  (list (pool-size p) (best-score p)))', 5_000_000),
    # lib/ray.lova -- the first-person maze.
    ("ray-orbs", '(use "ray")\n(orbs-live (new-game 0))', 5_000_000),
    ("ray-walls", '(use "ray")\n(len (map-pairs walls))', 5_000_000),
    ("ray-view", '(use "ray")\n(len (wall-view (new-game 0) 40 20))', 20_000_000),
    ("ray-frame", '(use "ray")\n(len (map-pairs (frame (new-game 0) 40 20)))', 20_000_000),
    ("ray-step", '(use "ray")\n(let w (step (step (new-game 0) 0) 0) (list (get w px) (get w py)))', 5_000_000),
    # lib/g2048.lova
    ("g2048-new", '(use "g2048")\n(list (biggest (new-game 7)) (moves-left (get (new-game 7) board)))', 5_000_000),
    ("g2048-sweep", '(use "g2048")\n'
                    '(map (lambda d (biggest (move (new-game 7) d))) (range 0 4))', 20_000_000),
    ("g2048-four-twos", '(use "g2048")\n(list (cells-of (get (sweep four-twos 3) b)) (get (sweep four-twos 3) s) (get (sweep four-twos 0) moved))', 5_000_000),
    ("g2048-rows", '(use "g2048")\n(rows (new-game 7))', 5_000_000),
    # lib/tanks.lova
    ("tanks-render", '(use "tanks")\n(render (new-game 7))', 20_000_000),
    ("tanks-steps", '(use "tanks")\n(let w (step (step (step (new-game 7) 0) 4) 1)\n'
                    '  (list (enemies-left w) (status-of w)))', 20_000_000),
    # lib/war.lova -- noise terrain, sun lighting, twelve soldiers.
    ("war-terrain", '(use "war")\n(len (terrain))', 50_000_000),
    ("war-army", '(use "war")\n(let w (new-war 0) (list (alive w) (len (sprites w))))', 50_000_000),
    ("war-tick", '(use "war")\n(let w (tick (tick (new-war 0))) (alive w))', 50_000_000),
    ("war-light", '(use "war")\n(map (lambda x (cell-lo x 4)) (range 0 8))', 20_000_000),
    # lib/tactics.lova
    ("tactics-heights", '(use "tactics")\n(len (map-pairs heights))', 20_000_000),
    ("tactics-living", '(use "tactics")\n(living (new-battle 0))', 20_000_000),
    ("tactics-scene", '(use "tactics")\n(len (scene (new-battle 0)))', 50_000_000),
    ("tactics-ai", '(use "tactics")\n(let w (ai-step (new-battle 0)) (living w))', 50_000_000),
    # lib/mesh3d.lova + lib/models.lova
    ("mesh3d-count", '(use "models")\n(map (lambda m (list (vertex-count m) (face-count m)))'
                     ' (list sphere tree house gem ship))', 20_000_000),
    ("mesh3d-shot", '(use "models")\n(len (shot house 32 16 3400 800 600))', 20_000_000),
    ("mesh3d-shots", '(use "models")\n'
                     '(map (lambda m (len (shot m 48 24 3400 320 240))) (list sphere tree gem))', 50_000_000),
    # lib/platformer.lova
    ("platformer-new", '(use "platformer")\n(get (get new-game p) y)', 50_000_000),
    ("platformer-tick", '(use "platformer")\n'
                        '(let w (tick (tick new-game still) still)\n'
                        '  (list (get (get w p) x) (get (get w p) y) (get (get w p) z)))', 50_000_000),
    # lib/citybuilder.lova
    ("citybuilder-new", '(use "citybuilder")\n(cell-count new-game)', 50_000_000),
    ("citybuilder-sample", '(use "citybuilder")\n(cell-count sample-game)', 50_000_000),
    ("citybuilder-tick", '(use "citybuilder")\n'
                         '(cell-count (tick sample-game still 800 800 600))', 50_000_000),
    # lib/fleet.lova -- the policy layer, text parsing.
    ("fleet-groups", '(use "fleet")\n(len group-names)', 5_000_000),
    ("fleet-numbers", '(use "fleet")\n(list (tenths "12.5") (hundredths "0.75") (first-number "cpu 42%"))', 5_000_000),
    # lib/prelude.lova, exercised as a program in its own right.
    ("prelude-sort", '(sort-by (lambda a (lambda b (lt a b))) (map (lambda n (mod (mul n 37) 101)) (range 0 60)))', 5_000_000),
    ("prelude-text", '(let t (text-join (map int-text (range 0 40)) ",") '
                     '(list (len (text-split t ",")) (text-len t) (text-find t "37")))', 5_000_000),
    ("prelude-digits", '(map (lambda n (sum (digits n))) (range 1000 1100))', 5_000_000),
]


def group_lib() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for index, (slug, source, steps) in enumerate(LIB_PROGRAMS, start=1):
        record = make_record("lib", index, slug, source,
                             max_steps=steps, max_depth=CLI_DEPTH)
        if record is not None:
            records.append(record)
    return records


# --- group (f): the fault sites ---------------------------------------------

# One short program per anomaly a run can raise: every `kind`, and every
# `DomainTrap` site in core/runtime.py that a surface program can reach.
# (slug, source, kwargs)
TRAPS: List[Tuple[str, str, Dict[str, Any]]] = [
    # -- domain-error: arithmetic
    ("div-zero", "(div 7 0)", {}),
    ("mod-zero", "(mod 7 0)", {}),
    ("div-zero-var", "(let d 0 (div 7 d))", {}),
    ("mod-zero-var", "(let d 0 (mod 7 d))", {}),
    ("mul-too-big", "(fold (lambda a (lambda x (mul a a))) 3 (range 0 13))", {}),
    # -- domain-error: the number-theory ceiling (MAX_NT_INPUT)
    ("p-too-big", "(p 5000)", {}),
    ("tau-too-big", "(tau 5000)", {}),
    ("sigma-too-big", "(sigma 5000)", {}),
    ("mobius-too-big", "(mobius 5000)", {}),
    # -- domain-error: lists
    ("head-nil", "(head (nil))", {}),
    ("tail-nil", "(tail (nil))", {}),
    ("head-nil-deep", "(head (tail (cons 1 (nil))))", {}),
    ("head-empty-text", '(head "")', {}),
    # -- type-violation
    # A parameter is untyped (M20), so a wrong-typed value reaches the
    # operator at run time instead of being refused by the compiler.
    ("not-a-list-head", "(let f (lambda x (head x)) (f 7))", {}),
    ("not-a-list-tail", "(let f (lambda x (tail x)) (f 7))", {}),
    ("int-slot-list", "(let f (lambda x (merge x 1)) (f (cons 1 (nil))))", {}),
    ("int-slot-fn", "(let f (lambda x (merge x 1)) (f (lambda y y)))", {}),
    ("int-slot-program", "(let f (lambda x (merge x 1)) (f (quote (merge 1 2))))", {}),
    ("int-slot-population",
     "(let f (lambda x (merge x 1)) (f (defpop (lambda g 1) (quote (merge 1 2)) (quote (mul 2 3)))))", {}),
    ("apply-non-fn", "(let f (lambda x (apply x 1)) (f 7))", {}),
    ("loop-until-non-fn", "(let f (lambda p (lambda s (loop-until p s))) (apply (f 1) 2))", {}),
    ("write-a-map", "(stdout (map-of (nil)))", {}),
    ("write-a-program", "(stdout (quote (merge 1 2)))", {}),
    ("write-a-function", "(stdout (lambda x x))", {}),
    ("map-key-fn", "(map-put (nil) (lambda x x) 1)", {}),
    ("map-from-non-pairs", "(map-of (list 1 2))", {}),
    ("map-pair-wrong-size", "(map-of (list (list 1)))", {}),
    ("not-a-map", "(let f (lambda x (map-pairs x)) (f 7))", {}),
    ("not-a-population", "(let f (lambda x (fitness x)) (f 7))", {}),
    ("not-a-program", "(let f (lambda x (eval x)) (f 7))", {}),
    # -- domain-error: writing a bad codepoint
    ("write-bad-codepoint", "(stdout (cons -5 (nil)))", {}),
    # -- unbound-ref, reached at run time through `eval` (the compiler
    #    catches a written one before the program starts)
    ("unbound-eval", '(eval (read "(ref 12345)"))', {}),
    # -- malformed
    ("read-garbage", '(eval (read "(merge 1"))', {}),
    ("defpop-no-scorer", "(defpop)", {}),
    ("defpop-scorer-not-fn", "(let f (lambda x (defpop x (quote (merge 1 2)))) (f 1))", {}),
    # -- signalled (the program's own, and text-int's)
    ("signal-17", "(signal 17)", {}),
    ("signal-too-low", "(signal 3)", {}),
    ("text-int-not-a-number", '(text-int "twelve")', {}),
    ("text-int-empty", '(text-int "")', {}),
    # -- when-anomaly catching each kind
    ("catch-domain", "(when-anomaly (div 1 0) (lambda c c))", {}),
    ("catch-type", "(let f (lambda x (head x)) (when-anomaly (f 7) (lambda c c)))", {}),
    ("catch-signal", "(when-anomaly (signal 21) (lambda c c))", {}),
    ("catch-budget", "(when-anomaly (budget 3 (apply (lambda x (merge (p x) (tau x))) 12)) (lambda c c))", {}),
    ("catch-depth", "(when-anomaly (let f (lambda n (merge 1 (f (merge n 1)))) (f 0)) (lambda c c))",
     {"max_depth": 200}),
    ("catch-capability", '(when-anomaly (boundary "fs-read" (fs-read "x")) (lambda c c))', {}),
    ("catch-delta", "(when-anomaly (conserve 10 (merge 5 6)) (lambda c c))", {}),
    ("catch-rethrow", "(when-anomaly (when-anomaly (div 1 0) (lambda c (signal 30))) (lambda c c))", {}),
    ("uncaught-step-under-catch",
     "(when-anomaly (apply (loop-until (lambda n 0) (lambda n (merge n 1))) 0) (lambda c c))",
     {"max_steps": 20_000}),
    # -- capability-denied
    # The compiler refuses an effect outside a boundary, so the run-time
    # check is reached through `eval`, which no compiler pass saw.
    ("cap-outside-boundary", '(eval (read "(fs-read 120)"))', {}),
    ("cap-clock-outside-boundary", '(eval (read "(clock)"))', {"allow": ["clock"], "deterministic": True}),
    ("cap-not-granted", '(boundary "fs-read" (fs-read "README.md"))', {}),
    ("cap-clock-denied", '(boundary "clock" (clock))', {"deterministic": True}),
    ("cap-write-denied", '(boundary "fs-write" (fs-write "x" 1))', {}),
    # -- fs faults with the capability granted
    ("fs-read-missing", '(boundary "fs-read" (fs-read "no/such/file.txt"))',
     {"allow": ["fs-read"]}),
    ("fs-write-bad-path", '(boundary "fs-write" (fs-write "no/such/dir/x.txt" 1))',
     {"allow": ["fs-write"]}),
    # -- net without a granted place
    # All three trap on the grant, before a datagram is ever built, so
    # they are deterministic although they name the network.
    ("net-recv-no-port", '(boundary "net" (net-recv))',
     {"allow": ["net=127.0.0.1:1"], "deterministic": True}),
    ("net-send-no-place", '(boundary "net" (net-send "127.0.0.1:39999" "x"))',
     {"allow": ["net=127.0.0.1:1"], "deterministic": True}),
    ("net-bad-address", '(boundary "net" (net-send "not-an-address" "x"))',
     {"allow": ["net=127.0.0.1:1"], "deterministic": True}),
    # -- text-match: the pattern subset refusals (M32)
    ("match-outside-subset", '(text-match "abc" "a(?:b)c")', {}),
    ("match-bad-pattern", '(text-match "abc" "a[")', {}),
    ("match-backref", '(text-match "abc" "(a)\\\\1")', {}),
    # -- budget / delta / depth / step
    # Constants fold before the run, so the body has to be one the
    # compiler cannot compute: a lambda applied to a literal.
    ("budget-exceeded", "(budget 3 (apply (lambda x (merge (p x) (tau x))) 12))", {}),
    ("budget-nested", "(budget 20 (budget 3 (sum (map (lambda k (mul k k)) (range 0 9)))))", {}),
    ("delta-trap", "(conserve 10 (merge 5 6))", {}),
    ("delta-trap-deep", "(conserve 30 (merge (mul 5 5) (merge 2 2)))", {}),
    ("depth-trap", "(let f (lambda n (merge 1 (f (merge n 1)))) (f 0))", {"max_depth": 300}),
    ("step-trap", "(apply (loop-until (lambda n 0) (lambda n (merge n 1))) 0)", {"max_steps": 50_000}),
    ("step-trap-hot", "(def slow [n] (sum (map (lambda k (mul k k)) (range 0 n))))"
                      "(def slower [n] (sum (map slow (range 0 n))))(slower 200)",
     {"max_steps": 200_000}),
    # -- populations
    ("variant-out-of-range", "(variant (defpop (lambda g 1) (quote (merge 1 2))) 5)", {}),
    ("select-out-of-range", "(select (defpop (lambda g 1) (quote (merge 1 2))) 5)", {}),
    ("retire-last", "(retire (defpop (lambda g 1) (quote (merge 1 2))))", {}),
    ("evolve-one", "(evolve (defpop (lambda g 1) (quote (merge 1 2))))", {}),
    ("select-of-one", "(select (defpop (lambda g 1) (quote (merge 1 2))) 3)", {}),
    ("mutate-bad-strength", "(mutate (quote (merge 1 2)) 500)", {}),
]


def _hand_built_trees() -> List[Tuple[str, str, Node]]:
    """Trees no surface text can spell, for the byte decoder's sake.

    A native runtime reads bytes, not s-expressions, so it can meet a
    `let` whose name slot is not a literal.  The Python runtime answers
    `malformed`; a port must too.
    """
    from core.tokens import (APPLY, LAMBDA, LET, LIT_INT, LOOP_UNTIL, MERGE,
                             REF, Lit)
    return [
        ("malformed-let-name",
         ";; hand-built tree: (let <non-literal> 1 1) -- no surface spelling",
         Node(op=LET, args=[Node(op=MERGE, args=[Lit(1), Lit(1)]), Lit(1), Lit(1)])),
        ("malformed-ref-name",
         ";; hand-built tree: (ref <non-literal>) -- no surface spelling",
         Node(op=REF, args=[Node(op=MERGE, args=[Lit(1), Lit(1)])])),
        ("malformed-lambda-param",
         ";; hand-built tree: (lambda <non-literal> 1) -- no surface spelling",
         Node(op=LAMBDA, args=[Node(op=MERGE, args=[Lit(1), Lit(1)]), Lit(1)])),
        ("malformed-apply-empty",
         ";; hand-built tree: (apply) with an empty head slot",
         Node(op=APPLY, args=[])),
        ("loop-until-int-slots",
         ";; hand-built tree: (loop-until 1 2 3), both function slots integers",
         Node(op=LOOP_UNTIL, args=[Lit(1), Lit(2)])),
        ("unbound-ref-direct",
         ";; hand-built tree: (ref 9999), a name nothing bound",
         Node(op=REF, args=[Lit(9999)])),
    ]


def group_traps() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    index = 0
    for slug, source, kwargs in TRAPS:
        index += 1
        allow = parse_allow(kwargs.get("allow"))
        record = make_record("traps", index, slug, source,
                             allow=allow,
                             stdin=kwargs.get("stdin", ""),
                             max_steps=kwargs.get("max_steps", DEF_STEPS),
                             max_depth=kwargs.get("max_depth", DEF_DEPTH),
                             deterministic=kwargs.get("deterministic"),
                             reason=kwargs.get("reason"))
        if record is not None:
            records.append(record)
    for slug, note, tree in _hand_built_trees():
        index += 1
        record = make_record("traps", index, slug, note, prelude=False, tree=tree)
        if record is not None:
            records.append(record)
    return records


GROUPS = {
    "tests": group_tests,
    "lovabench": group_lovabench,
    "card": group_card,
    "apps": group_apps,
    "lib": group_lib,
    "traps": group_traps,
}


# --- fixtures ----------------------------------------------------------------

SAMPLE_LOG = ("api 200 100\napi 500 300\nweb 200 50\n"
              "not a record\napi 200 200\nweb 404 150\n"
              "api 200 120\ndb 200 15\ndb 503 400\nweb 200 60\n")

NOTES = ("the quick brown fox jumps over the lazy dog\n"
         "the dog barks and the fox runs\n"
         "a language for machines to write and machines to read\n"
         "the quick fox again and again the quick fox\n") * 8


def write_fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "sample.log").write_text(SAMPLE_LOG, encoding="utf-8", newline="\n")
    (FIXTURES / "notes.txt").write_text(NOTES, encoding="utf-8", newline="\n")


# --- main --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append",
                        choices=sorted(GROUPS), help="only these groups")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_fixtures()
    wanted = args.group or list(GROUPS)

    rows = []
    for name in wanted:
        started = time.time()
        print(f"[{name}] harvesting ...")
        records = GROUPS[name]()
        path = OUT_DIR / f"{name}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        det = sum(1 for r in records if r["deterministic"])
        anom = sum(1 for r in records if "anomaly" in r["expect"])
        rows.append((name, len(records), det, anom, time.time() - started))
        print(f"[{name}] {len(records)} records -> {path.name} "
              f"({time.time() - started:.1f}s)")

    print()
    print(f"{'group':12s} {'records':>8s} {'determ.':>8s} {'anomaly':>8s} {'seconds':>8s}")
    for name, total, det, anom, secs in rows:
        print(f"{name:12s} {total:8d} {det:8d} {anom:8d} {secs:8.1f}")
    print(f"{'total':12s} {sum(r[1] for r in rows):8d} "
          f"{sum(r[2] for r in rows):8d} {sum(r[3] for r in rows):8d}")
    if skipped:
        print(f"\nskipped ({len(skipped)}):")
        for ident, why in skipped:
            print(f"  {ident}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
