//! A small, fast, non-cryptographic hasher (Q124).
//!
//! The evaluator's hash tables are keyed by a name id, a map key or a
//! node id, never by anything an attacker chooses, and the default
//! SipHash costs more than the lookups it protects: it was a fifth of
//! the run on `war.lova`.  This is rustc's own `FxHasher`, which is a
//! rotate, an xor and a multiply per word.
//!
//! It changes no value, no step and no order: `OrderedMap` keeps
//! insertion order in a vector of its own, and `Scope` is looked up by
//! key, never iterated in hash order except through `flatten`, whose
//! callers sort or re-insert.

use std::hash::{BuildHasherDefault, Hasher};

const SEED: u64 = 0x51_7c_c1_b7_27_22_0a_95;

#[derive(Default, Clone, Copy)]
pub struct FxHasher {
    hash: u64,
}

impl FxHasher {
    #[inline]
    fn add(&mut self, word: u64) {
        self.hash = (self.hash.rotate_left(5) ^ word).wrapping_mul(SEED);
    }
}

impl Hasher for FxHasher {
    #[inline]
    fn write(&mut self, bytes: &[u8]) {
        let mut rest = bytes;
        while rest.len() >= 8 {
            let mut word = [0u8; 8];
            word.copy_from_slice(&rest[..8]);
            self.add(u64::from_ne_bytes(word));
            rest = &rest[8..];
        }
        for b in rest {
            self.add(*b as u64);
        }
    }

    #[inline]
    fn write_u8(&mut self, n: u8) {
        self.add(n as u64);
    }

    #[inline]
    fn write_u32(&mut self, n: u32) {
        self.add(n as u64);
    }

    #[inline]
    fn write_u64(&mut self, n: u64) {
        self.add(n);
    }

    #[inline]
    fn write_usize(&mut self, n: usize) {
        self.add(n as u64);
    }

    #[inline]
    fn write_i64(&mut self, n: i64) {
        self.add(n as u64);
    }

    #[inline]
    fn finish(&self) -> u64 {
        self.hash
    }
}

pub type Fx = BuildHasherDefault<FxHasher>;
pub type FxMap<K, V> = std::collections::HashMap<K, V, Fx>;
