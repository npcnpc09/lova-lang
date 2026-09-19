//! `conserve` and the Δ-trap body scanner (spec §5.3).
//!
//! The scanner runs only on a violation, and only in probe runtimes of
//! its own, so no step, budget or output of a probe reaches the run.

use crate::int::Int;
use crate::rt::{as_int, eval, Rt};
use crate::tokens::*;
use crate::trap::*;
use crate::value::Value;
use serde_json::{Map as JMap, Value as J};
use std::collections::HashMap;

pub fn op_conserve(a: &mut Arena, rt: &mut Rt, id: u32) -> R<Value> {
    let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
    let expected = eval(a, rt, k0, false)?;
    let expected = as_int(a, &expected, "conserve")?;
    let actual = eval(a, rt, k1, false)?;
    let actual = as_int(a, &actual, "conserve")?;
    if expected == actual {
        return Ok(Value::Int(actual));
    }
    let env = rt.env.flatten();
    let offender = scan_body_offender(a, k1, &expected, &actual, &env);
    let hint = match &offender {
        None => "body produced a value different from the expected conserve target; \
replace the divergent op with one that preserves the value"
            .to_string(),
        Some(o) => {
            let correction = o.get("correction").and_then(|c| c.as_i64()).unwrap_or(0);
            format!(
                "body-offender `{}` at path {} returns {}; needs {} (correction {:+}) to \
restore the conserve invariant",
                o.get("op_name").and_then(|v| v.as_str()).unwrap_or("?"),
                py_tuple(o.get("path")),
                json_str(o.get("observed")),
                json_str(o.get("needed")),
                correction
            )
        }
    };
    let deviation = actual.sub(&expected);
    let d = detail(vec![
        ("invariant", J::from("conserve/equality")),
        ("entry", expected.to_json()),
        ("exit", actual.to_json()),
        ("deviation", deviation.to_json()),
    ]);
    let mut anomaly = Anomaly::new(
        "conservation-violated",
        format!(
            "Delta trap: conserve/equality violated -- entry {} vs exit {}",
            expected, actual
        ),
        d,
        &hint,
    );
    anomaly.body_offender = offender;
    Err(Fault::Trap(Box::new(Trap { class: Class::Delta, anomaly })))
}

fn json_str(v: Option<&J>) -> String {
    match v {
        Some(J::Null) | None => "None".to_string(),
        Some(other) => other.to_string(),
    }
}

/// A Python tuple, as the repair hint prints it.
fn py_tuple(v: Option<&J>) -> String {
    let items = match v.and_then(|x| x.as_array()) {
        Some(a) => a,
        None => return "()".to_string(),
    };
    if items.len() == 1 {
        return format!("({},)", items[0]);
    }
    let parts: Vec<String> = items.iter().map(|i| i.to_string()).collect();
    format!("({})", parts.join(", "))
}

struct Candidate {
    path: Vec<usize>,
    node: u32,
    depth: usize,
}

fn walk(a: &Arena, node: u32, path: Vec<usize>, depth: usize, out: &mut Vec<Candidate>) {
    out.push(Candidate { path: path.clone(), node, depth });
    let kids = a.kids(node).to_vec();
    for (i, k) in kids.iter().enumerate() {
        let mut p = path.clone();
        p.push(i);
        walk(a, *k, p, depth + 1, out);
    }
}

fn probe(a: &mut Arena, env: &HashMap<i64, Value>, tree: u32) -> Option<Int> {
    let mut prt = Rt::new(1_000_000, 10_000, 0, "");
    for (k, v) in env {
        prt.env.set(*k, v.clone());
    }
    match eval(a, &mut prt, tree, false) {
        Ok(Value::Int(i)) => Some(i),
        _ => None,
    }
}

fn clone_with_replacement(a: &mut Arena, target: u32, path: &[usize], new_node: u32) -> u32 {
    if path.is_empty() {
        return new_node;
    }
    let mut kids = a.kids(target).to_vec();
    let cur = kids[path[0]];
    kids[path[0]] = clone_with_replacement(a, cur, &path[1..], new_node);
    let (op, ival, sval) = {
        let n = a.get(target);
        (n.op, n.ival.clone(), n.sval.clone())
    };
    a.push(crate::tokens::node(op, kids, ival, sval))
}

fn lit(a: &mut Arena, v: Int) -> u32 {
    a.push(node(LIT_INT, Vec::new(), Some(v), None))
}

