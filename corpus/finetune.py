"""M8 -- a verified synthetic corpus of (prompt, program) pairs.

    python -m corpus.finetune --n 4000 --seed 1 --out corpus/finetune

Every pair is produced by a *family*: a generator that draws
parameters and renders, from the same parameters, an English prompt,
a LOVA program with ``{var}`` placeholders, and a Python oracle.  The
oracle makes three test cases; the LOVA program is run against them
through the benchmark evaluator (prelude in scope, compiler on) and
the pair is kept only if it passes.  So the corpus cannot teach a
wrong program: a family with a bug drops its pairs, and the drop is
reported.

Held out by construction: a pair whose program is a LOVABench v3
template, or whose family and parameters reproduce a benchmark task
(each family names them), is discarded.  What the model is judged on
it has not seen.

Two files per split.  ``pairs_*.jsonl`` is plain: ``{"id", "family",
"prompt", "program", "variables", "tests"}``.  ``chat_*.jsonl`` is
the chat fine-tuning format (system card, user prompt, assistant
program) that OpenAI-style trainers take.

The largest family is compositional -- an aggregate of a transform of
a filter of a source, each fragment carrying its own English -- which
is where the distinct programs come from; the others cover the
shapes LOVABench v1/v2 has (number-theory composition, `let`,
`conserve`, `surprise`) and the algorithmic ones (recursion,
recurrences, digits, primes).  ``constrained_random`` is not used: it
makes programs nobody asked for, and a fine-tune needs the asking.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from corpus.evaluator import evaluate_template
from corpus.tasks import TASKS_V3

Oracle = Callable[..., int]


@dataclass
class Pair:
    family: str
    prompt: str
    program: str
    variables: Tuple[str, ...]
    oracle: Oracle
    domain: Callable[[random.Random], Dict[str, int]]
    # Set when this parameterisation reproduces a benchmark task.
    benchmark_id: Optional[str] = None


# --- helpers ---------------------------------------------------------------

# The runtime refuses a number-theory input beyond MAX_NT_INPUT (2000);
# the oracle refuses the same, so a composition that blows up -- p of
# p of n runs to ten million -- is dropped instead of computed.
_NT_LIMIT = 2000


def _bounded(f):
    def g(n):
        if n > _NT_LIMIT:
            raise ValueError("beyond MAX_NT_INPUT")
        return f(n)
    return g


def _partitions(n: int) -> int:
    t = [1] + [0] * n
    for k in range(1, n + 1):
        for m in range(k, n + 1):
            t[m] += t[m - k]
    return t[n]


_NT = {
    "p": ("the number of partitions", _bounded(_partitions)),
    "tau": ("the number of divisors", _bounded(lambda n: sum(1 for d in range(1, n + 1) if n % d == 0))),
    "sigma": ("the sum of the divisors", _bounded(lambda n: sum(d for d in range(1, n + 1) if n % d == 0))),
}


def _small(rng: random.Random, lo: int = 1, hi: int = 30) -> int:
    return rng.randint(lo, hi)


def _is_prime(k: int) -> bool:
    if k < 2:
        return False
    d = 2
    while d * d <= k:
        if k % d == 0:
            return False
        d += 1
    return True


_PRIME_DEFS = ("(def check [d n] (if (gt (mul d d) n) 1 (if (mod n d) (check (inc d) n) 0)))"
               "(def prime? [n] (if (lt n 2) 0 (check 2 n)))")

_OPENINGS = ("Given an integer {v} >= {lo}, return ",
             "For an integer {v} >= {lo}, compute ",
             "{v} is an integer, at least {lo}. Return ")


def _open(rng: random.Random, v: str, lo: int) -> str:
    return rng.choice(_OPENINGS).format(v=v, lo=lo)


# --- the compositional family ------------------------------------------------
#
# aggregate ( transform ( filter ( source ) ) ).  Each fragment is a
# (program text, English, oracle) triple; the pieces compose in all
# three at once, which is what keeps prompt and program in step.

def _sources(rng: random.Random, v: str):
    """(program, english, python-iterable, lower bound of v)"""
    return rng.choice([
        (f"(range 1 (inc {{{v}}}))", f"the integers from 1 to {v}", lambda n: range(1, n + 1), 1, "range1n"),
        (f"(range 0 {{{v}}})", f"the integers from 0 to {v} - 1", lambda n: range(0, n), 1, "range0n"),
        (f"(range 2 {{{v}}})", f"the integers from 2 to {v} - 1", lambda n: range(2, n), 3, "range2n"),
        (f"(digits {{{v}}})", f"the decimal digits of {v}", lambda n: [int(c) for c in str(n)], 0, "digits"),
    ])


def _predicates(rng: random.Random, v: str):
    """(lambda-or-name, english clause, python predicate(k, n), needs prime defs, tag)"""
    d = rng.choice([2, 3, 4, 5, 6, 7, 9])
    c = rng.randint(1, 9)
    r = rng.randint(1, d - 1)
    return rng.choice([
        ("", "", lambda k, n: True, False, "none"),
        ("", "", lambda k, n: True, False, "none"),
        ("(lambda k (even k))", "even", lambda k, n: k % 2 == 0, False, "even"),
        ("(lambda k (odd k))", "odd", lambda k, n: k % 2 == 1, False, "odd"),
        (f"(lambda k (not (mod k {d})))", f"divisible by {d}", lambda k, n: k % d == 0, False, f"div{d}"),
        (f"(lambda k (mod k {d}))", f"not divisible by {d}", lambda k, n: k % d != 0, False, f"ndiv{d}"),
        (f"(lambda k (eq (mod k {d}) {r}))", f"that leave remainder {r} when divided by {d}",
         lambda k, n: k % d == r, False, f"rem{d}{r}"),
        (f"(lambda k (gt k {c}))", f"greater than {c}", lambda k, n: k > c, False, f"gt{c}"),
        (f"(lambda k (not (mod {{{v}}} k)))", f"that divide {v}", lambda k, n: k != 0 and n % k == 0, False, "divides"),
        ("prime?", "prime", lambda k, n: _is_prime(k), True, "prime"),
    ])


def _transforms(rng: random.Random):
    """(lambda, english, python f(k), tag)"""
    m = rng.choice([2, 3, 4, 5, 7, 10])
    c = rng.randint(1, 9)
    return rng.choice([
        ("", "", lambda k: k, "none"),
        ("", "", lambda k: k, "none"),
        ("(lambda k (mul k k))", "the squares of", lambda k: k * k, "square"),
        ("(lambda k (mul k (mul k k)))", "the cubes of", lambda k: k ** 3, "cube"),
        (f"(lambda k (mul {m} k))", f"{m} times each of", lambda k: m * k, f"times{m}"),
        (f"(lambda k (merge k {c}))", f"{c} plus each of", lambda k: k + c, f"plus{c}"),
        (f"(lambda k (mod k {m}))", f"the remainders modulo {m} of", lambda k: k % m, f"mod{m}"),
    ])


def _aggregates(rng: random.Random):
    """(wrapper(program) -> program, english, python f(list), tag)"""
    return rng.choice([
        (lambda xs: f"(sum {xs})", "the sum of", lambda xs: sum(xs), "sum"),
        (lambda xs: f"(len {xs})", "how many there are of", lambda xs: len(xs), "count"),
        (lambda xs: f"(product {xs})", "the product of", lambda xs: math.prod(xs), "product"),
        (lambda xs: f"(fold (lambda a (lambda b (max a b))) 0 {xs})", "the largest of (or 0 if there are none)",
         lambda xs: max(xs) if xs else 0, "max"),
    ])


# (aggregate, source, predicate, transform) settings that are benchmark tasks.
_PIPELINE_BENCH = {
    ("sum", "range1n", "none", "none"): "pb65",
    ("sum", "range1n", "none", "square"): "pb71",
    ("count", "range1n", "divides", "none"): "pb68",
    ("sum", "digits", "none", "none"): "pb69",
    ("max", "digits", "none", "none"): "pb73",
    ("count", "digits", "none", "none"): "pb79",
    ("count", "range2n", "prime", "none"): "pb72",
}


def fam_pipeline(rng: random.Random) -> Pair:
    v = rng.choice(["n", "n", "m", "x"])
    src_prog, src_text, src_py, lo, src_tag = _sources(rng, v)
    pred_prog, pred_text, pred_py, needs_prime, pred_tag = _predicates(rng, v)
    tr_prog, tr_text, tr_py, tr_tag = _transforms(rng)
    agg, agg_text, agg_py, agg_tag = _aggregates(rng)
    if src_tag == "digits" and pred_tag in ("divides", "prime"):
        pred_prog, pred_text, pred_py, needs_prime, pred_tag = "", "", (lambda k, n: True), False, "none"
    if agg_tag == "count":
        tr_prog, tr_text, tr_py, tr_tag = "", "", (lambda k: k), "none"   # a count ignores a transform
    if pred_tag == "divides":
        lo = max(lo, 1)
    xs = src_prog
    if pred_prog:
        xs = f"(filter {pred_prog} {xs})"
    if tr_prog:
        xs = f"(map {tr_prog} {xs})"
    program = (_PRIME_DEFS if needs_prime else "") + agg(xs)
    # English: "the sum of the squares of the odd integers from 1 to n"
    noun = src_text
    if pred_text:
        noun = noun.replace("the integers", f"the {pred_text} integers", 1) if "integers" in noun \
            else noun.replace("the decimal digits", f"the {pred_text} decimal digits", 1)
        if pred_tag in ("divides", "prime") or pred_text.startswith("that") or pred_text.startswith("greater") \
                or pred_text.startswith("divisible") or pred_text.startswith("not"):
            # clauses go after the noun
            noun = src_text + " that are " + pred_text if not pred_text.startswith("that") else src_text + " " + pred_text
    what = f"{agg_text} {tr_text} {noun}".replace("  ", " ")
    prompt = _open(rng, v, lo) + what + "."

    def oracle(**kw):
        n = kw[v]
        vals = [tr_py(k) for k in src_py(n) if pred_py(k, n)]
        return agg_py(vals)
    hi = 25 if agg_tag == "product" else 60
    dom = (lambda r: {v: r.choice([r.randint(0, 9), r.randint(10, 9999)])}) if src_tag == "digits" \
        else (lambda r: {v: _small(r, lo, hi)})
    return Pair("pipeline", prompt, program, (v,), oracle, dom,
                benchmark_id=_PIPELINE_BENCH.get((agg_tag, src_tag, pred_tag, tr_tag)))


# --- the recall families (LOVABench v1/v2's shapes) ---------------------------

def fam_nt_compose(rng: random.Random) -> Pair:
    depth = rng.choice([1, 2, 2, 3])
    ops = [rng.choice(list(_NT)) for _ in range(depth)]
    inner = rng.choice(["n", "n", "sum", "gcd", "plus"])
    c = rng.randint(1, 9)
    if inner == "n":
        inner_prog, inner_text, variables, inner_fn = "{n}", "n", ("n",), (lambda n: n)
    elif inner == "plus":
        inner_prog, inner_text, variables, inner_fn = f"(merge {{n}} {c})", f"n + {c}", ("n",), (lambda n: n + c)
    elif inner == "sum":
        inner_prog, inner_text, variables, inner_fn = "(merge {a} {b})", "a + b", ("a", "b"), (lambda a, b: a + b)
    else:
        inner_prog, inner_text, variables, inner_fn = "(gcd {a} {b})", "gcd(a, b)", ("a", "b"), (lambda a, b: math.gcd(a, b))
    prog, text = inner_prog, inner_text
    for op in ops:
        prog, text = f"({op} {prog})", f"{op}({text})"
    words = " of ".join(_NT[op][0] for op in reversed(ops))
    outer = rng.choice(["", "", "plus", "times"])
    k = rng.randint(2, 9)
    if outer == "plus":
        prog, text = f"(merge {prog} {k})", f"{text} + {k}"
    elif outer == "times":
        prog, text = f"(mul {k} {prog})", f"{k} * {text}"

    def oracle(**kw):
        val = inner_fn(**kw)
        for op in ops:
            val = _NT[op][1](val)
        return val + k if outer == "plus" else k * val if outer == "times" else val
    given = "an integer n" if variables == ("n",) else "integers a and b"
    prompt = f"Given {given}, return {text}, where {words} of {inner_text} is meant."
    dom = lambda r: {v: _small(r, 1, 12) for v in variables}
    return Pair("nt-compose", prompt, prog, variables, oracle, dom)


def fam_let_share(rng: random.Random) -> Pair:
    op = rng.choice(list(_NT))
    c = rng.randint(1, 9)
    shape = rng.choice(["x+x", "x*x", "x+n", "x-n", "x+c", "c*x"])
    body = {"x+x": "(merge x x)", "x*x": "(mul x x)", "x+n": "(merge x {n})",
            "x-n": "(sub x {n})", "x+c": f"(merge x {c})", "c*x": f"(mul {c} x)"}[shape]
    text = {"x+x": "x + x", "x*x": "x * x", "x+n": "x + n", "x-n": "x - n",
            "x+c": f"x + {c}", "c*x": f"{c} * x"}[shape]
    prog = f"(let x ({op} {{n}}) {body})"
    f = _NT[op][1]
    oracle = lambda n: {"x+x": f(n) + f(n), "x*x": f(n) * f(n), "x+n": f(n) + n,
                        "x-n": f(n) - n, "x+c": f(n) + c, "c*x": c * f(n)}[shape]
    prompt = f"Let x = {op}(n), {_NT[op][0]} of n; return {text}."
    return Pair("let-share", prompt, prog, ("n",), oracle,
                lambda r: {"n": _small(r, 1, 20)},
                benchmark_id="pb57" if (op, shape) == ("sigma", "x+x") else None)


def fam_conserve(rng: random.Random) -> Pair:
    op = rng.choice(list(_NT))
    prog = f"(conserve {{k}} ({op} {{n}}))"
    prompt = (f"Given integers n and k, return {op}(n), {_NT[op][0]} of n, under a "
              f"conservation contract that it equals k.")
    oracle = lambda n, k: _NT[op][1](n)
    dom = lambda r: (lambda m: {"n": m, "k": _NT[op][1](m)})(_small(r, 1, 15))
    return Pair("conserve", prompt, prog, ("n", "k"), oracle, dom)


def fam_surprise_test(rng: random.Random) -> Pair:
    op = rng.choice(list(_NT))
    flip = rng.random() < 0.5
    prog = f"(if (dist {{k}} ({op} {{n}})) {0 if not flip else 1} {1 if not flip else 0})"
    prompt = (f"Given integers n and k, return {1 if not flip else 0} if {op}(n), {_NT[op][0]} of n, "
              f"is exactly k, and {0 if not flip else 1} otherwise.")
    oracle = lambda n, k: (1 if _NT[op][1](n) == k else 0) ^ (1 if flip else 0)

    def dom(r):
        m = _small(r, 1, 15)
        return {"n": m, "k": _NT[op][1](m) if r.random() < 0.5 else _small(r, 1, 40)}
    return Pair("surprise-test", prompt, prog, ("n", "k"), oracle, dom)


# --- the algorithmic families ---------------------------------------------------

def fam_recurrence(rng: random.Random) -> Pair:
    x, y = rng.randint(0, 3), rng.randint(1, 4)
    c1, c2 = rng.choice([(1, 1), (2, 1), (1, 2), (3, -1), (2, -1), (1, -1), (2, 2)])
    prog = (f"(def a [n] (if (lt n 2) (if n {y} {x}) "
            f"(merge (mul {c1} (a (sub n 1))) (mul {c2} (a (sub n 2))))))(a {{n}})")
    prompt = (f"A sequence has a(0) = {x}, a(1) = {y} and a(n) = {c1}*a(n-1) + "
              f"{c2}*a(n-2) for n >= 2. Given n >= 0, return a(n).")

    def oracle(n):
        a, b = x, y
        for _ in range(n):
            a, b = b, c1 * b + c2 * a
        return a
    return Pair("recurrence", prompt, prog, ("n",), oracle,
                lambda r: {"n": _small(r, 0, 10)},
                benchmark_id="pb62" if (x, y, c1, c2) == (0, 1, 1, 1) else None)


def fam_digits(rng: random.Random) -> Pair:
    kind = rng.choice(["count", "reverse", "first", "alternating", "product", "distinct"])
    d = rng.randint(0, 9)
    if kind == "count":
        prog = f"(len (filter (lambda c (eq c {d})) (digits {{n}})))"
        prompt = f"Given an integer n >= 0, return how many times the digit {d} occurs in its decimal representation."
        oracle, bid = (lambda n: str(n).count(str(d))), None
    elif kind == "reverse":
        prog = "(def rev [n acc] (if n (rev (div n 10) (merge (mul acc 10) (mod n 10))) acc))(rev {n} 0)"
        prompt = "Given an integer n >= 0, return the integer whose decimal digits are those of n reversed."
        oracle, bid = (lambda n: int(str(n)[::-1])), "pb70"
    elif kind == "first":
        prog = "(head (digits {n}))"
        prompt = "Given an integer n >= 0, return its first (most significant) decimal digit."
        oracle, bid = (lambda n: int(str(n)[0])), None
    elif kind == "alternating":
        prog = "(fold (lambda a (lambda d (sub d a))) 0 (reverse (digits {n})))"
        prompt = ("Given an integer n >= 0, return the alternating sum of its decimal digits "
                  "taken from the right: the last digit, minus the one before it, plus the one before that, and so on.")

        def oracle(n):
            acc = 0
            for ch in reversed(str(n)):
                acc = int(ch) - acc
            return acc
        bid = None
    elif kind == "product":
        prog = "(product (digits {n}))"
        prompt = "Given an integer n >= 0, return the product of its decimal digits."
        oracle, bid = (lambda n: math.prod(int(c) for c in str(n))), None
    else:
        prog = ("(def uniq [xs acc] (if (nil? xs) acc (uniq (tail xs) "
                "(if (contains acc (head xs)) acc (cons (head xs) acc)))))(len (uniq (digits {n}) (nil)))")
        prompt = "Given an integer n >= 0, return how many distinct decimal digits it has."
        oracle, bid = (lambda n: len(set(str(n)))), None
    return Pair("digits", prompt, prog, ("n",), oracle,
                lambda r: {"n": r.choice([r.randint(0, 9), r.randint(10, 999), r.randint(1000, 99999)])},
                benchmark_id=bid)


def fam_primes(rng: random.Random) -> Pair:
    kind = rng.choice(["test", "sum", "nth", "largest-below", "gap"])
    if kind == "test":
        prog, prompt, bid = _PRIME_DEFS + "(prime? {n})", "Given an integer n, return 1 if n is prime and 0 otherwise.", "pb63"
        oracle = lambda n: int(_is_prime(n))
        dom = lambda r: {"n": r.choice([r.randint(0, 3), r.randint(4, 200), r.choice([97, 561, 1999])])}
    elif kind == "sum":
        prog, prompt, bid = _PRIME_DEFS + "(sum (filter prime? (range 2 {n})))", "Given an integer n, return the sum of the primes smaller than n.", None
        oracle = lambda n: sum(k for k in range(2, n) if _is_prime(k))
        dom = lambda r: {"n": _small(r, 2, 120)}
    elif kind == "nth":
        prog = _PRIME_DEFS + "(nth (filter prime? (range 2 (mul 12 (inc {n})))) (sub {n} 1))"
        prompt, bid = "Given an integer n >= 1, return the n-th prime (the first prime is 2).", None
        oracle = lambda n: [k for k in range(2, 12 * (n + 1)) if _is_prime(k)][n - 1]
        dom = lambda r: {"n": _small(r, 1, 25)}
    elif kind == "largest-below":
        prog = _PRIME_DEFS + "(last (filter prime? (range 2 {n})))"
        prompt, bid = "Given an integer n >= 3, return the largest prime smaller than n.", None
        oracle = lambda n: max(k for k in range(2, n) if _is_prime(k))
        dom = lambda r: {"n": _small(r, 3, 150)}
    else:
        prog = (_PRIME_DEFS + "(def after [k] (if (prime? k) k (after (inc k))))"
                "(sub (after (inc {n})) {n})")
        prompt, bid = "Given a prime n, return the distance to the next prime after it.", None

        def oracle(n):
            k = n + 1
            while not _is_prime(k):
                k += 1
            return k - n
        dom = lambda r: {"n": r.choice([2, 3, 5, 7, 11, 13, 23, 31, 47, 89, 113, 199])}
    return Pair("primes", prompt, prog, ("n",), oracle, dom, benchmark_id=bid)


def fam_iterate(rng: random.Random) -> Pair:
    kind = rng.choice(["collatz-max", "halve", "digital-root-steps", "double-until", "subtract-until", "collatz"])
    if kind == "collatz":
        prog = ("(def next [n] (if (mod n 2) (merge (mul 3 n) 1) (div n 2)))"
                "(def steps [n acc] (if (eq n 1) acc (steps (next n) (inc acc))))(steps {n} 0)")
        prompt = "Given an integer n >= 1, return how many Collatz steps (halve if even, else 3n+1) it takes to reach 1."

        def oracle(n):
            c = 0
            while n != 1:
                n = n // 2 if n % 2 == 0 else 3 * n + 1
                c += 1
            return c
        bid, dom = "pb64", (lambda r: {"n": _small(r, 1, 60)})
    elif kind == "collatz-max":
        prog = ("(def next [n] (if (mod n 2) (merge (mul 3 n) 1) (div n 2)))"
                "(def peak [n best] (if (eq n 1) (max best 1) (peak (next n) (max best n))))(peak {n} 0)")
        prompt = "Given an integer n >= 1, return the largest value reached on its Collatz trajectory (halve if even, else 3n+1) before it reaches 1, n itself included."

        def oracle(n):
            best = n
            while n != 1:
                n = n // 2 if n % 2 == 0 else 3 * n + 1
                best = max(best, n)
            return best
        bid, dom = None, (lambda r: {"n": _small(r, 1, 60)})
    elif kind == "halve":
        prog = "(def lg [n] (if (lt n 2) 0 (inc (lg (div n 2)))))(lg {n})"
        prompt = "Given an integer n >= 1, return how many times n can be halved (rounding down) before it is smaller than 2."
        oracle, bid, dom = (lambda n: n.bit_length() - 1), "pb76", (lambda r: {"n": _small(r, 1, 5000)})
    elif kind == "digital-root-steps":
        prog = "(def steps [n acc] (if (lt n 10) acc (steps (sum (digits n)) (inc acc))))(steps {n} 0)"
        prompt = "Given an integer n >= 0, return how many times its digits must be summed (repeatedly) until a single digit remains."

        def oracle(n):
            c = 0
            while n >= 10:
                n = sum(int(ch) for ch in str(n))
                c += 1
            return c
        bid, dom = None, (lambda r: {"n": r.choice([r.randint(0, 9), r.randint(10, 99999), 99999999])})
    elif kind == "double-until":
        m = rng.choice([100, 1000, 5000, 20000])
        prog = f"(def steps [n acc] (if (ge n {m}) acc (steps (mul n 2) (inc acc))))(steps {{n}} 0)"
        prompt = f"Given an integer n >= 1, return how many times n must be doubled to reach at least {m}."

        def oracle(n):
            c = 0
            while n < m:
                n *= 2
                c += 1
            return c
        bid, dom = None, (lambda r: {"n": _small(r, 1, 300)})
    else:
        d = rng.choice([3, 4, 5, 7, 9])
        prog = f"(def steps [n acc] (if (lt n {d}) acc (steps (sub n {d}) (inc acc))))(steps {{n}} 0)"
        prompt = f"Given an integer n >= 0, return how many times {d} can be subtracted from n while the result stays non-negative."
        oracle, bid, dom = (lambda n: n // d), None, (lambda r: {"n": _small(r, 0, 200)})
    return Pair("iterate", prompt, prog, ("n",), oracle, dom, benchmark_id=bid)


def fam_binary(rng: random.Random) -> Pair:
    kind = rng.choice(["ones", "length", "power", "base-digits", "trailing-zeros"])
    b = rng.choice([2, 3, 5, 6, 7, 10])
    if kind == "ones":
        prog = "(def ones [n] (if n (merge (mod n 2) (ones (div n 2))) 0))(ones {n})"
        prompt, oracle, bid = "Given an integer n >= 0, return the number of 1 bits in its binary representation.", (lambda n: bin(n).count("1")), "pb74"
        dom = lambda r: {"n": _small(r, 0, 5000)}
    elif kind == "length":
        prog = "(def bits [n] (if n (inc (bits (div n 2))) 0))(bits {n})"
        prompt, oracle, bid = "Given an integer n >= 0, return the number of binary digits of n (0 has none).", (lambda n: n.bit_length()), None
        dom = lambda r: {"n": _small(r, 0, 5000)}
    elif kind == "power":
        prog = f"(def power [e] (if e (mul {b} (power (sub e 1))) 1))(power {{n}})"
        prompt, oracle, bid = f"Given an integer n >= 0, return {b} raised to the power n.", (lambda n: b ** n), None
        dom = lambda r: {"n": _small(r, 0, 10)}
    elif kind == "base-digits":
        prog = f"(def ds [n] (if n (merge (mod n {b}) (ds (div n {b}))) 0))(ds {{n}})"
        prompt, bid = f"Given an integer n >= 0, return the sum of its digits when written in base {b}.", None

        def oracle(n):
            s = 0
            while n:
                s += n % b
                n //= b
            return s
        dom = lambda r: {"n": _small(r, 0, 5000)}
    else:
        prog = f"(def tz [n] (if (mod n {b}) 0 (inc (tz (div n {b})))))(tz {{n}})"
        prompt, bid = f"Given an integer n >= 1, return how many times {b} divides n exactly (the number of trailing zeros of n in base {b}).", None

        def oracle(n):
            c = 0
            while n % b == 0:
                n //= b
                c += 1
            return c
        dom = lambda r: {"n": _small(r, 1, 5000)}
    return Pair("binary", prompt, prog, ("n",), oracle, dom, benchmark_id=bid)


def fam_two_arg(rng: random.Random) -> Pair:
    kind = rng.choice(["euclid", "power", "lcm", "count-between", "sum-between", "binomial"])
    if kind == "euclid":
        prog = "(def euclid [a b] (if b (euclid b (mod a b)) a))(euclid {a} {b})"
        prompt, oracle, bid = "Given integers a and b, return their greatest common divisor by Euclid's algorithm, without the gcd operator.", (lambda a, b: math.gcd(a, b)), "pb67"
        dom = lambda r: {"a": _small(r, 0, 300), "b": _small(r, 1, 300)}
    elif kind == "power":
        prog = "(def power [b e] (if e (mul b (power b (sub e 1))) 1))(power {b} {e})"
        prompt, oracle, bid = "Given integers b and e >= 0, return b raised to the power e.", (lambda b, e: b ** e), "pb66"
        dom = lambda r: {"b": _small(r, 0, 9), "e": _small(r, 0, 8)}
        return Pair("two-arg", prompt, prog, ("b", "e"), oracle, dom, benchmark_id=bid)
    elif kind == "lcm":
        prog = "(div (mul {a} {b}) (gcd {a} {b}))"
        prompt, oracle, bid = "Given integers a and b >= 1, return their least common multiple.", (lambda a, b: a * b // math.gcd(a, b)), None
        dom = lambda r: {"a": _small(r, 1, 60), "b": _small(r, 1, 60)}
    elif kind == "count-between":
        d = rng.choice([2, 3, 4, 5, 7])
        prog = f"(len (filter (lambda k (not (mod k {d}))) (range {{a}} (inc {{b}}))))"
        prompt, oracle, bid = f"Given integers a <= b, return how many integers from a to b inclusive are divisible by {d}.", (lambda a, b: sum(1 for k in range(a, b + 1) if k % d == 0)), None

        def dom(r):
            a = _small(r, 1, 50)
            return {"a": a, "b": a + _small(r, 0, 60)}
    elif kind == "sum-between":
        prog = "(sum (range {a} (inc {b})))"
        prompt, oracle, bid = "Given integers a <= b, return the sum of the integers from a to b inclusive.", (lambda a, b: sum(range(a, b + 1))), None

        def dom(r):
            a = _small(r, 0, 50)
            return {"a": a, "b": a + _small(r, 0, 60)}
    else:
        prog = ("(def choose [n k] (if (or (eq k 0) (eq k n)) 1 "
                "(merge (choose (sub n 1) (sub k 1)) (choose (sub n 1) k))))(choose {n} {k})")
        prompt, oracle, bid = "Given integers n >= k >= 0, return the binomial coefficient n choose k.", (lambda n, k: math.comb(n, k)), None

        def dom(r):
            n = _small(r, 0, 12)
            return {"n": n, "k": _small(r, 0, n)}
        return Pair("two-arg", prompt, prog, ("n", "k"), oracle, dom, benchmark_id=bid)
    return Pair("two-arg", prompt, prog, ("a", "b"), oracle, dom, benchmark_id=bid)


# Families and how often each is drawn: the compositional one is the
# source of variety, the rest keep every shape of the language present.
FAMILIES: Sequence[Tuple[Callable[[random.Random], Pair], int]] = (
    (fam_pipeline, 10),
    (fam_nt_compose, 3), (fam_let_share, 2), (fam_conserve, 1), (fam_surprise_test, 1),
    (fam_recurrence, 2), (fam_digits, 2), (fam_primes, 2), (fam_iterate, 2),
    (fam_binary, 2), (fam_two_arg, 2),
)

# --- held-out benchmark ---------------------------------------------------------

_BENCH_TEMPLATES = {re.sub(r"\s+", " ", t.template).strip() for t in TASKS_V3}


def _held_out(pair: Pair) -> bool:
    if pair.benchmark_id is not None:
        return True
    return re.sub(r"\s+", " ", pair.program).strip() in _BENCH_TEMPLATES


# --- verification ---------------------------------------------------------------

def _tests_for(pair: Pair, rng: random.Random, k: int = 3) -> List[dict]:
    tests: List[dict] = []
    seen = set()
    for _ in range(k * 6):
        inputs = pair.domain(rng)
        key = tuple(sorted(inputs.items()))
        if key in seen:
            continue
        seen.add(key)
        tests.append({"inputs": inputs, "expected": int(pair.oracle(**inputs))})
        if len(tests) == k:
            break
    return tests


def _verified(pair: Pair, tests: List[dict]) -> bool:
    for t in tests:
        got = evaluate_template(pair.program, t["inputs"])
        if not isinstance(got, int) or got != t["expected"]:
            return False
    return True


# --- generation ------------------------------------------------------------------

def generate(n: int, seed: int) -> Tuple[List[dict], Dict[str, int]]:
    """``n`` verified, distinct pairs, and the counts of what was dropped."""
    rng = random.Random(seed)
    families = [f for f, w in FAMILIES for _ in range(w)]
    out: List[dict] = []
    seen = set()
    dropped = {"held-out": 0, "duplicate": 0, "failed": 0}
    attempts = 0
    while len(out) < n and attempts < n * 40:
        attempts += 1
        pair = rng.choice(families)(rng)
        if _held_out(pair):
            dropped["held-out"] += 1
            continue
        key = (pair.prompt, pair.program)
        if key in seen:
            dropped["duplicate"] += 1
            continue
        try:
            tests = _tests_for(pair, rng)
        except (ValueError, ZeroDivisionError, IndexError, RecursionError, OverflowError):
            dropped["failed"] += 1          # the oracle refused the parameters
            continue
        if len(tests) < 2 or not _verified(pair, tests):
            dropped["failed"] += 1
            continue
        seen.add(key)
        out.append({
            "id": f"ft{len(out) + 1:05d}",
            "family": pair.family,
            "prompt": pair.prompt,
            "program": pair.program,
            "variables": list(pair.variables),
            "tests": tests,
        })
    return out, dropped


SYSTEM_PROMPT = (
    "You write programs in LOVA. Reply with the program only: no prose, "
    "no code fence, no explanation.")
INPUT_NOTE = "Write the inputs as the placeholders {names}."


def chat_record(card: Optional[str], pair: dict) -> dict:
    """One line of the chat fine-tuning format.

    With ``card`` the system prompt carries the one-page language
    card, which is what a base model is prompted with; without it the
    system prompt is one sentence and the model has to know the
    language -- the cheaper format to train on (the card is a
    thousand tokens an example), and the one a fine-tuned model is
    then benchmarked with (`experiment_17 --no-card`).
    """
    system = SYSTEM_PROMPT if not card else SYSTEM_PROMPT + "\n\n" + card
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": pair["prompt"] + "\n\n" + INPUT_NOTE.format(
            names=", ".join("{" + v + "}" for v in pair["variables"]))},
        {"role": "assistant", "content": pair["program"]},
    ]}


def write(pairs: List[dict], out_dir: Path, val_fraction: float = 0.1, seed: int = 0) -> Dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    card = (Path(__file__).parent / "language_card.md").read_text(encoding="utf-8")
    rng = random.Random(seed)
    shuffled = list(pairs)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_fraction)) if len(shuffled) > 10 else 0
    splits = {"val": shuffled[:n_val], "train": shuffled[n_val:]}
    counts = {}
    for name, rows in splits.items():
        with (out_dir / f"pairs_{name}.jsonl").open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
        write_chat(rows, name, out_dir, card)
        counts[name] = len(rows)
    return counts


def write_chat(rows: List[dict], name: str, out_dir: Path, card: str) -> None:
    """``chat_<name>.jsonl`` without the card, ``chat_card_<name>.jsonl`` with it."""
    for fname, with_card in ((f"chat_{name}.jsonl", None), (f"chat_card_{name}.jsonl", card)):
        with (out_dir / fname).open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(chat_record(with_card, row), ensure_ascii=False) + "\n")


def rewrite_chat(out_dir: Path) -> None:
    """Rebuild the chat files from the pairs files already written."""
    card = (Path(__file__).parent / "language_card.md").read_text(encoding="utf-8")
    for name in ("train", "val"):
        rows = [json.loads(line) for line in (out_dir / f"pairs_{name}.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
        write_chat(rows, name, out_dir, card)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="corpus/finetune")
    ap.add_argument("--rewrite-chat", action="store_true",
                    help="rebuild the chat files from the pairs files, no generation")
    args = ap.parse_args(argv)
    if args.rewrite_chat:
        rewrite_chat(Path(args.out))
        print(f"chat files rewritten in {args.out}")
        return 0
    pairs, dropped = generate(args.n, args.seed)
    counts = write(pairs, Path(args.out), seed=args.seed)
    by_family: Dict[str, int] = {}
    for p in pairs:
        by_family[p["family"]] = by_family.get(p["family"], 0) + 1
    print(f"{len(pairs)} verified pairs -> {args.out}  (train {counts['train']}, val {counts['val']})")
    print("dropped:", dropped)
    for fam, k in sorted(by_family.items()):
        print(f"  {fam:14s} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
