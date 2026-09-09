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
    APPLY, BUDGET, CONS, CONSERVE, DEVIATION, DIV, GCD, HEAD, IDENTITY,
    IF_SURPRISE, IS_NIL, LAMBDA, LET, LIT_INT, LOOP_UNTIL, MERGE, MOBIUS,
    MOD, MUL, NIL, P, PARTITION, REF, RESULT_FOLLOWS_OPERANDS, SIGMA,
    SIGNATURES, SURPRISE, SEQ, TAIL, TAU, THRESHOLD, TRACE_SURPRISE,
    VIOLATE, WHEN_ANOMALY, QUOTE, Lit, Node,
    CAPABILITY_OF, EXTERNAL_BOUNDARY, capability_names,
)
from core.types import (
    FN, INT, LIST, LITERAL_INT, VALUE, FnType, Type, fn_type, is_subtype,
)


# A lambda parameter's type is not knowable from the definition: LOVA has
# no parameter annotations, and inferring one would mean checking the body
# once per call site.  The checker therefore treats a parameter as
# *unknown* and accepts a reference to it in any slot, leaving a genuine
# misuse -- passing a list where an Int is wanted -- to the runtime, which
# reports it with the same structured error as every other fault.
#
# This is the same boundary the scope pass already draws (Exp 08) and the
# same one `Fn`'s untracked curried arity draws (journal Q35): the static
# guarantee is operator-level, and anything that depends on a *name* is
# checked later or not at all.  See journal Q43.
_UNKNOWN = object()

# Operators whose result type is not their own but their operands'.
#
# ``(if c a b)`` is whatever its branches are; ``(let n v body)`` is
# whatever ``body`` is; ``(seq ... last)`` is whatever ``last`` is; and
# ``(apply f ...)`` is whatever ``f`` returns.  Declaring them all `Int`
# -- which is what the table does, because ``valid_next`` needs a single
# answer per operator -- made every list-returning conditional
# unrepresentable: `map`, `filter` and `reverse` could not be written,
# because each is `(if (nil? xs) (nil) (cons ...))` and the branches were
# forced to `Int`.
#
# So the checker treats these four as transparent: it pushes the
# *expected* type into the position that determines the result, and does
# not gate on their declared ``out_type``.  For the first three that is
# strictly more precise than before.  For ``APPLY`` it is strictly less:
# the result of a call is unknown, for the same reason curried arity is
# unknown (journal Q35), so a call used in the wrong slot fails at run
# time with a structured error rather than at compile time.
# SEQ joins the generator's set here: the compiler can see how many
# children a `seq` has, so it can check the empty case separately.
_RESULT_FOLLOWS_OPERANDS = RESULT_FOLLOWS_OPERANDS | {SEQ}


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

def _chain_names(node: Node) -> Set[int]:
    """Every name bound by a chain of ``LET``s in body position.

    ``(let f .. (let g .. (let h .. body)))`` binds f, g and h as one
    group, matching the single frame the runtime gives them.  A shadowed
    name ends the chain, because the runtime starts a new frame there.
    """
    names: Set[int] = set()
    current = node
    while (current.op == LET and len(current.args) == 3
           and current.args[0].op == LIT_INT):
        name_id = int(current.args[0].args[0])
        if name_id in names:
            break                     # shadowing: a fresh frame starts here
        names.add(name_id)
        current = current.args[2]
    return names


def _scope_check(node: Node, env: Set[int], path: Tuple[int, ...]) -> None:
    """Walk the tree; every REF must bind to a name in ``env``."""
    if node.op == LIT_INT:
        return
    if node.op == QUOTE:
        # A quoted program is data until something evaluates it, and it
        # is evaluated in *that* environment.  Its references are
        # resolved then, by the runtime, with the same structured error.
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
        # LET is a letrec (M9), and a *chain* of LETs is one mutually
        # recursive group (M12): every name in the chain is in scope in
        # every value and body of it.  The runtime shares one frame
        # across such a chain, so the checker has to see the same shape,
        # or it would reject programs that run.
        #
        # Both changes strictly widen what compiles -- a forward or self
        # reference used to be an unbound-ref error -- so nothing that
        # used to compile changes meaning.
        group = env | _chain_names(node)
        _scope_check(node.args[1], group, path + (node.op, 1))
        _scope_check(node.args[2], group, path + (node.op, 2))
        return
    if node.op == LAMBDA:
        # (lambda param body) -- param is a LiteralInt; body sees it bound.
        param_node = node.args[0]
        if param_node.op != LIT_INT:
            raise CompileError(
                kind="type-mismatch",
                detail={
                    "context": "LAMBDA param slot",
                    "expected": "LiteralInt",
                    "got": SIGNATURES[param_node.op]["name"],
                },
                position_path=path + (node.op, param_node.op),
                offending_op=param_node.op,
                repair_hint=(
                    "LAMBDA's first slot demands a LiteralInt naming the "
                    "parameter; replace the current expression with a "
                    "literal integer."
                ),
            )
        param_id = int(param_node.args[0])
        _scope_check(node.args[1], env | {param_id}, path + (node.op, 1))
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

