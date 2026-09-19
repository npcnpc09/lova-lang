//! Unbounded integers with an `i64` fast path.
//!
//! Every LOVA integer is a bignum (spec 8.1).  Allocating a `BigInt`
//! for every `merge` would cost more than the interpreter, so a value
//! that fits an `i64` is one, and promotes on overflow.  The
//! normalisation rule is absolute: a `Big` never holds a value that an
//! `i64` could carry, so `==`, `Ord` and `Hash` can be derived from the
//! representation.
//!
//! Division and modulo are Python's -- floor, remainder taking the
//! divisor's sign (spec 2.5).

use num_bigint::BigInt;
use num_integer::Integer;
use num_traits::{Signed, ToPrimitive, Zero};
use std::cmp::Ordering;
use std::hash::{Hash, Hasher};
use std::rc::Rc;

#[derive(Clone, Debug)]
pub enum Int {
    S(i64),
    B(Rc<BigInt>),
}

impl Int {
    #[inline]
    pub fn zero() -> Int {
        Int::S(0)
    }

    #[inline]
    pub fn from_i64(v: i64) -> Int {
        Int::S(v)
    }

    #[inline]
    pub fn from_usize(v: usize) -> Int {
        if v <= i64::MAX as usize {
            Int::S(v as i64)
        } else {
            Int::B(Rc::new(BigInt::from(v)))
        }
    }

    pub fn from_big(b: BigInt) -> Int {
        match b.to_i64() {
            Some(v) => Int::S(v),
            None => Int::B(Rc::new(b)),
        }
    }

    /// Big-endian two's complement, as `LIT_INT` carries it.
    pub fn from_signed_bytes_be(bytes: &[u8]) -> Int {
        if bytes.is_empty() {
            return Int::S(0);
        }
        if bytes.len() <= 8 {
            let mut v: i64 = if bytes[0] & 0x80 != 0 { -1 } else { 0 };
            for b in bytes {
                v = (v << 8) | (*b as i64);
            }
            return Int::S(v);
        }
        Int::from_big(BigInt::from_signed_bytes_be(bytes))
    }

    #[inline]
    pub fn to_i64(&self) -> Option<i64> {
        match self {
            Int::S(v) => Some(*v),
            Int::B(_) => None,
        }
    }

    #[inline]
    pub fn to_usize(&self) -> Option<usize> {
        match self {
            Int::S(v) if *v >= 0 => Some(*v as usize),
            _ => None,
        }
    }

    pub fn to_big(&self) -> BigInt {
        match self {
            Int::S(v) => BigInt::from(*v),
            Int::B(b) => (**b).clone(),
        }
    }

    #[inline]
    pub fn is_zero(&self) -> bool {
        match self {
            Int::S(v) => *v == 0,
            Int::B(b) => b.is_zero(),
        }
    }

    #[inline]
    pub fn is_negative(&self) -> bool {
        match self {
            Int::S(v) => *v < 0,
            Int::B(b) => b.is_negative(),
        }
    }

    /// Python's `int.bit_length()`: the bits of the absolute value; 0 for 0.
    pub fn bit_length(&self) -> u64 {
        match self {
            Int::S(v) => {
                if *v == 0 {
                    0
                } else {
                    let m = (*v as i128).unsigned_abs();
                    (128 - m.leading_zeros()) as u64
                }
            }
            Int::B(b) => b.bits(),
        }
    }

    pub fn add(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if let Some(v) = a.checked_add(*b) {
                return Int::S(v);
            }
        }
        Int::from_big(self.to_big() + other.to_big())
    }

    pub fn sub(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if let Some(v) = a.checked_sub(*b) {
                return Int::S(v);
            }
        }
        Int::from_big(self.to_big() - other.to_big())
    }

    pub fn mul(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if let Some(v) = a.checked_mul(*b) {
                return Int::S(v);
            }
        }
        Int::from_big(self.to_big() * other.to_big())
    }

    pub fn neg(&self) -> Int {
        match self {
            Int::S(v) => match v.checked_neg() {
                Some(n) => Int::S(n),
                None => Int::from_big(-BigInt::from(*v)),
            },
            Int::B(b) => Int::from_big(-(**b).clone()),
        }
    }

    pub fn abs(&self) -> Int {
        if self.is_negative() {
            self.neg()
        } else {
            self.clone()
        }
    }

    /// Python `a // b`: floor division.  The caller has checked `b != 0`.
    pub fn div_floor(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if !(*a == i64::MIN && *b == -1) {
                let q = a / b;
                let r = a % b;
                return Int::S(if r != 0 && ((r < 0) != (*b < 0)) { q - 1 } else { q });
            }
        }
        Int::from_big(self.to_big().div_floor(&other.to_big()))
    }

    /// Python `a % b`: the remainder takes the divisor's sign.
    pub fn mod_floor(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if !(*a == i64::MIN && *b == -1) {
                let r = a % b;
                let r = if r != 0 && ((r < 0) != (*b < 0)) { r + b } else { r };
                return Int::S(r);
            }
        }
        Int::from_big(self.to_big().mod_floor(&other.to_big()))
    }

    /// `math.gcd`: never negative, `gcd(0, 0) == 0`.
    pub fn gcd(&self, other: &Int) -> Int {
        if let (Int::S(a), Int::S(b)) = (self, other) {
            if *a != i64::MIN && *b != i64::MIN {
                let (mut x, mut y) = (a.abs(), b.abs());
                while y != 0 {
                    let t = x % y;
                    x = y;
                    y = t;
                }
                return Int::S(x);
            }
        }
        Int::from_big(self.to_big().gcd(&other.to_big()))
    }

    pub fn to_json(&self) -> serde_json::Value {
        match self {
            Int::S(v) => serde_json::Value::from(*v),
            // Outside JSON's reach; a reader gets the digits.
            Int::B(b) => serde_json::Value::from(b.to_string()),
        }
    }
}

impl std::fmt::Display for Int {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Int::S(v) => write!(f, "{}", v),
            Int::B(b) => write!(f, "{}", b),
        }
    }
}

impl PartialEq for Int {
    fn eq(&self, other: &Int) -> bool {
        match (self, other) {
            (Int::S(a), Int::S(b)) => a == b,
            (Int::B(a), Int::B(b)) => a == b,
            // Normalised: a Big never equals a Small.
            _ => false,
        }
    }
}
impl Eq for Int {}

impl Ord for Int {
    fn cmp(&self, other: &Int) -> Ordering {
        match (self, other) {
            (Int::S(a), Int::S(b)) => a.cmp(b),
            (Int::B(a), Int::B(b)) => a.cmp(b),
            (Int::S(_), Int::B(b)) => {
                if b.is_negative() {
                    Ordering::Greater
                } else {
                    Ordering::Less
                }
            }
            (Int::B(a), Int::S(_)) => {
                if a.is_negative() {
                    Ordering::Less
                } else {
                    Ordering::Greater
                }
            }
        }
    }
}
impl PartialOrd for Int {
    fn partial_cmp(&self, other: &Int) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Hash for Int {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            Int::S(v) => {
                state.write_u8(0);
                state.write_i64(*v);
            }
            Int::B(b) => {
                state.write_u8(1);
                b.hash(state);
            }
        }
    }
}
