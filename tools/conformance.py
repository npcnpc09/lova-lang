"""Check a LOVA runtime against the golden set.

    python tools/conformance.py --runtime python
    python tools/conformance.py --runtime python corpus/golden/traps.jsonl
    python tools/conformance.py --runtime ./target/release/lova-rt

``--runtime python`` decodes each record's ``bytes`` and evaluates the
tree with the Python runtime.  The source text is never re-read: that
is the point.  If the bytes alone reproduce the value, the anomaly and
the step count, then the byte sequence really is the program, and a
port has something complete to aim at.

``--runtime <path>`` starts the binary and speaks the line protocol in
``spec/native-runtime-protocol.md``.

What is compared:

    value                exact string (``core.cli.format_value``)
    anomaly.kind         exact
    anomaly.offending_op exact
    anomaly.position_path exact
    anomaly.detail       the keys `operator`, `limit`, `expected`,
                         `code`, `name_id`, where the record has them
    steps                exact, unless ``--loose-steps``

Records flagged ``deterministic: false`` are run and reported, but
never fail the run unless ``--strict``.

Exit code 1 on any failure.  Stdlib only.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN = ROOT / "corpus" / "golden"

DETAIL_KEYS = ("operator", "limit", "expected", "code", "name_id")


# --- the runtimes ------------------------------------------------------------

class PythonRuntime:
    """The reference: decode the bytes, run them, describe what happened."""

    name = "python"

    def __init__(self) -> None:
        from core.cli import format_value
        from core.conservation import BudgetTrap, DeltaTrap
        from core.runtime import Runtime, evaluate
        from core.tokens import decode
        self._format = format_value
        self._traps = (BudgetTrap, DeltaTrap, ValueError, NotImplementedError)
        self._Runtime = Runtime
        self._evaluate = evaluate
        self._decode = decode

    def run(self, record: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tree = self._decode(bytes.fromhex(record["bytes"]))
        except Exception as exc:                       # noqa: BLE001
            return {"error": f"decode: {type(exc).__name__}: {exc}"}
        feed = io.StringIO(record.get("stdin", ""))
        rt = self._Runtime(max_steps=record["max_steps"],
                           max_call_depth=record["max_depth"],
                           granted=record.get("allow", 0),
                           input_source=feed.readline)
        out: Dict[str, Any] = {}
        try:
            value = self._evaluate(tree, rt)
            out["value"] = self._format(value)
        except self._traps as exc:                     # noqa: BLE001
            anomaly = getattr(exc, "anomaly", None)
            if anomaly is None:
                return {"error": f"{type(exc).__name__}: {exc}", "steps": rt.steps}
            out["anomaly"] = {
                "kind": anomaly.get("kind"),
                "offending_op": anomaly.get("offending_op"),
                "offending_op_name": anomaly.get("offending_op_name", ""),
                "position_path": list(anomaly.get("position_path") or ()),
                "detail": _jsonable(anomaly.get("detail") or {}),
            }
        except Exception as exc:                       # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}", "steps": rt.steps}
        out["steps"] = rt.steps
        out["stdout"] = rt.written()
        return out

    def close(self) -> None:
        pass


class NativeRuntime:
    """A binary speaking `spec/native-runtime-protocol.md` over its pipes."""

    def __init__(self, path: str) -> None:
        import shlex
        self.name = path
        # A command, not only a path, so the reference server
        # (`python tools/mock_runtime.py`) can be driven the same way.
        self.proc = subprocess.Popen(
            shlex.split(path, posix=False) if " " in path else [path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, text=True, encoding="utf-8", bufsize=1, cwd=str(ROOT))
        self._id = 0
        hello = self._call({"op": "ping"})
        self.version = hello.get("version", "?")

    def _call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("the runtime closed its output")
        return json.loads(line)

    def run(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self._id += 1
        try:
            reply = self._call({
                "id": self._id, "op": "run", "bytes": record["bytes"],
                "stdin": record.get("stdin", ""), "allow": record.get("allow", 0),
                "max_steps": record["max_steps"], "max_depth": record["max_depth"],
            })
        except Exception as exc:                       # noqa: BLE001
            return {"error": f"protocol: {type(exc).__name__}: {exc}"}
        if reply.get("ok") is False and "anomaly" not in reply:
            return {"error": reply.get("error", "runtime said not ok")}
        out: Dict[str, Any] = {"steps": reply.get("steps"),
                               "stdout": reply.get("stdout", "")}
        if reply.get("ok"):
            out["value"] = reply.get("value")
        else:
            anomaly = reply.get("anomaly") or {}
            out["anomaly"] = {
                "kind": anomaly.get("kind"),
                "offending_op": anomaly.get("offending_op"),
                "offending_op_name": anomaly.get("offending_op_name", ""),
                "position_path": list(anomaly.get("position_path") or ()),
                "detail": anomaly.get("detail") or {},
            }
        return out

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:                              # noqa: BLE001
            self.proc.kill()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)


# --- comparison --------------------------------------------------------------

def differences(record: Dict[str, Any], got: Dict[str, Any],
                loose_steps: bool = False) -> List[str]:
    """Every way ``got`` differs from what the record expects."""
    out: List[str] = []
    if "error" in got:
        return [f"runtime error: {got['error']}"]
    want = record["expect"]
    if "value" in want:
        if "value" not in got:
            kind = (got.get("anomaly") or {}).get("kind")
            return [f"expected value {want['value']!r}, got anomaly {kind!r}"]
        if got["value"] != want["value"]:
            out.append(f"value: want {want['value']!r}, got {got['value']!r}")
    else:
        wa = want["anomaly"]
        if "anomaly" not in got:
            return [f"expected anomaly {wa['kind']!r}, got value {got.get('value')!r}"]
        ga = got["anomaly"]
        for key in ("kind", "offending_op"):
            if ga.get(key) != wa.get(key):
                out.append(f"anomaly.{key}: want {wa.get(key)!r}, got {ga.get(key)!r}")
        if list(ga.get("position_path") or []) != list(wa.get("position_path") or []):
            out.append(f"anomaly.position_path: want {wa.get('position_path')}, "
                       f"got {ga.get('position_path')}")
        wd, gd = wa.get("detail") or {}, ga.get("detail") or {}
        for key in DETAIL_KEYS:
            if key in wd and gd.get(key) != wd.get(key):
                out.append(f"anomaly.detail.{key}: want {wd[key]!r}, got {gd.get(key)!r}")
    if not loose_steps and got.get("steps") != record["steps"]:
        out.append(f"steps: want {record['steps']}, got {got.get('steps')}")
    return out


# --- driving -----------------------------------------------------------------

def load(paths: List[Path]) -> List[Tuple[str, Dict[str, Any]]]:
    records: List[Tuple[str, Dict[str, Any]]] = []
    for path in paths:
        group = path.stem
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append((group, json.loads(line)))
    return records


def targets(args: argparse.Namespace) -> List[Path]:
    if args.files:
        return [Path(f) for f in args.files]
    return sorted(GOLDEN.glob("*.jsonl"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="golden files (default: all)")
    parser.add_argument("--runtime", default="python",
                        help="'python' or the path to a native runtime binary")
    parser.add_argument("--loose-steps", action="store_true",
                        help="do not compare step counts")
    parser.add_argument("--strict", action="store_true",
                        help="non-deterministic records must match too")
    parser.add_argument("--verbose", action="store_true",
                        help="print a line per record, not only failures")
    parser.add_argument("--max-failures", type=int, default=25,
                        help="stop printing after this many failures")
    args = parser.parse_args(argv)

    files = targets(args)
    if not files:
        print(f"no golden files in {GOLDEN}; run tools/golden.py first")
        return 1
    records = load(files)

    runtime: Any
    if args.runtime == "python":
        runtime = PythonRuntime()
    else:
        runtime = NativeRuntime(args.runtime)
        print(f"runtime {args.runtime} version {runtime.version}")

    stats: Dict[str, List[int]] = {}
    failures: List[Tuple[str, List[str]]] = []
    shaky: List[Tuple[str, List[str]]] = []
    try:
        for group, record in records:
            row = stats.setdefault(group, [0, 0, 0, 0])   # total, pass, fail, nondet
            row[0] += 1
            if not record.get("deterministic", True):
                row[3] += 1
            got = runtime.run(record)
            diff = differences(record, got, loose_steps=args.loose_steps)
            solid = record.get("deterministic", True) or args.strict
            if not diff:
                row[1] += 1
                if args.verbose:
                    print(f"PASS {record['id']}")
            elif not solid:
                shaky.append((record["id"], diff))
                if args.verbose:
                    print(f"SKIP {record['id']}: {diff[0]}")
            else:
                row[2] += 1
                failures.append((record["id"], diff))
                if len(failures) <= args.max_failures:
                    print(f"FAIL {record['id']}: {diff[0]}")
    finally:
        runtime.close()

    print()
    print(f"{'group':12s} {'records':>8s} {'pass':>8s} {'fail':>8s} {'nondet':>8s}")
    for group in sorted(stats):
        total, ok, bad, skip = stats[group]
        print(f"{group:12s} {total:8d} {ok:8d} {bad:8d} {skip:8d}")
    tot = [sum(v[i] for v in stats.values()) for i in range(4)]
    print(f"{'total':12s} {tot[0]:8d} {tot[1]:8d} {tot[2]:8d} {tot[3]:8d}")
    if shaky:
        print(f"\nnon-deterministic records that differed ({len(shaky)}, not failures):")
        for ident, diff in shaky[:10]:
            print(f"  {ident}: {diff[0]}")
    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nconformant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
