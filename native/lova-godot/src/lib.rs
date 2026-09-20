//! LOVA inside Godot.
//!
//! One class, `LovaRuntime`, that a GDScript makes with `LovaRuntime.new()`
//! and speaks to as the native-runtime protocol
//! (`spec/native-runtime-protocol.md`) is spoken over stdio -- except
//! that nothing crosses a process boundary: the runtime is `lova_rt`
//! linked into this library, and a call is a function call.  The
//! protocol is kept as the contract on purpose: what a session, a
//! handle, a call and an anomaly are is decided once, in the spec, and
//! this file only carries them as Godot values.
//!
//! The evaluator runs on its own thread with a large stack, as the
//! stdio binary does: a LOVA call is several Rust frames and the depth
//! ceiling is ten thousand calls, which Godot's main thread cannot
//! hold.  A request is sent to that thread and its reply waited for,
//! so a call is still synchronous to the script that made it.
//!
//! Values cross as the protocol encodes them: an integer is an `int`
//! (or, beyond 2^53, a Dictionary `{"int": "..."}`), a text a String,
//! a list an Array, `nil` null, and anything else -- a map, a closure,
//! a program -- a Dictionary `{"ref": id}` that names a value the
//! session holds.  A float is refused: LOVA has no floats, and a
//! Vector3 that leaks in unconverted is a mistake worth a message.

use godot::prelude::*;
use lova_rt::server::{choose_evaluator, handle, Sessions};
use serde_json::{json, Value as J};
use std::sync::mpsc::{channel, Sender};

/// Small allocations go through the runtime's own size-class free
/// list, as they do in the stdio binary.
#[global_allocator]
static ALLOCATOR: lova_rt::alloc::Pooled = lova_rt::alloc::Pooled;

struct LovaExtension;

#[gdextension]
unsafe impl ExtensionLibrary for LovaExtension {}

// --- the evaluator thread ---------------------------------------------------

struct Worker {
    tx: Sender<(J, Sender<J>)>,
}

impl Worker {
    fn start() -> Worker {
        let (tx, rx) = channel::<(J, Sender<J>)>();
        std::thread::Builder::new()
            .name("lova-rt".into())
            .stack_size(1 << 30)
            .spawn(move || {
                choose_evaluator();
                let mut sessions = Sessions::new();
                let mut next: u64 = 0;
                while let Ok((request, reply_to)) = rx.recv() {
                    let reply = handle(&request, &mut sessions, &mut next);
                    let _ = reply_to.send(reply);
                }
                // The sender is gone: the LovaRuntime was freed, and the
                // sessions go with this thread.
            })
            .expect("lova-godot: could not start the evaluator thread");
        Worker { tx }
    }

    fn ask(&self, request: J) -> J {
        let (reply_tx, reply_rx) = channel::<J>();
        if self.tx.send((request, reply_tx)).is_err() {
            return json!({"ok": false, "error": "the evaluator thread is gone"});
        }
        reply_rx
            .recv()
            .unwrap_or_else(|_| json!({"ok": false, "error": "the evaluator thread died"}))
    }
}

// --- Godot values <-> the protocol's JSON -----------------------------------

fn to_json(v: &Variant) -> Result<J, String> {
    match v.get_type() {
        VariantType::NIL => Ok(J::Null),
        VariantType::BOOL => Ok(J::from(if v.to::<bool>() { 1 } else { 0 })),
        VariantType::INT => Ok(J::from(v.to::<i64>())),
        VariantType::FLOAT => Err(format!(
            "a float ({}) cannot enter a LOVA program: convert it to an int first",
            v.to::<f64>()
        )),
        VariantType::STRING => Ok(J::from(v.to::<GString>().to_string())),
        VariantType::STRING_NAME => Ok(J::from(v.to::<StringName>().to_string())),
        VariantType::ARRAY => {
            let arr = v.to::<VarArray>();
            let mut out = Vec::with_capacity(arr.len());
            for item in arr.iter_shared() {
                out.push(to_json(&item)?);
            }
            Ok(J::Array(out))
        }
        VariantType::DICTIONARY => {
            let d = v.to::<VarDictionary>();
            if let Some(r) = d.get("ref") {
                return Ok(json!({ "ref": r.to::<i64>() }));
            }
            if let Some(i) = d.get("int") {
                return Ok(json!({ "int": i.to::<GString>().to_string() }));
            }
            Err(String::from("a Dictionary crosses only as {\"ref\": id} or {\"int\": \"digits\"}"))
        }
        other => Err(format!("a {:?} has no LOVA value", other)),
    }
}

