# LOVA — first programs

The first real LOVA programs.  Everything in `corpus/` and
`experiments/` is either benchmark input or test harness; the files
here are **LOVA code that exists to do something**, not to prove
LOVA exists.

## Running them

Since M11 there is a command line, so none of these needs its Python
driver any more:

```
python -m core.cli run apps/is_prime.lova 1999
python -m core.cli run apps/palindrome.lova racecar
python -m core.cli analyze apps/collatz.lova 27
python -m core.cli emit apps/coprime.lova 14 15 --form stage2
```

A `{placeholder}` in a program is filled positionally from the command
line; an argument that is not an integer is quoted as a string literal,
which is how `palindrome.lova racecar` works.  The `.py` drivers are
kept because each prints a little more of the pipeline than the CLI
does, but they are no longer the way in.

## Programs

### `is_perfect.lova`

Classify an integer as a number-theoretic *perfect* number
(σ(n) = 2n; examples 6, 28, 496, 8128).

```
(let 0 {n}
  (if-surprise
    (surprise
      (merge (ref 0) (ref 0))      ; predicted: 2n (if perfect)
      (sigma (ref 0)))             ; actual:    sigma(n)
    0                              ; non-zero surprise -> not perfect
    1))                            ; zero surprise     -> PERFECT
```

Run:

```
PYTHONPATH=. python apps/is_perfect.py 6     # -> 1 (perfect)
PYTHONPATH=. python apps/is_perfect.py 12    # -> 0 (not perfect, deviation=4)
PYTHONPATH=. python apps/is_perfect.py 28    # -> 1
PYTHONPATH=. python apps/is_perfect.py 496   # -> 1
```

### `coprime.lova`

Two integers are coprime iff their gcd is 1.  Shorter than
`is_perfect`; shows that `surprise` works as a general-purpose
equality check against any literal.

```
(if-surprise
  (surprise 1 (gcd {a} {b}))       ; |1 - gcd(a,b)|
  0                                ; non-zero surprise -> not coprime
  1)                               ; zero surprise     -> coprime
```

Run:

```
PYTHONPATH=. python apps/coprime.py 7 13     # -> 1 (coprime)
PYTHONPATH=. python apps/coprime.py 12 18    # -> 0 (not coprime, gcd=6)
```

### `is_prime.lova`

The first program here with an actual algorithm in it. Trial division
by recursion: walk a divisor upward until its square passes `n`.

```
(defn check [d n]
  (if-surprise (threshold (deviation (mul d d) n))
    1                                 ; d*d > n  -- no divisor, prime
    (if-surprise (mod n d)
      (check (merge d 1) n)           ; n mod d != 0  -- next d
      0)))                            ; d divides n   -- composite

(defn is-prime [n]
  (if-surprise (threshold (deviation 2 n)) 0 (check 2 n)))

(is-prime {n})
```

Run:

```
PYTHONPATH=. python apps/is_prime.py 97          # -> 1
PYTHONPATH=. python apps/is_prime.py 91          # -> 0 (7 x 13)
PYTHONPATH=. python apps/is_prime.py 561 1999    # Carmichael, then a prime
```

Note `(threshold (deviation a b))`: the core has no `<`. Ordering is
built from the surprise family — `deviation` is the signed sibling of
`surprise`, `threshold` is the sign test.

### `collatz.lova`

Counts Collatz steps to reach 1, carrying the counter as a second
curried parameter because LOVA has no mutable state and no pair type.

```
(defn next [n]
  (if-surprise (mod n 2) (merge (mul 3 n) 1) (partition n)))

(defn steps [n acc]
  (if-surprise (deviation n 1) (steps (next n) (merge acc 1)) acc))

(steps {n} 0)
```

Run:

```
PYTHONPATH=. python apps/collatz.py 27      # -> 111 steps
PYTHONPATH=. python apps/collatz.py 2463    # -> DepthTrap, not a crash
```

The second invocation is the point. Its trajectory is 208 steps, past
`MAX_CALL_DEPTH`, so the run ends in a structured anomaly naming the
limit, the overrun and what to do about it — the same schema as every
other LOVA trap. The Python equivalent raises `RecursionError` with a
stack trace an agent has to parse.

### `palindrome.lova`

The first program here that operates on **data** rather than on a
number.  Reverses a string and compares elementwise.

```
(def rev [xs acc]
  (if (nil? xs) acc (rev (tail xs) (cons (head xs) acc))))

(def same [a b]
  (if (nil? a) (nil? b)
    (if (nil? b) 0
      (if (dist (head a) (head b)) 0 (same (tail a) (tail b))))))

(def palindrome? [s] (same s (rev s (nil))))

(palindrome? {s})
```

Run:

```
PYTHONPATH=. python apps/palindrome.py racecar level abc
PYTHONPATH=. python apps/palindrome.py            # a default set
```

Three things it demonstrates:

- **A string is a list of codepoints.**  `"racecar"` is surface sugar
  for `(cons 114 (cons 97 ...))`, which is why the token table spends
  no slots at all on strings.
- **`dist` is `surprise`** — |a - b|, zero exactly when two codepoints
  match.  Equality never needed its own operator here.
- **The short spellings** (`if`, `dist`, `def`) are the one-token
  aliases Exp 13 measured: identical program, 30% fewer LLM tokens.

## Why these particular programs?

`is_perfect` and `coprime` use the four pieces that make LOVA actually
LOVA:

- **`let` / `ref`** — input binding (shows scope).
- **`merge`, `sigma`, `gcd`** — number-theoretic primitives as
  substrate operators.
- **`surprise`** — used as an *equality predicate* rather than a
  debugger.  The substrate records the comparison as a surprise
  event; the AI observer sees *why* the program decided.
- **`if-surprise`** — branching based on the surprise magnitude.

`is_perfect` in particular is **LOVA-idiomatic**: rather than
`if sigma(n) == 2*n`, it says *"hypothesise perfection; see how
surprised we are"*.  Identical outcome, different cognitive frame —
and the surprise trace is available to any AI post-hoc inspector.

## What's missing (so you know what these programs cannot do yet)

- No string or list output — the drivers format results in Python.
  Once the IO effects family (0x30-0x37) lands, LOVA programs will
  emit their own output.
- No lists of lists.  `cons` takes an integer, so strings (flat lists
  of codepoints) work but trees do not.
- No modules.  `lib/prelude.lova` is prepended textually, which works
  for one library and will not scale to two.
- No way for a program to name its own provenance.  `why`, `explain`
  and `lineage-query` are reserved slots; provenance is queryable from
  Python only.

Functions, recursion and iteration arrived in M9, and data in M10; the
first two programs here predate both and remain single expressions
because they do not need more.  `collatz.lova` still threads its
counter through a curried parameter rather than a pair — worth
rewriting now that a cons cell is a pair.

These are the first programs; they are intentionally narrow.  As
the language grows, the programs here will grow with it.
