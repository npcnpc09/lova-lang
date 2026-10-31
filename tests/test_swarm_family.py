"""The swarm family (6c): swarm-age and swarm-hit, checked against the
LOVA they replace.

The oracle is the danmaku game's own walk (东方天球谭, rules/danmaku.lova
as of 2026-10-31: `throw`'s let-in and let-go, `weave`'s `close`, `d2`,
`wave-real`, the graze test), copied here with its arithmetic untouched.
Random swarms near a random body -- plain, spun, falling, rods, harmless
(reach and hit 0), on the waves, in and out of their time -- must give
the operators' answer to the bit, on the Python runtime and, when one is
built, on the native runtime's VM and tree-walker alike.
"""

from __future__ import annotations

import random
import unittest
from pathlib import Path

from core.cli import build, format_value
from core.native import NativeRuntime
from core.runtime import DomainTrap, Runtime, evaluate
from core.tokens import SIGNATURES, SWARM_AGE, SWARM_FAMILY, SWARM_HIT

ROOT = Path(__file__).resolve().parent.parent
BIN = next((p for p in (ROOT / "native" / "lova-rt" / "target" / "release" / n
                        for n in ("lova-rt.exe", "lova-rt")) if p.is_file()), None)

ORACLE = r"""
(def sq [n] (mul n n))
(def clamp [v lo hi] (max lo (min hi v)))
(def onto [xs ys] (fold (fn [acc x] (cons x acc)) ys xs))
(def born-by [t bs] (filter (lambda b (le (get b born) t)) bs))
(def not-yet [t bs] (filter (lambda b (gt (get b born) t)) bs))
(def o-age [t fresh pd bs]
  (list (filter (lambda b (lt t (get b die))) (onto (born-by t (onto fresh pd)) bs))
        (not-yet t (onto fresh pd))))
(def fine-sin [an]
  (let [i (div an 256)
        s0 (sin i)]
    (merge s0 (div (mul (sub (sin (merge i 1)) s0) (sub an (mul i 256))) 256))))
(def fine-cos [an] (fine-sin (merge an 16384)))
(def spin-x [b a]
  (let [qx (merge (sub (get b ox) (get b cx)) (mul (get b vx) a))
        qz (merge (sub (get b oz) (get b cz)) (mul (get b vz) a))
        an (mul (get b w) a)]
    (merge (get b cx) (div (sub (mul qx (fine-cos an)) (mul qz (fine-sin an))) 1024))))
(def spin-z [b a]
  (let [qx (merge (sub (get b ox) (get b cx)) (mul (get b vx) a))
        qz (merge (sub (get b oz) (get b cz)) (mul (get b vz) a))
        an (mul (get b w) a)]
    (merge (get b cz) (div (merge (mul qx (fine-sin an)) (mul qz (fine-cos an))) 1024))))
(def bx-at [b a] (if (get b w) (spin-x b a) (merge (get b ox) (mul (get b vx) a))))
(def by-at [b a] (sub (merge (get b oy) (mul (get b vy) a)) (div (mul (get b g) (mul a a)) 2)))
(def bz-at [b a] (if (get b w) (spin-z b a) (merge (get b oz) (mul (get b vz) a))))
(def ROD [] 125)
(def rod-d2 [b t px py pz]
  (let [a (sub t (get b born))
        sx (get b sx) sy (get b sy) sz (get b sz)
        dx (sub px (bx-at b a))
        dy (sub py (by-at b a))
        dz (sub pz (bz-at b a))
        l2 (max 1 (merge (mul sx sx) (merge (mul sy sy) (mul sz sz))))
        f (div (mul (clamp (merge (mul dx sx) (merge (mul dy sy) (mul dz sz))) 0 l2) 1024) l2)
        ex (sub dx (div (mul sx f) 1024))
        ey (sub dy (div (mul sy f) 1024))
        ez (sub dz (div (mul sz f) 1024))]
    (merge (mul ex ex) (merge (mul ey ey) (mul ez ez)))))
(def rod-out [d s e] (if (lt s 0) (or (lt d (sub s e)) (gt d e)) (or (lt d (neg e)) (gt d (merge s e)))))
(def close-rod [b t px py pz]
  (let [a (sub t (get b born))
        e (get b reach)]
    (if (rod-out (sub px (bx-at b a)) (get b sx) e)
        0
        (if (rod-out (sub pz (bz-at b a)) (get b sz) e)
            0
            (if (rod-out (sub py (by-at b a)) (get b sy) e)
                0
                (lt (rod-d2 b t px py pz) (sq e)))))))
(def close-point [b t px py pz]
  (let [a (sub t (get b born))
        e (get b reach)
        dx (sub (if (get b w) (spin-x b a) (merge (get b ox) (mul (get b vx) a))) px)]
    (if (gt (abs dx) e)
        0
        (let dz (sub (if (get b w) (spin-z b a) (merge (get b oz) (mul (get b vz) a))) pz)
          (if (gt (abs dz) e)
              0
              (let dy (sub (by-at b a) py)
                (lt (merge (mul dx dx) (merge (mul dy dy) (mul dz dz))) (mul e e))))))))
(def close [b t px py pz]
  (if (eq (get b kind) ROD) (close-rod b t px py pz) (close-point b t px py pz)))
(def d2-point [b t px py pz]
  (let [a (sub t (get b born))
        dx (sub (bx-at b a) px)
        dy (sub (by-at b a) py)
        dz (sub (bz-at b a) pz)]
    (merge (mul dx dx) (merge (mul dy dy) (mul dz dz)))))
(def d2 [b t px py pz]
  (if (eq (get b kind) ROD) (rod-d2 b t px py pz) (d2-point b t px py pz)))
(def wave-at [w b t]
  (let r (get w wave-r)
    (if (eq r 0)
        (get w wave)
        (inc (mod (div (merge (mul (get w wave-sp) (sub t (get b born))) (sub (mul 2 r) (get w wave-o))) r) 2)))))
(def wave-real [w b t]
  (let k (get b kind)
    (if (or (lt k 70) (gt k 99))
        1
        (let c (div (sub k 60) 10)
          (and (lt c 3) (or (eq (get w wave) 0) (eq c (wave-at w b t))))))))
(def o-hit [w bs t px py pz]
  (let [near0 (filter (lambda b (close b t px py pz)) bs)
        near (filter (lambda b (wave-real w b t)) near0)
        fakes (if (lt (len near) (len near0))
                  (len (filter (lambda b (and (not (wave-real w b t)) (lt (d2 b t px py pz) (sq (get b hit))))) near0))
                  0)
        hit (any (lambda b (lt (d2 b t px py pz) (sq (get b hit)))) near)
        grazing (if (get w blinked)
                    (nil)
                    (filter (lambda b (ge (d2 b (sub t 1) (get w x0) (get w y0) (get w z0))
                                          (sq (get b reach))))
                            near))
        waved (len (filter (lambda b (let k (get b kind) (and (ge k 70) (lt k 100)))) grazing))]
    (list hit fakes (len grazing) waved)))
(def n-hit [w bs t px py pz]
  (swarm-hit bs t (list px py pz)
             (if (get w blinked) (nil) (list (get w x0) (get w y0) (get w z0)))
             (list (get w wave) (get w wave-r) (get w wave-o) (get w wave-sp))))
"""

