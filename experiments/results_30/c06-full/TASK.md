# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def idc [c] c)
(def three [x y z] (and (ne x 46) (and (eq x y) (eq y z))))
(def setat [xs i v] (if (eq i 0) (cons v (tail xs)) (cons (head xs) (setat (tail xs) (sub i 1) v))))
(def winner [b]
  (let q0 (head b) (let r1 (tail b)
  (let q1 (head r1) (let r2 (tail r1)
  (let q2 (head r2) (let r3 (tail r2)
  (let q3 (head r3) (let r4 (tail r3)
  (let q4 (head r4) (let r5 (tail r4)
  (let q5 (head r5) (let r6 (tail r5)
  (let q6 (head r6) (let r7 (tail r6)
  (let q7 (head r7) (let r8 (tail r7)
  (let q8 (head r8)
    (cond
      (three q0 q1 q2) q0
      (three q3 q4 q5) q3
      (three q6 q7 q8) q6
      (three q0 q3 q6) q0
      (three q1 q4 q7) q1
      (three q2 q5 q8) q2
      (three q0 q4 q8) q0
      (three q2 q4 q6) q2
      0)))))))))))))))))))
(def other [w] (if (eq w 88) 79 88))
(def nm [b who alpha beta i rest e]
  (if (nil? rest) alpha
    (if (ne (head rest) 46) (nm b who alpha beta (inc i) (tail rest) e)
      (let nb (setat b i who)
        (let w (winner nb)
          (let v (if (eq w who) 1 (if (eq e 1) 0 (neg (nm nb (other who) (neg beta) (neg alpha) 0 nb (sub e 1)))))
            (let a2 (max alpha v)
              (if (ge a2 beta) a2 (nm b who a2 beta (inc i) (tail rest) e)))))))))
(def pick [b who i rest e bi bv]
  (if (nil? rest) bi
    (if (eq bv 1) bi
      (if (ne (head rest) 46) (pick b who (inc i) (tail rest) e bi bv)
        (let nb (setat b i who)
          (let w (winner nb)
            (let v (if (eq w who) 1 (if (eq e 1) 0 (neg (nm nb (other who) (neg 2) 2 0 nb (sub e 1)))))
              (if (gt v bv) (pick b who (inc i) (tail rest) e i v) (pick b who (inc i) (tail rest) e bi bv)))))))))
(let b (map idc {board})
  (let s (head {side})
    (pick b s 0 b (len (filter (lambda c (eq c 46)) b)) (neg 1) (neg 2))))

```

## What the test run said

```
FAIL {"inputs": {"board": ".........", "side": "O"}, "expected": 0, "anomaly": {"kind": "step-limit-exceeded", "excerpt": "xs", "line": 3, "col": 82, "repair_hint": "the budget of 7000000 steps ran out.  The span is where the counter expired, not where the cost is; `hot` in the detail is: the steps each function spent in its own body, costliest first.  If a library walker leads (`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost 20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, `map-get`, `get` a few steps), change the representation -- a map keyed by index, a text, a packed integer -- before the algorithm; if a function of yours leads, cut work there; if the program cannot reach its base case, fix that; if the work is genuinely this large, the budget is the host's setting (`--max-steps`, `max_steps`), not a fault in the program  Where the steps went: nm (2343672 steps in 61892 calls), setat (1568092 steps in 87760 calls), three (1544667 steps in 97633 calls), winner (1323782 steps in 14192 calls), inc (160473 steps in 53491 calls), other (58835 steps in 8405 calls), pick (368 steps in 5 calls), idc (9 steps in 9 calls).", "detail": {"limit": 7000000, "overrun": 1, "spent": 7000001, "hot": [["nm", 2343672, 61892], ["setat", 1568092, 87760], ["three", 1544667, 97633], ["winner", 1323782, 14192], ["inc", 160473, 53491], ["other", 58835, 8405], ["pick", 368, 5], ["idc", 9, 9]]}, "message": "Step trap: 7000001 evaluation steps > limit 7000000", "span": [157, 159], "stage": "run"}}
```
