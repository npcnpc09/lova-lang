"""Stage-1 interpreter — token-sequence evaluator.

This is the smallest runtime that can demonstrate the LOVA concept
end-to-end.  It evaluates a decoded ``Node`` tree recursively,
maintaining a variable environment, a budget stack (Axiom 4), and a
surprise trace (Axiom 7).

Operators implemented:

- LIT_INT, MERGE, PARTITION (heat-free, simple 2-split)
- NIL, CONS, HEAD, TAIL, IS_NIL          (lists -- and therefore pairs,
  and therefore strings as codepoint lists)
- STDOUT, STDIN                          (the terminal, ambient)
- EXTERNAL_BOUNDARY, FS_READ, FS_WRITE, CLOCK, NET_SEND, NET_RECV
                                         (M19/M21: the world, under a declared boundary)
- WHEN_ANOMALY, SIGNAL                   (in-language error handling: catch and raise)
- MAP_PUT, MAP_GET, MAP_PAIRS            (M22: a persistent map, the sixth value kind)
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

import os
import platform
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from math import gcd as _gcd
from typing import Any, Dict, List, Optional, Tuple

from core.conservation import (
    ANOMALY_CODES, Budget, BudgetTrap, DeltaTrap, DepthTrap, DomainTrap,
    FIRST_PROGRAM_SIGNAL, StepTrap, SurpriseTrace, anomaly_code,
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
    CLOCK, EXTERNAL_BOUNDARY, FS_READ, FS_WRITE, CAPABILITY_OF,
    capability_names, NET_RECV, NET_SEND, SIGNAL, MAP_GET, MAP_PAIRS, MAP_PUT,
    LIT_TEXT, TEXT_LEN, TEXT_CAT, TEXT_SLICE, TEXT_FIND, TEXT_SPLIT, TEXT_JOIN, TEXT_CHARS, TEXT_OF_CHARS, TEXT_CMP, TEXT_INT, INT_TEXT, IS_TEXT, TEXT_TRIM,
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
MAX_CALL_DEPTH = 10_000      # M22: was 200; a 300-element recursive `len` tripped it
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

# M23 -- PyPy.  CPython 3.11+ runs a Python-to-Python call without
# consuming C stack, so the recursion limit alone bounds a run.  PyPy
# spends real stack per frame, and on Windows the main thread has a
# megabyte of it: ten thousand LOVA frames overflow it and the process
# dies without a traceback.  `evaluate` therefore runs on a thread
# with a stack sized to the depth ceiling when the host is PyPy.  The
# figure is ~1.6 KB per LOVA frame measured, taken at 4 KB.
_NEEDS_BIG_STACK = platform.python_implementation() == "PyPy"
_STACK_BYTES_PER_FRAME = 4_096
_STACK_FLOOR = 64 * 1024 * 1024
_big_stack = threading.local()


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
    # M19 -- the capabilities in force where the lambda was written.  A
    # boundary is lexical: the body may use what the boundary around
    # its *definition* declared, wherever it is eventually applied.
    # That is what the compiler checks, so it is what the runtime does.
    caps: int = 0
    enclosed: bool = False       # written inside some boundary (Q70)
    # M23 -- the body, compiled to a Python closure once (see `_code`).
    # ``body`` stays the Node: `explain`, `mutate` and the lineage work
    # on the tree; only `_call` runs the code.
    code: Any = None

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        tag = f" name={self.name}" if self.name is not None else ""
        return f"<closure param={self.param}{tag}>"


class _Nil:
    """The empty list.  A singleton, so ``value is NIL_VALUE`` is the test."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "()"


NIL_VALUE = _Nil()


@dataclass(slots=True, unsafe_hash=True)
class Cons:
    """A cons cell -- ``(cons x xs)``.

    A linked cell rather than a Python tuple, so ``tail`` is O(1).  With
    tuple slicing a loop over a list of n elements would cost O(n^2),
    which for strings-as-codepoint-lists is the difference between
    usable and not.
    """

    # Never mutated after construction -- which is what the hash needs
    # and what ``frozen`` used to enforce at the price of a slower
    # constructor (M23: `object.__setattr__` per field, per cell).
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
    """An environment frame opened by ``LET`` or by a call.

    A plain dict would do, except that the runtime needs to tell a frame
    it may *extend* from one it may not.  A chain of ``LET``s -- which is
    exactly what a group of ``def``s desugars to -- shares one frame, so
    that a closure built for the first binding can see the last.  That
    is what makes mutual recursion work; see the LET handler.

    M23: a frame holds only its own bindings and points at the frame it
    extends.  A lookup that misses here falls through to ``parent``
    (``__missing__``), so opening a frame is O(1) where it used to copy
    the whole environment -- ninety entries per call, in the prelude.
    ``in`` tests this frame alone; `bound` asks the whole chain.
    """

    __slots__ = ("parent",)

    # No ``__init__``: a Python-level constructor is a call per frame,
    # and a frame is opened per LOVA call.  ``open`` is the constructor.

    @staticmethod
    def open(parent: Any) -> "Scope":
        scope = Scope()
        scope.parent = parent
        return scope

    def __missing__(self, key: int) -> Any:
        # One Python call per miss however deep the chain: walk the
        # frames here rather than recurse through each one's miss.
        env = self.parent
        while env.__class__ is Scope:
            if key in env:
                return dict.__getitem__(env, key)
            env = env.parent
        if env is None:
            raise KeyError(key)
        return env[key]          # a plain dict at the root, or its KeyError

    def bound(self, key: int) -> bool:
        """True iff ``key`` is bound in this frame or one it extends."""
        env: Any = self
        while env is not None:
            if key in env:
                return True
            env = env.parent if isinstance(env, Scope) else None
        return False


def flatten_env(env: Any) -> Dict[int, Any]:
    """Every binding visible from ``env``, inner frames winning, as one dict."""
    frames = []
    while env is not None:
        frames.append(env)
        env = env.parent if isinstance(env, Scope) else None
    out: Dict[int, Any] = {}
    for frame in reversed(frames):
        out.update(frame)
    return out


def is_list_value(v: Any) -> bool:
    """True iff ``v`` is a LOVA list (type ``List``)."""
    return v is NIL_VALUE or isinstance(v, Cons)


def is_text_value(v: Any) -> bool:
    """True iff ``v`` is a text (M25): a Python ``str``."""
    return isinstance(v, str)


def _text_chars(v: Any, ctx: str) -> Any:
    """A text as the codepoint list a list operator expects."""
    return list_from([ord(ch) for ch in v])


def list_from(values) -> Any:
    """Build a LOVA list from a Python iterable, right to left."""
    out = NIL_VALUE
    for value in reversed(list(values)):
        out = Cons(head=value, tail=out)
    return out


