# LOVA — first programs

The first real LOVA programs.  Everything in `corpus/` and
`experiments/` is either benchmark input or test harness; the files
here are **LOVA code that exists to do something**, not to prove
LOVA exists.

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

## Why these particular programs?

Both use the four pieces that make LOVA actually LOVA:

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

- No string or list output — `is_perfect.py` formats the result in
  Python.  Once the IO effects family (0x30-0x37) lands in M7+,
  LOVA programs will emit their own output.
- No real functions (M7+ LAMBDA/APPLY).  Each program is a single
  expression with a placeholder for input; the driver substitutes
  before parse.
- No interactive loops / iteration over data.  Integer-valued
  computations only.

These are the first programs; they are intentionally narrow.  As
the language grows, the programs here will grow with it.
