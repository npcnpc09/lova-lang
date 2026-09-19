//! `core/lineage.py`: the session-wide provenance store (Axiom 5).
//!
//! Records are a side-car table keyed by uid; the uid lives on the node
//! as metadata and never enters the bytes.  The store owns the one PRNG
//! the language draws on (spec §5.5, decision D4).

use crate::int::Int;
use crate::rng::Random;
use crate::tokens::*;
use std::collections::HashMap;

pub struct Record {
    pub parent_uid: Option<u64>,
    pub generation: i64,
    pub mutation_kind: &'static str,
    pub notes: String,
}

pub struct Lineage {
    next_uid: u64,
    records: HashMap<u64, Record>,
    pub rng: Random,
}

impl Lineage {
    pub fn new() -> Lineage {
        Lineage { next_uid: 1, records: HashMap::new(), rng: Random::new(0) }
    }

    /// `register_root`: a fresh root record, the uid written on the node.
    pub fn register_root(&mut self, a: &Arena, id: u32, notes: &str) -> u64 {
        let uid = self.next_uid;
        self.next_uid += 1;
        self.records.insert(
            uid,
            Record {
                parent_uid: None,
                generation: 0,
                mutation_kind: "root",
                notes: notes.to_string(),
            },
        );
        a.get(id).uid.set(Some(uid));
        uid
    }

    fn register_child(
        &mut self,
        a: &Arena,
        id: u32,
        parent_uid: u64,
        mutation_kind: &'static str,
        notes: String,
    ) -> u64 {
        let uid = self.next_uid;
        self.next_uid += 1;
        let generation = self.records[&parent_uid].generation + 1;
        self.records.insert(
            uid,
            Record { parent_uid: Some(parent_uid), generation, mutation_kind, notes },
        );
        a.get(id).uid.set(Some(uid));
        uid
    }

    /// `ensure_registered`: the uid a program already has, or a fresh root.
    pub fn ensure_registered(&mut self, a: &Arena, id: u32) -> u64 {
        match a.get(id).uid.get() {
            Some(uid) => uid,
            None => self.register_root(a, id, "quoted"),
        }
    }

    /// `clone(parent)`: a structurally identical copy with a fresh uid.
    pub fn clone_program(&mut self, a: &mut Arena, parent: u32) -> u32 {
        let parent_uid = a.get(parent).uid.get().expect("parent must be registered");
        let child = a.deep_copy(parent);
        self.register_child(a, child, parent_uid, "clone", String::new());
        child
    }

    /// `mutate(parent, strength)`: a copy walked by `_mutate_inplace`.
    pub fn mutate_program(&mut self, a: &mut Arena, parent: u32, strength: f64) -> u32 {
        let parent_uid = a.get(parent).uid.get().expect("parent must be registered");
        let child = a.deep_copy(parent);
        let mut log: Vec<String> = Vec::new();
        mutate_inplace(a, &mut self.rng, child, strength, &mut log);
        let applied = if log.is_empty() { "no-op".to_string() } else { log.join(",") };
        let notes = format!("strength={} [{}]", py_float(strength), applied);
        self.register_child(a, child, parent_uid, "mutate", notes);
        child
    }

    pub fn record(&self, uid: u64) -> &Record {
        &self.records[&uid]
    }

    /// `ancestors(uid)`: self -> parent -> ... -> root.
    pub fn ancestors(&self, uid: u64) -> Vec<u64> {
        let mut out = Vec::new();
        let mut cur = Some(uid);
        while let Some(u) = cur {
            out.push(u);
            cur = self.records[&u].parent_uid;
        }
        out
    }

    pub fn is_ancestor_of(&self, a: u64, b: u64) -> bool {
        self.ancestors(b).contains(&a)
    }
}

/// `str(float)` as Python writes it -- the one difference from Rust's
/// shortest form is that an integral value keeps its `.0`.
pub fn py_float(v: f64) -> String {
    if v.is_finite() && v == v.trunc() && v.abs() < 1e16 {
        format!("{:.1}", v)
    } else {
        format!("{}", v)
    }
}

/// The mutation swap groups -- narrower than the repair suggestion
/// groups, and sorted, because `choice(sorted(g - {op}))` is.
fn swap_group(op: u8) -> Option<&'static [u8]> {
    const NT: [u8; 4] = [P, TAU, SIGMA, MOBIUS];
    const ADD: [u8; 2] = [MERGE, GCD];
    if NT.contains(&op) {
        return Some(&NT);
    }
    if ADD.contains(&op) {
        return Some(&ADD);
    }
    None
}

/// `_mutate_inplace`: walk the copy, perturbing with probability
/// `strength` at each node, and log what was applied.
pub fn mutate_inplace(
    a: &mut Arena,
    rng: &mut Random,
    id: u32,
    strength: f64,
    log: &mut Vec<String>,
) {
    if rng.random() < strength {
        // kind is "auto": `choice(["literal", "operator"])`.
        let literal = rng.choice_index(2) == 0;
        let op = a.op(id);
        if literal && op == LIT_INT {
            let old = a.get(id).ival.clone().unwrap();
            let mut delta = rng.randint(-5, 5);
            while delta == 0 {
                delta = rng.randint(-5, 5);
            }
            let new = old.add(&Int::from_i64(delta));
            log.push(format!("lit:{}->{}", old, new));
            a.nodes[id as usize].ival = Some(new);
        } else if !literal {
            if let Some(group) = swap_group(op) {
                let mut candidates: Vec<u8> =
                    group.iter().copied().filter(|o| *o != op).collect();
                candidates.sort_unstable();
                let pick = rng.choice_index(candidates.len());
                let new_op = candidates[pick];
                log.push(format!("op:{}->{}", op_name(op), op_name(new_op)));
                a.nodes[id as usize].op = new_op;
            }
        }
    }
    if a.op(id) != LIT_INT {
        let kids = a.kids(id).to_vec();
        for k in kids {
            mutate_inplace(a, rng, k, strength, log);
        }
    }
}
