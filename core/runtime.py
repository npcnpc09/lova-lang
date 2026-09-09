"""Stage-1 interpreter — token-sequence evaluator.

This is the smallest runtime that can demonstrate the LOVA concept
end-to-end.  It evaluates a decoded ``Node`` tree recursively,
maintaining a variable environment, a budget stack (Axiom 4), and a
surprise trace (Axiom 7).

Operators implemented in Milestone 1:

- LIT_INT, MERGE, PARTITION (heat-free, simple 2-split)
- P, TAU, SIGMA, GCD, MOBIUS  (number-theory primitives)
- BUDGET, CONSERVE, VIOLATE   (conservation layer)
- SURPRISE, TRACE_SURPRISE    (the debugger primitive)
- SEQ, LET, REF, IF_SURPRISE, LAMBDA, APPLY  (minimal composition)

Everything else in the 64-token table is reserved for later milestones
and raises ``NotImplementedError`` with a pointer to the relevant family.

The runtime is intentionally simple — no JIT, no evolutionary dispatch.
Those arrive in Milestone 2+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import gcd as _gcd
from typing import Any, Dict, List, Optional, Tuple

from core.conservation import Budget, BudgetTrap, DeltaTrap, SurpriseTrace
from core.tokens import (
    APPLY, BUDGET, CONSERVE, GCD, IDENTITY, IF_SURPRISE, LAMBDA, LET, LIT_INT,
    MERGE, MOBIUS, Node, P, PARTITION, REF, SEQ, SIGMA, SIGNATURES, SURPRISE,
    TAU, TRACE_SURPRISE, VIOLATE,
)


# --- number theory helpers ---------------------------------------------------

# DoS guard: primitives reject inputs beyond this magnitude.  Intended
# for random / adversarial programs that compose operators into
# p(p(p(10))) -style bombs; production / benchmark inputs sit far below
# this (LOVABench uses n <= 100).  Raising ValueError rather than
# silently returning lets callers distinguish "out of domain" from
# legitimate results.
MAX_NT_INPUT = 2_000


def partition_number(n: int) -> int:
    """p(n) — number of partitions of n.  Euler's pentagonal recurrence."""
    if n < 0:
        return 0
    if n > MAX_NT_INPUT:
        raise ValueError(f"partition_number input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}")
    if n == 0:
        return 1
    table = [0] * (n + 1)
    table[0] = 1
    for m in range(1, n + 1):
        k = 1
        while True:
            g1 = k * (3 * k - 1) // 2
            g2 = k * (3 * k + 1) // 2
            if g1 > m:
                break
            sign = -1 if k % 2 == 0 else 1
            table[m] += sign * table[m - g1]
            if g2 <= m:
                table[m] += sign * table[m - g2]
            k += 1
    return table[n]


def tau(n: int) -> int:
    if n <= 0:
        return 0
    if n > MAX_NT_INPUT:
        raise ValueError(f"tau input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}")
    count = 0
    d = 1
    while d * d <= n:
        if n % d == 0:
            count += 2 if d * d != n else 1
        d += 1
    return count


def sigma(n: int) -> int:
    if n <= 0:
        return 0
    if n > MAX_NT_INPUT:
        raise ValueError(f"sigma input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}")
    total = 0
    d = 1
    while d * d <= n:
        if n % d == 0:
            total += d
            other = n // d
            if other != d:
                total += other
        d += 1
    return total


def mobius(n: int) -> int:
    """μ(n) — Möbius function."""
    if n <= 0:
        return 0
    if n > MAX_NT_INPUT:
        raise ValueError(f"mobius input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}")
    if n == 1:
        return 1
    m = n
    prime_count = 0
    d = 2
    while d * d <= m:
        if m % d == 0:
            m //= d
            if m % d == 0:
                return 0  # squared prime divisor
            prime_count += 1
        else:
            d += 1
    if m > 1:
        prime_count += 1
    return 1 if prime_count % 2 == 0 else -1


# --- runtime state -----------------------------------------------------------