fn record(
    a: &Arena,
    c: &Candidate,
    observed: Option<&Int>,
    needed: Option<&Int>,
    correction: &Int,
    fix: &str,
    alt: Option<u8>,
) -> J {
    let mut m = JMap::new();
    let op = a.op(c.node);
    m.insert("op".into(), J::from(op));
    m.insert("op_name".into(), J::from(op_name(op)));
    m.insert(
        "path".into(),
        J::Array(c.path.iter().map(|i| J::from(*i)).collect()),
    );
    m.insert("depth".into(), J::from(c.depth));
    m.insert("observed".into(), observed.map(|v| v.to_json()).unwrap_or(J::Null));
    m.insert("needed".into(), needed.map(|v| v.to_json()).unwrap_or(J::Null));
    m.insert("correction".into(), correction.to_json());
    m.insert("fix".into(), J::from(fix));
    if let Some(alt) = alt {
        m.insert("alternative_op".into(), J::from(alt));
        m.insert("alternative_op_name".into(), J::from(op_name(alt)));
    }
    J::Object(m)
}

fn scan_body_offender(
    a: &mut Arena,
    body: u32,
    expected: &Int,
    actual: &Int,
    env: &HashMap<i64, Value>,
) -> Option<J> {
    let deviation = actual.sub(expected);
    if deviation.is_zero() {
        return None;
    }
    let mut candidates: Vec<Candidate> = Vec::new();
    walk(a, body, Vec::new(), 0, &mut candidates);

    let mut values: HashMap<Vec<usize>, Int> = HashMap::new();
    for c in &candidates {
        if let Some(v) = probe(a, env, c.node) {
            values.insert(c.path.clone(), v);
        }
    }

    // Deepest first; ties by path, lexicographically.
    let mut ordered: Vec<usize> = (0..candidates.len()).collect();
    ordered.sort_by(|x, y| {
        let (p, q) = (&candidates[*x], &candidates[*y]);
        q.depth.cmp(&p.depth).then_with(|| p.path.cmp(&q.path))
    });

    // Pass A -- operator swap.
    for i in &ordered {
        let c = &candidates[*i];
        let op = a.op(c.node);
        if op == LIT_INT {
            continue;
        }
        let alts = suggest_alternatives(op);
        if alts.is_empty() {
            continue;
        }
        let observed = values.get(&c.path).cloned();
        for alt in alts {
            let kids = a.kids(c.node).to_vec();
            // A swap that changes the arity (`threshold` for
            // `deviation`) builds a node no handler can read.  The
            // reference probes it anyway and records the exception as
            // "unknown"; a port with indexed children would fault, so
            // the candidate is skipped -- which is the same outcome,
            // since such a probe never returns the expected value.
            if !matches!(sig(alt).map(|s| &s.arity), Some(Arity::N(n)) if *n as usize == kids.len())
            {
                continue;
            }
            let (ival, sval) = {
                let n = a.get(c.node);
                (n.ival.clone(), n.sval.clone())
            };
            let swapped = a.push(node(alt, kids, ival, sval));
            let path = candidates[*i].path.clone();
            let modified = clone_with_replacement(a, body, &path, swapped);
            if probe(a, env, modified).as_ref() != Some(expected) {
                continue;
            }
            let swapped_val = probe(a, env, swapped);
            let correction = match (&swapped_val, &observed) {
                (Some(s), Some(o)) => s.sub(o),
                _ => Int::zero(),
            };
            let c = &candidates[*i];
            return Some(record(
                a,
                c,
                observed.as_ref(),
                swapped_val.as_ref(),
                &correction,
                "operator-swap",
                Some(alt),
            ));
        }
    }

    // Pass B -- literal replacement.
    for i in &ordered {
        let path = candidates[*i].path.clone();
        let observed = match values.get(&path) {
            Some(v) => v.clone(),
            None => continue,
        };
        let op = a.op(candidates[*i].node);
        if op == LIT_INT && !path.is_empty() {
            continue;
        }
        let needed = observed.sub(&deviation);
        let replacement = lit(a, needed.clone());
        let modified = clone_with_replacement(a, body, &path, replacement);
        if probe(a, env, modified).as_ref() == Some(expected) {
            let correction = needed.sub(&observed);
            let c = &candidates[*i];
            return Some(record(
                a,
                c,
                Some(&observed),
                Some(&needed),
                &correction,
                "literal-replacement",
                None,
            ));
        }
    }

    // Fallback: the deepest non-root subtree whose own value is the deviation.
    for i in &ordered {
        let c = &candidates[*i];
        if c.path.is_empty() {
            continue;
        }
        if values.get(&c.path) == Some(&deviation) {
            return Some(record(
                a,
                c,
                Some(&deviation),
                Some(&Int::zero()),
                &deviation.neg(),
                "heuristic-value-equals-deviation",
                None,
            ));
        }
    }
    None
}
