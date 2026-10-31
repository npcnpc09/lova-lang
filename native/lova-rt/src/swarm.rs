//! The swarm family (0x5F-0x61): `swarm-age`, `swarm-hit` and
//! `swarm-draw` -- a shooter's bullet records walked natively
//! (spec/runtime-semantics.md §5.12; `core/runtime.py`, `swarm_age`,
//! `swarm_hit` and `swarm_draw`, is the reference).  One step for the node, like a fixed-point operator; the
//! values are the reference's to the bit: unbounded integers, floor
//! division, the same order, each field read only in the case that
//! needs it.  A needed field that is absent is `get`'s signal 17.
//!
//! Both evaluators come here once the operands are values
//! (`vm::ops::work`), so they cannot differ.

use crate::fixed::SIN_Q;
use crate::int::Int;
use crate::rt::{as_int, as_list, as_map};
use crate::tokens::Arena;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;
use std::rc::Rc;

/// A rod: it hits along (sx sy sz) from where it is.
const ROD: i64 = 125;

const NAMES: [&str; 18] = [
    "born", "die", "kind", "reach", "hit", "w", "ox", "oy", "oz", "vx", "vy", "vz", "g", "cx",
    "cz", "sx", "sy", "sz",
];
const BORN: usize = 0;
const DIE: usize = 1;
const KIND: usize = 2;
const REACH: usize = 3;
const HIT: usize = 4;
const W: usize = 5;
const OX: usize = 6;
const OY: usize = 7;
const OZ: usize = 8;
const VX: usize = 9;
const VY: usize = 10;
const VZ: usize = 11;
const G: usize = 12;
const CX: usize = 13;
const CZ: usize = 14;
const SX: usize = 15;
const SY: usize = 16;
const SZ: usize = 17;

struct Keys(Vec<MapKey>);

impl Keys {
    fn new() -> Keys {
        Keys(NAMES.iter().map(|n| MapKey::T(Rc::new(n.to_string()))).collect())
    }
}

fn missing() -> Fault {
    domain(
        "signalled",
        "signal 17".to_string(),
        detail(vec![("operator", J::from("signal")), ("code", J::from(17))]),
        "catch it with `when-anomaly` and branch on the code",
    )
}

fn field(a: &Arena, m: &MapValue, keys: &Keys, i: usize, ctx: &str) -> R<Int> {
    match m.get(&keys.0[i]) {
        Some(e) => as_int(a, &e.val, ctx),
        None => Err(missing()),
    }
}

#[inline]
fn i(v: i64) -> Int {
    Int::from_i64(v)
}

fn sq(x: &Int) -> Int {
    x.mul(x)
}

/// `fixed_sin`: 1024 sin of `k` 256ths of a turn, any `k`.
fn sin256(k: &Int) -> Int {
    let k = match k {
        Int::S(v) => v.rem_euclid(256),
        _ => k.mod_floor(&i(256)).to_i64().unwrap_or(0),
    };
    i(if k <= 64 {
        SIN_Q[k as usize]
    } else if k <= 128 {
        SIN_Q[(128 - k) as usize]
    } else if k <= 192 {
        -SIN_Q[(k - 128) as usize]
    } else {
        -SIN_Q[(256 - k) as usize]
    })
}

/// A spun bullet's sine: the table read between entries, floor division.
fn fine_sin(an: &Int) -> Int {
    let c256 = i(256);
    let k = an.div_floor(&c256);
    let s0 = sin256(&k);
    let s1 = sin256(&k.add(&i(1)));
    let f = an.sub(&k.mul(&c256));
    s0.add(&s1.sub(&s0).mul(&f).div_floor(&c256))
}

struct Bullet<'k> {
    m: MapValue,
    keys: &'k Keys,
    a: Int,
    ctx: &'static str,
}

impl<'k> Bullet<'k> {
    fn f(&self, ar: &Arena, n: usize) -> R<Int> {
        field(ar, &self.m, self.keys, n, self.ctx)
    }

    fn spun(&self, ar: &Arena) -> R<bool> {
        Ok(!self.f(ar, W)?.is_zero())
    }