def _join(a: Any, b: Any) -> Any:
    """The type two branches have in common, or unknown."""
    if a is _UNKNOWN or b is _UNKNOWN:
        return _UNKNOWN
    if a == b or is_subtype(a, b):
        return b
    if is_subtype(b, a):
        return a
    return _UNKNOWN


def _applied(fn: Any, count: int) -> Any:
    """The type of applying ``fn`` to ``count`` arguments, or unknown."""
    while count > 0:
        if not isinstance(fn, FnType):
            return _UNKNOWN
        if count < fn.arity:
            return fn_type(fn.arity - count, fn.ret)
        count -= fn.arity
        if fn.ret is None:
            return _UNKNOWN
        fn = fn.ret
    return fn


def _excess_arguments(fn: Any, count: int) -> int:
    """How many of ``count`` arguments ``fn`` provably cannot take."""
    taken = 0
    while isinstance(fn, FnType):
        taken += fn.arity
        if count <= taken:
            return 0
        fn = fn.ret
    if fn is None or fn is _UNKNOWN or is_subtype(FN, fn):
        return 0              # may still be a function; the runtime decides
    return count - taken


def _describe(t: Any) -> Dict[str, str]:
    """``produces`` for an anomaly: the family, and the shape when known."""
    if isinstance(t, FnType):
        return {"produces": "Fn", "shape": str(t)}
    return {"produces": str(t)}


def _binding_type(node: Node, type_env: Dict[int, Type]) -> Type:
    """The static type of an expression, as far as the checker can see.

    ``REF`` declares ``out_type = Int`` because that is what the vast
    majority of references are and because ``valid_next`` has no scope
    to consult.  The compiler *does* have scope, so here a reference
    resolves to whatever its binding holds.

    M20 made this an inference rather than a lookup.  A lambda has a
    *shape* -- its curried arity, and the type of its innermost body --
    and the shape flows: through `let` into the names that hold it,
    through `apply` into what a call produces (a shorter shape for a
    partial application, the return type for a full one), through both
    branches of an `if` when they agree.  Unknown is still the answer
    whenever the tree does not say -- a parameter (Q43), a `head`, an
    `eval`, a recursive call whose binding is still being typed -- and
    an unknown is accepted anywhere, so a misuse there fails at run
    time with a structured error, as before.
    """
    op = node.op
    if op == LIT_INT:
        return LITERAL_INT
    if op == REF and node.args and node.args[0].op == LIT_INT:
        return type_env.get(int(node.args[0].args[0]), INT)  # type: ignore[return-value]
    if op == LAMBDA and len(node.args) == 2 and node.args[0].op == LIT_INT:
        arity, body, inner_env = 0, node, dict(type_env)
        while (body.op == LAMBDA and len(body.args) == 2
               and body.args[0].op == LIT_INT):
            inner_env[int(body.args[0].args[0])] = _UNKNOWN
            arity += 1
            body = body.args[1]
        ret = _binding_type(body, inner_env)
        return fn_type(arity, None if ret is _UNKNOWN else ret)
    if op == APPLY and node.args:
        return _applied(_binding_type(node.args[0], type_env), len(node.args) - 1)
    if op == IF_SURPRISE and len(node.args) == 3:
        return _join(_binding_type(node.args[1], type_env),
                     _binding_type(node.args[2], type_env))
    if op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
        inner_env = dict(type_env)
        for other in _chain_names(node):
            inner_env.setdefault(other, _UNKNOWN)
        inner_env[int(node.args[0].args[0])] = _binding_type(node.args[1], inner_env)
        return _binding_type(node.args[2], inner_env)
    if op == SEQ:
        return _binding_type(node.args[-1], type_env) if node.args else INT
    if op == WHEN_ANOMALY and len(node.args) == 2:
        # Either the guarded value or what the handler returns.
        return _join(_binding_type(node.args[0], type_env),
                     _applied(_binding_type(node.args[1], type_env), 1))
    if op == EXTERNAL_BOUNDARY and len(node.args) == 2:
        return _binding_type(node.args[1], type_env)
    if op in _RESULT_FOLLOWS_OPERANDS:
        # `head`, `eval`: what they produce is not written anywhere the
        # checker can read.  Recording a placeholder would make every
        # value that comes out of one statically an integer --
        # `(explain (twice p))` failed to compile for exactly that
        # reason at M14.  Unknown is honest.
        return _UNKNOWN  # type: ignore[return-value]
    declared = SIGNATURES[op].get("out_type")
    return declared if declared is not None else INT


