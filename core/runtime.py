"""Stage-1 interpreter — token-sequence evaluator.

This is the smallest runtime that can demonstrate the LOVA concept
end-to-end.  It evaluates a decoded ``Node`` tree recursively,
maintaining a variable environment, a budget stack (Axiom 4), and a
surprise trace (Axiom 7).

Operators implemented:

- LIT_INT, MERGE, PARTITION (heat-free, simple 2-split)
- NIL, CONS, HEAD, TAIL, IS_NIL          (lists -- and therefore pairs,
  and therefore strings as codepoint lists)
- STDOUT, STDIN                          (the effects boundary)
- WHEN_ANOMALY                           (in-language error handling)
- QUOTE, EVAL, READ                      (programs as values; text -> program)
- EXPLAIN, HASH, UID, GENERATION, ANCESTOR_OF, LINEAGE_QUERY, WHY, TRACE
                                         (Axiom 5, in the language)
- CLONE, MUTATE, DEFPOP, VARIANT, EVOLVE, SELECT, FITNESS, RETIRE
                                         (Axiom 6, in the language)
- P, TAU, SIGMA, GCD, MOBIUS, MUL, MOD, DIV  (number-theory primitives)
- BUDGET, CONSERVE, VIOLATE              (conservation layer)
- SURPRISE, TRACE_SURPRISE, DEVIATION, THRESHOLD  (the debugger
  primitive plus its signed / sign-test siblings, which together give
  ordering: ``a < b`` is ``(threshold (deviation b a))``)
- SEQ, LET, REF, IF_SURPRISE, LAMBDA, APPLY, LOOP_UNTIL  (composition
  and abstraction)

Everything else in the 64-token table is reserved for later milestones
and raises ``NotImplementedError`` with a pointer to the relevant family.

**M12 — mutual recursion.**  A chain of ``LET``s shares one
environment frame, so a group of ``def``s can refer to each other in
any order.  Costs no token and changes no program that already worked:
before this, a forward reference was an ``unbound-ref`` *compile*
error, so the set of programs that used to compile is untouched and
only widens -- the same shape the letrec change took in M9.

**M10 — data.**  One cons cell (``nil`` / ``cons`` / ``head`` / ``tail``
/ ``nil?``) buys pairs, lists and strings at once, and ends the era in
which the only LOVA value was a scalar integer.  ``div`` lands at the
same time: division was previously O(a/b) repeated subtraction burning
call depth to do arithmetic.

**M9 — abstraction and iteration.** Before M9 a LOVA program was a
fixed-depth expression over built-ins: no user-defined functions, no
recursion, no loops.  M9 makes the substrate computationally
universal:

- ``LAMBDA`` is unary — ``(lambda p body)``.  Multi-argument functions
  are curried: ``(lambda a (lambda b body))``.  This is exactly the
  arity-2 slot the token table already declared, so the 64-token
  budget is untouched (Axiom 8).
- ``APPLY`` is variadic with a typed head — ``(apply f a b)`` applies
  ``f`` one argument at a time, left-associatively.
- ``LET`` is a **letrec**: the bound name is visible inside its own
  value.  This is what makes recursion expressible.  The change is
  backward-compatible — before M9 a self-reference was an
  ``unbound-ref`` compile error, so no previously-valid program
  changes meaning.
- ``LOOP_UNTIL`` is a *combinator*, not a statement: ``(loop-until
  pred step)`` returns the function that iterates ``step`` until
  ``pred`` reports non-zero.  It runs iteratively, so it gives
  unbounded iteration without consuming call depth.

Non-termination is now reachable, so the substrate grows two
always-on ceilings (Axiom 7 — no silent failures, and no hangs
either): ``MAX_CALL_DEPTH`` raises ``DepthTrap`` and ``MAX_STEPS``
raises ``StepTrap``.  Both subclass ``BudgetTrap`` and carry the same
L2 anomaly schema as every other trap, so an AI consumer's single
error handler covers them.

The runtime is intentionally simple — no JIT, no evolutionary dispatch.
Those arrive in Milestone 2+.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from math import gcd as _gcd
from typing import Any, Dict, List, Optional, Tuple

from core.conservation import (
    ANOMALY_CODES, Budget, BudgetTrap, DeltaTrap, DepthTrap, DomainTrap,
    StepTrap, SurpriseTrace, anomaly_code,
)
from core.tokens import (
    APPLY, BUDGET, CONS, CONSERVE, DEVIATION, DIV, GCD, HEAD, IDENTITY,
    IF_SURPRISE, IS_NIL, LAMBDA, LET, LIT_INT, LOOP_UNTIL, MERGE, MOBIUS,
    MOD, MUL, NIL, Node, P, PARTITION, REF, SEQ, SIGMA, SIGNATURES,
    STDIN, STDOUT, SURPRISE, TAIL, TAU, THRESHOLD, TRACE_SURPRISE, VIOLATE,
    WHEN_ANOMALY,
    ANCESTOR_OF, CLONE, EVAL, EXPLAIN, GENERATION, HASH, LINEAGE_QUERY,
    MUTATE, QUOTE, TRACE, UID, WHY, encode,
    DEFPOP, EVOLVE, FITNESS, RETIRE, SELECT, VARIANT, READ,
)
from core.lineage import LineageStore, _deep_copy_node


# --- number theory helpers ---------------------------------------------------

# DoS guard: primitives reject inputs beyond this magnitude.  Intended
# for random / adversarial programs that compose operators into
# p(p(p(10))) -style bombs; production / benchmark inputs sit far below
# this (LOVABench uses n <= 100).  Raising ValueError rather than
# silently returning lets callers distinguish "out of domain" from
# legitimate results.
MAX_NT_INPUT = 2_000

# Result-magnitude guard for MUL.  Number-theory primitives are bounded
# by MAX_NT_INPUT on their *input*; multiplication is bounded on its
# *output*, because `(mul x x)` nested k deep squares k times and would
# otherwise let a random program allocate a gigabyte-wide integer.
MAX_INT_BITS = 4_096

# Substrate ceilings for the M9 abstraction layer.  A program that
# recurses without a base case, or loops without a reachable
# termination condition, must produce a structured anomaly rather than
# a Python traceback or a hang.  Both are overridable per-Runtime so
# tests (and budget-conscious hosts) can tighten them.
MAX_CALL_DEPTH = 200
MAX_STEPS = 1_000_000

# Python frames consumed per LOVA call frame — the evaluator nests
# roughly a dozen Python frames per user-level call, so the interpreter
# needs headroom above CPython's default 1000 to reach MAX_CALL_DEPTH.
# ``evaluate`` raises the limit for the duration of a run and restores
# it afterwards; a RecursionError that slips through anyway is
# converted to a DepthTrap so the failure stays inside LOVA's error
# model.
_PY_FRAMES_PER_CALL = 14
_PY_RECURSION_HEADROOM = 1_000


def partition_number(n: int) -> int:
    """p(n) — number of partitions of n.  Euler's pentagonal recurrence."""
    if n < 0:
        return 0
    if n > MAX_NT_INPUT:
        raise DomainTrap(
            "domain-error",
            f"partition_number input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}",
            {"operator": "partition_number", "input": n, "limit": MAX_NT_INPUT},
            f"reduce the argument below {MAX_NT_INPUT}",
        )
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
        raise DomainTrap(
            "domain-error",
            f"tau input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}",
            {"operator": "tau", "input": n, "limit": MAX_NT_INPUT},
            f"reduce the argument below {MAX_NT_INPUT}",
        )
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
        raise DomainTrap(
            "domain-error",
            f"sigma input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}",
            {"operator": "sigma", "input": n, "limit": MAX_NT_INPUT},
            f"reduce the argument below {MAX_NT_INPUT}",
        )
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
        raise DomainTrap(
            "domain-error",
            f"mobius input {n} exceeds MAX_NT_INPUT={MAX_NT_INPUT}",
            {"operator": "mobius", "input": n, "limit": MAX_NT_INPUT},
            f"reduce the argument below {MAX_NT_INPUT}",
        )
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


