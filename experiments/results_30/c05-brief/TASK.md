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
FAIL inputs={"board": ".........", "side": "O"} expected=0
run step-limit-exceeded 7:15 [316,319) `nth`: step budget of 7000000 spent; stopped here, not where the cost is. steps by function: winloop 2.3M (58k calls), nth 2.2M (273k calls), nm 1.3M (34k calls), setat 877k (48k calls), +4 more
```