fn to_variant(j: &J) -> Variant {
    match j {
        J::Null => Variant::nil(),
        J::Bool(b) => Variant::from(*b),
        J::Number(n) => match n.as_i64() {
            Some(i) => Variant::from(i),
            None => Variant::from(n.to_string()),
        },
        J::String(s) => Variant::from(s.as_str()),
        J::Array(items) => {
            let mut arr = VarArray::new();
            for item in items {
                arr.push(&to_variant(item));
            }
            Variant::from(arr)
        }
        J::Object(map) => {
            let mut d = VarDictionary::new();
            for (k, v) in map {
                d.set(k.as_str(), &to_variant(v));
            }
            Variant::from(d)
        }
    }
}

// --- the class ---------------------------------------------------------------

#[derive(GodotClass)]
#[class(base=RefCounted)]
pub struct LovaRuntime {
    worker: Worker,
    session: Option<u64>,
    /// The program's own value, a handle on the record the program
    /// evaluates to, which `get` reads by name.
    api: Option<u64>,
    steps: i64,
    error: String,
    /// The last anomaly as the protocol reports it, or null.
    anomaly: Variant,
    max_steps: i64,
    base: Base<RefCounted>,
}

#[godot_api]
impl IRefCounted for LovaRuntime {
    fn init(base: Base<RefCounted>) -> Self {
        LovaRuntime {
            worker: Worker::start(),
            session: None,
            api: None,
            steps: 0,
            error: String::new(),
            anomaly: Variant::nil(),
            max_steps: 1_000_000,
            base,
        }
    }
}

impl LovaRuntime {
    fn take_reply(&mut self, reply: &J) -> bool {
        self.steps = reply.get("steps").and_then(|s| s.as_i64()).unwrap_or(0);
        let ok = reply.get("ok").and_then(|o| o.as_bool()).unwrap_or(false);
        if ok {
            self.error.clear();
            self.anomaly = Variant::nil();
        } else if let Some(a) = reply.get("anomaly") {
            self.anomaly = to_variant(a);
            self.error = format!(
                "{} at {}",
                a.get("kind").and_then(|k| k.as_str()).unwrap_or("trap"),
                a.get("offending_op_name").and_then(|k| k.as_str()).unwrap_or("?")
            );
        } else {
            self.anomaly = Variant::nil();
            self.error = reply
                .get("error")
                .and_then(|e| e.as_str())
                .unwrap_or("unknown error")
                .to_string();
        }
        ok
    }

    fn with_session(&self, mut request: J) -> Option<J> {
        let sid = self.session?;
        request["session"] = J::from(sid);
        Some(request)
    }

    fn handle_of(v: &Variant) -> Option<u64> {
        match to_json(v) {
            Ok(J::Object(m)) => m.get("ref").and_then(|r| r.as_u64()),
            _ => None,
        }
    }
}

#[godot_api]
impl LovaRuntime {
    /// The protocol, raw: one request as JSON text, one reply as JSON text.
    #[func]
    fn request(&mut self, line: GString) -> GString {
        let request: J = match serde_json::from_str(&line.to_string()) {
            Ok(r) => r,
            Err(e) => {
                let bad = json!({"ok": false, "error": format!("bad request: {}", e)});
                return GString::from(&bad.to_string());
            }
        };
        let reply = self.worker.ask(request);
        GString::from(&reply.to_string())
    }

    /// What this runtime is: the `ping` reply.
    #[func]
    fn ping(&mut self) -> VarDictionary {
        to_variant(&self.worker.ask(json!({"op": "ping"}))).to::<VarDictionary>()
    }

    /// Evaluate a program, given as the hex of its byte sequence, and
    /// keep it as this runtime's session.  `false` on a decode error or
    /// a trap during evaluation; `error()` says which.
    #[func]
    fn open(&mut self, hex: GString, max_steps: i64, max_depth: i64) -> bool {
        self.close();
        self.max_steps = max_steps;
        let reply = self.worker.ask(json!({
            "op": "session", "bytes": hex.to_string(),
            "max_steps": max_steps, "max_depth": max_depth,
        }));
        if !self.take_reply(&reply) {
            return false;
        }
        self.session = reply.get("session").and_then(|s| s.as_u64());
        self.api = reply
            .get("value")
            .and_then(|v| v.get("ref"))
            .and_then(|r| r.as_u64());
        true
    }