    /// (qx, qz, cos, sin) of the turned frame at age `a`.
    fn spin(&self, ar: &Arena, a: &Int) -> R<(Int, Int, Int, Int)> {
        let qx = self.f(ar, OX)?.sub(&self.f(ar, CX)?).add(&self.f(ar, VX)?.mul(a));
        let qz = self.f(ar, OZ)?.sub(&self.f(ar, CZ)?).add(&self.f(ar, VZ)?.mul(a));
        let an = self.f(ar, W)?.mul(a);
        Ok((qx, qz, fine_sin(&an.add(&i(16384))), fine_sin(&an)))
    }

    fn x(&self, ar: &Arena, a: &Int) -> R<Int> {
        if self.spun(ar)? {
            let (qx, qz, c, s) = self.spin(ar, a)?;
            Ok(self.f(ar, CX)?.add(&qx.mul(&c).sub(&qz.mul(&s)).div_floor(&i(1024))))
        } else {
            Ok(self.f(ar, OX)?.add(&self.f(ar, VX)?.mul(a)))
        }
    }

    fn z(&self, ar: &Arena, a: &Int) -> R<Int> {
        if self.spun(ar)? {
            let (qx, qz, c, s) = self.spin(ar, a)?;
            Ok(self.f(ar, CZ)?.add(&qx.mul(&s).add(&qz.mul(&c)).div_floor(&i(1024))))
        } else {
            Ok(self.f(ar, OZ)?.add(&self.f(ar, VZ)?.mul(a)))
        }
    }

    fn y(&self, ar: &Arena, a: &Int) -> R<Int> {
        let up = self.f(ar, OY)?.add(&self.f(ar, VY)?.mul(a));
        Ok(up.sub(&self.f(ar, G)?.mul(&a.mul(a)).div_floor(&i(2))))
    }

    fn rod_d2(&self, ar: &Arena, a: &Int, p: &[Int; 3]) -> R<Int> {
        let (sx, sy, sz) = (self.f(ar, SX)?, self.f(ar, SY)?, self.f(ar, SZ)?);
        let dx = p[0].sub(&self.x(ar, a)?);
        let dy = p[1].sub(&self.y(ar, a)?);
        let dz = p[2].sub(&self.z(ar, a)?);
        let l2 = std::cmp::max(i(1), sq(&sx).add(&sq(&sy).add(&sq(&sz))));
        let dot = dx.mul(&sx).add(&dy.mul(&sy).add(&dz.mul(&sz)));
        let cl = std::cmp::max(i(0), std::cmp::min(l2.clone(), dot));
        let f = cl.mul(&i(1024)).div_floor(&l2);
        let c1024 = i(1024);
        let ex = dx.sub(&sx.mul(&f).div_floor(&c1024));
        let ey = dy.sub(&sy.mul(&f).div_floor(&c1024));
        let ez = dz.sub(&sz.mul(&f).div_floor(&c1024));
        Ok(sq(&ex).add(&sq(&ey).add(&sq(&ez))))
    }

    fn d2(&self, ar: &Arena, rod: bool, a: &Int, p: &[Int; 3]) -> R<Int> {
        if rod {
            return self.rod_d2(ar, a, p);
        }
        let dx = self.x(ar, a)?.sub(&p[0]);
        let dy = self.y(ar, a)?.sub(&p[1]);
        let dz = self.z(ar, a)?.sub(&p[2]);
        Ok(sq(&dx).add(&sq(&dy).add(&sq(&dz))))
    }

