# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def idc [c] c)
(def setat [xs i v] (if (eq i 0) (cons v (tail xs)) (cons (head xs) (setat (tail xs) (sub i 1) v))))
(def won [b who]
  (let q0 (head b) (let r1 (tail b)
  (let q1 (head r1) (let r2 (tail r1)
  (let q2 (head r2) (let r3 (tail r2)
  (let q3 (head r3) (let r4 (tail r3)
  (let q4 (head r4) (let r5 (tail r4)
  (let q5 (head r5) (let r6 (tail r5)
  (let q6 (head r6) (let r7 (tail r6)
  (let q7 (head r7) (let r8 (tail r7)
  (let q8 (head r8)
    (or (and (eq q0 who) (and (eq q1 who) (eq q2 who)))
    (or (and (eq q3 who) (and (eq q4 who) (eq q5 who)))
    (or (and (eq q6 who) (and (eq q7 who) (eq q8 who)))
    (or (and (eq q0 who) (and (eq q3 who) (eq q6 who)))
    (or (and (eq q1 who) (and (eq q4 who) (eq q7 who)))
    (or (and (eq q2 who) (and (eq q5 who) (eq q8 who)))
    (or (and (eq q0 who) (and (eq q4 who) (eq q8 who)))
        (and (eq q2 who) (and (eq q4 who) (eq q6 who)))))))))
  )))))))))))))))))))
(def nm [b who alpha beta i rest e]
  (if (nil? rest) alpha
    (if (ne (head rest) 46) (nm b who alpha beta (merge i 1) (tail rest) e)
      (let nb (setat b i who)
        (let v (if (won nb who) 1
                 (if (eq e 1) 0
                   (neg (nm nb (if (eq who 88) 79 88) (neg beta) (neg alpha) 0 nb (sub e 1)))))
          (let a2 (max alpha v)
            (if (ge a2 beta) a2 (nm b who a2 beta (merge i 1) (tail rest) e))))))))
(def pick [b who i rest e bi bv]
  (if (nil? rest) bi
    (if (eq bv 1) bi
      (if (ne (head rest) 46) (pick b who (merge i 1) (tail rest) e bi bv)
        (let nb (setat b i who)
          (let v (if (won nb who) 1
                   (if (eq e 1) 0
                     (neg (nm nb (if (eq who 88) 79 88) (neg 2) (neg bv) 0 nb (sub e 1)))))
            (if (gt v bv)
              (pick b who (merge i 1) (tail rest) e i v)
              (pick b who (merge i 1) (tail rest) e bi bv))))))))
(let b (map idc {board})
  (let s (head {side})
    (pick b s 0 b (len (filter (lambda c (eq c 46)) b)) (neg 1) (neg 2))))

```

## What the test run said

```
FAIL inputs={"board": ".........", "side": "O"} expected=0
run step-limit-exceeded 24:5 [996,1373) `(if (ne (head rest) 46) (nm b who alpha beta ...`: step budget of 7000000 spent; stopped here, not where the cost is. steps by function: nm 2.8M (74k calls), won 2.4M (16k calls), setat 1.8M (99k calls), pick 685 (9 calls), +2 more
```
