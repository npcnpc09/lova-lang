//! Anomalies and the trap classes (spec §6).

use crate::int::Int;
use crate::tokens::*;
use serde_json::{json, Map as JMap, Value as J};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Class {
    Budget,
    Depth,
    Step,
    Delta,
    Domain,
}

pub struct Anomaly {
    pub kind: &'static str,
    pub message: String,
    pub detail: JMap<String, J>,
    pub repair_hint: String,
    pub position_path: Vec<u8>,
    /// Parallel to `position_path`: each frame's node as its 0-based
    /// ordinal in the decoded program, byte-stream (preorder) order,
    /// literals counted.  `None` for a node that is not from the
    /// program's own bytes -- one `quote` / `clone` / `mutate` made.
    pub position_nodes: Vec<Option<u32>>,
    pub offending_op: Option<u8>,
    pub offending_op_name: String,
    pub valid_alternatives: Vec<u8>,
    pub body_offender: Option<J>,
    pub enriched: bool,
}

impl Anomaly {
    pub fn new(kind: &'static str, message: String, detail: JMap<String, J>, hint: &str) -> Anomaly {
        Anomaly {
            kind,
            message,
            detail,
            repair_hint: hint.to_string(),
            position_path: Vec::new(),
            position_nodes: Vec::new(),
            offending_op: None,
            offending_op_name: String::new(),
            valid_alternatives: Vec::new(),
            body_offender: None,
            enriched: false,
        }
    }
}

pub struct Trap {
    pub class: Class,
    pub anomaly: Anomaly,
}

pub enum Fault {
    Trap(Box<Trap>),
    /// `END` has no handler: a plain `NotImplementedError`, which is
    /// not a LOVA anomaly and `when-anomaly` does not catch (quirk 31).
    NotImplemented(String),
}

pub type R<T> = Result<T, Fault>;

pub fn detail(pairs: Vec<(&str, J)>) -> JMap<String, J> {
    let mut m = JMap::new();
    for (k, v) in pairs {
        m.insert(k.to_string(), v);
    }
    m
}

pub fn domain(kind: &'static str, message: String, d: JMap<String, J>, hint: &str) -> Fault {
    Fault::Trap(Box::new(Trap {
        class: Class::Domain,
        anomaly: Anomaly::new(kind, message, d, hint),
    }))
}

pub fn budget_trap(limit: &Int, spent: i64) -> Fault {
    let overrun = Int::from_i64(spent).sub(limit);
    let d = detail(vec![
        ("limit", limit.to_json()),
        ("spent", J::from(spent)),
        ("overrun", overrun.to_json()),
    ]);
    Fault::Trap(Box::new(Trap {
        class: Class::Budget,
        anomaly: Anomaly::new(
            "budget-exceeded",
            format!("BUDGET trap: spent {} > limit {} (overrun {})", spent, limit, overrun),
            d,
            &format!("reduce body size (fewer operators) or raise budget to >= {}", spent),
        ),
    }))
}

pub fn step_trap(steps: u64, limit: u64) -> Fault {
    let d = detail(vec![
        ("limit", J::from(limit)),
        ("spent", J::from(steps)),
        ("overrun", J::from(steps - limit)),
    ]);
    Fault::Trap(Box::new(Trap {
        class: Class::Step,
        anomaly: Anomaly::new(
            "step-limit-exceeded",
            format!("Step trap: {} evaluation steps > limit {}", steps, limit),
            d,
            &format!(
                "the budget of {limit} steps ran out.  The span is where the \
counter expired, not where the cost is; `hot` in the detail is: the steps each \
function spent in its own body, costliest first.  If a library walker leads \
(`map`, `filter`, `fold`, `reverse`, `range`, `sum`, `any`, `contains` cost \
20-40 steps per element, `sort` ~200; `nth`, `take`, `drop`, `append`, `len`, \
`map-get`, `get` a few steps), change the representation -- a map keyed by \
index, a text, a packed integer -- before the algorithm; if a function of yours \
leads, cut work there; if the program cannot reach its base case, fix that; if \
the work is genuinely this large, the budget is the host's setting \
(`--max-steps`, `max_steps`), not a fault in the program",
                limit = limit
            ),
        ),
    }))
}

pub fn depth_trap(depth: u32, limit: u32) -> Fault {
    let d = detail(vec![
        ("limit", J::from(limit)),
        ("spent", J::from(depth)),
        ("overrun", J::from(depth - limit)),
        ("call_chain", json!([])),
    ]);
    Fault::Trap(Box::new(Trap {
        class: Class::Depth,
        anomaly: Anomaly::new(
            "recursion-depth-exceeded",
            format!("Depth trap: call depth {} > limit {}", depth, limit),
            d,
            &format!(
                "the recursion has no reachable base case, or keeps more than \
{limit} frames; add or fix the `if` that terminates it.  A call in tail \
position costs no frame (M32), so a recursion whose last act is the call runs \
in constant depth; this one does something with the result after the call \
returns, so every level keeps a frame -- carry the result in an accumulator \
argument, or use `fold` / `map` / `range` or `loop-until`",
                limit = limit
            ),
        ),
    }))
}

// --- codes (spec §6.1) ------------------------------------------------------

pub const FIRST_PROGRAM_SIGNAL: i64 = 16;

pub fn anomaly_code(a: &Anomaly) -> i64 {
    if a.kind == "signalled" {
        if let Some(J::Number(n)) = a.detail.get("code") {
            if let Some(v) = n.as_i64() {
                return v;
            }
        }
        return 10;
    }
    match a.kind {
        "budget-exceeded" => 1,
        "recursion-depth-exceeded" => 2,
        "conservation-violated" => 3,
        "domain-error" => 4,
        "type-violation" => 5,
        "unbound-ref" => 6,
        "malformed" => 7,
        "step-limit-exceeded" => 8,
        "capability-denied" => 9,
        "signalled" => 10,
        _ => 0,
    }
}

// --- repair suggestions (core/observability.py) -----------------------------

pub fn suggest_alternatives(op: u8) -> Vec<u8> {
    if op == VIOLATE {
        return vec![IDENTITY];
    }
    const GROUPS: [&[u8]; 6] = [
        &[P, TAU, SIGMA, MOBIUS],
        &[MERGE, GCD],
        &[IDENTITY, PARTITION],
        &[MUL, MOD, DIV],
        &[HEAD, TAIL],
        &[DEVIATION, THRESHOLD],
    ];
    for group in GROUPS.iter() {
        if group.contains(&op) {
            let mut out: Vec<u8> = group.iter().copied().filter(|o| *o != op).collect();
            out.sort_unstable();
            return out;
        }
    }
    Vec::new()
}
