"""Run every program through both native evaluators and compare (Q128).

    python tools/differential.py                  # the whole set
    python tools/differential.py --only war       # rows whose name matches
    python tools/differential.py --generated 500  # fewer random programs

The native runtime carries two evaluators: the tree-walker (`rt.rs`,
the reference port) and the bytecode VM (`vm/`).  They must be
indistinguishable.  This starts the binary twice -- once with
``LOVA_RT_EVAL=tree``, once with ``LOVA_RT_EVAL=vm`` -- sends each
program to both, and compares **the whole reply**: the value, the step
count, stdout, and every field of the anomaly, including
``position_path``, ``position_nodes``, ``detail.calls`` (the `hot`
table), ``repair_hint`` and ``message``.

The programs are every ``.lova`` file under ``apps/``, ``lib/``,
``tools/bench/`` and ``corpus/``, the golden set's own byte sequences,
a fixed corpus of shapes a review found the gates blind to (a closed
`let` region a closure kept alive, a letrec hole, a catch inside a
batched run, a tail call whose last argument traps, `eval` reading a
name bound after it, lambdas that must not look like escapes), and N
programs from ``core.generator.constrained_random`` -- half of them
grafted into the prelude's `let` chain.  Each is run at several
step ceilings, chosen so that a good half of the runs trap: a trap is
where the two evaluators have the most to disagree about.

Stdlib only.  Exit code 1 on any difference.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BINARY = os.environ.get(
    "LOVA_NATIVE", str(ROOT / "native" / "lova-rt" / "target" / "release" / "lova-rt.exe")
)

# A ceiling per run.  Small ones trap in the prelude, the largest lets
# most programs finish.
CEILINGS = (200, 3_000, 50_000, 2_000_000)

# fs-read only: `clock` would differ between two processes anyway, and
# `fs-write` would touch the tree.  A denied capability is a trap, and
# a trap is what this compares.
ALLOW = 1

STDIN = "3\n5\nq\n\n"


class Runtime:
    """One binary, one evaluator, spoken to over its pipes."""

    def __init__(self, path: str, mode: str) -> None:
        env = dict(os.environ)
        env["LOVA_RT_EVAL"] = mode
        self.mode = mode
        self.proc = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, cwd=str(ROOT), env=env)
        self._id = 0
        hello = self.call({"op": "ping"})
        if hello.get("eval") != mode:
            raise SystemExit(f"the binary ignored LOVA_RT_EVAL={mode}: {hello}")
        self.version = hello.get("version", "?")

    def call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"the {self.mode} runtime closed its output")
        return json.loads(line)

    def run(self, data: bytes, max_steps: int) -> Dict[str, Any]:
        self._id += 1
        reply = self.call({
            "id": self._id, "op": "run", "bytes": data.hex(),
            "stdin": STDIN, "allow": ALLOW,
            "max_steps": max_steps, "max_depth": 10_000,
        })
        reply.pop("id", None)
        return reply

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:                          # noqa: BLE001
            self.proc.kill()


# --- the programs ------------------------------------------------------------

def source_files() -> List[Path]:
    out: List[Path] = []
    for folder in ("apps", "lib", "tools/bench", "corpus"):
        out.extend(sorted((ROOT / folder).rglob("*.lova")))
    return out


def compiled(path: Path) -> Optional[bytes]:
    """A source file as the bytes the runtime is given, or None."""
    from core.cli import build
    from core.tokens import encode
    try:
        source = path.read_text(encoding="utf-8")
        # Placeholders a driver would fill: give them a small number, so
        # the program is a program rather than a parse error.
        import re
        source = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", "7", source)
        tree, _ = build(source, prelude=True)
        return encode(tree)
    except Exception:                              # noqa: BLE001
        return None


# Shapes an adversarial review found, kept as programs: each one is a
# place where the two evaluators could disagree and the golden set does
# not look.  They are cheap, so they run at every ceiling, every time.
FIXED: List[Tuple[str, str]] = [
    ("fixed:closed-region-conserve",
     "(let yy 5 (seq (let yy 1 (lambda q yy)) (conserve 10 (merge yy yy))))"),
    ("fixed:closed-region-eval",
     "(let yy 5 (seq (let yy 1 (lambda q yy)) (eval (quote yy))))"),
    ("fixed:closed-region-unbound",
     "(seq (let yy 1 (lambda q yy)) (eval (quote yy)))"),
    ("fixed:closed-region-trace",
     "(let yy 5 (seq (let yy 1 (lambda q yy)) (trace (quote (surprise yy 0)))))"),
    ("fixed:closed-region-in-a-lambda",
     "(defn outer [n] (seq (let yy 1 (lambda q yy)) (eval (quote n)))) (outer 7)"),
    ("fixed:closure-reads-its-region",
     "(let yy 5 (let f (let yy 1 (lambda q (eval (quote yy)))) (f 0)))"),
    ("fixed:sibling-regions",
     "(seq (let aa 1 (lambda q aa)) (seq (let bb 2 (lambda q bb)) (eval (quote bb))))"),
    ("fixed:letrec-hole",
     "(let g (let f (lambda x (merge x g)) (let g (f 1) 1)) g)"),
    ("fixed:pending-binder",
     "(let f (lambda x (merge x later)) (let later (f 1) later))"),
    ("fixed:catch-in-a-batched-run",
     "(merge 1 (when-anomaly (merge 2 (div 1 0)) (lambda c (merge c 100))))"),
    ("fixed:tail-argument-traps",
     "(defn f [a b] (merge a b)) (defn g [n] (f n (div 1 0))) (g 1)"),
    ("fixed:eval-before-the-binding", "(let a (eval (quote b)) (let b 2 a))"),
    ("fixed:three-deep-capture",
     "(defn a3 [x] (lambda y (lambda z (merge x (merge y z)))))"
     " (apply (apply (apply a3 1) 2) 3)"),
    ("fixed:lambda-in-a-quote", "(let q (quote (lambda x x)) (let y 5 (eval q)))"),
    ("fixed:lambda-in-an-untaken-branch", "(let y 5 (if 0 (lambda x y) (eval (quote y))))"),
    ("fixed:lambda-in-a-callback",
     "(let y 5 (seq (map (lambda x (merge x y)) (list 1 2)) (eval (quote y))))"),
    ("fixed:deep-non-tail-recursion",
     "(defn deep [n] (if n (merge 1 (deep (sub n 1))) 0)) (deep 200)"),
    ("fixed:shadowing-in-a-group",
     "(let a 1 (let b (let a 2 (lambda q a)) (eval (quote a))))"),
    ("fixed:conserve-after-a-held-region",
     "(defn mk [n] (lambda q n)) (let z 3 (seq (mk 9) (conserve 3 z)))"),
    # the surface's type pass refuses this, so it travels as bytes
    ("fixed:non-integer-test", bytes.fromhex("2a15010101010102")),   # (if (nil) 1 2)
    ("fixed:depth-ceiling",
     "(defn down [n] (merge 1 (down (merge n 1)))) (down 0)"),
]


def fixed_programs() -> Iterator[Tuple[str, bytes]]:
    """The review's shapes, compiled with the prelude."""
    from core.cli import build
    from core.tokens import encode
    for name, source in FIXED:
        if isinstance(source, bytes):
            yield name, source
            continue
        try:
            tree, _ = build(source, prelude=True)
            yield name, encode(tree)
        except Exception as exc:                   # noqa: BLE001
            # A regression case that stops compiling is a case the
            # harness has silently lost (review of 2026-09-19: the
            # non-integer `if` test never ran).  Fail loudly instead.
            raise SystemExit(
                f"{name}: does not compile: {type(exc).__name__}: {exc} -- "
                "a FIXED entry must compile; give it raw bytes if the "
                "surface refuses it")


