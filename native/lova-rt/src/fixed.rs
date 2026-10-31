//! The fixed-point family (0x58-0x5E): `sin`, `cos`, `sin-fine`,
//! `cos-fine`, `quot`, `nth`, `isqrt` -- what `lib/fixed.lova` and the
//! prelude computed in LOVA, as operators (`core/runtime.py`,
//! `fixed_sin` and its neighbours, is the reference).  Each is one step
//! for its node, like a text operator; the values are the library's to
//! the bit: the same quarter table, the same floored reflections, the
//! same twelve Newton rounds.
//!
//! Both evaluators come here once the operands are values
//! (`vm::ops::work`), so they cannot differ.

use crate::int::Int;
use crate::rt::{as_int, as_list};
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;

/// 1024 * sin(k * pi / 128) for k = 0..64: the first quarter of the
/// 256ths circle, `sin-table` in `lib/fixed.lova` as it was.
pub const SIN_Q: [i64; 65] = [
    0, 25, 50, 75, 100, 125, 150, 175, 200, 224, 249, 273, 297, 321, 345, 369, 392, 415, 438, 460,
    483, 505, 526, 548, 569, 590, 610, 630, 650, 669, 688, 706, 724, 742, 759, 775, 792, 807, 822,
    837, 851, 865, 878, 891, 903, 915, 926, 936, 946, 955, 964, 972, 980, 987, 993, 999, 1004,
    1009, 1013, 1016, 1019, 1021, 1023, 1024, 1024,
];

/// `a mod m` (floored) as an `i64` in 0..m, for a bignum `a` too.
fn mod_small(a: &Int, m: i64) -> i64 {
    match a {
        Int::S(v) => v.rem_euclid(m),
        _ => a.mod_floor(&Int::from_i64(m)).to_i64().unwrap_or(0),
    }
}

/// The sine of `k` 256ths of a turn, `k` already in 0..256.
fn sin_k(k: i64) -> i64 {
    if k <= 64 {
        SIN_Q[k as usize]
    } else if k <= 128 {
        SIN_Q[(128 - k) as usize]
    } else if k <= 192 {
        -SIN_Q[(k - 128) as usize]
    } else {
        -SIN_Q[(256 - k) as usize]
    }
}

/// The fine sine of `a` 4096ths of a turn, `a` already in 0..4096:
/// the 256ths table read on the line between two entries, the step
/// rounded toward zero (`quot`).
fn sin_fine_a(a: i64) -> i64 {
    let k = a / 16;
    let f = a % 16;
    let s0 = sin_k(k);
    let s1 = sin_k((k + 1).rem_euclid(256));
    let d = (s1 - s0) * f;
    let q = d.abs() / 16;
    s0 + if d < 0 { -q } else { q }
}

/// `quot`: division toward zero.  The caller has checked `b != 0`.
pub fn quot(a: &Int, b: &Int) -> Int {
    let q = a.abs().div_floor(&b.abs());
    if a.is_negative() == b.is_negative() {
        q
    } else {
        q.neg()
    }
}

/// `isqrt` as `lib/fixed.lova` had it: nought below 1, one for 1-3,
/// else twelve rounds of Newton from max(ONE, n / ONE).
pub fn isqrt(n: &Int) -> Int {
    if let Int::S(v) = n {
        let v = *v;
        if v < 4 {
            return Int::from_i64(if v > 0 { 1 } else { 0 });
        }
        let mut x = std::cmp::max(1024, v / 1024);
        for _ in 0..12 {
            // x >= 1 and x + v/x <= 2^63 - 1 for every v >= 4 here:
            // x stays within [1, max(1024, v/1024)] after the first round.
            x = match x.checked_add(v / x) {
                Some(s) => s / 2,
                None => return isqrt_big(n),
            };
        }
        return Int::from_i64(x);
    }
    isqrt_big(n)
}

fn isqrt_big(n: &Int) -> Int {
    if n.is_negative() {
        return Int::zero();
    }
    let one = Int::from_i64(1024);
    let two = Int::from_i64(2);
    let start = n.div_floor(&one);
    let mut x = if start > one { start } else { one };
    for _ in 0..12 {
        x = x.add(&n.div_floor(&x)).div_floor(&two);
    }
    x
}

fn past_end(_k: &Int) -> Fault {
    domain(
        "domain-error",
        "nth: the index is outside the list".to_string(),
        detail(vec![("operator", J::from("nth"))]),
        "the index is past the end (or negative): guard it with `(lt k (len xs))`; indices start at 0",
    )
}

/// The element of `xs` at `k` (a text's codepoint), or a fault.
pub fn nth(a: &Arena, xs: &Value, k: &Int) -> R<Value> {
    let i = match k.to_i64() {
        Some(i) if i >= 0 => i as u64,
        _ => {
            // A negative index, or one past any list that could exist:
            // the operand is still checked first, as `text-slice` did.
            if !matches!(xs, Value::Text(_)) {
                as_list(a, xs, "nth")?;
            }
            return Err(past_end(k));
        }
    };
    match xs {
        Value::Text(s) => match s.chars().nth(i as usize) {
            Some(c) => Ok(Value::Int(Int::from_i64(c as i64))),
            None => Err(past_end(k)),
        },
        Value::Cons(_) | Value::Nil => {
            let mut cur = xs;
            let mut left = i;
            loop {
                match cur {
                    Value::Cons(c) => {
                        if left == 0 {
                            return Ok(c.head.clone());
                        }
                        left -= 1;
                        cur = &c.tail;
                    }
                    _ => return Err(past_end(k)),
                }
            }
        }
        other => {
            as_list(a, other, "nth")?;
            Err(past_end(k))
        }
    }
}

/// The family's work over evaluated operands.
pub fn work_fixed(a: &Arena, op: u8, args: &[Value]) -> R<Value> {
    match op {
        FIX_SIN | FIX_COS => {
            let x = as_int(a, &args[0], op_name(op))?;
            let k = mod_small(&x, 256);
            let k = if op == FIX_COS { (k + 64) % 256 } else { k };
            Ok(Value::Int(Int::from_i64(sin_k(k))))
        }
        FIX_SIN_FINE | FIX_COS_FINE => {
            let x = as_int(a, &args[0], op_name(op))?;
            let v = mod_small(&x, 4096);
            let v = if op == FIX_COS_FINE { (v + 1024) % 4096 } else { v };
            Ok(Value::Int(Int::from_i64(sin_fine_a(v))))
        }
        FIX_QUOT => {
            let x = as_int(a, &args[0], "quot")?;
            let y = as_int(a, &args[1], "quot")?;
            if y.is_zero() {
                return Err(domain(
                    "domain-error",
                    "quot: division by zero".to_string(),
                    detail(vec![("operator", J::from("quot"))]),
                    "guard the divisor with `(if d (quot a d) fallback)`",
                ));
            }
            Ok(Value::Int(quot(&x, &y)))
        }
        FIX_NTH => {
            let k = as_int(a, &args[1], "nth")?;
            nth(a, &args[0], &k)
        }
        FIX_ISQRT => {
            let x = as_int(a, &args[0], "isqrt")?;
            Ok(Value::Int(isqrt(&x)))
        }
        _ => unreachable!(),
    }
}
