"""LOVA compiler — static passes over the Node tree.

Pipeline (call ``compile(node)`` for the whole lot):

  1. **Scope resolution** -- walk `LET` / `REF`, verify every `REF`
     binds to a name introduced by an outer `LET`.  Catches the
     `unbound-ref` error at compile-time instead of runtime (moved
     from the runtime's "(ref 99) -> ValueError" path).

  2. **Type check** -- walk every node, verify its `out_type` is a
     subtype of the slot's expected type.  This is structurally
     redundant with `valid_next` at generation time, but runs over
     *imported* / *mutated* / *hand-edited* trees where the
     generation-time constraint may not apply.

  3. **Constant folding** -- evaluate pure subtrees at compile time
     and replace them with `LIT_INT` nodes.  `(p 12)` becomes `77`
     as a literal in the bytecode.  Density win + runtime win.

A compile error is a structured object with the same shape as runtime
anomalies (``kind / position_path / offending_op / valid_alternatives
/ repair_hint``), so downstream AI consumers use the same handler
regardless of when the error surfaces.

**Paradigm lineage**:

- Middle-end passes (GCC, LLVM, Roslyn).
- Elaboration + type checking (Agda/Lean/Idris).
- Scope resolution (every Lisp implementation since 1958).

LOVA's synthesis: passes operate on the same AST shape the runtime
uses; compile output is the same `Node` type; compilation is
*optional* but always *safe*.  Uncompiled programs still run -- just
with errors surfaced later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.tokens import (
    BUDGET, CONSERVE, GCD, IDENTITY, IF_SURPRISE, LET, LIT_INT, MERGE,
    MOBIUS, P, PARTITION, REF, SIGMA, SIGNATURES, SURPRISE, SEQ, TAU,
    TRACE_SURPRISE, VIOLATE, Lit, Node,
)
from core.types import INT, LITERAL_INT, Type, is_subtype


# --- CompileError ----------------------------------------------------------

class CompileError(Exception):
    """A static-pass error, structured for AI consumption.

    The ``anomaly`` dict has the same shape as runtime trap anomalies
    (``core.conservation.enrich_anomaly``) so a single error handler can
    process both compile-time and runtime errors uniformly.
    """

    def __init__(
        self,
        kind: str,
        detail: Dict[str, Any],
        position_path: Tuple[int, ...] = (),
        offending_op: Optional[int] = None,
        valid_alternatives: Tuple[int, ...] = (),
        repair_hint: str = "",
    ):
        offending_name = (
            SIGNATURES.get(offending_op, {"name": ""}).get("name", "")
            if offending_op is not None else ""
        )
        self.anomaly: Dict[str, Any] = {
            "kind": kind,
            "stage": "compile",
            "detail": detail,
            "position_path": position_path,
            "offending_op": offending_op,
            "offending_op_name": offending_name,
            "valid_alternatives": valid_alternatives,
            "repair_hint": repair_hint,
        }
        super().__init__(f"CompileError[{kind}]: {detail}")


# --- Pass 1: scope resolution ----------------------------------------------

def _scope_check(node: Node, env: Set[int], path: Tuple[int, ...]) -> None:
    """Walk the tree; every REF must bind to a name in ``env``."""
    if node.op == LIT_INT:
        return
    if node.op == LET:
        # (let name value body) -- name is a LiteralInt; body sees name bound.
        name_node = node.args[0]
        if name_node.op != LIT_INT:
            raise CompileError(
                kind="type-mismatch",
                detail={
                    "context": "LET name slot",
                    "expected": "LiteralInt",
                    "got": SIGNATURES[name_node.op]["name"],
                },
                position_path=path + (node.op, name_node.op),
                offending_op=name_node.op,
                repair_hint=(
                    "LET's first slot demands a LiteralInt; replace the "
                    "current expression with a literal integer."
                ),
            )
        name_id = int(name_node.args[0])
        _scope_check(node.args[1], env, path + (node.op, 1))  # value uses outer env
        _scope_check(node.args[2], env | {name_id}, path + (node.op, 2))
        return
    if node.op == REF:
        name_node = node.args[0]
        if name_node.op != LIT_INT:
            raise CompileError(
                kind="type-mismatch",
                detail={
                    "context": "REF name slot",
                    "expected": "LiteralInt",
                    "got": SIGNATURES[name_node.op]["name"],
                },
                position_path=path + (node.op, name_node.op),
                offending_op=name_node.op,
                repair_hint=(
                    "REF's first slot demands a LiteralInt; replace with "
                    "a literal integer that matches a bound name."
                ),
            )
        name_id = int(name_node.args[0])
        if name_id not in env:
            raise CompileError(
                kind="unbound-ref",
                detail={
                    "name_id": name_id,
                    "bound_names": sorted(env),
                },
                position_path=path + (node.op,),
                offending_op=REF,
                repair_hint=(
                    f"REF {name_id} is not in scope.  Either wrap in a LET "
                    f"that binds {name_id}, or use a bound name from "
                    f"{sorted(env) or '(none in scope)'}."
                ),
            )
        return
    # Default: recurse into children
    for i, child in enumerate(node.args):
        if isinstance(child, Node):
            _scope_check(child, env, path + (node.op, i))


# --- Pass 2: type check ----------------------------------------------------

def _type_check(node: Node, expected: Type, path: Tuple[int, ...]) -> None:
    """Walk the tree; each node's out_type must be a subtype of expected."""
    sig = SIGNATURES[node.op]
    out_type = sig.get("out_type")
    if out_type is None:
        # Reserved operator without a type -- M1 runtime can't handle
        # these but compile is about correctness-of-form; let it pass
        # (runtime will raise NotImplementedError).
        return
    if not is_subtype(out_type, expected):
        raise CompileError(
            kind="type-mismatch",
            detail={
                "at_operator": sig["name"],
                "produces": str(out_type),
                "expected": str(expected),
            },
            position_path=path + (node.op,),
            offending_op=node.op,
            repair_hint=(
                f"Operator `{sig['name']}` produces {out_type}, but slot "
                f"expects {expected}.  Replace with an operator whose "
                f"output type is (a subtype of) {expected}."
            ),
        )
    if node.op == LIT_INT:
        return
    if "variadic_type" in sig:
        inner = sig["variadic_type"]
        for i, child in enumerate(node.args):
            if isinstance(child, Node):
                _type_check(child, inner, path + (node.op, i))
    elif sig.get("in_types") is not None:
        for i, (child, in_type) in enumerate(zip(node.args, sig["in_types"])):
            if isinstance(child, Node):
                _type_check(child, in_type, path + (node.op, i))


