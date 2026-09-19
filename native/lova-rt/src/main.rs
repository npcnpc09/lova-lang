//! `spec/native-runtime-protocol.md`: one JSON request per line in, one
//! JSON reply per line out.  Nothing else goes on stdout.

mod conserve;
mod evolve;
mod fx;
mod int;
mod lineage;
mod meta;
mod nt;
#[cfg(feature = "prof")]
mod prof;
mod rng;
mod rt;
mod session;
mod text;
mod tokens;
mod tokens_table;
mod trap;
mod value;

use serde_json::{json, Map as JMap, Value as J};
use session::Session;
use std::collections::HashMap;
use std::io::{BufRead, Write};
use tokens::*;
use trap::Fault;

const VERSION: &str = "lova-rt 0.3.0";

/// D7, phase 3: everything but `read` / `explain`, which need the
/// Stage-1 surface, and the network.
const UNSUPPORTED: [u8; 4] = [READ, EXPLAIN, NET_SEND, NET_RECV];

fn unsupported(op: u8) -> bool {
    UNSUPPORTED.contains(&op)
}

fn main() {
    // A LOVA call is several Rust frames, and the depth ceiling is ten
    // thousand calls; the main thread's stack is not enough.
    #[cfg(feature = "prof")]
    prof::start();
    let worker = std::thread::Builder::new()
        .stack_size(1 << 30)
        .spawn(serve)
        .expect("failed to start the evaluator thread");
    let code = worker.join().unwrap_or(1);
    #[cfg(feature = "prof")]
    prof::stop();
    std::process::exit(code);
}

fn serve() -> i32 {
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    let mut sessions: HashMap<u64, Session> = HashMap::new();
    let mut next_session: u64 = 0;
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
                Some("session") => open(&request, &mut sessions, &mut next_session),
                Some("get") => session::get(&mut sessions, &request),
                Some("call") => session::call(&mut sessions, &request),
                Some("release") => session::release(&mut sessions, &request),
                Some("close") => session::close(&mut sessions, &request),
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

/// What `run` and `session` share: the bytes decoded, the program
/// screened against `UNSUPPORTED`, and a runtime on this request's
/// ceilings with the preorder table the anomaly's `position_nodes`
/// reads.
struct Ready {
    arena: Arena,
    root: u32,
    state: rt::Rt,
    max_steps: u64,
}

fn prepare(request: &J, id: &J) -> Result<Ready, J> {
    let hexed = request.get("bytes").and_then(|v| v.as_str()).unwrap_or("");
    let data = match hex::decode(hexed) {
        Ok(d) => d,
        Err(e) => return Err(json!({"id": id, "ok": false, "error": format!("decode: {}", e)})),
    };
    let mut arena = Arena::new();
    let root = match decode(&mut arena, &data) {
        Ok(r) => r,
        Err(e) => {
            return Err(
                json!({"id": id, "ok": false, "error": format!("decode: ValueError: {}", e)}),
            )
        }
    };
    let mut seen = [false; 0x58];
    operators_used(&arena, root, &mut seen);
    for (op, used) in seen.iter().enumerate() {
        if *used && unsupported(op as u8) {
            return Err(json!({
                "id": id, "ok": false,
                "error": format!("unsupported: {}", op_name(op as u8)),
            }));
        }
    }

    let stdin_text = request.get("stdin").and_then(|v| v.as_str()).unwrap_or("");
    let allow = request.get("allow").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
    let max_steps = request.get("max_steps").and_then(|v| v.as_u64()).unwrap_or(1_000_000);
    let max_depth = request.get("max_depth").and_then(|v| v.as_u64()).unwrap_or(10_000) as u32;

    let mut state = rt::Rt::new(max_steps, max_depth, allow, stdin_text);
    state.ordinals = std::rc::Rc::new(preorder_ordinals(&arena, root));
    Ok(Ready { arena, root, state, max_steps })
}

fn run(request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let mut ready = match prepare(request, &id) {
        Ok(r) => r,
        Err(reply) => return reply,
    };
    let (arena, state) = (&mut ready.arena, &mut ready.state);
    let root = ready.root;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        rt::eval(arena, state, root, false)
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
            reply.insert("value".into(), J::from(value::format_value(arena, &v)));
        }
        Ok(Err(Fault::NotImplemented(message))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from(format!("NotImplementedError: {}", message)));
            reply.insert("steps".into(), J::from(state.steps));
            return J::Object(reply);
        }
        Ok(Err(Fault::Trap(t))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("anomaly".into(), session::anomaly_json(&t.anomaly));
        }
    }
    reply.insert("steps".into(), J::from(state.steps));
    reply.insert("stdout".into(), J::from(state.output.clone()));
    J::Object(reply)
}

/// `session`: a `run` that keeps what it made.
fn open(request: &J, sessions: &mut HashMap<u64, Session>, next: &mut u64) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let mut ready = match prepare(request, &id) {
        Ok(r) => r,
        Err(reply) => return reply,
    };
    let root = ready.root;
    let outcome = {
        let (arena, state) = (&mut ready.arena, &mut ready.state);
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            rt::eval(arena, state, root, false)
        }))
    };

    let mut reply = JMap::new();
    reply.insert("id".into(), id);
    let value = match outcome {
        Err(_) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from("panic in the evaluator"));
            reply.insert("steps".into(), J::from(ready.state.steps));
            return J::Object(reply);
        }
        Ok(Err(Fault::NotImplemented(message))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from(format!("NotImplementedError: {}", message)));
            reply.insert("steps".into(), J::from(ready.state.steps));
            return J::Object(reply);
        }
        // A trap during evaluation is a `run` failure, and no session
        // is opened.
        Ok(Err(Fault::Trap(t))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("anomaly".into(), session::anomaly_json(&t.anomaly));
            reply.insert("steps".into(), J::from(ready.state.steps));
            reply.insert("stdout".into(), J::from(ready.state.output.clone()));
            return J::Object(reply);
        }
        Ok(Ok(v)) => v,
    };

    *next += 1;
    let sid = *next;
    let steps = ready.state.steps;
    let output = ready.state.output.clone();
    let mut kept = Session::new(ready.arena, ready.state, value.clone(), ready.max_steps);
    let encoded = kept.encode(&value);
    sessions.insert(sid, kept);

    reply.insert("ok".into(), J::Bool(true));
    reply.insert("session".into(), J::from(sid));
    reply.insert("value".into(), encoded);
    reply.insert("steps".into(), J::from(steps));
    reply.insert("stdout".into(), J::from(output));
    J::Object(reply)
}
