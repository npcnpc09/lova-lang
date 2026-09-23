# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def wins [] (list (list 0 1 2) (list 3 4 5) (list 6 7 8)
                   (list 0 3 6) (list 1 4 7) (list 2 5 8)
                   (list 0 4 8) (list 2 4 6)))
(def winline [b l]
  (let a (nth b (nth l 0))
    (if (eq a 46) 0
      (if (and (eq a (nth b (nth l 1))) (eq a (nth b (nth l 2)))) a 0))))
(def winner [b] (fold (lambda acc (lambda l (if acc acc (winline b l)))) 0 (wins)))
(def full [b] (not (contains b 46)))
(def empties [b] (filter (lambda i (eq (nth b i) 46)) (range 0 9)))
(def setat [b i c] (append (take i b) (cons c (drop (inc i) b))))
(def other [c] (if (eq c 88) 79 88))
(def ab [b cur me alpha beta]
  (let wn (winner b)
    (if wn (if (eq wn me) 1 (neg 1))
      (if (full b) 0
        (if (eq cur me)
            (maxloop b cur me (empties b) alpha beta)
            (minloop b cur me (empties b) alpha beta))))))
(def maxloop [b cur me ms alpha beta]
  (if (nil? ms) alpha
    (let v (ab (setat b (head ms) cur) (other cur) me alpha beta)
      (let a2 (max alpha v)
        (if (ge a2 beta) a2 (maxloop b cur me (tail ms) a2 beta))))))
(def minloop [b cur me ms alpha beta]
  (if (nil? ms) beta
    (let v (ab (setat b (head ms) cur) (other cur) me alpha beta)
      (let b2 (min beta v)
        (if (le b2 alpha) b2 (minloop b cur me (tail ms) alpha b2))))))
(def pick [b me ms bi bs]
  (if (nil? ms) bi
    (let i (head ms)
      (let s (ab (setat b i me) (other me) me (neg 2) 2)
        (if (gt s bs) (pick b me (tail ms) i s) (pick b me (tail ms) bi bs))))))
(let b (text-chars {board})
  (let me (head (text-chars {side}))
    (pick b me (empties b) (neg 1) (neg 2))))

```

## What the test run said

```
FAIL compile type-mismatch 8:77 [379,383) `wins`: `ref` gives List; the slot wants Fn
```