    fn close(&self, ar: &Arena, rod: bool, p: &[Int; 3]) -> R<bool> {
        let a = &self.a;
        let e = self.f(ar, REACH)?;
        if rod {
            let out = |d: Int, s: Int| -> bool {
                if s.is_negative() {
                    d < s.sub(&e) || d > e
                } else {
                    d < e.neg() || d > s.add(&e)
                }
            };
            if out(p[0].sub(&self.x(ar, a)?), self.f(ar, SX)?) {
                return Ok(false);
            }
            if out(p[2].sub(&self.z(ar, a)?), self.f(ar, SZ)?) {
                return Ok(false);
            }
            if out(p[1].sub(&self.y(ar, a)?), self.f(ar, SY)?) {
                return Ok(false);
            }
            return Ok(self.rod_d2(ar, a, p)? < sq(&e));
        }
        let dx = self.x(ar, a)?.sub(&p[0]);
        if dx.abs() > e {
            return Ok(false);
        }
        let dz = self.z(ar, a)?.sub(&p[2]);
        if dz.abs() > e {
            return Ok(false);
        }
        let dy = self.y(ar, a)?.sub(&p[1]);
        Ok(sq(&dx).add(&sq(&dy).add(&sq(&dz))) < sq(&e))
    }
}

fn ints(a: &Arena, v: &Value, n: usize, ctx: &str) -> R<Vec<Int>> {
    let xs = list_walk(&as_list(a, v, ctx)?);
    if xs.len() != n {
        return Err(domain(
            "domain-error",
            format!("{}: expected a list of {} integers, got {} elements", ctx, n, xs.len()),
            detail(vec![("operator", J::from(ctx)), ("length", J::from(xs.len()))]),
            &format!(
                "give `{}` the place as `(list x y z)` and the wave as \
`(list wave wave-r wave-o wave-sp)`",
                ctx
            ),
        ));
    }
    xs.iter().map(|x| as_int(a, x, ctx)).collect()
}

fn point(v: Vec<Int>) -> [Int; 3] {
    let mut it = v.into_iter();
    [it.next().unwrap(), it.next().unwrap(), it.next().unwrap()]
}

/// `(swarm-age t new pending live)` -> `(list live' pending')`.
pub fn swarm_age(a: &Arena, args: &[Value]) -> R<Value> {
    let ctx = "swarm-age";
    let t = as_int(a, &args[0], ctx)?;
    let mut every = list_walk(&as_list(a, &args[1], ctx)?);
    every.reverse();
    every.extend(list_walk(&as_list(a, &args[2], ctx)?));
    let old = list_walk(&as_list(a, &args[3], ctx)?);
    let keys = Keys::new();
    let mut due: Vec<bool> = Vec::with_capacity(every.len());
    for b in every.iter() {
        let m = as_map(a, b, ctx)?;
        due.push(field(a, &m, &keys, BORN, ctx)? <= t);
    }
    let mut kept: Vec<Value> = Vec::with_capacity(every.len() + old.len());
    let mut later: Vec<Value> = Vec::new();
    let mut fresh: Vec<Value> = Vec::new();
    for (b, d) in every.into_iter().zip(due.into_iter()) {
        if d {
            fresh.push(b);
        } else {
            later.push(b);
        }
    }
    for b in fresh.into_iter().rev().chain(old.into_iter()) {
        let m = as_map(a, &b, ctx)?;
        if t < field(a, &m, &keys, DIE, ctx)? {
            kept.push(b);
        }
    }
    Ok(list_from(vec![list_from(kept), list_from(later)]))
}

