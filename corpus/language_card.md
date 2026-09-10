# LOVA in one page

LOVA is a small integer language written as s-expressions. Every value is an
integer, a list, a function, a map or a program. There are no floats, no
strings other than lists of codepoints, no mutable variables.

## Writing a program

```
(def name [param ...] body)      ; a function; several may precede the expression
(def k [] value)                 ; no parameters: a constant, computed once
(f a b)                          ; call a defined function (curried under the hood)
(lambda x body)                  ; an anonymous function of ONE parameter
(let name value body)            ; bind name in body (recursive under a lambda)
(if c then else)                 ; c is an integer: non-zero is true
(cond c1 v1 c2 v2 ... default)   ; a chain of ifs
(seq a b c)                      ; evaluate in order, value of the last
```

A program is zero or more `def` forms followed by exactly one expression.
Inputs are written as `{name}` placeholders and are filled with integers
before the program runs, e.g. `(fact {n})`.

## Arithmetic (integers only)

```
(merge a b)  a + b        (sub a b)  a - b        (mul a b)  a * b
(div a b)    a // b       (mod a b)  a mod b      (neg a)    -a
(inc n) n+1  (abs a)      (min a b)  (max a b)    (pow b e)  b^e
(gcd a b)    (p n) partitions   (tau n) divisor count   (sigma n) divisor sum
(mobius n)   (partition n) n // 2
```

Comparisons return 1 or 0: `(eq a b) (ne a b) (lt a b) (gt a b) (le a b)
(ge a b)`. Logic: `(not x) (and a b) (or a b)`, short-circuit. `(even n)`,
`(odd n)`.

## Lists and text

`(nil)` is the empty list; `(cons x xs)` prepends; `(head xs)` and
`(tail xs)`; `(nil? xs)` tests emptiness. `(list 1 2 3)` builds a list.
A string literal `"abc"` is the list of its codepoints.

Library (always available):

```
(len xs) (sum xs) (product xs) (reverse xs) (append xs ys) (nth xs k)
(take n xs) (drop n xs) (last xs) (contains xs v) (same xs ys)
(map f xs) (filter f xs) (fold f acc xs) (any f xs) (all f xs) (zip xs ys)
(sort xs) (sort-by less xs) (range a b) ; a .. b-1   (repeat x n)
(digits n) ; decimal digits, most significant first
(text-of n) ; decimal text of n     (parse-int text)   (words text) (lines text)
(join parts sep) (split text sep)
(map-put m k v) (map-get m k default) (map-pairs m) (map-count m k) (map-size m)
```

`f` in `map`, `filter`, `fold` is a function value: a `lambda`, or the name
of a `def`. `fold` calls `(f acc x)`; write a two-argument fold step as
`(lambda a (lambda x ...))`.

## Contracts and effects (rarely needed for a task)

`(conserve k body)` traps unless body equals k. `(budget n body)` traps
if body costs more than n nodes. `(surprise a b)` is |a - b|. `(try body
fallback)` catches a fault. `(stdout text)`, `(stdin)`, and file, clock and
network operators exist under `(boundary "kind" ...)`.

## Examples

```
(def cubes [n] (if n (merge (mul n (mul n n)) (cubes (sub n 1))) 0))(cubes {n})   ; 1^3 + ... + n^3
(def has-factor [d n] (if (gt (mul d d) n) 0 (if (mod n d) (has-factor (inc d) n) 1)))
(has-factor 2 {n})                                                                  ; 1 if n has a divisor in 2..sqrt(n)
(len (filter odd (filter (lambda d (not (mod {n} d))) (range 1 (inc {n})))))        ; odd divisors of n
(product (map (lambda k (merge k 1)) (range 1 (inc {n}))))                          ; 2 * 3 * ... * (n+1)
(fold (lambda a (lambda d (merge (mul a 10) d))) 0 (take 2 (digits {n})))           ; the first two digits as a number
(let x (tau {n}) (mul x x))
```

Rules of thumb: recursion is fine (depth 10 000); a loop is recursion with
an accumulator parameter; there is no `return`, `while` or assignment;
every `(` has its `)`.