def _check_transparent(
    node: Node,
    expected: Type,
    path: Tuple[int, ...],
    type_env: Dict[int, Type],
) -> None:
    """Check an operator whose result type follows its operands."""
    if node.op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
        name_id = int(node.args[0].args[0])
        value_node = node.args[1]
        inner_env = dict(type_env)
        # Every name in the binding group is visible, matching the scope
        # pass and the runtime's shared frame.  A group member whose type
        # is not yet known is recorded as unknown rather than guessed.
        for other in _chain_names(node):
            inner_env.setdefault(other, _UNKNOWN)
        inner_env[name_id] = _binding_type(value_node, inner_env)
        _type_check(value_node, VALUE, path + (node.op, 1), inner_env)
        _type_check(node.args[2], expected, path + (node.op, 2), inner_env)
        return

    if node.op == IF_SURPRISE and len(node.args) == 3:
        # The condition is a surprise magnitude, always an Int; the two
        # branches are whatever the context wants.
        _type_check(node.args[0], INT, path + (node.op, 0), type_env)
        _type_check(node.args[1], expected, path + (node.op, 1), type_env)
        _type_check(node.args[2], expected, path + (node.op, 2), type_env)
        return

    if node.op == SEQ:
        if not node.args:
            # `(seq)` evaluates to 0, so it is an Int wherever it stands.
            if not is_subtype(INT, expected):
                raise CompileError(
                    kind="type-mismatch",
                    detail={"at_operator": "seq", "produces": "Int",
                            "expected": str(expected),
                            "note": "an empty seq evaluates to 0"},
                    position_path=path + (node.op,),
                    offending_op=node.op,
                    repair_hint=(
                        "an empty `seq` yields the integer 0; give it a "
                        f"final expression of type {expected}, or use an "
                        "operator that produces one"
                    ),
                )
            return
        # Everything but the last is evaluated for effect.
        for index, child in enumerate(node.args[:-1]):
            if isinstance(child, Node):
                _type_check(child, VALUE, path + (node.op, index), type_env)
        if node.args and isinstance(node.args[-1], Node):
            _type_check(node.args[-1], expected,
                        path + (node.op, len(node.args) - 1), type_env)
        return

    if node.op == QUOTE and len(node.args) == 1:
        # Well-formed, of any type: it is not evaluated here.
        _type_check(node.args[0], VALUE, path + (node.op, 0), {})
        return

    if node.op == WHEN_ANOMALY and len(node.args) == 2:
        # The guarded expression carries the result type; the handler is
        # a function, and what it returns is its own business (the same
        # boundary every call has -- journal Q51).
        _type_check(node.args[0], expected, path + (node.op, 0), type_env)
        _type_check(node.args[1], FN, path + (node.op, 1), type_env)
        # When the handler's shape is visible, what it returns has to
        # fit here too (M20): `(merge (try x (nil)) 1)` is refused.
        fallback = _applied(_binding_type(node.args[1], type_env), 1)
        if fallback is not _UNKNOWN and not is_subtype(fallback, expected):
            raise CompileError(
                kind="type-mismatch",
                detail={"at_operator": "when-anomaly", **_describe(fallback),
                        "expected": str(expected),
                        "note": "the handler's return type is known from its lambda"},
                position_path=path + (node.op, 1),
                offending_op=node.op,
                repair_hint=(
                    f"the handler returns {fallback} where the slot expects "
                    f"{expected}; make both branches of the recovery agree"
                ),
            )
        return

    if node.op == EXTERNAL_BOUNDARY and len(node.args) == 2:
        # A declaration around an expression: the literal is checked as
        # a literal, the body is whatever the context wants (M19).
        _type_check(node.args[0], LITERAL_INT, path + (node.op, 0), type_env)
        _type_check(node.args[1], expected, path + (node.op, 1), type_env)
        return

    if node.op == APPLY:
        sig = SIGNATURES[node.op]
        head_types = sig.get("head_types", ())
        for index, child in enumerate(node.args):
            if not isinstance(child, Node):
                continue
            here = head_types[index] if index < len(head_types) else VALUE
            _type_check(child, here, path + (node.op, index), type_env)
        if node.args:
            # M20: when the function's shape is visible, the call is
            # checked against it -- too many arguments, and the result
            # against the slot.  Nothing is said when it is not.
            head = _binding_type(node.args[0], type_env)
            given = len(node.args) - 1
            excess = _excess_arguments(head, given)
            if excess:
                raise CompileError(
                    kind="type-mismatch",
                    detail={"at_operator": "apply", "function": str(head),
                            "takes": given - excess, "given": given},
                    position_path=path + (node.op,),
                    offending_op=node.op,
                    repair_hint=(
                        f"the function takes {given - excess} argument(s) "
                        f"and {given} were given; drop {excess}"
                    ),
                )
            result = _applied(head, given)
            if result is not _UNKNOWN and not is_subtype(result, expected):
                raise CompileError(
                    kind="type-mismatch",
                    detail={"at_operator": "apply", **_describe(result),
                            "expected": str(expected),
                            "note": "the result type is known from the function's lambda"},
                    position_path=path + (node.op,),
                    offending_op=node.op,
                    repair_hint=(
                        f"this call produces {result} where the slot expects "
                        f"{expected}"
                        + ("; give it the rest of its arguments"
                           if isinstance(result, FnType) else "")
                    ),
                )
        return

    # Any other result-follows-operands operator: the result is unknown,
    # the children are what the table declares.  `eval` lands here.
    sig = SIGNATURES[node.op]
    for index, (child, in_type) in enumerate(zip(node.args, sig.get("in_types") or ())):
        if isinstance(child, Node):
            _type_check(child, in_type, path + (node.op, index), type_env)


