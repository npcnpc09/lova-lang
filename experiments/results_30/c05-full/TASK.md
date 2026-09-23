# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def idc [c] c)
(def wins [] (list (list 0 1 2) (list 3 4 5) (list 6 7 8) (list 0 3 6) (list 1 4 7) (list 2 5 8) (list 0 4 8) (list 2 4 6)))
(def setat [xs i v] (if (eq i 0) (cons v (tail xs)) (cons (head xs) (setat (tail xs) (sub i 1) v))))
(def winloop [b ls]
  (if (nil? ls) 0
    (let ln (head ls)
      (let a (nth b (nth ln 0))
        (if (and (ne a 46) (and (eq a (nth b (nth ln 1))) (eq a (nth b (nth ln 2)))))
          a (winloop b (tail ls)))))))
(def winner [b] (winloop b wins))
(def full [b] (not (contains b 46)))
(def other [w] (if (eq w 88) 79 88))
(def nm [b who alpha beta i]
  (if (eq i 9) alpha
    (if (ne (nth b i) 46) (nm b who alpha beta (inc i))
      (let nb (setat b i who)
        (let w (winner nb)
          (let v (if (eq w who) 1 (if (full nb) 0 (neg (nm nb (other who) (neg beta) (neg alpha) 0))))
            (let a2 (max alpha v)
              (if (ge a2 beta) a2 (nm b who a2 beta (inc i))))))))))
(def pick [b who i bi bv]
  (if (eq i 9) bi
    (if (eq bv 1) bi
      (if (ne (nth b i) 46) (pick b who (inc i) bi bv)
        (let nb (setat b i who)
          (let w (winner nb)
            (let v (if (eq w who) 1 (if (full nb) 0 (neg (nm nb (other who) (neg 2) 2 0))))
              (if (gt v bv) (pick b who (inc i) i v) (pick b who (inc i) bi bv)))))))))
(let b (map idc {board}) (let s (head {side}) (pick b s 0 (neg 1) (neg 2))))

```

## What the test run said

```
FAIL {"inputs": {"board": ".........", "side": "O"}, "expected": 0, "anomaly": {"kind": "step-limit-exceeded", "excerpt": "nth", "line": 7, "col": 15, "repair_hint": "the budget of 7000000 steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program  Where the steps went: winloop (2270139 steps in 58200 calls), nth (2190312 steps in 273789 calls), nm (1276298 steps in 34493 calls), setat (877590 steps in 48993 calls), contains (202948 steps in 5047 calls), inc (89847 steps in 29949 calls), other (31822 steps in 4546 calls), winner (30444 steps in 7611 calls).", "detail": {"limit": 7000000, "overrun": 1, "spent": 7000001, "hot": [["winloop", 2270139, 58200], ["nth", 2190312, 273789], ["nm", 1276298, 34493], ["setat", 877590, 48993], ["contains", 202948, 5047], ["inc", 89847, 29949], ["other", 31822, 4546], ["winner", 30444, 7611]]}, "message": "Step trap: 7000001 evaluation steps > limit 7000000", "span": [316, 319], "stage": "run"}}
```