# --- values ------------------------------------------------------------------
#
# Before M9 every LOVA value was an ``int``.  Abstraction adds exactly
# one more shape: a callable.  ``Value = int | Closure | LoopFn``.
# The type system (``core.types.FN``) keeps the two apart statically;
# these classes are how they differ at run time.


@dataclass
class Closure:
    """A unary function value — ``(lambda param body)`` plus its scope.

    ``env`` is held **by reference**, not copied.  That is what makes
    ``LET`` a letrec: the LET handler installs the binding into the
    same dict the closure captured, after the closure has been built,
    so a self-reference inside ``body`` resolves when the function is
    finally applied.
    """

    param: int
    body: Node
    env: Dict[int, Any]
    name: Optional[int] = None   # binding name, when known (debug only)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        tag = f" name={self.name}" if self.name is not None else ""
        return f"<closure param={self.param}{tag}>"


class _Nil:
    """The empty list.  A singleton, so ``value is NIL_VALUE`` is the test."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "()"


NIL_VALUE = _Nil()


@dataclass(frozen=True)
class Cons:
    """A cons cell -- ``(cons x xs)``.

    A linked cell rather than a Python tuple, so ``tail`` is O(1).  With
    tuple slicing a loop over a list of n elements would cost O(n^2),
    which for strings-as-codepoint-lists is the difference between
    usable and not.
    """

    head: Any
    tail: Any            # Cons or NIL_VALUE

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        items, rest = [], self
        while isinstance(rest, Cons):
            items.append(repr(rest.head))
            rest = rest.tail
        return "(" + " ".join(items) + ")"

    def depth(self) -> int:
        """Nesting depth: 1 for a flat list, 2 for a list of lists."""
        deepest = 0
        rest = self
        while isinstance(rest, Cons):
            if isinstance(rest.head, Cons):
                deepest = max(deepest, rest.head.depth())
            rest = rest.tail
        return deepest + 1


class Scope(dict):
    """An environment frame opened by ``LET``.

    A plain dict would do, except that the runtime needs to tell a frame
    it may *extend* from one it may not.  A chain of ``LET``s -- which is
    exactly what a group of ``def``s desugars to -- shares one frame, so
    that a closure built for the first binding can see the last.  That
    is what makes mutual recursion work; see the LET handler.
    """

    __slots__ = ()


def is_list_value(v: Any) -> bool:
    """True iff ``v`` is a LOVA list (type ``List``)."""
    return v is NIL_VALUE or isinstance(v, Cons)


def list_from(values) -> Any:
    """Build a LOVA list from a Python iterable, right to left."""
    out = NIL_VALUE
    for value in reversed(list(values)):
        out = Cons(head=value, tail=out)
    return out


def list_to_python(value: Any) -> list:
    """Unpack a LOVA list into a Python list.  Raises on a non-list."""
    out = []
    rest = value
    while isinstance(rest, Cons):
        out.append(rest.head)
        rest = rest.tail
    if rest is not NIL_VALUE:
        raise DomainTrap(
            "type-violation", f"not a list: {value!r}",
            {"expected": "List"},
            "only `nil`, `cons` and `tail` produce list values",
        )
    return out


def _as_text(v: Any, ctx: str) -> str:
    """Render a value for output.

    An integer writes as its decimal digits; a list writes as the text of
    its codepoints, which is what makes ``"abc"`` -- a list of codepoints
    -- print as ``abc``.  A function has no textual form and says so; a
    program has one, but asking for it is what `explain` is for.
    """
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if is_population_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: cannot write a population; `explain` a selected variant",
            {"operator": ctx, "got": "Population"},
            "write `(explain (select pop 0))`",
        )
    if is_program_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: cannot write a program directly; `explain` renders it",
            {"operator": ctx, "got": "Program"},
            "write `(explain p)` instead of `p`",
        )
    if is_list_value(v):
        codes = list_to_python(v)
        out = []
        for code in codes:
            if not isinstance(code, int) or not 0 <= code <= 0x10FFFF:
                raise DomainTrap(
                    "domain-error",
                    f"{ctx}: {code!r} is not a codepoint; a list is written "
                    "as text, so every element must be one",
                    {"operator": ctx, "element": code},
                    "write a list whose elements are all valid codepoints",
                )
            out.append(chr(code))
        return "".join(out)
    raise DomainTrap(
        "type-violation",
        f"{ctx}: cannot write a function value ({v!r}); write an integer "
        "or a list of codepoints",
        {"operator": ctx, "got": "Fn"},
        "write an integer or a list of codepoints",
    )


@dataclass
class Population:
    """A pool of program variants under a scorer (M15) -- Axiom 6's value.

    Immutable: ``evolve`` and ``retire`` return a new pool.  The scorer
    is a LOVA function from Program to Int, lower being fitter, so a
    surprise magnitude is a score without translation.
    """

    scorer: Any
    variants: List[Node]
    generation: int = 0

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<population n={len(self.variants)} gen={self.generation}>"


# A variant whose scorer traps is not scored; it is unfit.  The anomaly
# is recorded on the runtime, so a variant that mutated into dividing by
# zero is visible, not silent -- it just loses.
UNFIT = 1 << 62

# The evolution rule, matching core/populations.py's defaults so the
# in-language step is the same step Exp 05 ran from Python.
RETIRE_FRACTION = 0.2
CLONE_PROBABILITY = 0.3
EVOLVE_STRENGTH = 0.3
SELECTION_SHARPNESS = 3


def is_population_value(v: Any) -> bool:
    return isinstance(v, Population)


def _as_population(v: Any, ctx: str) -> Population:
    if isinstance(v, Population):
        return v
    raise DomainTrap(
        "type-violation",
        f"{ctx}: expected a Population, got {v!r}; `defpop` builds one",
        {"operator": ctx, "expected": "Population"},
        "build a pool with `(defpop scorer program ...)`",
    )


def _score_population(pop: Population, rt: "Runtime") -> List[int]:
    """Every variant's score, in pool order.  Lower is fitter."""
    scores: List[int] = []
    for variant in pop.variants:
        try:
            scores.append(_as_int(_call(pop.scorer, variant, rt), "fitness"))
        except StepTrap:
            raise                       # the ceiling is not a fitness signal
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            rt.caught.append(trap.anomaly)
            scores.append(UNFIT)
    return scores


