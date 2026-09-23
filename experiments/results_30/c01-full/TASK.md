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
(def winner [b] (fold (lambda acc (lambda l (if acc acc (winline b l)))) 0 wins))
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
FAIL {"inputs": {"board": ".........", "side": "O"}, "expected": 0, "anomaly": {"kind": "step-limit-exceeded", "excerpt": "(eq a (nth b (nth l 1)))", "line": 7, "col": 16, "repair_hint": "the budget of 7000000 steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program  Where the steps went: nth (2617880 steps in 327235 calls), winline (1992092 steps in 61990 calls), winner (577389 steps in 8896 calls), empties (504735 steps in 5313 calls), contains (236210 steps in 5921 calls), maxloop (221209 steps in 5438 calls), ab (219061 steps in 8896 calls), minloop (204224 steps in 4833 calls).", "detail": {"limit": 7000000, "overrun": 1, "spent": 7000001, "hot": [["nth", 2617880, 327235], ["winline", 1992092, 61990], ["winner", 577389, 8896], ["empties", 504735, 5313], ["contains", 236210, 5921], ["maxloop", 221209, 5438], ["ab", 219061, 8896], ["minloop", 204224, 4833]]}, "message": "Step trap: 7000001 evaluation steps > limit 7000000", "span": [244, 268], "stage": "run"}}
```
