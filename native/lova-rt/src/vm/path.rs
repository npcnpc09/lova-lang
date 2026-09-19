//! `position_path`, derived (`spec/vm.md` §6).
//!
//! The tree-walker pushes a frame per node; the VM pushes none.  On a
//! trap it reconstructs the same list: within one activation the nodes
//! still being evaluated are exactly the static ancestors of the node
//! in hand, and each activation below contributes the chain of the node
//! that made the call -- an `apply`, a list walker, a delegated
//! subtree.  A tail call replaced its frame, so it contributes nothing:
//! its activation was popped before the new body ran.
//!
//! A delegated subtree is evaluated by the tree-walker, which does push
//! per node, so `rt.path` and the VM's frames interleave: every frame
//! records how long `rt.path` was when it started, and the segments
//! between those marks belong between the frames' chains.

use super::*;
use crate::rt::Rt;
use crate::tokens::{Arena, LAMBDA, LIT_INT, LIT_TEXT, QUOTE};

/// The ancestors of `node` inside this unit, outermost first.  The
/// chain is found by walking the arena from the unit's root rather than
/// from a table built at compile time: it is the trap path, which runs
/// once, and the table cost a hash insert per node of every program.
fn chain_into(a: &Arena, unit: &Unit, node: u32, inclusive: bool, out: &mut Vec<(u8, u32)>) {
    let mut chain: Vec<u32> = Vec::new();
    if !descend(a, unit.root, node, &mut chain) {
        return;
    }
    if !inclusive {
        chain.pop();
    }
    for id in chain {
        out.push((a.op(id), id));
    }
}

/// A `lambda`'s body is another unit, `quote`'s operand is not
/// evaluated, and a delegated subtree is the tree-walker's: none of
/// them holds a node of this unit.
fn descend(a: &Arena, here: u32, target: u32, chain: &mut Vec<u32>) -> bool {
    chain.push(here);
    if here == target {
        return true;
    }
    let op = a.op(here);
    if op != LAMBDA && op != QUOTE && !crate::vm::compile::delegated(op) {
        for i in 0..a.kids(here).len() {
            let kid = a.kids(here)[i];
            if descend(a, kid, target, chain) {
                return true;
            }
        }
    }
    chain.pop();
    false
}

/// The live evaluation path, outermost first.  `innermost` is the node
/// the VM trapped at; `None` means the trap came out of a delegated
/// subtree, whose own nodes are already on `rt.path`.
pub fn full(a: &Arena, rt: &Rt, innermost: Option<u32>) -> Vec<(u8, u32)> {
    if rt.vm.frames.is_empty() {
        return rt.path.clone();
    }
    let mut out: Vec<(u8, u32)> = Vec::new();
    let mut prev = 0usize;
    let n = rt.vm.frames.len();
    for (i, f) in rt.vm.frames.iter().enumerate() {
        let upto = f.path_len.min(rt.path.len());
        if upto > prev {
            out.extend_from_slice(&rt.path[prev..upto]);
            prev = upto;
        }
        let last = i + 1 == n;
        let (node, inclusive) = match (last, innermost) {
            (true, Some(nd)) => (nd, true),
            _ => (f.site, !f.site_exclusive),
        };
        if node != u32::MAX {
            // Safety: the record is alive only while its activation is,
            // and the activation holds the unit.
            let unit: &Unit = unsafe { &*f.unit };
            chain_into(a, unit, node, inclusive, &mut out);
        }
    }
    if rt.path.len() > prev {
        out.extend_from_slice(&rt.path[prev..]);
    }
    // A literal takes no entry: the reference's `_node_path` only sees
    // frames with a `node` local, and a literal's closure has none
    // (quirk 15).  Only the innermost entry can be one.
    if let Some((op, _)) = out.last() {
        if *op == LIT_INT || *op == LIT_TEXT {
            out.pop();
        }
    }
    out
}