def _rank_population(pop: Population, rt: "Runtime") -> Tuple[List[int], List[int]]:
    """(scores, indices fittest-first).  Ties keep pool order."""
    scores = _score_population(pop, rt)
    order = sorted(range(len(scores)), key=lambda i: (scores[i], i))
    return scores, order


def is_program_value(v: Any) -> bool:
    """True iff ``v`` is a program (type ``Program``): a bare AST node."""
    return isinstance(v, Node)


def _as_program(v: Any, ctx: str) -> Node:
    if isinstance(v, Node):
        return v
    raise DomainTrap(
        "type-violation",
        f"{ctx}: expected a Program, got {v!r}; `quote` produces one",
        {"operator": ctx, "expected": "Program"},
        "wrap the expression in `quote`, or pass a program produced by "
        "`clone` or `mutate`",
    )


def _ensure_registered(program: Node, rt: "Runtime") -> int:
    """A program's lineage uid, registering it as a root on first need."""
    uid = getattr(program, "uid", None)
    if uid is None:
        uid = rt.lineage.register_root(program, notes="quoted")
    return uid


def _as_list(v: Any, ctx: str) -> Any:
    """Coerce a runtime value to List, or fail loudly."""
    if is_list_value(v):
        return v
    raise DomainTrap(
        "type-violation",
        f"{ctx}: expected a List, got {v!r}; only `nil`, `cons` and `tail` "
        "produce list values",
        {"operator": ctx, "expected": "List"},
        "use `nil`, `cons` or `tail` to produce a list",
    )


@dataclass
class LoopFn:
    """The function produced by ``(loop-until pred step)``.

    Applying it to a seed iterates ``step`` until ``pred`` returns
    non-zero, then yields the accumulated value.  The iteration is a
    Python ``while`` loop, not recursion, so a loop of a million
    rounds costs one call frame — unbounded iteration without
    consuming MAX_CALL_DEPTH.  ``MAX_STEPS`` is what stops it if the
    predicate is never satisfied.
    """

    pred: Any
    step: Any

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<loop-until>"


def is_callable_value(v: Any) -> bool:
    """True iff ``v`` is a LOVA function value (type ``Fn``)."""
    return isinstance(v, (Closure, LoopFn))


def _as_int(v: Any, ctx: str) -> int:
    """Coerce a runtime value to Int, or fail loudly.

    Well-typed programs *mostly* never hit the error path: ``Fn`` and
    ``List`` are disjoint from ``Int``, so neither ``valid_next`` nor the
    compiler's type-check pass will place one in an integer slot.  Two
    holes remain, and both are why every arithmetic site in this module
    routes through here rather than trusting its slot type:

    - ``APPLY`` declares ``Int`` but a *partially* applied function
      evaluates to a callable, because ``Fn`` does not track curried
      arity (journal Q35).  A generated ``(violate (apply f))`` is
      well-typed and yields a closure.
    - hand-built and mutated trees bypass both checks entirely.
    """
    if isinstance(v, bool):  # defensive: bool is an int subclass
        return int(v)
    if isinstance(v, int):
        return v
    if is_population_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: expected an Int, got a population; `fitness` gives "
            "its scores, `select` gives a variant",
            {"operator": ctx, "expected": "Int", "got": "Population"},
            "use `fitness` for the scores or `select` for a variant",
        )
    if is_program_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: expected an Int, got a program; `hash` gives its "
            "integer, `eval` gives its result",
            {"operator": ctx, "expected": "Int", "got": "Program"},
            "use `hash` for the program's integer or `eval` for its value",
        )
    if is_list_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: expected an Int, got a list ({v!r}); use `head` to take "
            "an element out of it",
            {"operator": ctx, "expected": "Int", "got": "List"},
            "use `head` to take an element out of the list",
        )
    raise DomainTrap(
        "type-violation",
        f"{ctx}: expected an Int, got a function value ({v!r}); "
        "a function can only appear in the head slot of `apply` or in a "
        "slot typed Fn",
        {"operator": ctx, "expected": "Int", "got": "Fn"},
        "apply the function to get an integer, or use it in an Fn slot",
    )