@dataclass
class Runtime:
    """Evaluator state carried through a program run."""

    env: Dict[int, int] = field(default_factory=dict)
    budget_stack: List[Budget] = field(default_factory=list)
    surprise: SurpriseTrace = field(default_factory=SurpriseTrace)
    # lineage tracking placeholder; populated by ``core.lineage``.
    lineage: List[Any] = field(default_factory=list)
    # Stack of nodes currently being evaluated — used to enrich trap
    # anomalies with positional info (L2 observability).
    node_stack: List[Any] = field(default_factory=list)

    def charge(self, cost: int = 1) -> None:
        """Decrement the current budget (if any scope is active)."""
        if self.budget_stack:
            self.budget_stack[-1].charge(cost)


# --- evaluator ---------------------------------------------------------------

def evaluate(node: Node, rt: Optional[Runtime] = None) -> int:
    """Evaluate a program tree, returning an integer result.

    If a trap is raised during evaluation, ``_eval`` enriches the
    anomaly with the offending operator, suggested alternatives, and
    a repair hint at the innermost frame; this function just
    propagates the already-enriched trap.  AI consumers can then
    patch the program without parsing a stack trace.
    """
    if rt is None:
        rt = Runtime()
    return _eval(node, rt)


def _enrich_trap(trap, rt: Runtime) -> None:
    """Attach positional + repair-hint fields to an in-flight trap."""
    from core.conservation import enrich_anomaly
    from core.observability import suggest_alternatives

    top = rt.node_stack[-1] if rt.node_stack else None
    op = top.op if top is not None else None
    alternatives = suggest_alternatives(op) if op is not None else ()
    enrich_anomaly(
        trap.anomaly,
        position_path=tuple(n.op for n in rt.node_stack),
        offending_op=op,
        valid_alternatives=alternatives,
        op_name_for=lambda tok: SIGNATURES.get(tok, {"name": "?"}).get("name", "?"),
    )
    # Kind-specific repair hints.  Only overwrite the generic hint if no
    # body-level offender was identified by the probe — when one IS set
    # (Q20), the CONSERVE handler has already written a more specific hint
    # naming the actual sub-expression at fault.
    if trap.anomaly.get("kind") == "conservation-violated":
        already_specific = trap.anomaly.get("body_offender") is not None
        if op is not None and not already_specific:
            trap.anomaly["repair_hint"] = (
                f"replace operator `{SIGNATURES[op]['name']}` with one of "
                f"{[SIGNATURES[a]['name'] for a in alternatives]} "
                "to keep the body in the conserve invariant"
            )
        # Swap valid_alternatives to track the inner offender when known
        # — AI consumers can then step() with one of these to patch.
        if already_specific:
            from core.observability import suggest_alternatives as _alt
            inner_op = trap.anomaly["body_offender"]["op"]
            trap.anomaly["valid_alternatives"] = _alt(inner_op)


def _clone_with_replacement(
    node: Node, path: Tuple[int, ...], new_node: Node
) -> Node:
    """Return a deep-clone of `node` with the subtree at `path` replaced."""
    if not path:
        return new_node
    idx = path[0]
    rest = path[1:]
    new_args = list(node.args)
    cur = new_args[idx]
    if isinstance(cur, Node):
        new_args[idx] = _clone_with_replacement(cur, rest, new_node)
    else:
        # Only reached when path descends into a scalar leaf; substitute
        # only if we are AT the leaf (no further descent requested).
        if not rest:
            new_args[idx] = new_node
    return Node(op=node.op, args=new_args)