def list_to_python(value: Any) -> list:
    """Unpack a LOVA list into a Python list.  Raises on a non-list.

    A text unpacks to its codepoints (M25): every consumer of a list
    reads a text as the list it stands for.
    """
    if isinstance(value, str):
        return [ord(ch) for ch in value]
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
    if isinstance(v, str):
        return v
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
    if is_map_value(v):
        raise DomainTrap(
            "type-violation",
            f"{ctx}: cannot write a map; write its `map-pairs`",
            {"operator": ctx, "got": "Map"},
            "iterate `(map-pairs m)` and write each entry",
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


_MISSING = object()


class MapValue:
    """A persistent map (M22): the sixth value kind.

    ``entries`` is keyed by a hashable rendering of the LOVA key and
    holds the original key with the value, so `map-pairs` gives keys
    back as they were.

    M22 made `map-put` persistent by copying the dict, O(n) a put,
    which was fast enough by a factor of a hundred over the
    association list -- and quadratic in the number of keys. On
    CPython the copy is a memcpy and hides behind the interpreter at
    any size measured; under PyPy it was half the time of a count over
    a large vocabulary (journal M23). M23 keeps one dict per family of
    versions and moves it to
    whichever version is asked for (Baker's rerooting, as OCaml's
    persistent arrays): the newest version owns the dict; an older
    one holds the single difference that leads back toward it, and is
    made the owner again by undoing that chain when it is read. A
    program that threads one map through a fold -- the shape every
    count has -- never reroots, and pays O(1) a put and a get. A
    program that keeps old versions and reads them alternately pays
    the length of the chain between them each time, which is what the
    copy cost before, at worst.
    """

    __slots__ = ("_entries", "_diff")

    def __init__(self, entries: Optional[Dict[Any, Tuple[Any, Any]]] = None):
        self._entries: Optional[Dict[Any, Tuple[Any, Any]]] = (
            {} if entries is None else entries)
        # For a version that does not own the dict: (hashed key, the
        # entry this version has there or _MISSING, the version one
        # step nearer the owner).
        self._diff: Optional[Tuple[Any, Any, "MapValue"]] = None

    @property
    def entries(self) -> Dict[Any, Tuple[Any, Any]]:
        if self._diff is not None:
            self._reroot()
        return self._entries          # type: ignore[return-value]

    def _reroot(self) -> None:
        """Make this version the owner of the dict."""
        path = []
        version: MapValue = self
        while version._diff is not None:
            path.append(version)
            version = version._diff[2]
        entries = version._entries
        owner = version
        for version in reversed(path):
            hashed, wanted, _ = version._diff      # type: ignore[misc]
            current = entries.get(hashed, _MISSING)
            if wanted is _MISSING:
                del entries[hashed]
            else:
                entries[hashed] = wanted
            owner._entries, owner._diff = None, (hashed, current, version)
            version._entries, version._diff = entries, None
            owner = version

    def put(self, hashed: Any, key: Any, value: Any) -> "MapValue":
        """A new version with ``key`` bound; this one keeps its meaning."""
        entries = self.entries
        previous = entries.get(hashed, _MISSING)
        entries[hashed] = (key, value)
        successor = MapValue(entries)
        self._entries, self._diff = None, (hashed, previous, successor)
        return successor

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MapValue) and self.entries == other.entries

    __hash__ = None                   # type: ignore[assignment]

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"MapValue({self.entries!r})"


def is_map_value(v: Any) -> bool:
    return isinstance(v, MapValue)


def _map_key(v: Any, ctx: str) -> Any:
    """A hashable stand-in for a key: an integer, or a list as a tuple."""
    if isinstance(v, int) and not isinstance(v, bool):
        return ("i", v)
    if isinstance(v, str):
        return ("l", tuple(("i", ord(ch)) for ch in v))     # as its codepoint list
    if is_list_value(v):
        return ("l", tuple(_map_key(item, ctx) for item in list_to_python(v)))
    raise DomainTrap(
        "type-violation",
        f"{ctx}: a map key is an integer or a list, not {type(v).__name__}",
        {"operator": ctx, "got": type(v).__name__},
        "key the map by an integer or by text",
    )