# --- runtime state -----------------------------------------------------------

@dataclass
class Runtime:
    """Evaluator state carried through a program run."""

    env: Dict[int, Any] = field(default_factory=dict)
    budget_stack: List[Budget] = field(default_factory=list)
    surprise: SurpriseTrace = field(default_factory=SurpriseTrace)
    # Provenance for every program value this run creates or derives
    # (M14).  Was a placeholder list from M1 to M13 while Axiom 5 lived
    # in core/lineage.py; now the Meta operators query it from inside.
    lineage: LineageStore = field(default_factory=LineageStore)
    # Stack of nodes currently being evaluated — used to enrich trap
    # anomalies with positional info (L2 observability).
    node_stack: List[Any] = field(default_factory=list)
    # M9 — abstraction ceilings.  ``call_depth`` counts LOVA-level
    # function applications currently on the stack; ``steps`` counts
    # every evaluated node in the run.  Both ceilings are always on,
    # independent of whether the program declares a BUDGET.
    call_depth: int = 0
    steps: int = 0
    # True while evaluating the *body* of a LET, and only there.  A LET
    # that finds it set is directly nested in another's body, so the two
    # belong to one binding group and share a frame.  Anything else --
    # a LET in an argument position, a LET inside a lambda body -- finds
    # it cleared and opens its own frame.
    let_chain: bool = False
    max_call_depth: int = MAX_CALL_DEPTH
    max_steps: int = MAX_STEPS
    # M11 -- IO.  Output is always collected here so a caller can inspect
    # what a program wrote; ``out_stream`` additionally forwards it, which
    # is what the CLI and the REPL set.  Input is a queue of lines rather
    # than a live handle, so a test, an experiment or a generated program
    # can never block on a terminal: an empty queue is end-of-input, and
    # ``stdin`` yields the empty list.
    # Anomalies a `when-anomaly` handled.  A caught fault is not an
    # invisible one: this is what an agent reads to find out what the
    # program recovered from.
    caught: List[Any] = field(default_factory=list)
    output: List[str] = field(default_factory=list)
    out_stream: Any = None
    input_lines: List[str] = field(default_factory=list)
    input_source: Any = None

    def write(self, text: str) -> None:
        """Emit ``text``, recording it and forwarding it if asked."""
        self.output.append(text)
        if self.out_stream is not None:
            self.out_stream.write(text)

    def read_line(self) -> Optional[str]:
        """The next input line, or None at end of input.

        Queued lines first, then ``input_source`` if one is set -- which
        is how the CLI attaches a terminal without letting a test or a
        generated program ever block on one.
        """
        if self.input_lines:
            return self.input_lines.pop(0)
        if self.input_source is not None:
            line = self.input_source()
            if line:
                return line.rstrip(chr(10))
        return None

    def written(self) -> str:
        """Everything the program has written so far, as one string."""
        return "".join(self.output)

    def charge(self, cost: int = 1) -> None:
        """Decrement the current budget (if any scope is active)."""
        if self.budget_stack:
            self.budget_stack[-1].charge(cost)

    def tick(self, cost: int = 1) -> None:
        """Count one evaluation step against the substrate step ceiling."""
        self.steps += cost
        if self.steps > self.max_steps:
            raise StepTrap(steps=self.steps, limit=self.max_steps)


# --- evaluator ---------------------------------------------------------------

def evaluate(node: Node, rt: Optional[Runtime] = None) -> Any:
    """Evaluate a program tree, returning its value.

    The value is an ``int`` for every program whose top-level type is
    ``Int`` — which is every program the generator can produce, since
    ``GenState.fresh()`` starts from an ``Int`` slot.  A top-level
    ``(lambda ...)`` evaluates to a ``Closure``; that is a legal value,
    just not an integer one.

    If a trap is raised during evaluation, ``_eval`` enriches the
    anomaly with the offending operator, suggested alternatives, and
    a repair hint at the innermost frame; this function just
    propagates the already-enriched trap.  AI consumers can then
    patch the program without parsing a stack trace.

    Recursion (M9) needs more Python stack than CPython's default
    allows, so the limit is raised for the duration of the run and
    restored afterwards.  A ``RecursionError`` that escapes anyway is
    converted into a ``DepthTrap``: exhausting the host interpreter is
    still a LOVA depth overrun, and it must reach the caller in the
    same anomaly schema as every other trap.
    """
    if rt is None:
        rt = Runtime()
    needed = rt.max_call_depth * _PY_FRAMES_PER_CALL + _PY_RECURSION_HEADROOM
    previous = sys.getrecursionlimit()
    if needed > previous:
        sys.setrecursionlimit(needed)
    try:
        return _eval(node, rt)
    except RecursionError:
        raise DepthTrap(depth=rt.call_depth, limit=rt.max_call_depth) from None
    finally:
        sys.setrecursionlimit(previous)


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
    env: Dict[int, Any],
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
    if not isinstance(expected, int) or not isinstance(actual, int):
        # Defensive: the scanner reasons about numeric deviations only.
        return None
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
        """Evaluate `tree` with a fresh, side-effect-isolated runtime.

        Returns None for anything that is not an integer — a probe that
        yields a closure tells us nothing about closing a numeric
        deviation, and the arithmetic below would fail on it.
        """
        rt_probe = Runtime()
        rt_probe.env = dict(env)
        try:
            value = _eval(tree, rt_probe)
        except Exception:
            return None
        return value if isinstance(value, int) else None

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


