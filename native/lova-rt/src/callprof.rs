//! The step profiler: every step a call spends, put down to the closure
//! whose body was running and to the chain of calls that led there.
//!
//! Off unless a request asks for it (`"profile": true` on a session
//! `call`): `Rt::prof` is `None` and `rt::call` pays one test of it on
//! the way in and one on the way out, nothing per step.  On, each
//! application of a closure opens a node of a calling-context tree --
//! keyed by its parent node and the closure's body -- and charges it the
//! steps `rt.steps` moved while it was open.  Steps are never counted
//! here, only read: whatever charges them (a VM run, a walker, a
//! delegated subtree, the tree-walker) is attributed to the closure in
//! whose body it happened, so the profile adds up to the call's `steps`
//! exactly and both evaluators give the same one.
//!
//! What comes out is the tree, flat: one row per node,
//! `[parent, body ordinal, name id, owner name id, calls, inclusive]`;
//! self steps are a node's inclusive less its children's.  Names and
//! spans are the driver's to recover (`core/profile.py`): the ordinal is
//! the body's place in the decoded program, preorder, as an anomaly's
//! `position_nodes` are.

use crate::fx::FxMap;
use crate::value::ClosureData;
use serde_json::{json, Value as J};

/// No name: an anonymous lambda, or one with no owner.
pub const NO_NAME: i64 = i64::MIN;

struct Node {
    parent: u32,
    body: u32,
    name: i64,
    owner: i64,
    calls: u64,
    incl: u64,
}

pub struct StepProf {
    nodes: Vec<Node>,
    index: FxMap<(u32, u32), u32>,
    /// Open nodes, innermost last, with `rt.steps` when each opened.
    stack: Vec<(u32, u64)>,
}

impl StepProf {
    /// A profile whose root node stands for the call itself: the steps
    /// spent outside every closure are its own.
    pub fn new() -> StepProf {
        StepProf {
            nodes: vec![Node { parent: u32::MAX, body: u32::MAX, name: NO_NAME, owner: NO_NAME, calls: 1, incl: 0 }],
            index: FxMap::default(),
            stack: Vec::new(),
        }
    }

    /// A closure is applied, `steps` into the call.
    pub fn enter(&mut self, cl: &ClosureData, steps: u64) {
        let parent = self.stack.last().map(|e| e.0).unwrap_or(0);
        let key = (parent, cl.body);
        let at = match self.index.get(&key) {
            Some(i) => *i,
            None => {
                let owner = cl.owner.get();
                let owner_name = if owner.is_null() {
                    NO_NAME
                } else {
                    // Safety: an owner is a named closure, which
                    // `Rt::named` holds for the runtime's life.
                    unsafe { &*owner }.name.get().unwrap_or(NO_NAME)
                };
                let i = self.nodes.len() as u32;
                self.nodes.push(Node {
                    parent,
                    body: cl.body,
                    name: cl.name.get().unwrap_or(NO_NAME),
                    owner: owner_name,
                    calls: 0,
                    incl: 0,
                });
                self.index.insert(key, i);
                i
            }
        };
        self.nodes[at as usize].calls += 1;
        self.stack.push((at, steps));
    }

    /// The closure entered last has returned (or failed), `steps` into
    /// the call.
    pub fn exit(&mut self, steps: u64) {
        if let Some((at, start)) = self.stack.pop() {
            self.nodes[at as usize].incl += steps.saturating_sub(start);
        }
    }

    /// The rows, with the root's inclusive set to the call's `steps`.
    /// Nodes still open (a trap unwound past them) are closed at `steps`.
    pub fn finish(mut self, steps: u64, ordinal: impl Fn(u32) -> Option<u32>) -> J {
        while !self.stack.is_empty() {
            self.exit(steps);
        }
        self.nodes[0].incl = steps;
        let name = |n: i64| if n == NO_NAME { J::Null } else { J::from(n) };
        J::Array(
            self.nodes
                .iter()
                .map(|n| {
                    json!([
                        if n.parent == u32::MAX { J::Null } else { J::from(n.parent) },
                        if n.body == u32::MAX { J::Null } else { json!(ordinal(n.body)) },
                        name(n.name),
                        name(n.owner),
                        n.calls,
                        n.incl,
                    ])
                })
                .collect(),
        )
    }
}

impl Default for StepProf {
    fn default() -> Self {
        StepProf::new()
    }
}
