# Task h03

Given a text `text` of log lines, each `LEVEL component: message` where LEVEL is one of INFO, WARN, ERROR, return a text with one line per component, `component errors warnings` (the counts of its ERROR and WARN lines), ordered by errors descending, then warnings descending, then component name ascending. Components with only INFO lines still appear with 0 0. Blank lines in the input are skipped.  [inputs: {text}]

Each test runs under 7000000 steps.

## Your last submission (program.lova)

```lova
(def strip-colon [w]
  (let n (text-len w)
    (if (and (gt n 0) (eq (nth w (sub n 1)) 58)) (text-slice w 0 (sub n 1)) w)))
(def step [st ln]
  (let ws (words ln)
    (if (lt (len ws) 2)
        st
        (let lvl (head ws)
          (let comp (strip-colon (nth ws 1))
            (let st2 (put st seen (map-count (get st2x seen) comp))
              st2))))))
(let init (rec errs (map-of (nil)) warns (map-of (nil)) seen (map-of (nil)))
  (let st (fold (lambda a (lambda ln
              (let ws (words ln)
                (if (lt (len ws) 2)
                    a
                    (let lvl (head ws)
                      (let comp (strip-colon (nth ws 1))
                        (let a2 (put a seen (map-count (get a seen) comp))
                          (cond (eq lvl "ERROR") (put a2 errs (map-count (get a2 errs) comp))
                                (eq lvl "WARN") (put a2 warns (map-count (get a2 warns) comp))
                                a2))))))))
            init (lines {text}))
    (let ks (sort-by (lambda x (lambda y
                (let ex (map-get (get st errs) x 0)
                  (let ey (map-get (get st errs) y 0)
                    (let wx (map-get (get st warns) x 0)
                      (let wy (map-get (get st warns) y 0)
                        (cond (ne ex ey) (gt ex ey)
                              (ne wx wy) (gt wx wy)
                              (text-lt x y))))))))
              (map-keys (get st seen)))
      (join (map (lambda c (join (list c (text-of (map-get (get st errs) c 0))
                                        (text-of (map-get (get st warns) c 0))) " "))
                 ks)
            10))))

```

## What the test run said

```
FAIL compile unbound-ref 10:51 [320,324) `st2x`: `st2x` is not defined; nearest: step, st, st2
```