F = 65536


def _rec(fields):
    return "(rec " + " ".join(f"{k} {v}" for k, v in fields.items()) + ")"


def _bullet(rnd, n, t, near):
    kinds = [0, 1, 2, 3, 4, 5, 6, 7, 9, 13, 45, 46, 52, 71, 72, 81, 84, 93, 125, 125, 1003, 70, 73, 80, 82, 99]
    kind = rnd.choice(kinds)
    r = rnd.choice([F // 10, F // 5, F * 2 // 5, F // 20, F // 8])
    harmless = 50 <= kind < 60
    b = dict(n=n, ox=near[0] + rnd.randint(-3 * F, 3 * F), oy=near[1] + rnd.randint(-3 * F, 3 * F),
             oz=near[2] + rnd.randint(-3 * F, 3 * F),
             vx=rnd.randint(-F // 8, F // 8), vy=rnd.randint(-F // 8, F // 8), vz=rnd.randint(-F // 8, F // 8),
             g=rnd.choice([0, 0, 0, F // 400, -F // 300]),
             born=t - rnd.randint(-3, 40), kind=kind, r=r,
             w=rnd.choice([0, 0, 0, 37, -120, 900, 4096]),
             cx=near[0] + rnd.randint(-F, F), cz=near[2] + rnd.randint(-F, F),
             reach=0 if harmless else r + 7 * F // 10, hit=0 if harmless else r + F // 10, lk=0)
    b["die"] = b["born"] + rnd.randint(0, 80)
    if kind == 125:
        b.update(sx=rnd.randint(-4 * F, 4 * F), sy=rnd.randint(-F, F), sz=rnd.randint(-4 * F, 4 * F))
        if rnd.random() < 0.2:
            b.update(sx=0, sy=0, sz=0)
    if rnd.random() < 0.1:
        b.update(ox=near[0] + rnd.randint(-F // 4, F // 4), oy=near[1], oz=near[2], vx=0, vy=0, vz=0, g=0, w=0)
    return b


def _case(rnd):
    t = rnd.randint(-5, 5000)
    me = [rnd.randint(-8 * F, 8 * F), rnd.randint(0, 6 * F), rnd.randint(-8 * F, 8 * F)]
    step = rnd.choice([F // 8, F // 2, F])
    was = [me[0] + rnd.randint(-step, step), me[1] + rnd.randint(-step, step), me[2] + rnd.randint(-step, step)]
    wave = rnd.choice([(0, 0, 0, 0), (1, 0, 0, 0), (2, 0, 0, 0),
                       (1, 3 * F, rnd.randint(0, 6 * F), F // 6), (2, 2 * F, rnd.randint(-F, F), F // 4)])
    w = dict(wave=wave[0], **{"wave-r": wave[1], "wave-o": wave[2], "wave-sp": wave[3]},
             blinked=rnd.choice([0, 0, 0, 1]), x0=was[0], y0=was[1], z0=was[2])
    bs = [_bullet(rnd, i, t, me) for i in range(rnd.randint(0, 40))]
    return t, me, w, bs


def _program(seed: int, cases: int) -> str:
    rnd = random.Random(seed)
    checks = []
    for _ in range(cases):
        t, me, w, bs = _case(rnd)
        world = _rec(w)
        lst = "(list " + " ".join(_rec(b) for b in bs) + ")"
        args = f"{world} {lst} {t} {me[0]} {me[1]} {me[2]}"
        checks.append(f"(list (o-hit {args}) (n-hit {args}))")
        k = rnd.randint(0, len(bs))
        fresh = "(list " + " ".join(_rec(b) for b in bs[:k // 2]) + ")"
        pend = "(list " + " ".join(_rec(b) for b in bs[k // 2:k]) + ")"
        live = "(list " + " ".join(_rec(b) for b in bs[k:]) + ")"
        checks.append(f"(list (o-age {t} {fresh} {pend} {live}) (swarm-age {t} {fresh} {pend} {live}))")
    return ORACLE + "(list " + "\n".join(checks) + ")"


class TheTable(unittest.TestCase):

    def test_the_family_is_two_operators_at_0x5f(self):
        self.assertEqual(sorted(SWARM_FAMILY), [0x5F, 0x60])
        self.assertEqual((SWARM_AGE, SWARM_HIT), (0x5F, 0x60))
        self.assertEqual([SIGNATURES[t]["name"] for t in (SWARM_AGE, SWARM_HIT)], ["swarm-age", "swarm-hit"])
        self.assertEqual([SIGNATURES[t]["arity"] for t in (SWARM_AGE, SWARM_HIT)], [4, 5])


def _python(src: str):
    tree, _ = build(src)
    rt = Runtime(max_steps=500_000_000)
    return evaluate(tree, rt), rt.steps


class AgainstTheGame(unittest.TestCase):
    """Each pair the oracle's and the operator's, on random swarms."""

    def _check(self, value):
        from core.runtime import list_to_python
        pairs = list_to_python(value)
        hits = grazes = fakes = waved = 0
        for pair in pairs:
            old, new = list_to_python(pair)
            self.assertEqual(format_value(old), format_value(new))
            got = list_to_python(new)
            if isinstance(got[0], int):
                hits += got[0]
                fakes += got[1]
                grazes += got[2]
                waved += got[3]
        return hits, fakes, grazes, waved

    def test_python_runtime(self):
        total = [0, 0, 0, 0]
        for seed in range(4):
            value, _ = _python(_program(seed, 25))
            for i, n in enumerate(self._check(value)):
                total[i] += n
        # the random swarms do reach every case
        self.assertTrue(all(n > 2 for n in total), total)

    @unittest.skipUnless(BIN, "no native runtime built")
    def test_native_vm_and_tree(self):
        for flags in ([], ["--tree"]):
            rt = NativeRuntime([str(BIN)] + flags)
            try:
                for seed in range(6, 8):
                    src = _program(seed, 25)
                    tree, _ = build(src)
                    py, _ = _python(src)
                    got = rt.run(tree, max_steps=500_000_000)
                    self.assertEqual(got.value_text, format_value(py))
            finally:
                rt.close()


class Steps(unittest.TestCase):

    def test_one_step_a_node(self):
        """However many records, the walk is the operator's one step."""
        bs = "(list " + " ".join(f"(rec born {i} die {i + 5} kind 0 reach 9 hit 3 w 0 ox 0 oy 0 oz 0 "
                                 f"vx 0 vy 0 vz 0 g 0)" for i in range(50)) + ")"
        for call in ("(swarm-age 3 xs xs xs)", "(swarm-hit xs 9 (list 0 0 0) (list 0 0 0) (list 0 0 0 0))"):
            _, many = _python(f"(let xs {bs} {call})")
            _, none = _python(f"(let xs (nil) {call})")
            self.assertEqual(many - none, _python(bs)[1] - _python("(nil)")[1])


class Faults(unittest.TestCase):

    def test_a_needed_field_absent_is_get_s_signal(self):
        with self.assertRaises(DomainTrap) as cm:
            _python("(swarm-age 3 (list (rec born 1)) (nil) (nil))")
        self.assertEqual(cm.exception.anomaly["detail"]["code"], 17)

    def test_a_field_no_case_needs_may_be_absent(self):
        # not spun: no cx, cz; not a rod: no sx sy sz; far away: nothing past x
        v, _ = _python("(swarm-hit (list (rec born 0 kind 0 reach 10 w 0 ox 100 vx 0)) 5 (list 0 0 0) (nil) (list 0 0 0 0))")
        self.assertEqual(format_value(v), "(0 0 0 0)")

    def test_a_place_is_three_integers(self):
        with self.assertRaises(DomainTrap):
            _python("(swarm-hit (nil) 5 (list 0 0) (nil) (list 0 0 0 0))")


if __name__ == "__main__":
    unittest.main()