def _scan_body_offender(
    body: Node,
    expected: int,
    actual: int,
    env: Dict[int, int],
) -> Optional[Dict[str, Any]]:
    """Probe-based body scan for CONSERVE Δ-traps (Q20, M6 Day 2).

    Find the deepest subexpression whose replacement by ``LIT_INT(value -
    deviation)`` makes the whole body evaluate to ``expected``.  That
    subexpression is the *actual* offender; the outer CONSERVE is the
    merely the trap-raising frame.

    Returns a dict with keys ``op / op_name / path / depth / observed /
    needed / correction`` — or ``None`` if no single-node replacement
    closes the deviation and no heuristic matches.

    Cost: O(n²) for body size n.  Bodies are small (< 50 nodes in
    practice); this runs only on Δ-trap, not on every eval.
    """
    deviation = actual - expected
    if deviation == 0:
        return None

    # Collect (path, node, depth) for every Node-typed subtree in body.
    candidates: List[Tuple[Tuple[int, ...], Node, int]] = []

    def walk(n: Node, path: Tuple[int, ...], depth: int) -> None:
        candidates.append((path, n, depth))
        for i, arg in enumerate(n.args):
            if isinstance(arg, Node):
                walk(arg, path + (i,), depth + 1)

    walk(body, (), 0)

    def _probe(tree: Node) -> Optional[int]:
        """Evaluate `tree` with a fresh, side-effect-isolated runtime."""
        rt_probe = Runtime()
        rt_probe.env = dict(env)
        try:
            return _eval(tree, rt_probe)
        except Exception:
            return None

    # Cache each subnode's in-situ value (its output when evaluated with env).
    node_values: Dict[Tuple[int, ...], int] = {}
    for path, sub, _depth in candidates:
        v = _probe(sub)
        if v is not None:
            node_values[path] = v

    # Deepest-first; ties broken by path lex for determinism.
    ordered = sorted(candidates, key=lambda c: (-c[2], c[0]))

    # Pass A: operator-swap probe.  For each non-LIT_INT subnode, try
    # replacing the op itself with an entry from ``suggest_alternatives``
    # (same-family swap, or VIOLATE -> IDENTITY).  If ANY swap restores
    # the invariant, the subnode is a high-confidence "wrong operator"
    # offender — semantically cleaner than the LIT_INT band-aid probe.
    #
    # This pass is what catches the `(conserve N (violate (merge a b)))`
    # shape: the inner MERGE can be fixed by rewriting a literal, but
    # VIOLATE -> IDENTITY fixes it more naturally and names the real fault.
    from core.observability import suggest_alternatives
    for path, sub, depth in ordered:
        if sub.op == LIT_INT:
            continue
        alts = suggest_alternatives(sub.op)
        if not alts:
            continue
        observed_sub_val = node_values.get(path)
        for alt in alts:
            swapped = Node(op=alt, args=list(sub.args))
            modified = _clone_with_replacement(body, path, swapped)
            new_actual = _probe(modified)
            if new_actual != expected:
                continue
            swapped_val = _probe(swapped)
            correction = (
                (swapped_val - observed_sub_val)
                if (swapped_val is not None and observed_sub_val is not None)
                else 0
            )
            return {
                "op": sub.op,
                "op_name": SIGNATURES.get(sub.op, {}).get("name", "?"),
                "path": path,
                "depth": depth,
                "observed": observed_sub_val,
                "needed": swapped_val,
                "correction": correction,
                "fix": "operator-swap",
                "alternative_op": alt,
                "alternative_op_name": SIGNATURES.get(alt, {}).get("name", "?"),
            }

    # Pass B: LIT_INT replacement probe.  If no operator-swap fixes the
    # deviation, fall back to literal substitution: replace each non-LIT
    # subnode's subtree with LIT_INT(its_value - deviation).  This catches
    # "wrong literal / wrong computation" shapes where the op choice is
    # fine but the produced value happens to miss the contract.
    #
    # Skip LIT_INT candidates except at body root — replacing a non-root
    # literal is a trivial band-aid; the semantic offender is the op above.
    for path, sub, depth in ordered:
        if path not in node_values:
            continue
        if sub.op == LIT_INT and path:  # keep root-LIT_INT (body IS a literal)
            continue
        observed = node_values[path]
        needed = observed - deviation
        modified = _clone_with_replacement(
            body, path, Node(op=LIT_INT, args=[needed])
        )
        new_actual = _probe(modified)
        if new_actual == expected:
            return {
                "op": sub.op,
                "op_name": SIGNATURES.get(sub.op, {}).get("name", "?"),
                "path": path,
                "depth": depth,
                "observed": observed,
                "needed": needed,
                "correction": needed - observed,
                "fix": "literal-replacement",
            }

    # Heuristic fallback: no exact fix — return deepest non-root subnode
    # whose own value equals the deviation (catches VIOLATE-style +1 adds).
    for path, sub, depth in ordered:
        if not path:
            continue  # skip body root
        if node_values.get(path) == deviation:
            return {
                "op": sub.op,
                "op_name": SIGNATURES.get(sub.op, {}).get("name", "?"),
                "path": path,
                "depth": depth,
                "observed": deviation,
                "needed": 0,
                "correction": -deviation,
                "fix": "heuristic-value-equals-deviation",
            }
    return None


