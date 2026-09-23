# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def b0 [m] (mod m 2))
(def b1 [m] (mod (div m 2) 2))
(def b2 [m] (mod (div m 4) 2))
(def b3 [m] (mod (div m 8) 2))
(def b4 [m] (mod (div m 16) 2))
(def b5 [m] (mod (div m 32) 2))
(def b6 [m] (mod (div m 64) 2))
(def b7 [m] (mod (div m 128) 2))
(def b8 [m] (mod (div m 256) 2))
(def win-at [i m]
  (cond (eq i 0) (or (and (b1 m) (b2 m)) (or (and (b3 m) (b6 m)) (and (b4 m) (b8 m))))
        (eq i 1) (or (and (b0 m) (b2 m)) (and (b4 m) (b7 m)))
        (eq i 2) (or (and (b0 m) (b1 m)) (or (and (b5 m) (b8 m)) (and (b4 m) (b6 m))))
        (eq i 3) (or (and (b4 m) (b5 m)) (and (b0 m) (b6 m)))
        (eq i 4) (or (and (b3 m) (b5 m)) (or (and (b1 m) (b7 m)) (or (and (b0 m) (b8 m)) (and (b2 m) (b6 m)))))
        (eq i 5) (or (and (b3 m) (b4 m)) (and (b2 m) (b8 m)))
        (eq i 6) (or (and (b7 m) (b8 m)) (or (and (b0 m) (b3 m)) (and (b2 m) (b4 m))))
        (eq i 7) (or (and (b6 m) (b8 m)) (and (b1 m) (b4 m)))
        (or (and (b6 m) (b7 m)) (or (and (b2 m) (b5 m)) (and (b0 m) (b4 m))))))
(def nmax [mm oo n alpha beta] (nloop mm oo n 0 1 alpha beta (neg 2)))
(def nloop [mm oo n i pw alpha beta best]
  (if (ge i 9) best
    (if (mod (div (merge mm oo) pw) 2)
        (nloop mm oo n (inc i) (mul pw 2) alpha beta best)
        (let m2 (merge mm pw)
          (let v (if (win-at i m2) 1
                     (if (eq n 1) 0 (neg (nmax oo m2 (sub n 1) (neg beta) (neg alpha)))))
            (let best2 (max best v)
              (let a2 (max alpha v)
                (if (ge a2 beta) best2
                  (nloop mm oo n (inc i) (mul pw 2) a2 beta best2)))))))))
(def pick [mm oo n i pw besti bestv]
  (if (ge i 9) besti
    (if (mod (div (merge mm oo) pw) 2)
        (pick mm oo n (inc i) (mul pw 2) besti bestv)
        (let m2 (merge mm pw)
          (let v (if (win-at i m2) 1
                     (if (eq n 1) 0 (neg (nmax oo m2 (sub n 1) (neg 2) 2))))
            (if (gt v bestv)
                (pick mm oo n (inc i) (mul pw 2) i v)
                (pick mm oo n (inc i) (mul pw 2) besti bestv)))))))
(def mkx [cs pw] (if (nil? cs) 0 (merge (if (eq (head cs) 88) pw 0) (mkx (tail cs) (mul pw 2)))))
(def mko [cs pw] (if (nil? cs) 0 (merge (if (eq (head cs) 79) pw 0) (mko (tail cs) (mul pw 2)))))
(def empty-c [c] (eq c 46))
(let cs (text-chars {board})
  (let xm (mkx cs 1)
    (let om (mko cs 1)
      (let n (len (filter empty-c cs))
        (if (eq (head {side}) 88)
            (pick xm om n 0 1 0 (neg 2))
            (pick om xm n 0 1 0 (neg 2)))))))

```

## What the test run said

```
FAIL inputs={"board": ".........", "side": "O"} expected=0
run step-limit-exceeded 19:62 [978,984) `(b0 m)`: step budget of 7000000 spent; stopped here, not where the cost is. steps by function: nloop 4.8M (104k calls), win-at 1.3M (24k calls), inc 271k (90k calls), nmax 201k (14k calls), +4 more
```