# --- Pass 3: constant folding ---------------------------------------------

# Pure operators — no side effects, no surprise, no conservation, no
# control flow.  All inputs deterministically map to output.
_PURE_OPS = frozenset({
    P, TAU, SIGMA, MOBIUS, GCD, MERGE, PARTITION, IDENTITY,
})


def _is_lit(node: Node) -> bool:
    return node.op == LIT_INT


def _fold(node: Node) -> Node:
    """Fold pure subtrees with constant arguments to LIT_INT."""
    if node.op == LIT_INT:
        return node

    # Recurse first (bottom-up fold)
    new_args: List[Any] = []
    for child in node.args:
        if isinstance(child, Node):
            new_args.append(_fold(child))
        else:
            new_args.append(child)
    folded = Node(op=node.op, args=new_args)

    # Is this node foldable?
    if node.op in _PURE_OPS and all(
        isinstance(c, Node) and _is_lit(c) for c in new_args
    ):
        try:
            from core.runtime import Runtime, evaluate
            result = evaluate(folded, Runtime())
            return Lit(result)
        except Exception:
            # If evaluation fails (e.g., p of huge negative), leave
            # the node un-folded.  Runtime will handle it.
            return folded
    return folded


# --- public API ------------------------------------------------------------

@dataclass
class CompileReport:
    """Summary of a compile() run, useful for AI introspection."""
    original_nodes: int
    compiled_nodes: int
    folded_subtrees: int
    passes: Tuple[str, ...] = field(default_factory=tuple)

    def compression_ratio(self) -> float:
        if self.original_nodes == 0:
            return 1.0
        return self.compiled_nodes / self.original_nodes


def _count_nodes(node: Node) -> int:
    if node.op == LIT_INT:
        return 1
    return 1 + sum(
        _count_nodes(c) for c in node.args if isinstance(c, Node)
    )


def compile(
    node: Node,
    *,
    fold: bool = True,
    type_check: bool = True,
    scope_check: bool = True,
) -> Tuple[Node, CompileReport]:
    """Run the static pipeline on ``node``.

    Returns ``(compiled_node, report)``.  Raises ``CompileError`` at
    the first failure.  Flags exist to skip passes for debugging /
    comparing pipeline variants.
    """
    original_count = _count_nodes(node)
    passes: List[str] = []

    if scope_check:
        _scope_check(node, env=set(), path=())
        passes.append("scope-check")

    if type_check:
        _type_check(node, expected=INT, path=())
        passes.append("type-check")

    compiled = node
    folded_subtrees = 0
    if fold:
        before = original_count
        compiled = _fold(node)
        after = _count_nodes(compiled)
        folded_subtrees = max(0, (before - after) // 2)  # rough estimate
        passes.append("constant-fold")

    compiled_count = _count_nodes(compiled)
    report = CompileReport(
        original_nodes=original_count,
        compiled_nodes=compiled_count,
        folded_subtrees=folded_subtrees,
        passes=tuple(passes),
    )
    return compiled, report


# --- self-test -------------------------------------------------------------

def _self_test() -> None:
    from core.surface import parse, pretty

    # 1. Well-formed program compiles + folds
    src = "(merge (p 3) (tau 12))"
    compiled, report = compile(parse(src))
    assert compiled.op == LIT_INT, \
        f"expected folded to LIT_INT, got {pretty(compiled)}"
    assert compiled.args[0] == 9
    print(f"  {src:<30s} -> {pretty(compiled)}  "
          f"({report.original_nodes} -> {report.compiled_nodes} nodes)")

    # 2. let/ref with valid binding passes scope check
    src2 = "(let 0 12 (merge (p (ref 0)) (tau (ref 0))))"
    compiled2, report2 = compile(parse(src2))
    print(f"  {src2:<30s} -> {pretty(compiled2)} (scope OK)")

    # 3. Unbound ref raises CompileError
    try:
        compile(parse("(merge (ref 99) 3)"))
    except CompileError as e:
        assert e.anomaly["kind"] == "unbound-ref"
        print(f"  unbound ref caught at compile-time: "
              f"kind={e.anomaly['kind']} "
              f"detail={e.anomaly['detail']}")

    # 4. Pure but non-const doesn't fold
    src4 = "(merge (p 3) (ref 0))"
    # can't compile — unbound ref — but test fold via wrap
    src4_ok = "(let 0 5 (merge (p 3) (ref 0)))"
    compiled4, report4 = compile(parse(src4_ok))
    print(f"  {src4_ok} -> {pretty(compiled4)}  "
          f"(fold kept {report4.compiled_nodes} nodes due to ref)")

    print("core.compiler self-test OK")


if __name__ == "__main__":
    _self_test()