    /// Whether a program is open.
    #[func]
    fn is_open(&self) -> bool {
        self.session.is_some()
    }

    /// The program's value itself, as a handle.
    #[func]
    fn api_handle(&self) -> Variant {
        match self.api {
            Some(id) => {
                let mut d = VarDictionary::new();
                d.set("ref", id as i64);
                Variant::from(d)
            }
            None => Variant::nil(),
        }
    }

    /// A field of the program's value by name -- a closure, a record,
    /// a number -- or null.  Charges no steps.
    #[func]
    fn get(&mut self, name: GString) -> Variant {
        let api = self.api_handle();
        self.get_in(api, Variant::from(name))
    }

    /// `map-get` on a held map: a field of a record the program handed
    /// out, or null when the map does not hold the key.
    #[func]
    fn get_in(&mut self, map: Variant, key: Variant) -> Variant {
        let target = match Self::handle_of(&map) {
            Some(id) => id,
            None => {
                self.error = String::from("get: a handle on a map, not a value");
                return Variant::nil();
            }
        };
        let key = match to_json(&key) {
            Ok(k) => k,
            Err(e) => {
                self.error = e;
                return Variant::nil();
            }
        };
        let request = match self.with_session(json!({"op": "get", "ref": target, "key": key})) {
            Some(r) => r,
            None => {
                self.error = String::from("no program is open");
                return Variant::nil();
            }
        };
        let reply = self.worker.ask(request);
        if !self.take_reply(&reply) {
            return Variant::nil();
        }
        to_variant(reply.get("value").unwrap_or(&J::Null))
    }

    /// Apply a closure to its arguments, one at a time.  Fewer
    /// arguments than it takes gives a closure back; a trap gives null
    /// and sets `error()` / `anomaly()`; `steps()` is this call's count.
    #[func]
    fn call(&mut self, function: Variant, args: VarArray) -> Variant {
        let fnv = match to_json(&function) {
            Ok(f) => f,
            Err(e) => {
                self.error = e;
                return Variant::nil();
            }
        };
        let mut encoded = Vec::with_capacity(args.len());
        for a in args.iter_shared() {
            match to_json(&a) {
                Ok(j) => encoded.push(j),
                Err(e) => {
                    self.error = e;
                    return Variant::nil();
                }
            }
        }
        let request = match self.with_session(json!({
            "op": "call", "fn": fnv, "args": encoded, "max_steps": self.max_steps,
        })) {
            Some(r) => r,
            None => {
                self.error = String::from("no program is open");
                return Variant::nil();
            }
        };
        let reply = self.worker.ask(request);
        if !self.take_reply(&reply) {
            return Variant::nil();
        }
        to_variant(reply.get("value").unwrap_or(&J::Null))
    }

    /// Let go of handles the script no longer needs, so the session
    /// can free what they hold.
    #[func]
    fn release(&mut self, handles: VarArray) {
        let mut ids = Vec::new();
        for h in handles.iter_shared() {
            if let Some(id) = Self::handle_of(&h) {
                ids.push(id);
            }
        }
        if let Some(request) = self.with_session(json!({"op": "release", "refs": ids})) {
            let reply = self.worker.ask(request);
            self.take_reply(&reply);
        }
    }

    /// Close the session, if one is open.
    #[func]
    fn close(&mut self) {
        if let Some(request) = self.with_session(json!({"op": "close"})) {
            self.worker.ask(request);
        }
        self.session = None;
        self.api = None;
    }

    /// The steps the last call took.
    #[func]
    fn steps(&self) -> i64 {
        self.steps
    }

    /// Why the last request failed, or "".
    #[func]
    fn error(&self) -> GString {
        GString::from(self.error.as_str())
    }

    /// The last trap as the protocol reports it (kind, offending
    /// operator, position, message), or null.
    #[func]
    fn anomaly(&self) -> Variant {
        self.anomaly.clone()
    }

    /// The ceiling a call gets.
    #[func]
    fn set_max_steps(&mut self, max_steps: i64) {
        self.max_steps = max_steps;
    }
}
