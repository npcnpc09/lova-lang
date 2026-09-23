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
(def winner [b] (winner-of b (lines3)))
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
FAIL compile type-mismatch 9:31 [439,445) `lines3`: `ref` gives List; the slot wants Fn
```