def _as_map(v: Any, ctx: str) -> MapValue:
    """A Map, or a list of `(list k v)` pairs read as one."""
    if isinstance(v, MapValue):
        return v
    if is_list_value(v):
        out = MapValue()
        for entry in list_to_python(v):
            if not is_list_value(entry):
                raise DomainTrap(
                    "type-violation",
                    f"{ctx}: a map from a list needs `(list key value)` pairs",
                    {"operator": ctx, "got": type(entry).__name__},
                    "build the list with `(list (list k v) ...)`",
                )
            pair = list_to_python(entry)
            if len(pair) != 2:
                raise DomainTrap(
                    "domain-error",
                    f"{ctx}: a map entry is a two-element list, got {len(pair)}",
                    {"operator": ctx, "length": len(pair)},
                    "give each entry as `(list key value)`",
                )
            out.entries[_map_key(pair[0], ctx)] = (pair[0], pair[1])
        return out
    raise DomainTrap(
        "type-violation",
        f"{ctx}: expected a Map or a list of pairs, got {v!r}",
        {"operator": ctx, "expected": "Map"},
        "start from `(nil)` and `map-put` into it",
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
    """Coerce a runtime value to List, or fail loudly.  A text is its codepoints."""
    if is_list_value(v):
        return v
    if isinstance(v, str):
        return _text_chars(v, ctx)
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
    # M23 -- each node's compiled closure, keyed by the node's id and
    # holding the node so the id cannot be reused while cached.  Per
    # run, not per node: a tree edited in place between runs (`mutate`
    # copies first, but a Python caller need not) is recompiled.  The
    # node path of a trap is read off the Python stack at trap time
    # (`_node_path`) instead of being maintained per node.
    code_cache: Dict[int, Any] = field(default_factory=dict)
    # M9 — abstraction ceilings.  ``call_depth`` counts LOVA-level
    # function applications currently on the stack; ``steps`` counts
    # every evaluated node in the run.  Both ceilings are always on,
    # independent of whether the program declares a BUDGET.
    call_depth: int = 0
    steps: int = 0
    # The compiled closure of the node a LET is about to evaluate as its
    # *body*, and None otherwise.  A LET that finds its own closure here
    # is directly nested in another's body, so the two belong to one
    # binding group and share a frame.  Anything else -- a LET in an
    # argument position, a LET inside a lambda body -- finds another
    # node's closure, or None, and opens its own frame.  Until M23 this
    # was a flag that every node had to clear; naming the node lets the
    # flag be left alone by everything but LET.
    let_chain: Any = None
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
    # M19 -- capabilities.  ``granted`` is what the host allows this run
    # (the CLI's ``--allow``; nothing by default, so a test or an
    # experiment cannot touch the world by accident).  ``caps`` is what
    # the innermost `external-boundary` declared, and is what an effect
    # operator checks.  ``clock`` may be replaced for a reproducible run.
    granted: int = 0
    caps: int = 0
    # Inside some boundary, lexically.  A nested boundary may only narrow
    # (Q70); a closure carries the flag with its mask, so the rule is the
    # compiler's rule wherever the closure is applied.
    enclosed: bool = False
    clock: Any = None
    # M21 -- the network.  The host names the places: ``net_send_to`` is
    # the set of "host:port" strings a datagram may go to ("*" for any),
    # ``net_listen_on`` the ports `net-recv` may bind.  ``net_sockets``
    # caches a bound socket per port so consecutive receives share one
    # queue (a test may pre-bind and inject one); ``net_timeout`` is how
    # long a receive waits before yielding `nil`.
    net_send_to: Any = None
    net_listen_on: Any = None
    net_sockets: Dict[int, Any] = field(default_factory=dict)
    net_timeout: float = 5.0

    def write(self, text: str) -> None:
        """Emit ``text``, recording it and forwarding it if asked."""
        self.output.append(text)
        if self.out_stream is not None:
            self.out_stream.write(text)

    def read_line(self) -> Optional[str]:
        """The next input line, terminator included, or None at the end.

        Queued lines first, then ``input_source`` if one is set -- which
        is how the CLI attaches a terminal without letting a test or a
        generated program ever block on one.

        M23 (Q78): the line keeps its newline.  Until then it was
        stripped, and an empty line -- the empty string, which *is* the
        empty list -- was indistinguishable from the end of the input,
        so an interactive program could not ask again on Enter.  Now a
        blank line is `(10)`, and `nil` means nothing arrived.  A
        queued line without a terminator is passed as it is.
        """
        if self.input_lines:
            return self.input_lines.pop(0)
        if self.input_source is not None:
            line = self.input_source()
            if line:
                return line
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
    if _NEEDS_BIG_STACK and not getattr(_big_stack, "on", False):
        return _evaluate_on_big_stack(node, rt)
    # A run compiles what it meets (M23).  A tree the caller edited in
    # place since the last run must not meet its old closures, so the
    # cache is a run's, not the runtime's.
    rt.code_cache.clear()
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


def _evaluate_on_big_stack(node: Node, rt: Runtime) -> Any:
    """Run `evaluate` on a thread whose stack fits ``rt.max_call_depth``.

    The thread is a daemon so an interrupted host process can still
    exit; the result or the exception crosses back to the caller.
    """
    outcome: List[Any] = []

    def go() -> None:
        _big_stack.on = True
        try:
            outcome.append((True, evaluate(node, rt)))
        except BaseException as exc:      # re-raised below, on the caller's thread
            outcome.append((False, exc))

    wanted = max(_STACK_FLOOR, rt.max_call_depth * _STACK_BYTES_PER_FRAME)
    previous = threading.stack_size()
    try:
        try:
            threading.stack_size(wanted)
        except ValueError:                # more than the host allows
            threading.stack_size(_STACK_FLOOR)
        worker = threading.Thread(target=go, daemon=True)
        worker.start()
    finally:
        threading.stack_size(previous)
    # A join with no timeout cannot be interrupted on Windows; polling
    # keeps Ctrl-C working in the CLI and the REPL.
    while worker.is_alive():
        worker.join(0.05)
    ok, value = outcome[0]
    if ok:
        return value
    raise value


def _node_path(rt: Runtime) -> List[Node]:
    """The nodes being evaluated under ``rt``, outermost first.

    Read off the Python stack: every compiled node closure is named
    ``_n_*`` and closes over its ``node``, so the path a trap needs is
    already there and costs nothing until a trap asks for it (M23).
    Frames of another runtime -- a body-offender probe, a `trace`
    sandbox -- are skipped by identity.
    """
    path: List[Node] = []
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_name.startswith("_n_"):
            local = frame.f_locals
            if local.get("rt") is rt and "node" in local:
                path.append(local["node"])
        frame = frame.f_back
    path.reverse()
    return path


def _trapped(trap: Any, rt: Runtime, node: Node) -> None:
    """Enrich a trap on its first catch (the innermost node); no-op after.

    ``node`` is unused here: it is named by the caller so that the
    caller's frame carries it for `_node_path`.
    """
    if not trap.anomaly.get("_enriched"):
        _enrich_trap(trap, rt)
        trap.anomaly["_enriched"] = True


def _enrich_trap(trap, rt: Runtime) -> None:
    """Attach positional + repair-hint fields to an in-flight trap."""
    from core.conservation import enrich_anomaly
    from core.observability import suggest_alternatives

    path = _node_path(rt)
    top = path[-1] if path else None
    op = top.op if top is not None else None
    alternatives = suggest_alternatives(op) if op is not None else ()
    # M24: the innermost node that came from the program's own text.
    # A fault inside a library function reports the call that reached
    # it, which is the expression the author can change.
    for n in reversed(path):
        span = getattr(n, "span", None)
        if span is not None:
            trap.anomaly["span"] = span
            break
    enrich_anomaly(
        trap.anomaly,
        position_path=tuple(n.op for n in path),
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


def _net_address(text: str, ctx: str) -> Tuple[str, int]:
    """``"host:port"`` to a (host, port) pair, or a structured fault."""
    host, sep, port_text = text.rpartition(":")
    if not sep or not host or not port_text.isdigit() or not 0 < int(port_text) < 65536:
        raise DomainTrap(
            "domain-error", f"{ctx}: not an address: {text!r}",
            {"operator": ctx, "address": text},
            f'give {ctx} an address of the form "host:port"',
        )
    return host, int(port_text)


def _require_capability(rt: Runtime, op: int, name: str) -> None:
    """Trap unless the innermost boundary declared ``op``'s capability.

    The compiler refuses a program that gets here with a visible use;
    what reaches the runtime is code the static pass could not see --
    a quoted program, text `read` at run time -- and the rule is the
    same for it.
    """
    bit = CAPABILITY_OF[op]
    if not rt.caps & bit:
        needed = capability_names(bit)[0]
        raise DomainTrap(
            "capability-denied",
            f"{name}: used outside a boundary that declares {needed}",
            {"operator": name, "needs": needed,
             "declared": capability_names(rt.caps)},
            f'wrap the use in (boundary "{needed}" ...)',
        )


def _call(fn: Any, argument: Any, rt: Runtime) -> Any:
    """Apply a LOVA function value to one argument.

    Closures consume a call frame (and so are bounded by
    ``max_call_depth``); ``LoopFn`` iterates in Python and consumes
    none, which is what makes an unbounded loop expressible without an
    unbounded stack.
    """
    if fn.__class__ is LoopFn:
        value = argument
        pred, step = fn.pred, fn.step
        while True:
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            verdict = _call(pred, value, rt)
            if verdict.__class__ is not int:
                verdict = _as_int(verdict, "loop-until predicate")
            if verdict != 0:
                return value
            value = _call(step, value, rt)

    if fn.__class__ is not Closure:
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
    # A call frame extends the closure's environment by one binding.
    # A LET directly in the body opens its own frame rather than
    # extending this one: `let_chain` names the body of a LET, and a
    # lambda body is not one.
    scope = Scope()
    scope.parent = fn.env
    scope[fn.param] = argument
    saved_env = rt.env
    saved_caps = rt.caps
    saved_enclosed = rt.enclosed
    rt.env = scope
    rt.caps = fn.caps
    rt.enclosed = fn.enclosed
    try:
        code = fn.code
        if code is None:
            code = fn.code = _code(fn.body, rt)
        return code(rt)
    finally:
        rt.env = saved_env
        rt.caps = saved_caps
        rt.enclosed = saved_enclosed
        rt.call_depth -= 1


def _eval(node: Node, rt: Runtime) -> Any:
    """Evaluate one node under ``rt``.

    M23: a tree is compiled to Python closures -- one per node, the
    children's closures bound in -- the first time a run meets it
    (`_code`), and evaluation is a call.  The tree walk of M1-M22
    (`node.op`, a handler table, `node.args[i]` per child, a node stack
    pushed and popped per node) was ~45% of the per-node cost; see
    journal M23.  What every node still owes is the accounting: the
    active budget and the step ceiling.

    The handlers below (`_op_*`) remain the definition of each operator
    and run unchanged, wrapped, for every operator without a template
    of its own; a template is a hand-inlined handler for an operator
    that runs often.  Both call back through here for a child that is
    not theirs, which is how a quoted program, text `read` at run time
    or a probe's replacement tree is compiled on first sight.
    """
    entry = rt.code_cache.get(id(node))
    if entry is not None and entry[0] is node:
        return entry[1](rt)
    return _code(node, rt)(rt)


def _code(node: Node, rt: Runtime) -> Any:
    """The compiled closure for ``node``, built and cached on first use."""
    cache = rt.code_cache
    entry = cache.get(id(node))
    if entry is not None and entry[0] is node:
        return entry[1]
    fn = _COMPILERS.get(node.op, _compile_generic)(node, rt)
    cache[id(node)] = (node, fn)
    return fn


def _unbound(name_id: Any, rt: Runtime) -> DomainTrap:
    return DomainTrap(
        "unbound-ref", f"unbound ref: {name_id}",
        {"name_id": name_id, "bound_names": sorted(flatten_env(rt.env))},
        "bind the name with a `let`, or reference one that is bound",
    )


# Every template below has the same shape: the accounting first, inside
# the `try` so a step or budget trap raised there is enriched at this
# node; then the operator; and an `except` that names ``node`` so that
# `_node_path` can read it off the frame.  A literal takes no `except`
# and closes over no node, as it took no frame on the old node stack:
# the step trap it can raise is enriched by its parent.

def _compile_generic(node: Node, rt: Runtime) -> Any:
    handler = _HANDLERS.get(node.op)
    if handler is None:
        def _n_unimplemented(rt: Runtime) -> Any:
            try:
                if rt.budget_stack:
                    rt.budget_stack[-1].charge(1)
                rt.steps += 1
                if rt.steps > rt.max_steps:
                    raise StepTrap(steps=rt.steps, limit=rt.max_steps)
                return _eval_unimplemented(node, rt)
            except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
                _trapped(trap, rt, node)
                raise
        return _n_unimplemented

    def _n_generic(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            return handler(node, rt, False)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_generic


def _compile_LIT_INT(node: Node, rt: Runtime) -> Any:
    value = int(node.args[0])

    def _n_lit(rt: Runtime) -> Any:
        if rt.budget_stack:
            rt.budget_stack[-1].charge(1)
        rt.steps += 1
        if rt.steps > rt.max_steps:
            raise StepTrap(steps=rt.steps, limit=rt.max_steps)
        return value
    return _n_lit


def _compile_LIT_TEXT(node: Node, rt: Runtime) -> Any:
    value = node.args[0]

    def _n_text(rt: Runtime) -> Any:
        if rt.budget_stack:
            rt.budget_stack[-1].charge(1)
        rt.steps += 1
        if rt.steps > rt.max_steps:
            raise StepTrap(steps=rt.steps, limit=rt.max_steps)
        return value
    return _n_text


def _compile_REF(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1 or node.args[0].op != LIT_INT:
        return _compile_generic(node, rt)
    name_id = node.args[0].args[0]

    def _n_ref(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            return rt.env[name_id]
        except KeyError:
            trap = _unbound(name_id, rt)
            _trapped(trap, rt, node)          # this frame is the ref's
            raise trap from None
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_ref


def _compile_IDENTITY(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1:
        return _compile_generic(node, rt)
    inner = _code(node.args[0], rt)

    def _n_identity(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            return inner(rt)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_identity


def _compile_MERGE(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    left, right = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_merge(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            a = left(rt)
            if a.__class__ is not int:
                a = _as_int(a, "merge")
            b = right(rt)
            if b.__class__ is not int:
                b = _as_int(b, "merge")
            return a + b
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_merge


def _compile_DEVIATION(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    left, right = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_deviation(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            a = left(rt)
            b = right(rt)
            if a.__class__ is str or b.__class__ is str:
                return 0 if _as_text(a, "deviation") == _as_text(b, "deviation") else 1
            if a.__class__ is not int:
                a = _as_int(a, "deviation")
            if b.__class__ is not int:
                b = _as_int(b, "deviation")
            return a - b
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_deviation


def _compile_THRESHOLD(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1:
        return _compile_generic(node, rt)
    inner = _code(node.args[0], rt)

    def _n_threshold(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            x = inner(rt)
            if x.__class__ is not int:
                x = _as_int(x, "threshold")
            return 1 if x > 0 else 0
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_threshold


def _compile_MUL(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    left, right = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_mul(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            a = left(rt)
            if a.__class__ is not int:
                a = _as_int(a, "mul")
            b = right(rt)
            if b.__class__ is not int:
                b = _as_int(b, "mul")
            if a.bit_length() + b.bit_length() > MAX_INT_BITS:
                raise DomainTrap(
                    "domain-error",
                    f"mul result would exceed MAX_INT_BITS={MAX_INT_BITS} "
                    f"({a.bit_length()} + {b.bit_length()} bits)",
                    {"operator": "mul", "limit": MAX_INT_BITS},
                    "multiply smaller numbers",
                )
            return a * b
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_mul


def _compile_DIV(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    left, right = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_div(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            a = left(rt)
            if a.__class__ is not int:
                a = _as_int(a, "div")
            b = right(rt)
            if b.__class__ is not int:
                b = _as_int(b, "div")
            if b == 0:
                raise DomainTrap(
                    "domain-error", "div: division by zero",
                    {"operator": "div"},
                    "guard the divisor with `(if d (div a d) fallback)`",
                )
            return a // b
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_div


def _compile_MOD(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    left, right = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_mod(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            a = left(rt)
            if a.__class__ is not int:
                a = _as_int(a, "mod")
            b = right(rt)
            if b.__class__ is not int:
                b = _as_int(b, "mod")
            if b == 0:
                raise DomainTrap(
                    "domain-error", "mod: division by zero",
                    {"operator": "mod"},
                    "guard the divisor with `(if d (mod a d) fallback)`",
                )
            return a % b
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_mod


def _compile_NIL(node: Node, rt: Runtime) -> Any:
    def _n_nil(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            return NIL_VALUE
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_nil


def _compile_CONS(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    first, second = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_cons(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            element = first(rt)
            rest = second(rt)
            if rest.__class__ is str:
                # A codepoint onto a text is a text; anything else makes a list.
                if element.__class__ is int and 0 <= element <= 0x10FFFF:
                    return chr(element) + rest
                rest = _text_chars(rest, "cons")
            elif rest is not NIL_VALUE and rest.__class__ is not Cons:
                rest = _as_list(rest, "cons")
            return Cons(element, rest)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_cons


def _compile_HEAD(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1:
        return _compile_generic(node, rt)
    inner = _code(node.args[0], rt)

    def _n_head(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            target = inner(rt)
            if target.__class__ is Cons:
                return target.head
            if target.__class__ is str and target:
                return ord(target[0])
            target = _as_list(target, "head")
            if target is NIL_VALUE:
                raise DomainTrap(
                    "domain-error",
                    "head: the list is empty; guard with `nil?` before "
                    "taking a head",
                    {"operator": "head"},
                    "guard with `(if (nil? xs) fallback (head xs))`",
                )
            return target.head
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_head


def _compile_TAIL(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1:
        return _compile_generic(node, rt)
    inner = _code(node.args[0], rt)

    def _n_tail(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            target = inner(rt)
            if target.__class__ is Cons:
                return target.tail
            if target.__class__ is str and target:
                return target[1:]
            target = _as_list(target, "tail")
            if target is NIL_VALUE:
                raise DomainTrap(
                    "domain-error",
                    "tail: the list is empty; guard with `nil?` before "
                    "taking a tail",
                    {"operator": "tail"},
                    "guard with `(if (nil? xs) fallback (tail xs))`",
                )
            return target.tail
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_tail


def _compile_IS_NIL(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 1:
        return _compile_generic(node, rt)
    inner = _code(node.args[0], rt)

    def _n_is_nil(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            target = inner(rt)
            if target is NIL_VALUE:
                return 1
            if target.__class__ is Cons:
                return 0
            if target.__class__ is str:
                return 1 if not target else 0
            _as_list(target, "nil?")
            return 0
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_is_nil


def _compile_MAP_PUT(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 3:
        return _compile_generic(node, rt)
    cm, ck, cv = (_code(a, rt) for a in node.args)

    def _n_map_put(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            base = cm(rt)
            if base.__class__ is not MapValue:
                base = _as_map(base, "map-put")
            key = ck(rt)
            value = cv(rt)
            return base.put(_map_key(key, "map-put"), key, value)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_map_put


def _compile_MAP_GET(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 3:
        return _compile_generic(node, rt)
    cm, ck, cd = (_code(a, rt) for a in node.args)

    def _n_map_get(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            m = cm(rt)
            if m.__class__ is not MapValue:
                m = _as_map(m, "map-get")
            key = ck(rt)
            hit = m.entries.get(_map_key(key, "map-get"))
            if hit is None:
                return cd(rt)                       # the default, only when needed
            return hit[1]
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_map_get


def _compile_SEQ(node: Node, rt: Runtime) -> Any:
    codes = tuple(_code(child, rt) for child in node.args)

    def _n_seq(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            last = 0
            for code in codes:
                last = code(rt)
            return last
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_seq


def _compile_IF_SURPRISE(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 3:
        return _compile_generic(node, rt)
    test, then, otherwise = (_code(a, rt) for a in node.args)

    def _n_if(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            s = test(rt)
            if s.__class__ is not int:
                s = _as_int(s, "if-surprise")
            return then(rt) if s != 0 else otherwise(rt)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_if


def _compile_LET(node: Node, rt: Runtime) -> Any:
    # The semantics are the LET handler's, inlined; read it first.
    if len(node.args) != 3 or node.args[0].op != LIT_INT:
        return _compile_generic(node, rt)
    name_id = int(node.args[0].args[0])
    value_code, body_code = _code(node.args[1], rt), _code(node.args[2], rt)

    def _n_let(rt: Runtime) -> Any:
        try:
            chained = rt.let_chain is _n_let
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            saved_env = rt.env
            extend = (chained and saved_env.__class__ is Scope
                      and not saved_env.bound(name_id))
            if extend:
                scope = saved_env
            else:
                scope = Scope()
                scope.parent = saved_env
                rt.env = scope
            try:
                value = value_code(rt)
                if value.__class__ is Closure and value.name is None:
                    value.name = name_id
                scope[name_id] = value
                rt.let_chain = body_code     # the body may continue the group
                return body_code(rt)
            finally:
                rt.let_chain = None
                if not extend:
                    rt.env = saved_env
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_let


def _compile_LAMBDA(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2 or node.args[0].op != LIT_INT:
        return _compile_generic(node, rt)
    param = int(node.args[0].args[0])
    body = node.args[1]
    body_code = _code(body, rt)

    def _n_lambda(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            return Closure(param=param, body=body, env=rt.env,
                           caps=rt.caps, enclosed=rt.enclosed,
                           code=body_code)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_lambda


def _compile_APPLY(node: Node, rt: Runtime) -> Any:
    if not node.args:
        return _compile_generic(node, rt)
    codes = tuple(_code(child, rt) for child in node.args)
    head, arguments = codes[0], codes[1:]

    def _n_apply(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            fn = head(rt)
            for code in arguments:
                fn = _call(fn, code(rt), rt)
            return fn
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_apply


def _compile_LOOP_UNTIL(node: Node, rt: Runtime) -> Any:
    if len(node.args) != 2:
        return _compile_generic(node, rt)
    pred_code, step_code = _code(node.args[0], rt), _code(node.args[1], rt)

    def _n_loop_until(rt: Runtime) -> Any:
        try:
            if rt.budget_stack:
                rt.budget_stack[-1].charge(1)
            rt.steps += 1
            if rt.steps > rt.max_steps:
                raise StepTrap(steps=rt.steps, limit=rt.max_steps)
            pred = pred_code(rt)
            step = step_code(rt)
            if not is_callable_value(pred) or not is_callable_value(step):
                raise DomainTrap(
                    "type-violation",
                    "LOOP_UNTIL: both slots must be functions (type Fn); got "
                    f"pred={pred!r}, step={step!r}",
                    {"operator": "loop-until", "expected": "Fn"},
                    "pass two lambdas: a predicate and a step",
                )
            return LoopFn(pred=pred, step=step)
        except (BudgetTrap, DeltaTrap, DomainTrap) as trap:
            _trapped(trap, rt, node)
            raise
    return _n_loop_until


_COMPILERS = {
    LIT_INT: _compile_LIT_INT,
    LIT_TEXT: _compile_LIT_TEXT,
    REF: _compile_REF,
    IDENTITY: _compile_IDENTITY,
    MERGE: _compile_MERGE,
    DEVIATION: _compile_DEVIATION,
    THRESHOLD: _compile_THRESHOLD,
    MUL: _compile_MUL,
    DIV: _compile_DIV,
    MOD: _compile_MOD,
    NIL: _compile_NIL,
    CONS: _compile_CONS,
    HEAD: _compile_HEAD,
    TAIL: _compile_TAIL,
    IS_NIL: _compile_IS_NIL,
    MAP_PUT: _compile_MAP_PUT,
    MAP_GET: _compile_MAP_GET,
    SEQ: _compile_SEQ,
    IF_SURPRISE: _compile_IF_SURPRISE,
    LET: _compile_LET,
    LAMBDA: _compile_LAMBDA,
    APPLY: _compile_APPLY,
    LOOP_UNTIL: _compile_LOOP_UNTIL,
}


def _op_LIT_INT(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return int(node.args[0])


def _op_IDENTITY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return _eval(node.args[0], rt)


def _op_MERGE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    a = _as_int(_eval(node.args[0], rt), "merge")
    b = _as_int(_eval(node.args[1], rt), "merge")
    return a + b


def _op_PARTITION(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    n = _as_int(_eval(node.args[0], rt), "partition")
    # Milestone 1: return the first non-trivial 2-split, not a tuple.
    # Stage 1 uses a convention: partition is represented as the pair
    # (⌊n/2⌋, n - ⌊n/2⌋); we emit only ⌊n/2⌋ for integer-scalar return.
    # Subsequent milestones revisit this when we have Pair types.
    return n // 2


def _op_P(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return partition_number(_as_int(_eval(node.args[0], rt), "p"))


def _op_TAU(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return tau(_as_int(_eval(node.args[0], rt), "tau"))


def _op_SIGMA(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return sigma(_as_int(_eval(node.args[0], rt), "sigma"))


def _op_GCD(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    a = _as_int(_eval(node.args[0], rt), "gcd")
    b = _as_int(_eval(node.args[1], rt), "gcd")
    return _gcd(a, b)


def _op_MOBIUS(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return mobius(_as_int(_eval(node.args[0], rt), "mobius"))


def _op_MUL(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_DIV(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_MOD(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


# --- text (M25, Q85) ---------------------------------------------------------
#
# A text is a Python str.  Where an operator says Value it takes a text
# or a codepoint list (`_as_text`), so a program that still holds its
# text as a list loses nothing.  Separators may be a text or a codepoint.

def _sep(v: Any, ctx: str) -> str:
    if isinstance(v, int) and not isinstance(v, bool):
        return chr(v)
    return _as_text(v, ctx)


def _op_LIT_TEXT(node: Node, rt: Runtime, chained: bool) -> Any:
    return node.args[0]


def _op_TEXT_LEN(node: Node, rt: Runtime, chained: bool) -> Any:
    v = _eval(node.args[0], rt)
    if isinstance(v, str):
        return len(v)
    return len(list_to_python(_as_list(v, "text-len")))


def _op_TEXT_CAT(node: Node, rt: Runtime, chained: bool) -> Any:
    return _as_text(_eval(node.args[0], rt), "text-cat") + _as_text(_eval(node.args[1], rt), "text-cat")


def _op_TEXT_SLICE(node: Node, rt: Runtime, chained: bool) -> Any:
    t = _as_text(_eval(node.args[0], rt), "text-slice")
    start = _as_int(_eval(node.args[1], rt), "text-slice")
    end = _as_int(_eval(node.args[2], rt), "text-slice")
    return t[max(0, start):max(0, end)]


def _op_TEXT_FIND(node: Node, rt: Runtime, chained: bool) -> Any:
    t = _as_text(_eval(node.args[0], rt), "text-find")
    needle = _sep(_eval(node.args[1], rt), "text-find")
    return t.find(needle)


def _op_TEXT_SPLIT(node: Node, rt: Runtime, chained: bool) -> Any:
    t = _as_text(_eval(node.args[0], rt), "text-split")
    sep = _sep(_eval(node.args[1], rt), "text-split")
    return list_from(t.split() if sep == "" else t.split(sep))


def _op_TEXT_JOIN(node: Node, rt: Runtime, chained: bool) -> Any:
    parts = _eval(node.args[0], rt)
    sep = _sep(_eval(node.args[1], rt), "text-join")
    if isinstance(parts, str):
        parts = _text_chars(parts, "text-join")
    return sep.join(_as_text(p, "text-join") for p in list_to_python(_as_list(parts, "text-join")))


def _op_TEXT_CHARS(node: Node, rt: Runtime, chained: bool) -> Any:
    v = _eval(node.args[0], rt)
    return _text_chars(v, "text-chars") if isinstance(v, str) else _as_list(v, "text-chars")


def _op_TEXT_OF_CHARS(node: Node, rt: Runtime, chained: bool) -> Any:
    return _as_text(_eval(node.args[0], rt), "text-of-chars")


def _op_TEXT_CMP(node: Node, rt: Runtime, chained: bool) -> Any:
    a = _eval(node.args[0], rt)
    b = _eval(node.args[1], rt)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    # Element-wise on the codepoints, so two lists of integers compare
    # too, whatever the integers are.
    xs = list_to_python(a) if not isinstance(a, str) else [ord(c) for c in a]
    ys = list_to_python(b) if not isinstance(b, str) else [ord(c) for c in b]
    return (xs > ys) - (xs < ys)


def _op_TEXT_INT(node: Node, rt: Runtime, chained: bool) -> Any:
    t = _as_text(_eval(node.args[0], rt), "text-int").strip()
    body = t[1:] if t.startswith("-") else t
    if not body or not body.isdigit():
        # The prelude's `parse-int` has signalled 16 for this since M22;
        # the operator keeps the contract so `try` and `when-anomaly`
        # handlers written against it keep working.
        raise DomainTrap(
            "signalled", f"text-int: not a number: {t[:40]!r}",
            {"operator": "text-int", "code": 16, "text": t[:40]},
            "give `text-int` decimal digits, with an optional leading -",
        )
    return int(t)


def _op_INT_TEXT(node: Node, rt: Runtime, chained: bool) -> Any:
    return str(_as_int(_eval(node.args[0], rt), "int-text"))


def _op_IS_TEXT(node: Node, rt: Runtime, chained: bool) -> Any:
    return 1 if isinstance(_eval(node.args[0], rt), str) else 0


def _op_TEXT_TRIM(node: Node, rt: Runtime, chained: bool) -> Any:
    return _as_text(_eval(node.args[0], rt), "text-trim").strip()


def _op_NIL(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    return NIL_VALUE


def _op_CONS(node: Node, rt: Runtime, chained: bool) -> Any:
    # Any value may be an element (M17): an integer, a list, a
    # program, a function.  Only the tail has to be a list.
    element = _eval(node.args[0], rt)
    rest = _eval(node.args[1], rt)
    if isinstance(rest, str):
        if isinstance(element, int) and not isinstance(element, bool) and 0 <= element <= 0x10FFFF:
            return chr(element) + rest
        rest = _text_chars(rest, "cons")
    elif rest is not NIL_VALUE and not isinstance(rest, Cons):
        rest = _as_list(rest, "cons")          # the structured fault
    return Cons(element, rest)


def _op_HEAD(node: Node, rt: Runtime, chained: bool) -> Any:
    target = _eval(node.args[0], rt)
    if isinstance(target, Cons):
        return target.head
    target = _as_list(target, "head")
    if target is NIL_VALUE:
        raise DomainTrap(
            "domain-error",
            "head: the list is empty; guard with `nil?` before taking a "
            "head",
            {"operator": "head"},
            "guard with `(if (nil? xs) fallback (head xs))`",
        )
    return target.head


def _op_TAIL(node: Node, rt: Runtime, chained: bool) -> Any:
    target = _eval(node.args[0], rt)
    if isinstance(target, Cons):
        return target.tail
    target = _as_list(target, "tail")
    if target is NIL_VALUE:
        raise DomainTrap(
            "domain-error",
            "tail: the list is empty; guard with `nil?` before taking a "
            "tail",
            {"operator": "tail"},
            "guard with `(if (nil? xs) fallback (tail xs))`",
        )
    return target.tail


def _op_IS_NIL(node: Node, rt: Runtime, chained: bool) -> Any:
    target = _eval(node.args[0], rt)
    if target is NIL_VALUE:
        return 1
    if isinstance(target, Cons):
        return 0
    _as_list(target, "nil?")                  # raises the structured fault
    return 0


def _op_QUOTE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # The operand is not evaluated.  It is copied, so that registering
    # or mutating the value never reaches back into the program that
    # contains the quote.
    return _deep_copy_node(node.args[0])


def _op_EVAL(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Run a program value in the current environment.  Its steps and
    # budget charge to this run like any other node's, because it is
    # this run.
    program = _as_program(_eval(node.args[0], rt), "eval")
    return _eval(program, rt)


def _op_EXPLAIN(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Stage 3's human interface: a program, rendered as text -- which
    # in LOVA is a list of codepoints.  This is the Stage-1 surface
    # reached from *inside* the language for the first time.
    from core.surface import pretty
    program = _as_program(_eval(node.args[0], rt), "explain")
    return pretty(program)


def _op_READ(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_HASH(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Axiom 1, taken literally: the program *is* this integer.
    program = _as_program(_eval(node.args[0], rt), "hash")
    return int.from_bytes(encode(program), "big")


def _op_UID(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    program = _as_program(_eval(node.args[0], rt), "uid")
    return getattr(program, "uid", None) or 0


def _op_GENERATION(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    program = _as_program(_eval(node.args[0], rt), "generation")
    uid = getattr(program, "uid", None)
    return rt.lineage.record(uid).generation if uid else 0


def _op_ANCESTOR_OF(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    a = _as_program(_eval(node.args[0], rt), "ancestor-of")
    b = _as_program(_eval(node.args[1], rt), "ancestor-of")
    ua, ub = getattr(a, "uid", None), getattr(b, "uid", None)
    if not ua or not ub:
        return 0
    return 1 if rt.lineage.is_ancestor_of(ua, ub) else 0


def _op_LINEAGE_QUERY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # self -> parent -> ... -> root, as uids.  Empty for an
    # unregistered program: it has no history yet.
    program = _as_program(_eval(node.args[0], rt), "lineage-query")
    uid = getattr(program, "uid", None)
    if not uid:
        return NIL_VALUE
    return list_from([rec.uid for rec in rt.lineage.ancestors(uid)])


def _op_WHY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Why does this program exist?  Its mutation kind and notes, as
    # text.  The question Axiom 5 promised the language could answer.
    program = _as_program(_eval(node.args[0], rt), "why")
    uid = getattr(program, "uid", None)
    if not uid:
        text = "unregistered"
    else:
        rec = rt.lineage.record(uid)
        text = f"{rec.mutation_kind} {rec.notes}".strip()
    return text


def _op_TRACE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Run a program in a sandbox and return its surprise trace -- the
    # deviations, in order.  Introspection over Axiom 7's signal.
    # The sandbox inherits what is left of this run's ceilings, so a
    # loop of traces cannot slip past MAX_STEPS.
    program = _as_program(_eval(node.args[0], rt), "trace")
    inner = Runtime(
        env=flatten_env(rt.env), lineage=rt.lineage,
        max_steps=max(1, rt.max_steps - rt.steps),
        max_call_depth=max(1, rt.max_call_depth - rt.call_depth),
    )
    try:
        _eval(program, inner)
    finally:
        rt.steps += inner.steps
    return list_from([event["deviation"] for event in inner.surprise.events])


def _op_CLONE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    program = _as_program(_eval(node.args[0], rt), "clone")
    _ensure_registered(program, rt)
    return rt.lineage.clone(program)


def _op_MUTATE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_DEFPOP(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_VARIANT(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_SELECT(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_FITNESS(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    pop = _as_population(_eval(node.args[0], rt), "fitness")
    return list_from(_score_population(pop, rt))


def _op_RETIRE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_EVOLVE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_WHEN_ANOMALY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_STDOUT(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    value = _eval(node.args[0], rt)
    text = _as_text(value, "stdout")
    rt.write(text)
    return len(text)


def _op_STDIN(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    line = rt.read_line()
    if line is None:
        return NIL_VALUE          # end of input, not an error
    return line                                   # newline included (Q78)


def _op_MAP_PUT(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    base = _as_map(_eval(node.args[0], rt), "map-put")
    key = _eval(node.args[1], rt)
    value = _eval(node.args[2], rt)
    return base.put(_map_key(key, "map-put"), key, value)


def _op_MAP_GET(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    m = _as_map(_eval(node.args[0], rt), "map-get")
    key = _eval(node.args[1], rt)
    hit = m.entries.get(_map_key(key, "map-get"))
    if hit is None:
        return _eval(node.args[2], rt)          # the default, only when needed
    return hit[1]


def _op_MAP_PAIRS(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    m = _as_map(_eval(node.args[0], rt), "map-pairs")
    return list_from([list_from([k, v]) for k, v in m.entries.values()])


def _op_SIGNAL(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    code = _as_int(_eval(node.args[0], rt), "signal")
    if code < FIRST_PROGRAM_SIGNAL:
        raise DomainTrap(
            "domain-error",
            f"signal: codes below {FIRST_PROGRAM_SIGNAL} are the substrate's own kinds",
            {"operator": "signal", "code": code, "first_allowed": FIRST_PROGRAM_SIGNAL},
            f"signal with a code of {FIRST_PROGRAM_SIGNAL} or more",
        )
    raise DomainTrap(
        "signalled", f"signal {code}", {"operator": "signal", "code": code},
        "catch it with `when-anomaly` and branch on the code",
    )


def _op_EXTERNAL_BOUNDARY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Declares what the body may do.  Checked twice: statically,
    # that every effect inside is declared here (the compiler's
    # capability pass), and now, that the host granted what is
    # declared.  A boundary the host refuses traps *before* the body
    # runs -- the declaration is the contract, and the trap is
    # where the contract meets the world.
    if node.args[0].op != LIT_INT:
        raise DomainTrap(
            "malformed", "external-boundary: capability slot must be a literal",
            {"operator": "external-boundary", "slot": 0},
            "put a literal capability mask in the first slot",
        )
    declared = int(node.args[0].args[0])
    excess = declared & ~rt.caps
    if rt.enclosed and excess:
        # Nested boundaries narrow (Q70).  Reachable only for code
        # the compiler did not see -- evaluated or read at run time.
        raise DomainTrap(
            "capability-denied",
            f"external-boundary: nested boundary declares "
            f"{capability_names(excess)} beyond the enclosing "
            f"{capability_names(rt.caps)}",
            {"operator": "external-boundary",
             "declared": capability_names(declared),
             "enclosing": capability_names(rt.caps),
             "excess": capability_names(excess)},
            "a nested boundary may only narrow; declare it in the enclosing one",
        )
    missing = declared & ~rt.granted
    if missing:
        raise DomainTrap(
            "capability-denied",
            f"external-boundary: declares {capability_names(declared)} "
            f"but the host granted {capability_names(rt.granted) or 'nothing'}",
            {"operator": "external-boundary",
             "declared": capability_names(declared),
             "granted": capability_names(rt.granted),
             "missing": capability_names(missing)},
            "run with `--allow " + ",".join(capability_names(missing))
            + "`, or declare less",
        )
    saved_caps, saved_enclosed = rt.caps, rt.enclosed
    rt.caps, rt.enclosed = declared, True
    try:
        return _eval(node.args[1], rt)
    finally:
        rt.caps, rt.enclosed = saved_caps, saved_enclosed


def _op_FS_READ(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    _require_capability(rt, FS_READ, "fs-read")
    path = _as_text(_eval(node.args[0], rt), "fs-read")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise DomainTrap(
            "domain-error", f"fs-read: {path}: {exc}",
            {"operator": "fs-read", "path": path,
             "reason": type(exc).__name__},
            "give `fs-read` the path of a readable UTF-8 file",
        ) from None
    return text


def _op_FS_WRITE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    _require_capability(rt, FS_WRITE, "fs-write")
    path = _as_text(_eval(node.args[0], rt), "fs-write")
    text = _as_text(_eval(node.args[1], rt), "fs-write")
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as exc:
        raise DomainTrap(
            "domain-error", f"fs-write: {path}: {exc}",
            {"operator": "fs-write", "path": path,
             "reason": type(exc).__name__},
            "give `fs-write` a path in a directory that exists",
        ) from None
    return len(text)


def _listen_socket(rt: Runtime) -> Any:
    """The socket bound to the lowest granted listening port, or None.

    Bound on first use by either `net-send` or `net-recv` (M23): a
    reply to a datagram this run sent has to have somewhere to land
    *before* the run gets round to receiving it.  Bound only by
    `net-recv`, an answer that came back quickly was lost.
    """
    ports = sorted(rt.net_listen_on or ())
    if not ports:
        return None
    port = ports[0]                 # the lowest granted port listens
    sock = rt.net_sockets.get(port)
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", port))
        rt.net_sockets[port] = sock
    return sock


def _op_NET_SEND(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    _require_capability(rt, NET_SEND, "net-send")
    address = _as_text(_eval(node.args[0], rt), "net-send")
    payload = _as_text(_eval(node.args[1], rt), "net-send")
    host, port = _net_address(address, "net-send")
    allowed = set(rt.net_send_to or ())
    if "*" not in allowed and f"{host}:{port}" not in allowed:
        raise DomainTrap(
            "capability-denied",
            f"net-send: {host}:{port} is not a granted address",
            {"operator": "net-send", "address": f"{host}:{port}",
             "granted": sorted(allowed)},
            f"run with `--allow net={host}:{port}`",
        )
    data = payload.encode("utf-8")
    try:
        # From the listening socket when one is granted, so the peer
        # sees the port an answer can go to and the answer has a socket
        # to land in; otherwise from a socket that lives for the send.
        listener = _listen_socket(rt)
        if listener is not None:
            listener.sendto(data, (host, port))
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(data, (host, port))
    except OSError as exc:
        raise DomainTrap(
            "domain-error", f"net-send: {host}:{port}: {exc}",
            {"operator": "net-send", "address": f"{host}:{port}",
             "reason": type(exc).__name__},
            "give `net-send` a reachable host:port",
        ) from None
    return len(data)


def _op_NET_RECV(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    _require_capability(rt, NET_RECV, "net-recv")
    if not rt.net_listen_on:
        raise DomainTrap(
            "capability-denied",
            "net-recv: no listening port was granted",
            {"operator": "net-recv", "granted": []},
            "run with `--allow net=:PORT`",
        )
    port = min(rt.net_listen_on)
    try:
        sock = _listen_socket(rt)
        sock.settimeout(rt.net_timeout)
        data, _peer = sock.recvfrom(65535)
    except socket.timeout:
        return NIL_VALUE            # nothing arrived; not an error
    except OSError as exc:
        raise DomainTrap(
            "domain-error", f"net-recv: port {port}: {exc}",
            {"operator": "net-recv", "port": port,
             "reason": type(exc).__name__},
            "grant a port that is free to bind",
        ) from None
    text = data.decode("utf-8", errors="replace")
    return text


def _op_CLOCK(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    _require_capability(rt, CLOCK, "clock")
    if rt.clock is not None:
        return _as_int(rt.clock(), "clock")
    return time.time_ns() // 1_000_000


def _op_BUDGET(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    limit = _as_int(_eval(node.args[0], rt), "budget")
    b = Budget(limit=limit)
    rt.budget_stack.append(b)
    try:
        return _eval(node.args[1], rt)
    finally:
        rt.budget_stack.pop()


def _op_CONSERVE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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
            node.args[1], expected, actual, flatten_env(rt.env)
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


def _op_VIOLATE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Synthetic "break conservation" — returns first arg's value
    # plus one, so wrapping with CONSERVE always triggers Δ-trap.
    # For testing only.
    return _as_int(_eval(node.args[0], rt), "violate") + 1


def _op_SURPRISE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    predicted = _as_int(_eval(node.args[0], rt), "surprise")
    actual = _as_int(_eval(node.args[1], rt), "surprise")
    return rt.surprise.emit(predicted, actual, ctx="surprise")


def _op_TRACE_SURPRISE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    val = _as_int(_eval(node.args[0], rt), "trace-surprise")
    rt.surprise.emit(0, val, ctx="trace-surprise")
    return val


def _op_DEVIATION(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # The signed sibling of SURPRISE (which returns |a - b|).  Sign
    # is the whole point: it is what makes ordering expressible.
    # Emits no surprise event — this is a pure comparison, not an
    # observation about a prediction.
    a = _eval(node.args[0], rt)
    b = _eval(node.args[1], rt)
    if isinstance(a, str) or isinstance(b, str):
        return 0 if _as_text(a, "deviation") == _as_text(b, "deviation") else 1
    return _as_int(a, "deviation") - _as_int(b, "deviation")


def _op_THRESHOLD(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # Sign test: did the value cross zero from below?
    #   (a < b)  ==  (threshold (deviation b a))
    #   (a > b)  ==  (threshold (deviation a b))
    x = _as_int(_eval(node.args[0], rt), "threshold")
    return 1 if x > 0 else 0


def _op_SEQ(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    last = 0
    for child in node.args:
        last = _eval(child, rt)
    return last


def _op_LET(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # (let name value body) — ``name`` must be a LIT_INT symbol id.
    #
    # M23: a well-formed LET runs as `_compile_LET`'s closure, which
    # inlines this handler and is where the binding group is joined
    # (``rt.let_chain``); this handler is reached for the malformed
    # shapes and reports them.  The comments below are the semantics.
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
              and not rt.env.bound(name_id))
    saved_env = rt.env
    if extend:
        scope = rt.env
    else:
        scope = Scope.open(rt.env)
        rt.env = scope
    try:
        value = _eval(node.args[1], rt)
        if isinstance(value, Closure) and value.name is None:
            value.name = name_id
        scope[name_id] = value
        return _eval(node.args[2], rt)
    finally:
        if not extend:
            rt.env = saved_env


def _op_REF(node: Node, rt: Runtime, chained: bool) -> Any:
    slot = node.args[0]
    if slot.op != LIT_INT:
        raise DomainTrap(
            "malformed", "REF: name slot must be a literal integer id",
            {"operator": "ref", "slot": 0},
            "put a literal integer in REF's slot",
        )
    name_id = slot.args[0]
    try:
        return rt.env[name_id]
    except KeyError:
        raise _unbound(name_id, rt) from None


def _op_IF_SURPRISE(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
    # (if-surprise surprise-expr then else)
    # Milestone 1 predicate: non-zero surprise triggers the ``then`` branch.
    s = _as_int(_eval(node.args[0], rt), "if-surprise")
    branch = node.args[1] if s != 0 else node.args[2]
    return _eval(branch, rt)


def _op_LAMBDA(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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
        caps=rt.caps,
        enclosed=rt.enclosed,
    )


def _op_APPLY(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _op_LOOP_UNTIL(node: Node, rt: Runtime, chained: bool) -> Any:
    op = node.op
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


def _eval_unimplemented(node: Node, rt: Runtime) -> Any:
    op = node.op
    sig = SIGNATURES.get(op, {"name": "unknown", "family": "?"})
    raise NotImplementedError(
        f"operator {sig['name']} (family {sig['family']}) not implemented "
        f"in Milestone 1 runtime"
    )

# Operator dispatch (M22).  One hash per node where a chain of
# comparisons used to walk past fifty operators to reach `ref`.
_HANDLERS = {
    LIT_TEXT: _op_LIT_TEXT,
    TEXT_LEN: _op_TEXT_LEN, TEXT_CAT: _op_TEXT_CAT, TEXT_SLICE: _op_TEXT_SLICE,
    TEXT_FIND: _op_TEXT_FIND, TEXT_SPLIT: _op_TEXT_SPLIT, TEXT_JOIN: _op_TEXT_JOIN,
    TEXT_CHARS: _op_TEXT_CHARS, TEXT_OF_CHARS: _op_TEXT_OF_CHARS, TEXT_CMP: _op_TEXT_CMP,
    TEXT_INT: _op_TEXT_INT, INT_TEXT: _op_INT_TEXT, IS_TEXT: _op_IS_TEXT, TEXT_TRIM: _op_TEXT_TRIM,
    LIT_INT: _op_LIT_INT,
    IDENTITY: _op_IDENTITY,
    MERGE: _op_MERGE,
    PARTITION: _op_PARTITION,
    P: _op_P,
    TAU: _op_TAU,
    SIGMA: _op_SIGMA,
    GCD: _op_GCD,
    MOBIUS: _op_MOBIUS,
    MUL: _op_MUL,
    DIV: _op_DIV,
    MOD: _op_MOD,
    NIL: _op_NIL,
    CONS: _op_CONS,
    HEAD: _op_HEAD,
    TAIL: _op_TAIL,
    IS_NIL: _op_IS_NIL,
    QUOTE: _op_QUOTE,
    EVAL: _op_EVAL,
    EXPLAIN: _op_EXPLAIN,
    READ: _op_READ,
    HASH: _op_HASH,
    UID: _op_UID,
    GENERATION: _op_GENERATION,
    ANCESTOR_OF: _op_ANCESTOR_OF,
    LINEAGE_QUERY: _op_LINEAGE_QUERY,
    WHY: _op_WHY,
    TRACE: _op_TRACE,
    CLONE: _op_CLONE,
    MUTATE: _op_MUTATE,
    DEFPOP: _op_DEFPOP,
    VARIANT: _op_VARIANT,
    SELECT: _op_SELECT,
    FITNESS: _op_FITNESS,
    RETIRE: _op_RETIRE,
    EVOLVE: _op_EVOLVE,
    WHEN_ANOMALY: _op_WHEN_ANOMALY,
    STDOUT: _op_STDOUT,
    STDIN: _op_STDIN,
    MAP_PUT: _op_MAP_PUT,
    MAP_GET: _op_MAP_GET,
    MAP_PAIRS: _op_MAP_PAIRS,
    SIGNAL: _op_SIGNAL,
    EXTERNAL_BOUNDARY: _op_EXTERNAL_BOUNDARY,
    FS_READ: _op_FS_READ,
    FS_WRITE: _op_FS_WRITE,
    NET_SEND: _op_NET_SEND,
    NET_RECV: _op_NET_RECV,
    CLOCK: _op_CLOCK,
    BUDGET: _op_BUDGET,
    CONSERVE: _op_CONSERVE,
    VIOLATE: _op_VIOLATE,
    SURPRISE: _op_SURPRISE,
    TRACE_SURPRISE: _op_TRACE_SURPRISE,
    DEVIATION: _op_DEVIATION,
    THRESHOLD: _op_THRESHOLD,
    SEQ: _op_SEQ,
    LET: _op_LET,
    REF: _op_REF,
    IF_SURPRISE: _op_IF_SURPRISE,
    LAMBDA: _op_LAMBDA,
    APPLY: _op_APPLY,
    LOOP_UNTIL: _op_LOOP_UNTIL,
}



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
