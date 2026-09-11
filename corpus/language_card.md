# LOVA in one page

LOVA is a small language written as s-expressions. Every value is an
integer, a text, a list, a function, a map or a program. There are no
floats and no mutable variables.

## Writing a program

```
(def name [param ...] body)      ; a function; several may precede the expression
(def k [] value)                 ; no parameters: a constant, computed once; use it as k, not (k)
                                 ; defs may call each other in any order (mutual recursion is fine)
(f a b)                          ; call a defined function (curried under the hood)
(lambda x body)                  ; an anonymous function of ONE parameter
(let name value body)            ; bind name in body (recursive under a lambda)
(if c then else)                 ; c is an integer: non-zero is true
(cond c1 v1 c2 v2 ... default)   ; a chain of ifs
(seq a b c)                      ; evaluate in order, value of the last
```

A program is zero or more `def` forms followed by exactly one expression.
Inputs are written as `{name}` placeholders and are filled with integers
or texts before the program runs, e.g. `(fact {n})`, `(words {s})`. `(example expr expected)`
forms may stand beside the defs: they are not part of the program, they
are what it says about itself, and `lova check` runs them.

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
`(odd n)`. A negative literal is written `-3`.

## Lists, text, records

`(nil)` is the empty list; `(cons x xs)` prepends; `(head xs)` and
`(tail xs)`; `(nil? xs)` tests emptiness. `(list 1 2 3)` builds a list.
A string literal `"abc"` is a text (`\n`, `\t`, `\"` and `\\` are
escapes); `(eq a b)` compares texts, and every list function reads a
text as its codepoints (`(head "abc")` is 97). `words`, `lines` and
`split` yield texts. `(rec x 1 y 2)` is a record with named fields,
`(get r x)` reads one, `(put r x 9)` is `r` with `x` set; a field name
is a bare symbol, never evaluated, so `x` may also be a variable. Use a
record, not a list taken apart by position, to carry several values
through a fold or a recursion: `(get st memo)` rather than `(nth st 2)`.
The empty map is `(nil)`: `(map-put (nil) k v)` starts one.

The library, always available (this index is generated from `lib/prelude.lova`):

```
; lists
(len xs) (sum xs) (product xs) (reverse xs) (append xs ys) (nth xs k)
(last xs) (take n xs) (drop n xs) (contains xs v) (same a b)
; higher order
(map f xs) (filter f xs) (fold f acc xs) (any f xs) (all f xs) (zip xs ys)
; sorting
(sort-by less xs) (sort xs)
; construction
(range a b) (repeat x n)
; integers
(even n) (odd n) (inc n) (pow b e) (gcd2 a b) (digits n)
; text
(split text sep) (lines text) (chomp line) (words text) (join parts sep)
(parse-int text) (text-of n) (text-lt a b)
; maps
(map-of pairs) (map-count m k) (map-keys m) (map-vals m) (map-size m)
; programs
(digest p)
; output
(println v)
```

Notes: `(nth xs k)` The element of `xs` at 0-based index `k`; a fault past the end.  `(words text)` The words of `text`: runs of non-space characters.  `(join parts sep)` Join `parts` with `sep` between them; `sep` a codepoint or a text.  `(text-of n)` An integer as decimal text.  `(text-lt a b)` Lexicographic order on texts or codepoint lists, so `(sort-by text-lt words)`.  `(map-count m k)` `m` with the count under `k` one higher: the word-count step.

Text operators: `text-len` `text-cat` `text-slice` `text-find` `text-split` `text-join` `text-chars` `text-of-chars` `text-cmp` `text-int` `int-text` `text?` `text-trim`. `(text-slice t start end)`, `(text-find t needle)` (-1 if
absent), `(text-split t sep)` (`""` splits on whitespace), `(text-join
parts sep)`; a separator may be a text or a codepoint. Maps:
`(map-put m k v)`, `(map-get m k default)`, `(map-pairs m)`.

`f` in `map`, `filter`, `fold` is a function value: a `lambda`, or the name
of a `def`. An operator (`merge`, `sub`, `mul`, `text-int`, ...) is not a
value and cannot be passed by name: wrap it, `(lambda a (lambda b (merge a
b)))`. `fold` calls `(f acc x)`; write a two-argument fold step as
`(lambda a (lambda x ...))`.

## Cost

A program runs under a step budget the host sets; a run that exceeds it
is a `step-limit-exceeded` anomaly whose `hot` detail lists the
functions the steps went to. An operator costs 1 step, a call to a
`def` about 3 plus its body. Cheap: `nth`, `take`, `drop`, `append`,
`last`, `len` (a few steps, native), `map-get`, `map-put`, `get`, `put`
(~4), the `text-*` operators. Linear: `map`, `filter`, `fold`,
`reverse`, `range`, `sum`, `any`, `contains`, `zip` cost 20-40 steps per
element, `sort` about 200. A search that reads and rebuilds a list at
every node costs millions of steps; carry the state as a map, a text or
a packed integer instead.

## Contracts and effects (rarely needed for a task)

`(conserve k body)` traps unless body equals k. `(budget n body)` traps
if body costs more than n nodes. `(surprise a b)` is |a - b|. `(try body
fallback)` catches a fault. `(stdout text)`, `(stdin)`, and file, clock and
network operators exist under `(boundary "kind" ...)`; a `def` that uses
one must be written inside the boundary: `(boundary "clock" (def now []
(clock)) body)`.

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
