# Task h01

Given a text s holding an arithmetic expression over non-negative integer literals with the operators + - * / (division is floor division), parentheses, unary minus, and spaces anywhere between tokens, evaluate it with the usual precedence (* and / before + and -, left to right within a level) and return the integer result.  [inputs: {s}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def skip [cs] (if (nil? cs) cs (if (eq (head cs) 32) (skip (tail cs)) cs)))
(def digit? [c] (and (ge c 48) (le c 57)))
(def num [cs acc]
  (if (nil? cs) (rec v acc r cs)
    (if (digit? (head cs))
        (num (tail cs) (merge (mul acc 10) (sub (head cs) 48)))
        (rec v acc r cs))))
(def factor [cs0]
  (let cs (skip cs0)
    (if (eq (head cs) 45)
        (let f (factor (tail cs)) (rec (neg (get f v))v) r (get f r)))
        (if (eq (head cs) 40)
            (let e (expr (tail cs)) (rec v (get e v) r (tail (skip (get e r)))))
            (num cs 0)))))
(def term-loop [acc cs0]
  (let cs (skip cs0)
    (if (nil? cs) (rec v acc r cs)
      (if (eq (head cs) 42)
          (let f (factor (tail cs)) (term-loop (mul acc (get f v)) (get f r)))
      (if (eq (head cs) 47)
          (let f (factor (tail cs)) (term-loop (div acc (get f v)) (get f r)))
          (rec v acc r cs))))))
(def term [cs0] (let f (factor cs0) (term-loop (get f v) (get f r))))
(def expr-loop [acc cs0]
  (let cs (skip cs0)
    (if (nil? cs) (rec v acc r cs)
      (if (eq (head cs) 43)
          (let t (term (tail cs)) (expr-loop (merge acc (get t v)) (get t r)))
      (if (eq (head cs) 45)
          (let t (term (tail cs)) (expr-loop (sub acc (get t v)) (get t r)))
          (rec v acc r cs))))))
(def expr [cs0] (let t (term cs0) (expr-loop (get t v) (get t r))))
(get (expr (text-chars {s})) v)

```

## What the test run said

```
FAIL compile parse-error 14:26 [562,563) `)`: rec: a field is a bare name or a string, not (mul Lit(-1) (map-get (ref Lit(27)) Text('v') (signal Lit(17)))); a closing paren at line 14 has nothing open to close; a form above it closed too early
```
