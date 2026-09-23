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
are what it says about itself, and `lova check` runs them; what they
state may be a number, a text, a list or a record. A miss reports
expected and got, and then `fault: line:col excerpt -- edit -> replacement`:
the one single-node edit, in a def the example ran through or in the
example's own expression, that makes it pass, scored against the other
examples ("fixes every example" is a repair; "the fault may be
elsewhere" is a lead). Patch the span it names.

The one mistake nothing above can catch is a well-typed wrong value --
a reference swapped, a scale forgotten, a sign always the same -- and
only an example can, so state what a def must satisfy, not only what
it returns: the expected side is any expression over the program's own
defs, so an example can be a relation -- `(example (dist a b) (dist b
a))`, `(example (le (speed (press 30)) (speed (press 1))) 1)`, `(example
(both-signs? (map kick (range 1 25))) 1)`. A relation comes from the
rule, not from the code, so it catches what a value copied from the
code cannot; and choose inputs away from 0 and 1, where most wrong
programs give the right answer. `lova check FILE --strength` then says,
def by def, which single-node edits the examples would not notice and
which defs no example reaches: write the relation that would.

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
(len xs) (sum xs) (product xs) (append xs ys) (replace t old new) (nth xs k)
(last xs) (take n xs) (drop n xs) (contains xs v) (same a b)
; higher order
(all f xs)
; sorting
(sort xs)
; construction
(repeat x n)
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

Notes: `(replace t old new)` Every `old` in `t` replaced by `new` (M32).  `(nth xs k)` The element of `xs` at 0-based index `k`; a fault past the end.  `(words text)` The words of `text`: runs of non-space characters.  `(join parts sep)` Join `parts` with `sep` between them; `sep` a codepoint or a text.  `(text-of n)` An integer as decimal text.  `(text-lt a b)` Lexicographic order on texts or codepoint lists, so `(sort-by text-lt words)`.  `(map-count m k)` `m` with the count under `k` one higher: the word-count step.

List operators: `map` `filter` `fold` `reverse` `range` `any` `sort-by` `zip`. `(map f xs)`, `(filter f xs)` (keeps x where `(f x)` is
non-zero), `(fold f acc xs)` (calls `(f acc x)`), `(reverse xs)`,
`(range a b)` (a to b-1), `(any f xs)` (1 or 0, stops at the first
hit), `(sort-by less xs)` (stable; `(less a b)` non-zero puts a first),
`(zip xs ys)` (two-element lists, to the shorter). One step an element,
plus the function called.

Text operators: `text-len` `text-cat` `text-slice` `text-find` `text-split` `text-join` `text-chars` `text-of-chars` `text-cmp` `text-int` `int-text` `text?` `text-trim` `text-match` `text-match-all`. `(text-slice t start end)`, `(text-find t needle)` (-1 if
absent), `(text-split t sep)` (`""` splits on whitespace), `(text-join
parts sep)`; a separator may be a text or a codepoint. `(text-match t
pattern)` is the first match as `(whole group ...)` or `()` if none,
`(text-match-all t pattern)` every match; a pattern is literals, `.`,
`[a-z]`, `\d \w \s`, `* + ? {m,n}`, `( )`, `|`, `^ $` and nothing
else (no `\1`, no `(?`): `(text-match "mem 40%" "(\w+) (\d+)%")` is
`("mem 40%" "mem" "40")`. `(replace t old new)`. The empty map is `()`:
`(map-put m k v)`, `(map-get m k default)`, `(map-pairs m)`.

`f` in `map`, `filter`, `fold` is a function value: a `lambda`, the name
of a `def`, or an operator or macro named bare -- `(sort-by lt xs)`,
`(fold merge 0 xs)`, `(map neg xs)` -- which is the lambda that wraps
it. `fold` calls `(f acc x)`; write a two-argument fold step as
`(lambda a (lambda x ...))`.

## Cost

A program runs under a step budget the host sets; a run that exceeds it
is a `step-limit-exceeded` anomaly whose `hot` detail lists the
functions the steps went to, and -- when the program touches no file,
clock or network -- how many steps the whole run needs (measured up to
4x the budget), so a rewrite can be sized. An operator costs 1 step, a
call to a `def` about 3 plus its body. `pow` is a prelude loop, not an
operator: about 40 steps plus 20 per unit of exponent (`(pow 3 8)` is
~200, `mul` is 1); for fixed powers write the constants. Cheap: `nth`, `take`, `drop`, `append`,
`last`, `len` (a few steps, native), `map-get`, `map-put`, `get`, `put`
(~4), the `text-*` operators. The list operators cost one step an
element plus the function called (`map` with a one-operator body about
6 an element; `sort-by` one comparison per step, n log n of them);
`sum`, `contains`, `all` are folds. A search that rebuilds a list at
every node still costs millions of steps; carry the state as a map, a
text or a packed integer.

## Contracts and effects (rarely needed for a task)

`(conserve k body)` traps unless body equals k. `(budget n body)` traps
if body costs more than n nodes. `(surprise a b)` is |a - b|. `(try body
fallback)` catches a fault. `(stdout text)`, `(stdin)`, and file, clock and
network operators exist under `(boundary "kind" ...)`; a `def` that uses
one must be written inside the boundary: `(boundary "clock" (def now []
(clock)) body)`.

## What each operator gives (computed by the runtime when this card is made)

```
;; integers
(div 7 2)                                            ; 3
(div -7 2)                                           ; -4
(mod -7 3)                                           ; 2
(sub 3 5)                                            ; -2
(if 0 1 2)                                           ; 2
(or 0 5)                                             ; 5
;; lists (0-based; `range` stops before b)
(range 1 5)                                          ; (1 2 3 4)
(nth (list 5 6 7) 1)                                 ; 6
(take 2 (list 5 6 7))                                ; (5 6)
(drop 2 (list 5 6 7))                                ; (7)
(fold (lambda a (lambda x (sub a x))) 10 (list 1 2)) ; 7
(sort-by (lambda a (lambda b (gt a b))) (list 3 1 2)) ; (3 2 1)
(zip (list 1 2 3) (list 4 5))                        ; ((1 4) (2 5))
(digits 1048576)                                     ; (1 0 4 8 5 7 6)
(head "abc")                                         ; 97
(text-slice (list 1 2 3 4) 1 3)                      ; (2 3)
;; texts (half-open slices, clamped; -1 for not found)
(text-slice "hello" 1 3)                             ; "el"
(text-slice "hello" 3 99)                            ; "lo"
(text-find "hello" "ll")                             ; 2
(text-find "hello" "z")                              ; -1
(text-split "a,b,,c" ",")                            ; ("a" "b" "" "c")
(text-split " a  b " "")                             ; ("a" "b")
(text-join (list "a" "b") ", ")                      ; "a, b"
(text-trim "  a ")                                   ; "a"
(text-chars "ab")                                    ; (97 98)  "ab"
(text-of-chars (list 104 105))                       ; "hi"
(text-int "-7")                                      ; -7
(int-text 42)                                        ; "42"
(text-cmp "a" "b")                                   ; -1
(words "a b  c")                                     ; ("a" "b" "c")
(lines "a\nb")                                       ; ("a" "b")
;; maps and records
(map-get (map-put (nil) "k" 1) "k" 0)                ; 1
(map-get (map-of (nil)) "k" 0)                       ; 0
(map-pairs (map-put (map-put (nil) "a" 1) "b" 2))    ; (("a" 1) ("b" 2))
(get (rec x 1 y 2) y)                                ; 2
(get (put (rec x 1) x 9) x)                          ; 9
```

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

Rules of thumb: a call in tail position costs no frame, so a recursion
whose last act is the call (an accumulator recursion) runs in constant
depth; a recursion that does something with the result afterwards is
fine up to 10 000 frames, and past that is `fold` / `map` / `range` or
`loop-until`; there is no `return`, `while` or assignment; every `(`
has its `)`.
