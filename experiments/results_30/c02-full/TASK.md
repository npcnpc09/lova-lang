# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def lines3 [] (list (list 0 1 2) (list 3 4 5) (list 6 7 8)
                     (list 0 3 6) (list 1 4 7) (list 2 5 8)
                     (list 0 4 8) (list 2 4 6)))
(def line-win [b l]
  (let a (nth b (nth l 0))
    (if (and (ne a 46) (and (eq a (nth b (nth l 1))) (eq a (nth b (nth l 2))))) a 0)))
(def winner-of [b ls]
  (if (nil? ls) 0 (let w (line-win b (head ls)) (if w w (winner-of b (tail ls))))))
(def winner [b] (winner-of b lines3))
(def full [b] (not (contains b 46)))
(def other [p] (if (eq p 88) 79 88))
(def set-at [xs i v]
  (if (eq i 0) (cons v (tail xs)) (cons (head xs) (set-at (tail xs) (sub i 1) v))))
(def nmax [b p alpha beta]
  (if (winner b) (neg 1)
    (if (full b) 0 (nloop b p 0 alpha beta (neg 2)))))
(def nloop [b p i alpha beta best]
  (if (ge i 9) best
    (if (ne (nth b i) 46) (nloop b p (inc i) alpha beta best)
      (let v (neg (nmax (set-at b i p) (other p) (neg beta) (neg alpha)))
        (let best2 (max best v)
          (let a2 (max alpha v)
            (if (ge a2 beta) best2 (nloop b p (inc i) a2 beta best2))))))))
(def pick [b p i besti bestv]
  (if (ge i 9) besti
    (if (ne (nth b i) 46) (pick b p (inc i) besti bestv)
      (let v (neg (nmax (set-at b i p) (other p) (neg 2) 2))
        (if (gt v bestv) (pick b p (inc i) i v) (pick b p (inc i) besti bestv))))))
(let b (text-chars {board}) (pick b (head {side}) 0 0 (neg 2)))

```

## What the test run said

```
FAIL {"inputs": {"board": ".........", "side": "O"}, "expected": 0, "anomaly": {"kind": "step-limit-exceeded", "excerpt": "(nth l 1)", "line": 6, "col": 42, "repair_hint": "the budget of 7000000 steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program  Where the steps went: nth (2014186 steps in 251775 calls), line-win (1585093 steps in 48849 calls), nloop (1270898 steps in 31727 calls), winner-of (844388 steps in 53507 calls), set-at (805873 steps in 44990 calls), contains (187958 steps in 4658 calls), nmax (103917 steps in 6991 calls), inc (82605 steps in 27535 calls).", "detail": {"limit": 7000000, "overrun": 1, "spent": 7000001, "hot": [["nth", 2014186, 251775], ["line-win", 1585093, 48849], ["nloop", 1270898, 31727], ["winner-of", 844388, 53507], ["set-at", 805873, 44990], ["contains", 187958, 4658], ["nmax", 103917, 6991], ["inc", 82605, 27535]]}, "message": "Step trap: 7000001 evaluation steps > limit 7000000", "span": [257, 266], "stage": "run"}}
```
