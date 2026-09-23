# Task h04

Given a text board of nine characters (X, O or . for empty, rows first) and a text side (X or O) whose turn it is, return the 0-based index of the best move for side: a move that wins if one exists, else one that forces a draw, else any move; where several moves are equally good, the lowest index. Both players play perfectly after the move. The board has at least one empty square and no winner yet.  [inputs: {board}, {side}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def w3 [x y z] (and (ne x 46) (and (eq x y) (eq y z))))
(def winner [b]
 (let a (nth b 0) (let q (nth b 1) (let c (nth b 2)
 (let d (nth b 3) (let e (nth b 4) (let f (nth b 5)
 (let g (nth b 6) (let h (nth b 7) (let i (nth b 8)
  (cond (w3 a q c) a (w3 d e f) d (w3 g h i) g
        (w3 a d g) a (w3 q e h) q (w3 c f i) c
        (w3 a e i) a (w3 c e g) c 0))))))))))))
(def emp [b i]
  (if (nil? b) (nil)
    (if (eq (head b) 46) (cons i (emp (tail b) (inc i))) (emp (tail b) (inc i)))))
(def setat [b i c] (append (take i b) (cons c (drop (inc i) b))))
(def other [c] (if (eq c 88) 79 88))
(def memo-set [memo k v] (rec s v m (map-put memo k v)))
(def mm [b cur me memo]
  (let k (text-of-chars b)
    (let hit (map-get memo k 9)
      (if (ne hit 9) (rec s hit m memo)
        (let wn (winner b)
          (if wn (memo-set memo k (if (eq wn me) 1 (neg 1)))
            (let ms (emp b 0)
              (if (nil? ms) (memo-set memo k 0)
                (let r (loopm b cur me ms (if (eq cur me) (neg 2) 2) memo)
                  (memo-set (get r m) k (get r s)))))))))))
(def loopm [b cur me ms bestv memo]
  (if (nil? ms) (rec s bestv m memo)
    (let r (mm (setat b (head ms) cur) (other cur) me memo)
      (let v (get r s)
        (let nb (if (eq cur me) (max bestv v) (min bestv v))
          (if (eq nb (if (eq cur me) 1 (neg 1)))
              (rec s nb m (get r m))
              (loopm b cur me (tail ms) nb (get r m))))))))
(def pick [b me ms bi bs memo]
  (if (nil? ms) bi
    (let i (head ms)
      (let r (mm (setat b i me) (other me) me memo)
        (if (gt (get r s) bs)
            (pick b me (tail ms) i (get r s) (get r m))
            (pick b me (tail ms) bi bs (get r m)))))))
(let b (text-chars {board})
  (let me (head (text-chars {side}))
    (pick b me (emp b 0) (neg 1) (neg 2) (map-of (nil)))))

```

## What the test run said

```
FAIL {"inputs": {"board": "XX.OO....", "side": "X"}, "expected": 2, "anomaly": {"kind": "parse-error", "excerpt": ")", "line": 8, "col": 47, "repair_hint": "unexpected closing paren at token 178; a closing paren at line 8 has nothing open to close; a form above it closed too early", "detail": {"message": "unexpected closing paren at token 178; a closing paren at line 8 has nothing open to close; a form above it closed too early", "unclosed": {"line": 8, "col": 47, "excerpt": ")", "missing": 0, "kind": "extra-paren"}}, "span": [369, 370], "stage": "compile"}}
```
