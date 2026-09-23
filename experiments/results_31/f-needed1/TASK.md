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
FAIL inputs={"board": ".........", "side": "O"} expected=0
run step-limit-exceeded 3:82 [157,159) `xs`: step budget of 7000000 spent; stopped here, not where the cost is; the run needs 14.8M steps (2.1x the budget). steps by function: nm 2.3M (61k calls), setat 1.6M (87k calls), three 1.5M (97k calls), winner 1.3M (14k calls), +4 more
```
