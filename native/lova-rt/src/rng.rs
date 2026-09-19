//! CPython's `random.Random`, bit for bit (decision D4, spec §5.5).
//!
//! `LineageStore` holds one `random.Random(0)` and every evolution draw
//! comes out of it, so a recorded run only stays reproducible if a port
//! reproduces the stream.  This is MT19937 as CPython seeds it
//! (`random_seed` splits the integer into 32-bit words -- for 0 that is
//! the one word `[0]` -- and hands them to `init_by_array`), plus the
//! four draws `core/lineage.py` and `_op_EVOLVE` make: `random()`,
//! `getrandbits`, `_randbelow`, `randint` and `choice`.

const N: usize = 624;
const M: usize = 397;
const MATRIX_A: u32 = 0x9908_b0df;
const UPPER_MASK: u32 = 0x8000_0000;
const LOWER_MASK: u32 = 0x7fff_ffff;

pub struct Random {
    mt: [u32; N],
    mti: usize,
}

impl Random {
    /// `random.Random(seed)` for a non-negative integer seed.
    pub fn new(seed: u64) -> Random {
        let mut r = Random { mt: [0; N], mti: N + 1 };
        // `random_seed`: the absolute value, split into 32-bit chunks
        // from the right; a zero seed still carries one word.
        let mut key: Vec<u32> = Vec::new();
        let mut rest = seed;
        while rest != 0 {
            key.push((rest & 0xffff_ffff) as u32);
            rest >>= 32;
        }
        if key.is_empty() {
            key.push(0);
        }
        r.init_by_array(&key);
        r
    }

    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            let previous = self.mt[i - 1];
            self.mt[i] = 1812433253u32
                .wrapping_mul(previous ^ (previous >> 30))
                .wrapping_add(i as u32);
        }
        self.mti = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19650218);
        let mut i = 1usize;
        let mut j = 0usize;
        let mut k = if N > key.len() { N } else { key.len() };
        while k > 0 {
            let previous = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (previous ^ (previous >> 30)).wrapping_mul(1664525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
            k -= 1;
        }
        k = N - 1;
        while k > 0 {
            let previous = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (previous ^ (previous >> 30)).wrapping_mul(1566083941))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            k -= 1;
        }
        self.mt[0] = UPPER_MASK;
    }

    pub fn genrand_u32(&mut self) -> u32 {
        if self.mti >= N {
            for kk in 0..N - M {
                let y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk + 1] & LOWER_MASK);
                self.mt[kk] =
                    self.mt[kk + M] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
            }
            for kk in N - M..N - 1 {
                let y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk + 1] & LOWER_MASK);
                self.mt[kk] =
                    self.mt[kk + M - N] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
            }
            let y = (self.mt[N - 1] & UPPER_MASK) | (self.mt[0] & LOWER_MASK);
            self.mt[N - 1] = self.mt[M - 1] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
            self.mti = 0;
        }
        let mut y = self.mt[self.mti];
        self.mti += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    /// `random()`: 53 bits from two draws, the high word first.
    pub fn random(&mut self) -> f64 {
        let a = self.genrand_u32() >> 5;
        let b = self.genrand_u32() >> 6;
        (a as f64 * 67108864.0 + b as f64) * (1.0 / 9007199254740992.0)
    }

    /// `getrandbits(k)` for `k <= 32`, which is all the store asks for.
    pub fn getrandbits(&mut self, k: u32) -> u32 {
        if k == 0 {
            return 0;
        }
        self.genrand_u32() >> (32 - k)
    }

    /// `_randbelow_with_getrandbits`: rejection sampling on the bit length.
    pub fn randbelow(&mut self, n: u64) -> u64 {
        if n == 0 {
            return 0;
        }
        let k = 64 - n.leading_zeros();
        loop {
            let r = self.getrandbits(k) as u64;
            if r < n {
                return r;
            }
        }
    }

    /// `randint(a, b)`: `a + _randbelow(b - a + 1)`.
    pub fn randint(&mut self, a: i64, b: i64) -> i64 {
        a + self.randbelow((b - a + 1) as u64) as i64
    }

    /// `choice(seq)`: `seq[_randbelow(len(seq))]`.
    pub fn choice_index(&mut self, len: usize) -> usize {
        self.randbelow(len as u64) as usize
    }
}

#[cfg(test)]
mod tests {
    use super::Random;

    // Recorded from CPython 3.11:
    //   r = random.Random(0)
    #[test]
    fn matches_cpython() {
        let mut r = Random::new(0);
        assert_eq!(r.random(), 0.8444218515250481);
        assert_eq!(r.random(), 0.7579544029403025);
        assert_eq!(r.random(), 0.420571580830845);
        assert_eq!(r.getrandbits(4), 4);
        assert_eq!(r.randint(-5, 5), 3);

        let mut r = Random::new(0);
        let words: Vec<u32> = (0..6).map(|_| r.genrand_u32()).collect();
        assert_eq!(
            words,
            vec![3626764237, 1654615998, 3255389356, 3823568514, 1806341205, 173879092]
        );

        let mut r = Random::new(0);
        let picks: Vec<usize> = (0..8).map(|_| r.choice_index(2)).collect();
        assert_eq!(picks, vec![1, 1, 0, 1, 1, 1, 1, 1]);
    }
}