def _type_check(
    node: Node,
    expected: Type,
    path: Tuple[int, ...],
    type_env: Optional[Dict[int, Type]] = None,
) -> None:
    """Walk the tree; each node's out_type must be a subtype of expected.

    ``type_env`` maps bound name ids to the type of what they hold, so
    a reference to a function-valued binding is rejected in an integer
    slot (and accepted in the ``Fn`` head slot of APPLY).  This is the
    same division of labour as the scope pass: ``valid_next`` guarantees
    operator-level well-typedness at generation time, while everything
    that depends on *names* is settled at compile time.
    """
    if type_env is None:
        type_env = {}
    sig = SIGNATURES[node.op]
    out_type = _binding_type(node, type_env) if node.op == REF else sig.get("out_type")
    if out_type is _UNKNOWN:
        # A reference to a lambda parameter: accepted in any slot.
        return
    if out_type is None:
        # Reserved operator without a type -- M1 runtime can't handle
        # these but compile is about correctness-of-form; let it pass
        # (runtime will raise NotImplementedError).
        return
    if node.op == QUOTE:
        # Produces a Program regardless of what is inside; gate on that,
        # then check the inside as an expression in its own right.
        if not is_subtype(out_type, expected):
            raise CompileError(
                kind="type-mismatch",
                detail={"at_operator": "quote", "produces": "Program",
                        "expected": str(expected)},
                position_path=path + (node.op,),
                offending_op=node.op,
                repair_hint="a quoted program is a Program; `eval` it, "
                            "`hash` it, or `explain` it to get another type",
            )
        _type_check(node.args[0], VALUE, path + (node.op, 0), {})
        return
    if node.op in _RESULT_FOLLOWS_OPERANDS:
        _check_transparent(node, expected, path, type_env)
        return
    if not is_subtype(out_type, expected):
        raise CompileError(
            kind="type-mismatch",
            detail={
                "at_operator": sig["name"],
                **_describe(out_type),
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

    if node.op == LAMBDA and len(node.args) == 2 and node.args[0].op == LIT_INT:
        param_id = int(node.args[0].args[0])
        inner_env = dict(type_env)
        # APPLY's tail slots are typed Int, so a parameter is always an
        # integer.  LOVA functions are first-order in M9 — a function
        # cannot be passed to a function.  (See journal/experiment_12.)
        inner_env[param_id] = _UNKNOWN
        # The body is a Value: currying makes the body of an outer
        # lambda another lambda.
        _type_check(node.args[1], VALUE, path + (node.op, 1), inner_env)
        return

    if "variadic_type" in sig:
        # A head-typed variadic (APPLY) checks its leading slots against
        # ``head_types`` and everything after against ``variadic_type``.
        head_types = sig.get("head_types", ())
        inner = sig["variadic_type"]
        for i, child in enumerate(node.args):
            if not isinstance(child, Node):
                continue
            expected_here = head_types[i] if i < len(head_types) else inner
            _type_check(child, expected_here, path + (node.op, i), type_env)
    elif sig.get("in_types") is not None:
        for i, (child, in_type) in enumerate(zip(node.args, sig["in_types"])):
            if isinstance(child, Node):
                _type_check(child, in_type, path + (node.op, i), type_env)


# --- Pass 3: constant folding ---------------------------------------------

# Pure operators — no side effects, no surprise, no conservation, no
# control flow.  All inputs deterministically map to output.
_PURE_OPS = frozenset({
    P, TAU, SIGMA, MOBIUS, GCD, MERGE, PARTITION, IDENTITY, DIV,
    # M9 arithmetic and comparison.  DEVIATION and THRESHOLD are pure in
    # a way SURPRISE is not: SURPRISE writes to the surprise trace, so
    # folding it would erase an observation the program asked for.
    MUL, MOD, DEVIATION, THRESHOLD,
})

# Pure, but folding them is pointless: their result is a list, and the
# folder can only emit a LIT_INT.  Listed so the omission is deliberate
# rather than forgotten.
_PURE_BUT_UNFOLDABLE = frozenset({NIL, CONS, TAIL})


def _is_lit(node: Node) -> bool:
    return node.op == LIT_INT


def _fold(node: Node) -> Node:
    """Fold pure subtrees with constant arguments to LIT_INT."""
    if node.op == LIT_INT:
        return node
    if node.op == QUOTE:
        # Folding inside a quote would change the program that `hash`
        # and `explain` report -- the value is the tree, not its result.
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


# --- Pass 4: drop unused bindings ------------------------------------------
#
# A standard-library prelude is only usable if what a program does not
# call costs it nothing.  Without this pass, prepending ~15 definitions
# would add them to every program's node count, byte count and LLM-token
# count -- which, for a language whose pitch is density, would make the
# standard library a tax rather than a convenience.
#
# The pass is conservative in exactly one way that matters: a binding is
# dropped only when its *value* has no effects.  Before M11 that was
# vacuous; `stdout` made it load-bearing, because dropping
# `(let x (stdout 5) body)` would silently lose the write.


def _subtree_effects(node: Node) -> set:
    """Effects that fire when ``node`` is evaluated.

    Does not descend into a lambda body: building a closure is pure, and
    whatever the body would do happens only if something applies it.
    Without that distinction no recursive prelude function could ever be
    dropped, since its body contains an `apply`.
    """
    from core.observability import _EFFECTS

    found = set(_EFFECTS.get(node.op, frozenset()))
    if node.op == LIT_INT or node.op == QUOTE:
        return found          # quoting runs nothing
    for index, child in enumerate(node.args):
        if not isinstance(child, Node):
            continue
        if node.op == LAMBDA and index == 1:
            continue          # the body runs only when applied
        found |= _subtree_effects(child)
    return found


def _references(node: Node, found: Set[int]) -> None:
    """Collect every name id reachable from ``node`` via REF."""
    if node.op == LIT_INT:
        return
    if node.op == REF and node.args and node.args[0].op == LIT_INT:
        found.add(int(node.args[0].args[0]))
        return
    for child in node.args:
        if isinstance(child, Node):
            _references(child, found)


def _split_chain(node: Node) -> Tuple[List[Tuple[int, Node]], Node]:
    """A chain of ``LET``s as ``([(name, value), ...], final_body)``."""
    bindings: List[Tuple[int, Node]] = []
    seen: Set[int] = set()
    current = node
    while (current.op == LET and len(current.args) == 3
           and current.args[0].op == LIT_INT):
        name_id = int(current.args[0].args[0])
        if name_id in seen:
            break                     # shadowing starts a new group
        seen.add(name_id)
        bindings.append((name_id, current.args[1]))
        current = current.args[2]
    return bindings, current


def _drop_unused(node: Node) -> Tuple[Node, int]:
    """Remove bindings nothing in the group reaches.

    A quoted program is left exactly as written (references inside it
    still count as uses, conservatively, because it may be evaluated).

    Liveness is a fixpoint over the whole binding group, not a lookup in
    one body.  With mutual recursion (M12) a binding can be reached only
    from an *earlier* sibling's value -- `ev` calling `od` -- so asking
    "does my body mention me" drops half of every mutually recursive
    pair and produces a program that no longer runs.
    """
    if node.op == LIT_INT or node.op == QUOTE:
        return node, 0

    if node.op == LET and len(node.args) == 3 and node.args[0].op == LIT_INT:
        bindings, body = _split_chain(node)
        dropped = 0
        rebuilt: List[Tuple[int, Node]] = []
        for name_id, value in bindings:
            new_value, n = _drop_unused(value)
            rebuilt.append((name_id, new_value))
            dropped += n
        new_body, n = _drop_unused(body)
        dropped += n

        values = dict(rebuilt)
        live: Set[int] = set()
        _references(new_body, live)
        frontier = set(live)
        while frontier:
            name_id = frontier.pop()
            value = values.get(name_id)
            if value is None:
                continue
            reached: Set[int] = set()
            _references(value, reached)
            # A binding that only references itself is not thereby live.
            fresh = reached - live - {name_id}
            live |= fresh
            frontier |= fresh

        out = new_body
        for name_id, value in reversed(rebuilt):
            if name_id not in live and not _subtree_effects(value):
                dropped += 1
                continue
            out = Node(op=LET, args=[Lit(name_id), value, out])
        return out, dropped

    dropped = 0
    new_args: List[Any] = []
    for child in node.args:
        if isinstance(child, Node):
            rewritten, n = _drop_unused(child)
            new_args.append(rewritten)
            dropped += n
        else:
            new_args.append(child)
    return Node(op=node.op, args=new_args), dropped


# --- public API ------------------------------------------------------------

@dataclass
class CompileReport:
    """Summary of a compile() run, useful for AI introspection."""
    original_nodes: int
    compiled_nodes: int
    folded_subtrees: int
    passes: Tuple[str, ...] = field(default_factory=tuple)
    dropped_bindings: int = 0

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


# --- pass: capability check (M19) -------------------------------------------
#
# Axiom 4 says effect bounds are declared in the signature and checked
# at the declaration site.  `external-boundary` is that declaration for
# the effects that touch the world, and this pass is the static half of
# the check: an `fs-read`, `fs-write` or `clock` must sit inside a
# boundary whose mask has its bit.  The boundary is lexical -- a lambda
# written inside one may use what it declared wherever it is applied,
# and a lambda written outside may not, even if applied inside -- which
# is the only rule a static pass can enforce, and the runtime keeps the
# same one by capturing the mask in the closure.  Quoted code is data
# and is not checked here; if it is ever evaluated, the runtime checks
# it then.


def _capability_check(node: Node, caps: int, path: Tuple[int, ...]) -> None:
    if node.op == LIT_INT or node.op == QUOTE:
        return
    if node.op in CAPABILITY_OF:
        bit = CAPABILITY_OF[node.op]
        if not caps & bit:
            name = SIGNATURES[node.op]["name"]
            needed = capability_names(bit)[0]
            raise CompileError(
                kind="capability-denied",
                detail={"at_operator": name, "needs": needed,
                        "declared": capability_names(caps)},
                position_path=path + (node.op,),
                offending_op=node.op,
                repair_hint=(
                    f'wrap the use in (boundary "{needed}" ...); the host '
                    f"must then grant it (`--allow {needed}`)"
                ),
            )
    if (node.op == EXTERNAL_BOUNDARY and len(node.args) == 2
            and isinstance(node.args[0], Node) and node.args[0].op == LIT_INT):
        inner = int(node.args[0].args[0])
        _capability_check(node.args[1], inner, path + (node.op, 1))
        return
    for index, child in enumerate(node.args):
        if isinstance(child, Node):
            _capability_check(child, caps, path + (node.op, index))


def compile(
    node: Node,
    *,
    fold: bool = True,
    type_check: bool = True,
    scope_check: bool = True,
    drop_unused: bool = True,
    capability_check: bool = True,
    top_type: Type = VALUE,
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
        # A program is an expression of *any* type.  Demanding Int here
        # would reject `"hi"` and `(reverse xs)` as whole programs, which
        # is a statement about the top-level slot rather than about the
        # program.  Pass `top_type=INT` to require an integer result.
        _type_check(node, expected=top_type, path=())
        passes.append("type-check")

    if capability_check:
        # Before drop-unused: an undeclared effect in a binding nothing
        # uses is still a program that lied about its effects.
        _capability_check(node, caps=0, path=())
        passes.append("capability-check")

    compiled = node
    dropped = 0
    if drop_unused:
        compiled, dropped = _drop_unused(compiled)
        passes.append("drop-unused")

    node = compiled
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
        dropped_bindings=dropped,
    )
    return compiled, report


# --- self-test -------------------------------------------------------------

def evaluate_for_selftest(node):
    from core.runtime import evaluate
    return evaluate(node)


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

    # 5. Recursive binding passes scope check (letrec, M9)
    src5 = ("(let 1 (lambda 0 (if-surprise (ref 0) "
            "(mul (ref 0) (apply (ref 1) (merge (ref 0) -1))) 1)) "
            "(apply (ref 1) 6))")
    compiled5, report5 = compile(parse(src5))
    print(f"  recursive factorial compiles (letrec scope OK), "
          f"{report5.original_nodes} -> {report5.compiled_nodes} nodes")

    # 6. A function in an Int slot is a compile-time type error
    try:
        compile(parse("(merge (lambda 0 (ref 0)) 1)"))
        raise AssertionError("expected a type-mismatch for Fn in an Int slot")
    except CompileError as e:
        assert e.anomaly["kind"] == "type-mismatch"
        print(f"  Fn in Int slot caught at compile-time: "
              f"{e.anomaly['detail']}")

    # 7. New pure ops fold
    compiled7, _ = compile(parse("(mul (mod 17 5) (threshold (deviation 5 3)))"))
    assert compiled7.op == LIT_INT and compiled7.args[0] == 2, pretty(compiled7)
    print(f"  (mul (mod 17 5) (threshold (deviation 5 3))) -> {pretty(compiled7)}")

    # 8. Lists type-check, and a list in an Int slot does not
    node8, _ = compile(parse("(head (cons 7 (nil)))"))
    assert evaluate_for_selftest(node8) == 7
    try:
        compile(parse("(merge (nil) 1)"))
        raise AssertionError("expected a type-mismatch for List in an Int slot")
    except CompileError as e:
        assert e.anomaly["kind"] == "type-mismatch"
        print(f"  List in Int slot caught at compile-time: {e.anomaly['detail']}")

    # 9. A function may take a list -- the parameter type is unknown, so a
    #    reference to it is accepted in a List slot.
    src9 = "(defn total [xs] (if (nil? xs) 0 (merge (head xs) (total (tail xs)))))(total (cons 1 (cons 2 (nil))))"
    node9, _ = compile(parse(src9))
    assert evaluate_for_selftest(node9) == 3, pretty(node9)
    print("  list-consuming function compiles and runs (sum = 3)")

    # 10. Unused bindings go away; used and effectful ones stay.
    unused = "(let 0 (mul 6 7) (let 1 99 (ref 1)))"
    node10, report10 = compile(parse(unused))
    assert report10.dropped_bindings == 1, report10
    # Binding 0 goes (nothing mentions it); binding 1 stays (the body does).
    assert pretty(node10) == "(let 1 99 (ref 1))", pretty(node10)
    kept = "(let 0 (stdout 5) 7)"
    _node11, report11 = compile(parse(kept))
    assert report11.dropped_bindings == 0, "a write must never be dropped"
    # A whole unused function chain collapses, which is what makes a
    # prelude free for programs that do not call it.
    chain = "(def f [x] (mul x 2))(def g [x] (f x))7"
    node12, report12 = compile(parse(chain))
    assert report12.dropped_bindings == 2, report12
    assert pretty(node12) == "7", pretty(node12)
    print(f"  drop-unused: {unused}")
    print(f"               -> {pretty(node10)}  (effectful bindings kept)")
    print(f"               two unused definitions -> {pretty(node12)}, "
          f"{report12.original_nodes} -> {report12.compiled_nodes} nodes")

    print("core.compiler self-test OK")


if __name__ == "__main__":
    _self_test()
