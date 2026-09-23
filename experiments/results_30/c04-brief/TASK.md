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
FAIL inputs={"board": ".........", "side": "O"} expected=0
run step-limit-exceeded 5:19 [204,214) `(nth ln 0)`: step budget of 7000000 spent; stopped here, not where the cost is. steps by function: bestloop 1.2M (33k calls), code 1.1M (102k calls), put-at 1.1M (59k calls), nth 978k (122k calls), +4 more
```