def _eval(node: Node, rt: Runtime) -> int:
    rt.node_stack.append(node)
    try:
        try:
            return _eval_body(node, rt)
        except (BudgetTrap, DeltaTrap) as trap:
            # Enrich on first catch (innermost frame), re-raise.  Each
            # outer frame sees ``_enriched`` sentinel and skips.
            if not trap.anomaly.get("_enriched"):
                _enrich_trap(trap, rt)
                trap.anomaly["_enriched"] = True
            raise
    finally:
        rt.node_stack.pop()


def _eval_body(node: Node, rt: Runtime) -> int:
    op = node.op
    # Every op costs one unit against the active budget (if any).  This is
    # the crudest possible cost model; it is enough for Milestone 1.
    rt.charge(1)

    if op == LIT_INT:
        return int(node.args[0])

    # --- structural -----------------------------------------------------
    if op == IDENTITY:
        return _eval(node.args[0], rt)

    if op == MERGE:
        a = _eval(node.args[0], rt)
        b = _eval(node.args[1], rt)
        return a + b

    if op == PARTITION:
        n = _eval(node.args[0], rt)
        # Milestone 1: return the first non-trivial 2-split, not a tuple.
        # Stage 1 uses a convention: partition is represented as the pair
        # (⌊n/2⌋, n - ⌊n/2⌋); we emit only ⌊n/2⌋ for integer-scalar return.
        # Subsequent milestones revisit this when we have Pair types.
        return n // 2

    # --- number theory --------------------------------------------------
    if op == P:
        return partition_number(_eval(node.args[0], rt))
    if op == TAU:
        return tau(_eval(node.args[0], rt))
    if op == SIGMA:
        return sigma(_eval(node.args[0], rt))
    if op == GCD:
        a = _eval(node.args[0], rt)
        b = _eval(node.args[1], rt)
        return _gcd(a, b)
    if op == MOBIUS:
        return mobius(_eval(node.args[0], rt))

    # --- conservation ---------------------------------------------------
    if op == BUDGET:
        limit = _eval(node.args[0], rt)
        b = Budget(limit=limit)
        rt.budget_stack.append(b)
        try:
            return _eval(node.args[1], rt)
        finally:
            rt.budget_stack.pop()

    if op == CONSERVE:
        # In Milestone 1 the invariant argument is a literal int flag:
        #   0 = SUM_INVARIANT — expect body to preserve its own input sum.
        # The body is expected to compute something whose result equals
        # the first argument's value; otherwise Δ-trap.  This is a toy
        # semantic to show the *mechanism* — proper invariants in M2+.
        expected = _eval(node.args[0], rt)
        actual = _eval(node.args[1], rt)
        if expected != actual:
            body_offender = _scan_body_offender(
                node.args[1], expected, actual, dict(rt.env)
            )
            repair_hint = (
                "body produced a value different from the expected "
                "conserve target; replace the divergent op with "
                "one that preserves the value"
            )
            if body_offender is not None:
                repair_hint = (
                    f"body-offender `{body_offender['op_name']}` at "
                    f"path {body_offender['path']} returns "
                    f"{body_offender['observed']}; needs {body_offender['needed']} "
                    f"(correction {body_offender['correction']:+d}) to restore "
                    "the conserve invariant"
                )
            raise DeltaTrap(
                anomaly={
                    "kind": "conservation-violated",
                    "detail": {
                        "invariant": "conserve/equality",
                        "entry": expected,
                        "exit": actual,
                        "deviation": actual - expected,
                    },
                    "position_path": (),
                    "offending_op": None,
                    "offending_op_name": "",
                    "valid_alternatives": (),
                    "body_offender": body_offender,
                    "repair_hint": repair_hint,
                }
            )
        return actual

    if op == VIOLATE:
        # Synthetic "break conservation" — returns first arg's value
        # plus one, so wrapping with CONSERVE always triggers Δ-trap.
        # For testing only.
        return _eval(node.args[0], rt) + 1

    # --- surprise -------------------------------------------------------
    if op == SURPRISE:
        predicted = _eval(node.args[0], rt)
        actual = _eval(node.args[1], rt)
        return rt.surprise.emit(predicted, actual, ctx="surprise")

    if op == TRACE_SURPRISE:
        val = _eval(node.args[0], rt)
        rt.surprise.emit(0, val, ctx="trace-surprise")
        return val

    # --- composition ----------------------------------------------------
    if op == SEQ:
        last = 0
        for child in node.args:
            last = _eval(child, rt)
        return last

    if op == LET:
        # (let name value body) — ``name`` must be a LIT_INT symbol id.
        if node.args[0].op != LIT_INT:
            raise ValueError("LET: name slot must be a literal integer id")
        name_id = int(node.args[0].args[0])
        value = _eval(node.args[1], rt)
        saved = rt.env.get(name_id)
        rt.env[name_id] = value
        try:
            return _eval(node.args[2], rt)
        finally:
            if saved is None:
                rt.env.pop(name_id, None)
            else:
                rt.env[name_id] = saved

    if op == REF:
        if node.args[0].op != LIT_INT:
            raise ValueError("REF: name slot must be a literal integer id")
        name_id = int(node.args[0].args[0])
        if name_id not in rt.env:
            raise ValueError(f"unbound ref: {name_id}")
        return rt.env[name_id]

    if op == IF_SURPRISE:
        # (if-surprise surprise-expr then else)
        # Milestone 1 predicate: non-zero surprise triggers the ``then`` branch.
        s = _eval(node.args[0], rt)
        branch = node.args[1] if s != 0 else node.args[2]
        return _eval(branch, rt)

    # --- explicitly deferred --------------------------------------------
    if op in (LAMBDA, APPLY):
        raise NotImplementedError(
            "LAMBDA / APPLY — Milestone 2 (first-class closures)."
        )

    # --- everything else ------------------------------------------------
    sig = SIGNATURES.get(op, {"name": "unknown", "family": "?"})
    raise NotImplementedError(
        f"operator {sig['name']} (family {sig['family']}) not implemented "
        f"in Milestone 1 runtime"
    )


# --- self-test ---------------------------------------------------------------

def _self_test() -> None:
    from core.surface import parse

    assert partition_number(12) == 77, "p(12) reference value wrong"
    assert tau(12) == 6
    assert sigma(12) == 28
    assert mobius(30) == -1

    cases = [
        ("(p 12)", 77),
        ("(tau 12)", 6),
        ("(sigma 12)", 28),
        ("(gcd 12 18)", 6),
        ("(merge (p 3) (tau 12))", 3 + 6),   # p(3)=3, tau(12)=6
        ("(seq (p 3) (p 4) (p 5))", 7),        # p(5)=7, last wins
        ("(let 1 12 (p (ref 1)))", 77),        # binding
    ]
    for src, expected in cases:
        out = evaluate(parse(src))
        assert out == expected, f"{src} -> {out}, expected {expected}"
        print(f"  {src:<40s} = {out}")
    print("core.runtime self-test OK")


if __name__ == "__main__":
    _self_test()
