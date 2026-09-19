//! `spec/native-runtime-protocol.md`: one JSON request per line in, one
//! JSON reply per line out.  Nothing else goes on stdout.

mod conserve;
mod evolve;
mod int;
mod lineage;
mod meta;
mod nt;
mod rng;
mod rt;
mod text;
mod tokens;
mod tokens_table;
mod trap;
mod value;

use serde_json::{json, Map as JMap, Value as J};
use std::io::{BufRead, Write};
use tokens::*;
use trap::Fault;

const VERSION: &str = "lova-rt 0.2.0";

/// D7, phase 3: everything but `read` / `explain`, which need the
/// Stage-1 surface, and the network.
const UNSUPPORTED: [u8; 4] = [READ, EXPLAIN, NET_SEND, NET_RECV];

fn unsupported(op: u8) -> bool {
    UNSUPPORTED.contains(&op)
}

fn main() {
    // A LOVA call is several Rust frames, and the depth ceiling is ten
    // thousand calls; the main thread's stack is not enough.
    let worker = std::thread::Builder::new()
        .stack_size(1 << 30)
        .spawn(serve)
        .expect("failed to start the evaluator thread");
    let code = worker.join().unwrap_or(1);
    std::process::exit(code);
}

fn serve() -> i32 {
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let reply: J = match serde_json::from_str::<J>(line) {
            Err(e) => json!({"ok": false, "error": format!("bad request: {}", e)}),
            Ok(request) => match request.get("op").and_then(|v| v.as_str()) {
                Some("ping") => json!({
                    "ok": true,
                    "version": VERSION,
                    "unsupported": UNSUPPORTED.iter().map(|o| op_name(*o))
                        .collect::<Vec<&str>>(),
                }),
                Some("run") => run(&request),
                other => json!({
                    "id": request.get("id").cloned().unwrap_or(J::Null),
                    "ok": false,
                    "error": format!("unknown op {:?}", other.unwrap_or("")),
                }),
            },
        };
        if writeln!(out, "{}", reply).is_err() {
            break;
        }
        if out.flush().is_err() {
            break;
        }
    }
    0
}

fn run(request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let hexed = request.get("bytes").and_then(|v| v.as_str()).unwrap_or("");
    let data = match hex::decode(hexed) {
        Ok(d) => d,
        Err(e) => return json!({"id": id, "ok": false, "error": format!("decode: {}", e)}),
    };
    let mut arena = Arena::new();
    let root = match decode(&mut arena, &data) {
        Ok(r) => r,
        Err(e) => {
            return json!({"id": id, "ok": false, "error": format!("decode: ValueError: {}", e)})
        }
    };
    let mut seen = [false; 0x58];
    operators_used(&arena, root, &mut seen);
    for (op, used) in seen.iter().enumerate() {
        if *used && unsupported(op as u8) {
            return json!({
                "id": id, "ok": false,
                "error": format!("unsupported: {}", op_name(op as u8)),
            });
        }
    }

    let stdin_text = request.get("stdin").and_then(|v| v.as_str()).unwrap_or("");
    let allow = request.get("allow").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
    let max_steps = request.get("max_steps").and_then(|v| v.as_u64()).unwrap_or(1_000_000);
    let max_depth = request.get("max_depth").and_then(|v| v.as_u64()).unwrap_or(10_000) as u32;

    let mut state = rt::Rt::new(max_steps, max_depth, allow, stdin_text);
    state.ordinals = std::rc::Rc::new(preorder_ordinals(&arena, root));
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        rt::eval(&mut arena, &mut state, root, false)
    }));

    let mut reply = JMap::new();
    reply.insert("id".into(), id);
    match outcome {
        Err(_) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from("panic in the evaluator"));
            reply.insert("steps".into(), J::from(state.steps));
            return J::Object(reply);
        }
        Ok(Ok(v)) => {
            reply.insert("ok".into(), J::Bool(true));
            reply.insert("value".into(), J::from(value::format_value(&arena, &v)));
        }
        Ok(Err(Fault::NotImplemented(message))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from(format!("NotImplementedError: {}", message)));
            reply.insert("steps".into(), J::from(state.steps));
            return J::Object(reply);
        }
        Ok(Err(Fault::Trap(t))) => {
            let a = &t.anomaly;
            let mut an = JMap::new();
            an.insert("kind".into(), J::from(a.kind));
            an.insert(
                "offending_op".into(),
                a.offending_op.map(J::from).unwrap_or(J::Null),
            );
            an.insert("offending_op_name".into(), J::from(a.offending_op_name.clone()));
            an.insert(
                "position_path".into(),
                J::Array(a.position_path.iter().map(|o| J::from(*o)).collect()),
            );
            an.insert(
                "position_nodes".into(),
                J::Array(
                    a.position_nodes
                        .iter()
                        .map(|n| n.map(J::from).unwrap_or(J::Null))
                        .collect(),
                ),
            );
            if let Some(b) = &a.body_offender {
                an.insert("body_offender".into(), b.clone());
            }
            an.insert("detail".into(), J::Object(a.detail.clone()));
            an.insert("repair_hint".into(), J::from(a.repair_hint.clone()));
            an.insert("message".into(), J::from(a.message.clone()));
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("anomaly".into(), J::Object(an));
        }
    }
    reply.insert("steps".into(), J::from(state.steps));
    reply.insert("stdout".into(), J::from(state.output.clone()));
    J::Object(reply)
}