def golden_bytes() -> Iterator[Tuple[str, bytes]]:
    folder = ROOT / "corpus" / "golden"
    for jsonl in sorted(folder.glob("*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            try:
                yield f"golden:{record['id']}", bytes.fromhex(record["bytes"])
            except ValueError:
                continue


def generated(n: int) -> Iterator[Tuple[str, bytes]]:
    """Random well-typed programs, half of them inside the prelude."""
    from core.cli import build
    from core.generator import constrained_random
    from core.tokens import LET, decode, encode

    prelude_tree, _ = build("(nil)", prelude=True)

    def graft(body: Any) -> Any:
        import copy
        chain = copy.deepcopy(prelude_tree)
        node = chain
        if node.op != LET:
            return body
        while node.args[2].op == LET:
            node = node.args[2]
        node.args[2] = body
        return chain

    for seed in range(n):
        try:
            raw = constrained_random(seed=seed, max_depth=6)
        except Exception:                          # noqa: BLE001
            continue
        if seed % 2 == 0:
            yield f"gen:{seed}", raw
        else:
            try:
                yield f"gen+prelude:{seed}", encode(graft(decode(raw)))
            except Exception:                      # noqa: BLE001
                continue


# --- comparison ---------------------------------------------------------------

def differences(tree: Dict[str, Any], vm: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    keys = sorted(set(tree) | set(vm))
    for key in keys:
        left, right = tree.get(key), vm.get(key)
        if key == "anomaly":
            out.extend(anomaly_differences(left or {}, right or {}))
        elif left != right:
            out.append(f"{key}: tree {left!r}, vm {right!r}")
    return out


def anomaly_differences(left: Dict[str, Any], right: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if a != b:
            out.append(f"anomaly.{key}: tree {a!r}, vm {b!r}")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="only programs whose name matches")
    parser.add_argument("--generated", type=int, default=2000,
                        help="how many random programs (default 2000)")
    parser.add_argument("--binary", default=BINARY)
    parser.add_argument("--max-failures", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    jobs: List[Tuple[str, bytes]] = []
    for path in source_files():
        name = str(path.relative_to(ROOT)).replace("\\", "/")
        if args.only and args.only not in name:
            continue
        data = compiled(path)
        if data is not None:
            jobs.append((name, data))
    for name, data in golden_bytes():
        if args.only and args.only not in name:
            continue
        jobs.append((name, data))
    for name, data in fixed_programs():
        if args.only and args.only not in name:
            continue
        jobs.append((name, data))
    for name, data in generated(args.generated):
        if args.only and args.only not in name:
            continue
        jobs.append((name, data))

    tree = Runtime(args.binary, "tree")
    vm = Runtime(args.binary, "vm")
    print(f"{tree.version}: {len(jobs)} programs x {len(CEILINGS)} ceilings")

    runs = traps = bad = 0
    failures: List[str] = []
    try:
        for name, data in jobs:
            for ceiling in CEILINGS:
                left = tree.run(data, ceiling)
                right = vm.run(data, ceiling)
                runs += 1
                if "anomaly" in left:
                    traps += 1
                diff = differences(left, right)
                if diff:
                    bad += 1
                    failures.append(f"{name} @{ceiling}: " + "; ".join(diff[:3]))
                    if len(failures) <= args.max_failures:
                        print(f"DIFF {failures[-1]}")
                elif args.verbose:
                    print(f"same {name} @{ceiling}")
    finally:
        tree.close()
        vm.close()

    print()
    print(f"runs {runs}, of which trapped {traps} ({100 * traps // max(1, runs)}%)")
    print(f"differences {bad}")
    if failures:
        print(f"\n{len(failures)} differing run(s)")
        return 1
    print("\nthe two evaluators are indistinguishable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
