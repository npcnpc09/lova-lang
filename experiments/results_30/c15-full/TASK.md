# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def code [c] (if (eq c 88) 1 (if (eq c 79) 2 0)))
(def w3 [a b c q] (and (eq a q) (and (eq b q) (eq c q))))
(def best [p mm kb empt]
  (let kk (merge (mul kb 2) (sub p 1))
    (let hit (map-get mm kk 9)
      (if (ne hit 9) (rec s hit m mm)
        (let res (best2 p mm kb empt)
          (rec s (get res s) m (map-put (get res m) kk (get res s))))))))
(def best2 [p mm kb empt]
  (let c0 (mod (div kb 6561) 3)
  (let c1 (mod (div kb 2187) 3)
  (let c2 (mod (div kb 729) 3)
  (let c3 (mod (div kb 243) 3)
  (let c4 (mod (div kb 81) 3)
  (let c5 (mod (div kb 27) 3)
  (let c6 (mod (div kb 9) 3)
  (let c7 (mod (div kb 3) 3)
  (let c8 (mod kb 3)
  (let q (if (eq p 1) 2 1)
    (if (or (w3 c0 c1 c2 q) (or (w3 c3 c4 c5 q) (or (w3 c6 c7 c8 q)
        (or (w3 c0 c3 c6 q) (or (w3 c1 c4 c7 q) (or (w3 c2 c5 c8 q)
        (or (w3 c0 c4 c8 q) (wc2 c4 c6c8 q))))))))
        (rec s (neg 1) m mm)
        (if (eq empt 0) (rec s 0 m mm)
          (bestloop p 0 6561 (neg 2) mm kb empt))))))))))))))
(def bestloop [p i w acc mm kb empt]
  (if (or (eq i 9) (eq acc 1)) (rec s acc m mm)
    (if (ne (mod (div kb w) 3) 0)
        (bestloop p (inc i) (div w 3) acc mm kb empt)
      (let r (best (if (eq p 1) 2 1) mm (merge kb (mul w p)) (sub empt 1))
        (bestloop p (inc i) (div w 3) (max acc (neg (get r s))) (get r m) kb empt)))))
(def pick [p i w bi bs mm kb empt]
  (if (eq i 9) bi
    (if (ne (mod (div kb w) 3) 0) (pick p (inc i) (div w 3) bi bs mm kb empt)
      (let r (best (if (eq p 1) 2 1) mm (merge kb (mul w p)) (sub empt 1))
        (let sc (neg (get r s))
          (if (eq sc 1) i
            (if (gt sc bs) (pick p (inc i) (div w 3) i sc (get r m) kb empt)
                           (pick p (inc i) (div w 3) bi bs (get r m) kb empt))))))))
(let cs (text-chars {board})
  (let kb (fold (lambda a (lambda c (merge (mul a 3) (code c)))) 0 cs)
    (let empt (len (filter (lambda c (eq c 46)) cs))
      (pick (if (eq (head {side}) 88) 1 2) 0 6561 0 (neg 2) (map-of (nil)) kb empt))))

```

## What the test run said

```
FAIL {"inputs": {"board": "XX.OO....", "side": "X"}, "expected": 2, "anomaly": {"kind": "unbound-ref", "stage": "compile", "excerpt": "wc2", "line": 22, "col": 30, "repair_hint": "`wc2` is not defined.  Define it with (def wc2 [...] ...) or use a name in scope.  Nearest: le2, ge2, w3.", "detail": {"name_id": 87, "name": "wc2", "bound": ["le2", "ge2", "p", "code", "w3", "q", "best", "mm", "kb", "empt", "best2", "c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", " g89", " g90", " g91", " g92", " g93", " g94", " g95", "bestloop", "pick", "cs"]}, "span": [837, 840]}}
```
