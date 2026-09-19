//! The number-theory family (spec §5.2).  One step each, whatever the
//! input; the cost is bounded by `MAX_NT_INPUT` instead.

use crate::int::Int;
use crate::rt::MAX_NT_INPUT;
use crate::tokens::*;
use crate::trap::*;
use crate::value::Value;
use num_bigint::BigInt;
use serde_json::Value as J;

fn too_big(name: &str, n: &Int) -> Fault {
    domain(
        "domain-error",
        format!("{} input {} exceeds MAX_NT_INPUT={}", name, n, MAX_NT_INPUT),
        detail(vec![
            ("operator", J::from(name)),
            ("input", n.to_json()),
            ("limit", J::from(MAX_NT_INPUT)),
        ]),
        &format!("reduce the argument below {}", MAX_NT_INPUT),
    )
}

pub fn number_theory(op: u8, n: &Int) -> R<Value> {
    let limit = Int::from_i64(MAX_NT_INPUT);
    match op {
        P => {
            if n.is_negative() {
                return Ok(Value::Int(Int::zero()));
            }
            if *n > limit {
                return Err(too_big("partition_number", n));
            }
            let k = n.to_i64().unwrap() as usize;
            Ok(Value::Int(partition_number(k)))
        }
        TAU | SIGMA | MOBIUS => {
            let name = op_name(op);
            if n.is_negative() || n.is_zero() {
                return Ok(Value::Int(Int::zero()));
            }
            if *n > limit {
                return Err(too_big(name, n));
            }
            let k = n.to_i64().unwrap();
            Ok(Value::Int(Int::from_i64(match op {
                TAU => tau(k),
                SIGMA => sigma(k),
                _ => mobius(k),
            })))
        }
        _ => unreachable!(),
    }
}

/// Euler's pentagonal recurrence, as `core.runtime.partition_number`.
fn partition_number(n: usize) -> Int {
    if n == 0 {
        return Int::from_i64(1);
    }
    let mut table: Vec<BigInt> = vec![BigInt::from(0); n + 1];
    table[0] = BigInt::from(1);
    for m in 1..=n {
        let mut acc = BigInt::from(0);
        let mut k: i64 = 1;
        loop {
            let g1 = (k * (3 * k - 1) / 2) as usize;
            let g2 = (k * (3 * k + 1) / 2) as usize;
            if g1 > m {
                break;
            }
            let sign = if k % 2 == 0 { -1 } else { 1 };
            acc += sign * &table[m - g1];
            if g2 <= m {
                acc += sign * &table[m - g2];
            }
            k += 1;
        }
        table[m] = acc;
    }
    Int::from_big(table[n].clone())
}

fn tau(n: i64) -> i64 {
    let mut count = 0;
    let mut d = 1i64;
    while d * d <= n {
        if n % d == 0 {
            count += if d * d != n { 2 } else { 1 };
        }
        d += 1;
    }
    count
}

fn sigma(n: i64) -> i64 {
    let mut total = 0;
    let mut d = 1i64;
    while d * d <= n {
        if n % d == 0 {
            total += d;
            let other = n / d;
            if other != d {
                total += other;
            }
        }
        d += 1;
    }
    total
}

fn mobius(n: i64) -> i64 {
    if n == 1 {
        return 1;
    }
    let mut m = n;
    let mut primes = 0;
    let mut d = 2i64;
    while d * d <= m {
        if m % d == 0 {
            m /= d;
            if m % d == 0 {
                return 0;
            }
            primes += 1;
        } else {
            d += 1;
        }
    }
    if m > 1 {
        primes += 1;
    }
    if primes % 2 == 0 {
        1
    } else {
        -1
    }
}
