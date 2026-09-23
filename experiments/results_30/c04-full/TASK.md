# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def wins [] (list (list 0 1 2) (list 3 4 5) (list 6 7 8)
                   (list 0 3 6) (list 1 4 7) (list 2 5 8)
                   (list 0 4 8) (list 2 4 6)))
(def line-win [b p ln]
  (and (eq (nth b (nth ln 0)) p)
       (and (eq (nth b (nth ln 1)) p) (eq (nth b (nth ln 2)) p))))
(def has-win [b p] (any (lambda ln (line-win b p ln)) wins))
(def opp [p] (if (eq p 88) 79 88))
(def put-at [b i v]
  (if (eq i 0) (cons v (tail b)) (cons (head b) (put-at (tail b) (sub i 1) v))))
(def code [c] (if (eq c 88) 1 (if (eq c 79) 2 0)))
(def bkey [b] (fold (lambda a (lambda c (merge (mul a 3) (code c)))) 0 b))
(def best [b p mm]
  (let kk (merge (mul (bkey b) 2) (if (eq p 88) 1 0))
    (let hit (map-get mm kk 9)
      (if (ne hit 9) (rec s hit m mm)
        (let res (best2 b p mm)
          (rec s (get res s) m (map-put (get res m) kk (get res s))))))))
(def best2 [b p mm]
  (if (has-win b (opp p)) (rec s (neg 1) m mm)
    (if (not (contains b 46)) (rec s 0 m mm)
      (bestloop b p 0 (neg 2) mm))))
(def bestloop [b p i acc mm]
  (if (eq i 9) (rec s acc m mm)
    (if (ne (nth b i) 46) (bestloop b p (inc i) acc mm)
      (let r (best (put-at b i p) (opp p) mm)
        (bestloop b p (inc i) (max acc (neg (get r s))) (get r m))))))
(def pick [b p i bi bs mm]
  (if (eq i 9) bi
    (if (ne (nth b i) 46) (pick b p (inc i) bi bs mm)
      (let r (best (put-at b i p) (opp p) mm)
        (let sc (neg (get r s))
          (if (gt sc bs) (pick b p (inc i) i sc (get r m))
                         (pick b p (inc i) bi bs (get r m))))))))
(let b (text-chars {board}) (pick b (head {side}) 0 0 (neg 2) (map-of (nil))))

```

## What the test run said

```
FAIL {"inputs": {"board": ".........", "side": "O"}, "expected": 0, "anomaly": {"kind": "step-limit-exceeded", "excerpt": "(nth ln 0)", "line": 5, "col": 19, "repair_hint": "the budget of 7000000 steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program  Where the steps went: bestloop (1213733 steps in 33700 calls), code (1139466 steps in 102474 calls), put-at (1056726 steps in 59812 calls), nth (978266 steps in 122285 calls), bkey (967810 steps in 11386 calls), line-win (637901 steps in 31036 calls), best (442602 steps in 11386 calls), has-win (202960 steps in 4186 calls).", "detail": {"limit": 7000000, "overrun": 1, "spent": 7000001, "hot": [["bestloop", 1213733, 33700], ["code", 1139466, 102474], ["put-at", 1056726, 59812], ["nth", 978266, 122285], ["bkey", 967810, 11386], ["line-win", 637901, 31036], ["best", 442602, 11386], ["has-win", 202960, 4186]]}, "message": "Step trap: 7000001 evaluation steps > limit 7000000", "span": [204, 214], "stage": "run"}}
```