/// `(swarm-hit bs t at before wave)` -> `(list hit fakes grazes waved)`.
pub fn swarm_hit(a: &Arena, args: &[Value]) -> R<Value> {
    let ctx = "swarm-hit";
    let t = as_int(a, &args[1], ctx)?;
    let p = point(ints(a, &args[2], 3, ctx)?);
    let prev = match &args[3] {
        Value::Nil => None,
        v => Some(point(ints(a, v, 3, ctx)?)),
    };
    let wave = ints(a, &args[4], 4, ctx)?;
    let (wv, wr, wo, wsp) = (&wave[0], &wave[1], &wave[2], &wave[3]);
    let keys = Keys::new();
    let (mut hit, mut fakes, mut grazes, mut waved) = (false, 0i64, 0i64, 0i64);
    let one = i(1);
    for v in list_walk(&as_list(a, &args[0], ctx)?) {
        let m = as_map(a, &v, ctx)?;
        let born = field(a, &m, &keys, BORN, ctx)?;
        let b = Bullet { m, keys: &keys, a: t.sub(&born), ctx };
        let kind = b.f(a, KIND)?;
        let k = kind.to_i64();
        let rod = k == Some(ROD);
        if !b.close(a, rod, &p)? {
            continue;
        }
        let wavy = matches!(k, Some(70..=99));
        let real = if !wavy {
            true
        } else {
            let c = (k.unwrap() - 60).div_euclid(10);
            if c >= 3 {
                false
            } else if wv.is_zero() {
                true
            } else {
                let cur = if wr.is_zero() {
                    wv.clone()
                } else {
                    let n = wsp.mul(&b.a).add(&i(2).mul(wr).sub(wo));
                    one.add(&n.div_floor(wr).mod_floor(&i(2)))
                };
                cur == i(c)
            }
        };
        let inside = b.d2(a, rod, &b.a, &p)? < sq(&b.f(a, HIT)?);
        if !real {
            if inside {
                fakes += 1;
            }
            continue;
        }
        hit = hit || inside;
        if let Some(q) = &prev {
            let r = b.f(a, REACH)?;
            if b.d2(a, rod, &b.a.sub(&one), q)? >= sq(&r) {
                grazes += 1;
                if wavy {
                    waved += 1;
                }
            }
        }
    }
    Ok(list_from(vec![
        Value::Int(i(hit as i64)),
        Value::Int(i(fakes)),
        Value::Int(i(grazes)),
        Value::Int(i(waved)),
    ]))
}

/// The kind Godot draws for kind `k` at age `a` while the wave `wv` is
/// above 0: the game's `shown-band` when the wave runs in bands
/// (`wave-r > 0`), else its `shown-flat`.
fn shown(k: Int, a: &Int, wv: &Int, wr: &Int, wo: &Int, wsp: &Int) -> Int {
    let c10 = i(10);
    let zero = i(0);
    if *wr > zero {
        if k < i(70) || k > i(99) {
            return k;
        }
        let n = wsp.mul(a).add(&i(2).mul(wr).sub(wo));
        let cur = i(1).add(&n.div_floor(wr).mod_floor(&i(2)));
        if k.div_floor(&c10) == i(6).add(&cur) {
            return k;
        }
        if k < i(90) {
            return k.add(&i(100));
        }
        return k.mod_floor(&c10).add(&i(if cur == i(1) { 180 } else { 170 }));
    }
    if k < i(70) {
        return k;
    }
    if k.div_floor(&c10) == i(6).add(wv) {
        return k;
    }
    if k < i(90) {
        return k.add(&i(100));
    }
    if k > i(99) {
        return k;
    }
    k.mod_floor(&c10).add(&i(if *wv == i(1) { 180 } else { 170 }))
}

/// `(swarm-draw bs t wave tail)` -> each record's `x y z kind` consed
/// onto `tail`, the first record's deepest (a left fold).
pub fn swarm_draw(a: &Arena, args: &[Value]) -> R<Value> {
    let ctx = "swarm-draw";
    let t = as_int(a, &args[1], ctx)?;
    let wave = ints(a, &args[2], 4, ctx)?;
    let (wv, wr, wo, wsp) = (&wave[0], &wave[1], &wave[2], &wave[3]);
    let wavy = *wv > i(0);
    let mut out = as_list(a, &args[3], ctx)?;
    let keys = Keys::new();
    for v in list_walk(&as_list(a, &args[0], ctx)?) {
        let m = as_map(a, &v, ctx)?;
        let born = field(a, &m, &keys, BORN, ctx)?;
        let b = Bullet { m, keys: &keys, a: t.sub(&born), ctx };
        let x = b.x(a, &b.a)?;
        let y = b.y(a, &b.a)?;
        let z = b.z(a, &b.a)?;
        let mut k = b.f(a, KIND)?;
        if wavy {
            k = shown(k, &b.a, wv, wr, wo, wsp);
        }
        for n in [k, z, y, x] {
            out = Value::Cons(Rc::new(ConsCell { head: Value::Int(n), tail: out }));
        }
    }
    Ok(out)
}