def _call(fn: Any, argument: Any, rt: Runtime) -> Any:
    """Apply a LOVA function value to one argument.

    Closures consume a call frame (and so are bounded by
    ``max_call_depth``); ``LoopFn`` iterates in Python and consumes
    none, which is what makes an unbounded loop expressible without an
    unbounded stack.
    """
    if isinstance(fn, LoopFn):
        value = argument
        while True:
            rt.tick()
            verdict = _as_int(_call(fn.pred, value, rt), "loop-until predicate")
            if verdict != 0:
                return value
            value = _call(fn.step, value, rt)

    if not isinstance(fn, Closure):
        raise DomainTrap(
            "type-violation",
            f"apply: head slot is not a function (got {fn!r}); only "
            "`lambda` and `loop-until` produce callable values",
            {"operator": "apply", "expected": "Fn"},
            "apply a `lambda` or a `loop-until`, or a name bound to one",
        )

    rt.call_depth += 1
    if rt.call_depth > rt.max_call_depth:
        depth = rt.call_depth
        rt.call_depth -= 1
        raise DepthTrap(depth=depth, limit=rt.max_call_depth)
    # A call frame is a plain dict, not a Scope: a LET inside the body
    # must not extend it, or a binding would outlive the expression that
    # introduced it.
    scope: Dict[int, Any] = dict(fn.env)
    scope[fn.param] = argument
    saved_env = rt.env
    saved_chain = rt.let_chain
    rt.let_chain = False
    rt.env = scope
    try:
        return _eval(fn.body, rt)
    finally:
        rt.env = saved_env
        rt.let_chain = saved_chain
        rt.call_depth -= 1


def _eval(node: Node, rt: Runtime) -> Any:
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


def _eval_body(node: Node, rt: Runtime) -> Any:
    op = node.op
    # Consume the "directly inside a LET body" flag: it is true for at
    # most the one node that follows a LET, and false for everything else.
    chained = rt.let_chain
    rt.let_chain = False
    # Every op costs one unit against the active budget (if any).  This is
    # the crudest possible cost model; it is enough for Milestone 1.
    rt.charge(1)
    # ...and one step against the always-on substrate ceiling (M9).  A
    # BUDGET scope is what a *program* declares about itself; this is
    # what the substrate guarantees regardless.
    rt.tick()

    if op == LIT_INT:
        return int(node.args[0])

    # --- structural -----------------------------------------------------
    if op == IDENTITY:
        return _eval(node.args[0], rt)

    if op == MERGE:
        a = _as_int(_eval(node.args[0], rt), "merge")
        b = _as_int(_eval(node.args[1], rt), "merge")
        return a + b

    if op == PARTITION:
        n = _as_int(_eval(node.args[0], rt), "partition")
        # Milestone 1: return the first non-trivial 2-split, not a tuple.
        # Stage 1 uses a convention: partition is represented as the pair
        # (⌊n/2⌋, n - ⌊n/2⌋); we emit only ⌊n/2⌋ for integer-scalar return.
        # Subsequent milestones revisit this when we have Pair types.
        return n // 2

    # --- number theory --------------------------------------------------
    if op == P:
        return partition_number(_as_int(_eval(node.args[0], rt), "p"))
    if op == TAU:
        return tau(_as_int(_eval(node.args[0], rt), "tau"))
    if op == SIGMA:
        return sigma(_as_int(_eval(node.args[0], rt), "sigma"))
    if op == GCD:
        a = _as_int(_eval(node.args[0], rt), "gcd")
        b = _as_int(_eval(node.args[1], rt), "gcd")
        return _gcd(a, b)
    if op == MOBIUS:
        return mobius(_as_int(_eval(node.args[0], rt), "mobius"))

    if op == MUL:
        a = _as_int(_eval(node.args[0], rt), "mul")
        b = _as_int(_eval(node.args[1], rt), "mul")
        # Guard the *output*: nested squaring is the cheapest way for a
        # generated program to ask for an unbounded allocation.
        if a.bit_length() + b.bit_length() > MAX_INT_BITS:
            raise DomainTrap(
                "domain-error",
                f"mul result would exceed MAX_INT_BITS={MAX_INT_BITS} "
                f"({a.bit_length()} + {b.bit_length()} bits)",
                {"operator": "mul", "limit": MAX_INT_BITS},
                "multiply smaller numbers",
            )
        return a * b

    if op == DIV:
        a = _as_int(_eval(node.args[0], rt), "div")
        b = _as_int(_eval(node.args[1], rt), "div")
        if b == 0:
            # No silent failures (Constraint 5).
            raise DomainTrap(
                "domain-error", "div: division by zero",
                {"operator": "div"},
                "guard the divisor with `(if d (div a d) fallback)`",
            )
        return a // b      # floored, matching `mod`'s sign convention

    if op == MOD:
        a = _as_int(_eval(node.args[0], rt), "mod")
        b = _as_int(_eval(node.args[1], rt), "mod")
        if b == 0:
            # No silent failures (Constraint 5): a zero divisor is a
            # domain error, not a quietly-returned zero.
            raise DomainTrap(
                "domain-error", "mod: division by zero",
                {"operator": "mod"},
                "guard the divisor with `(if d (mod a d) fallback)`",
            )
        return a % b   # floored, sign follows the divisor (Python semantics)

    # --- lists (M10) ----------------------------------------------------
    if op == NIL:
        return NIL_VALUE

    if op == CONS:
        # Any value may be an element (M17): an integer, a list, a
        # program, a function.  Only the tail has to be a list.
        element = _eval(node.args[0], rt)
        rest = _as_list(_eval(node.args[1], rt), "cons")
        return Cons(head=element, tail=rest)

    if op == HEAD:
        target = _as_list(_eval(node.args[0], rt), "head")
        if target is NIL_VALUE:
            raise DomainTrap(
                "domain-error",
                "head: the list is empty; guard with `nil?` before taking a "
                "head",
                {"operator": "head"},
                "guard with `(if (nil? xs) fallback (head xs))`",
            )
        return target.head

    if op == TAIL:
        target = _as_list(_eval(node.args[0], rt), "tail")
        if target is NIL_VALUE:
            raise DomainTrap(
                "domain-error",
                "tail: the list is empty; guard with `nil?` before taking a "
                "tail",
                {"operator": "tail"},
                "guard with `(if (nil? xs) fallback (tail xs))`",
            )
        return target.tail

    if op == IS_NIL:
        target = _as_list(_eval(node.args[0], rt), "nil?")
        return 1 if target is NIL_VALUE else 0

    # --- programs as values (M14) ------------------------------------------
    if op == QUOTE:
        # The operand is not evaluated.  It is copied, so that registering
        # or mutating the value never reaches back into the program that
        # contains the quote.
        return _deep_copy_node(node.args[0])

    if op == EVAL:
        # Run a program value in the current environment.  Its steps and
        # budget charge to this run like any other node's, because it is
        # this run.
        program = _as_program(_eval(node.args[0], rt), "eval")
        return _eval(program, rt)

    # --- meta / lineage (M14) -- Axiom 5 ------------------------------------
    if op == EXPLAIN:
        # Stage 3's human interface: a program, rendered as text -- which
        # in LOVA is a list of codepoints.  This is the Stage-1 surface
        # reached from *inside* the language for the first time.
        from core.surface import pretty
        program = _as_program(_eval(node.args[0], rt), "explain")
        return list_from([ord(ch) for ch in pretty(program)])

    if op == READ:
        # The inverse of `explain`: Stage-1 text, as a codepoint list, to a
        # program.  The full surface is accepted -- `def`, macros, strings
        # -- so a program can be authored in the sugar and read back.
        # A malformed text is a structured fault, not a Python error.
        from core.surface import parse as parse_text
        source = _as_text(_eval(node.args[0], rt), "read")
        try:
            return parse_text(source)
        except ValueError as exc:
            raise DomainTrap(
                "malformed", f"read: {exc}",
                {"operator": "read", "source": source[:80]},
                "give `read` text that `explain` could have produced",
            ) from None

    if op == HASH:
        # Axiom 1, taken literally: the program *is* this integer.
        program = _as_program(_eval(node.args[0], rt), "hash")
        return int.from_bytes(encode(program), "big")

    if op == UID:
        program = _as_program(_eval(node.args[0], rt), "uid")
        return getattr(program, "uid", None) or 0

    if op == GENERATION:
        program = _as_program(_eval(node.args[0], rt), "generation")
        uid = getattr(program, "uid", None)
        return rt.lineage.record(uid).generation if uid else 0

    if op == ANCESTOR_OF:
        a = _as_program(_eval(node.args[0], rt), "ancestor-of")
        b = _as_program(_eval(node.args[1], rt), "ancestor-of")
        ua, ub = getattr(a, "uid", None), getattr(b, "uid", None)
        if not ua or not ub:
            return 0
        return 1 if rt.lineage.is_ancestor_of(ua, ub) else 0

    if op == LINEAGE_QUERY:
        # self -> parent -> ... -> root, as uids.  Empty for an
        # unregistered program: it has no history yet.
        program = _as_program(_eval(node.args[0], rt), "lineage-query")
        uid = getattr(program, "uid", None)
        if not uid:
            return NIL_VALUE
        return list_from([rec.uid for rec in rt.lineage.ancestors(uid)])

    if op == WHY:
        # Why does this program exist?  Its mutation kind and notes, as
        # text.  The question Axiom 5 promised the language could answer.
        program = _as_program(_eval(node.args[0], rt), "why")
        uid = getattr(program, "uid", None)
        if not uid:
            text = "unregistered"
        else:
            rec = rt.lineage.record(uid)
            text = f"{rec.mutation_kind} {rec.notes}".strip()
        return list_from([ord(ch) for ch in text])

    if op == TRACE:
        # Run a program in a sandbox and return its surprise trace -- the
        # deviations, in order.  Introspection over Axiom 7's signal.
        # The sandbox inherits what is left of this run's ceilings, so a
        # loop of traces cannot slip past MAX_STEPS.
        program = _as_program(_eval(node.args[0], rt), "trace")
        inner = Runtime(
            env=dict(rt.env), lineage=rt.lineage,
            max_steps=max(1, rt.max_steps - rt.steps),
            max_call_depth=max(1, rt.max_call_depth - rt.call_depth),
        )
        try:
            _eval(program, inner)
        finally:
            rt.steps += inner.steps
        return list_from([event["deviation"] for event in inner.surprise.events])

    # --- evolution (M14, first two) -- Axiom 6 ----------------------------------
    if op == CLONE:
        program = _as_program(_eval(node.args[0], rt), "clone")
        _ensure_registered(program, rt)
        return rt.lineage.clone(program)

    if op == MUTATE:
        # (mutate program percent): strength as a percentage, because the
        # language has no fractions.  Deterministic for a given store
        # seed, so a mutation is reproducible from the run that made it.
        program = _as_program(_eval(node.args[0], rt), "mutate")
        percent = _as_int(_eval(node.args[1], rt), "mutate")
        if not 0 <= percent <= 100:
            raise DomainTrap(
                "domain-error", f"mutate: strength {percent} is not a percentage",
                {"operator": "mutate", "strength": percent},
                "give a strength between 0 and 100",
            )
        _ensure_registered(program, rt)
        return rt.lineage.mutate(program, strength=percent / 100)

    # --- evolution, the rest (M15) -- Axiom 6 ------------------------------
    if op == DEFPOP:
        if not node.args:
            raise DomainTrap(
                "malformed", "defpop: missing scorer", {"operator": "defpop"},
                "give `defpop` a scorer function and at least one program",
            )
        scorer = _eval(node.args[0], rt)
        if not is_callable_value(scorer):
            raise DomainTrap(
                "type-violation",
                f"defpop: the scorer must be a function, got {scorer!r}",
                {"operator": "defpop", "expected": "Fn"},
                "pass a lambda from Program to Int as the first argument",
            )
        variants: List[Node] = []
        for arg in node.args[1:]:
            value = _eval(arg, rt)
            if is_list_value(value):
                # A list of programs is spliced in (M18), so a pool can
                # be rebuilt from `variants-of` by library code.
                for item in list_to_python(value):
                    variants.append(_as_program(item, "defpop"))
            else:
                variants.append(_as_program(value, "defpop"))
        if not variants:
            raise DomainTrap(
                "domain-error", "defpop: a population needs at least one variant",
                {"operator": "defpop"}, "quote at least one program",
            )
        for variant in variants:
            _ensure_registered(variant, rt)
        return Population(scorer=scorer, variants=variants)

    if op == VARIANT:
        pop = _as_population(_eval(node.args[0], rt), "variant")
        k = _as_int(_eval(node.args[1], rt), "variant")
        if not 0 <= k < len(pop.variants):
            raise DomainTrap(
                "domain-error",
                f"variant: index {k} out of range for a pool of {len(pop.variants)}",
                {"operator": "variant", "index": k, "size": len(pop.variants)},
                "index from 0 to one less than the pool size",
            )
        return pop.variants[k]

    if op == SELECT:
        pop = _as_population(_eval(node.args[0], rt), "select")
        k = _as_int(_eval(node.args[1], rt), "select")
        _scores, order = _rank_population(pop, rt)
        if not 0 <= k < len(order):
            raise DomainTrap(
                "domain-error",
                f"select: rank {k} out of range for a pool of {len(order)}",
                {"operator": "select", "rank": k, "size": len(order)},
                "rank 0 is the fittest; the last rank is the pool size less one",
            )
        return pop.variants[order[k]]

    if op == FITNESS:
        pop = _as_population(_eval(node.args[0], rt), "fitness")
        return list_from(_score_population(pop, rt))

    if op == RETIRE:
        pop = _as_population(_eval(node.args[0], rt), "retire")
        if len(pop.variants) < 2:
            raise DomainTrap(
                "domain-error", "retire: cannot retire the last variant",
                {"operator": "retire", "size": len(pop.variants)},
                "a population keeps at least one variant",
            )
        _scores, order = _rank_population(pop, rt)
        worst = order[-1]
        kept = [v for i, v in enumerate(pop.variants) if i != worst]
        return Population(scorer=pop.scorer, variants=kept,
                          generation=pop.generation)

    if op == EVOLVE:
        # One generation, the same rule core/populations.py applies: the
        # bottom RETIRE_FRACTION go; each vacated slot is refilled from
        # the survivors, chosen with sharply fitness-weighted odds, by a
        # clone or a mutation.  The mutation draws on the lineage
        # store's seeded generator, so a run is reproducible.
        pop = _as_population(_eval(node.args[0], rt), "evolve")
        size = len(pop.variants)
        if size < 2:
            raise DomainTrap(
                "domain-error", "evolve: a population of one cannot evolve",
                {"operator": "evolve", "size": size},
                "start with at least two variants",
            )
        scores, order = _rank_population(pop, rt)
        n_retire = max(1, int(size * RETIRE_FRACTION))
        survivors = order[:size - n_retire]                 # fittest first
        clamp = [min(scores[i], 10 ** 9) for i in survivors]
        worst_kept = max(clamp)
        weights = [(worst_kept - c + 1) ** SELECTION_SHARPNESS for c in clamp]
        rng = rt.lineage._rng
        children: List[Node] = []
        for _ in range(n_retire):
            pick = rng.random() * sum(weights)
            acc = 0.0
            chosen = survivors[-1]
            for idx, weight in zip(survivors, weights):
                acc += weight
                if pick <= acc:
                    chosen = idx
                    break
            parent = pop.variants[chosen]
            if rng.random() < CLONE_PROBABILITY:
                children.append(rt.lineage.clone(parent))
            else:
                children.append(rt.lineage.mutate(parent, strength=EVOLVE_STRENGTH))
        kept = [v for i, v in enumerate(pop.variants) if i in set(survivors)]
        return Population(scorer=pop.scorer, variants=kept + children,
                          generation=pop.generation + 1)

    # --- error handling (M13) --------------------------------------------
    if op == WHEN_ANOMALY:
        # Evaluate the body; on a trap, hand the handler the anomaly's
        # code and return what it produces.
        #
        # `StepTrap` is deliberately *not* caught.  The step ceiling is
        # the substrate's guarantee that a program terminates, and a
        # guarantee a program can mask is not a guarantee.  Every other
        # fault -- budget, depth, conservation, domain, type, unbound
        # reference -- is a condition a program may reasonably expect and
        # recover from.
        try:
            return _eval(node.args[0], rt)
        except StepTrap:
            raise
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            anomaly = getattr(trap, "anomaly", None)
            if anomaly is None:                      # not one of ours
                raise
            code = anomaly_code(anomaly)
            rt.caught.append(anomaly)
            # A handled anomaly is still an observation (Axiom 7): the
            # trace records it, so an AI reading the run afterwards sees
            # what the program swallowed.
            rt.surprise.emit(0, code, ctx="when-anomaly")
            handler = _eval(node.args[1], rt)
            return _call(handler, code, rt)

    # --- effects / IO (M11) ----------------------------------------------
    if op == STDOUT:
        value = _eval(node.args[0], rt)
        text = _as_text(value, "stdout")
        rt.write(text)
        return len(text)

    if op == STDIN:
        line = rt.read_line()
        if line is None:
            return NIL_VALUE          # end of input, not an error
        return list_from([ord(ch) for ch in line])

    # --- conservation ---------------------------------------------------
    if op == BUDGET:
        limit = _as_int(_eval(node.args[0], rt), "budget")
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
        # Both slots are typed Int, but a partially-applied function
        # evaluates to a callable while still declaring Int (the `Fn` type
        # does not track curried arity -- journal Q35).  Coerce here so a
        # generated `(conserve k (apply (loop-until ...)))` reports the
        # type violation instead of failing inside the body scanner.
        expected = _as_int(_eval(node.args[0], rt), "conserve")
        actual = _as_int(_eval(node.args[1], rt), "conserve")
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
        return _as_int(_eval(node.args[0], rt), "violate") + 1

    # --- surprise -------------------------------------------------------
    if op == SURPRISE:
        predicted = _as_int(_eval(node.args[0], rt), "surprise")
        actual = _as_int(_eval(node.args[1], rt), "surprise")
        return rt.surprise.emit(predicted, actual, ctx="surprise")

    if op == TRACE_SURPRISE:
        val = _as_int(_eval(node.args[0], rt), "trace-surprise")
        rt.surprise.emit(0, val, ctx="trace-surprise")
        return val

    if op == DEVIATION:
        # The signed sibling of SURPRISE (which returns |a - b|).  Sign
        # is the whole point: it is what makes ordering expressible.
        # Emits no surprise event — this is a pure comparison, not an
        # observation about a prediction.
        a = _as_int(_eval(node.args[0], rt), "deviation")
        b = _as_int(_eval(node.args[1], rt), "deviation")
        return a - b

    if op == THRESHOLD:
        # Sign test: did the value cross zero from below?
        #   (a < b)  ==  (threshold (deviation b a))
        #   (a > b)  ==  (threshold (deviation a b))
        x = _as_int(_eval(node.args[0], rt), "threshold")
        return 1 if x > 0 else 0

    # --- composition ----------------------------------------------------
    if op == SEQ:
        last = 0
        for child in node.args:
            last = _eval(child, rt)
        return last

    if op == LET:
        # (let name value body) — ``name`` must be a LIT_INT symbol id.
        #
        # M9: this is a **letrec**.  A fresh scope dict is created for
        # the binding and installed *before* the value is evaluated, so
        # any closure built while evaluating the value captures that
        # same dict by reference.  The binding is written into it after
        # the value exists, which is precisely late enough for a lambda
        # (whose body runs only at apply time) and precisely early
        # enough for the self-reference to resolve.
        #
        # Backward-compatible: before M9 a self-reference in the value
        # slot was an `unbound-ref` compile error, so no program that
        # used to be valid changes meaning.
        if node.args[0].op != LIT_INT:
            raise DomainTrap(
                "malformed", "LET: name slot must be a literal integer id",
                {"operator": "let", "slot": 0},
                "put a literal integer in LET's first slot",
            )
        name_id = int(node.args[0].args[0])

        # A LET directly in another LET's body joins that binding group
        # and writes into the same frame.  Since a closure captures the
        # frame by reference, the first function in a group of `def`s
        # sees the last one -- which is mutual recursion, at the cost of
        # no new token and no change to any program that already worked.
        #
        # Shadowing keeps its own frame: re-binding a name that the group
        # already holds would otherwise reach back and change what an
        # earlier closure sees.
        extend = (chained and isinstance(rt.env, Scope)
                  and name_id not in rt.env)
        saved_env = rt.env
        if extend:
            scope = rt.env
        else:
            scope = Scope(rt.env)
            rt.env = scope
        try:
            value = _eval(node.args[1], rt)
            if isinstance(value, Closure) and value.name is None:
                value.name = name_id
            scope[name_id] = value
            rt.let_chain = True          # the body may continue the group
            return _eval(node.args[2], rt)
        finally:
            rt.let_chain = False
            if not extend:
                rt.env = saved_env

    if op == REF:
        if node.args[0].op != LIT_INT:
            raise DomainTrap(
                "malformed", "REF: name slot must be a literal integer id",
                {"operator": "ref", "slot": 0},
                "put a literal integer in REF's slot",
            )
        name_id = int(node.args[0].args[0])
        if name_id not in rt.env:
            raise DomainTrap(
                "unbound-ref", f"unbound ref: {name_id}",
                {"name_id": name_id, "bound_names": sorted(rt.env)},
                "bind the name with a `let`, or reference one that is bound",
            )
        return rt.env[name_id]

    if op == IF_SURPRISE:
        # (if-surprise surprise-expr then else)
        # Milestone 1 predicate: non-zero surprise triggers the ``then`` branch.
        s = _as_int(_eval(node.args[0], rt), "if-surprise")
        branch = node.args[1] if s != 0 else node.args[2]
        return _eval(branch, rt)

    # --- abstraction (M9) ------------------------------------------------
    if op == LAMBDA:
        # (lambda param body) — unary.  Multi-argument functions are
        # curried: (lambda a (lambda b body)).  The environment is
        # captured by reference so an enclosing LET can complete a
        # recursive binding after the closure is built.
        if node.args[0].op != LIT_INT:
            raise DomainTrap(
                "malformed", "LAMBDA: param slot must be a literal integer id",
                {"operator": "lambda", "slot": 0},
                "put a literal integer in LAMBDA's first slot",
            )
        return Closure(
            param=int(node.args[0].args[0]),
            body=node.args[1],
            env=rt.env,
        )

    if op == APPLY:
        # (apply f a b ...) — left-associative currying.  Zero
        # arguments is legal and simply yields the function itself,
        # which keeps `(apply f)` from being a special case in the
        # generator.
        if not node.args:
            raise DomainTrap(
                "malformed", "APPLY: missing function in head slot",
                {"operator": "apply"},
                "give `apply` a function to call",
            )
        fn = _eval(node.args[0], rt)
        for arg_node in node.args[1:]:
            argument = _eval(arg_node, rt)
            fn = _call(fn, argument, rt)
        return fn

    if op == LOOP_UNTIL:
        # (loop-until pred step) — a combinator.  Returns the function
        # that, applied to a seed, iterates `step` until `pred` is
        # non-zero.  The seed arrives through APPLY, which is why this
        # fits the declared arity of 2.
        pred = _eval(node.args[0], rt)
        step = _eval(node.args[1], rt)
        if not is_callable_value(pred) or not is_callable_value(step):
            raise DomainTrap(
                "type-violation",
                "LOOP_UNTIL: both slots must be functions (type Fn); got "
                f"pred={pred!r}, step={step!r}",
                {"operator": "loop-until", "expected": "Fn"},
                "pass two lambdas: a predicate and a step",
            )
        return LoopFn(pred=pred, step=step)

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
