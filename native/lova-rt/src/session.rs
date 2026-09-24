//! Sessions (`spec/native-runtime-protocol.md`, "Sessions (since
//! 0.3.0, Q126)"): the program evaluated once and kept alive, its
//! values handed out as handles, its closures called by handle.
//!
//! This is `Rules` in `apps/war/war.py` over the wire.  A call sets
//! `steps` to zero and applies the arguments one at a time, exactly as
//! `core.runtime._call` does from Python; everything else on the
//! runtime -- the named closures and their `own` counters, the
//! surprise trace, the rest of stdin, the lineage store -- is the one
//! the program was evaluated with, because the driver's `Runtime` is.

use crate::int::Int;
use crate::rt;
use crate::tokens::Arena;
use crate::trap::{Anomaly, Fault};
use crate::value::*;
use num_bigint::BigInt;
use serde_json::{json, Map as JMap, Value as J};
use std::collections::HashMap;
use std::rc::Rc;
use std::str::FromStr;

/// The protocol's own boundary between a JSON number and `{"int": ...}`.
const SAFE_INT: i64 = 1 << 53;

pub struct Session {
    pub arena: Arena,
    pub rt: rt::Rt,
    /// The program's own value, held so that nothing it reaches is
    /// dropped -- the closures in it hold the scopes they were written
    /// in, and those hold the rest of the program's environment.  It is
    /// held, not read: releasing every handle must not empty the
    /// session.
    #[allow(dead_code)]
    pub value: Value,
    refs: HashMap<u64, Value>,
    /// The address of a held value to its handle, so that one value is
    /// one handle, as the reference server's `by_value` does.
    by_value: HashMap<usize, u64>,
    next_ref: u64,
    /// The ceiling a `call` gets when it does not name one.
    pub max_steps: u64,
}

/// The identity of a value that crosses as a handle: the address its
/// `Rc` holds, which is `id(value)` on the Python side.
fn address(v: &Value) -> Option<usize> {
    match v {
        Value::Map(m) => Some(Rc::as_ptr(&m.0) as *const u8 as usize),
        Value::Closure(c) => Some(Rc::as_ptr(c) as *const u8 as usize),
        Value::Loop(l) => Some(Rc::as_ptr(l) as *const u8 as usize),
        Value::Population(p) => Some(Rc::as_ptr(p) as *const u8 as usize),
        Value::Tail(t) => Some(Rc::as_ptr(t) as *const u8 as usize),
        // A program is an arena id, and that id is its identity.
        Value::Program(id) => Some((1usize << (usize::BITS - 1)) | (*id as usize)),
        _ => None,
    }
}

impl Session {
    pub fn new(arena: Arena, rt: rt::Rt, value: Value, max_steps: u64) -> Session {
        Session {
            arena,
            rt,
            value,
            refs: HashMap::new(),
            by_value: HashMap::new(),
            next_ref: 0,
            max_steps,
        }
    }

    /// The handle for a value, the same one each time it is seen.  Ids
    /// are never reused: a handle released and used again is an error,
    /// not a silent hit on somebody else's value.
    fn ref_for(&mut self, v: &Value) -> u64 {
        let key = address(v).unwrap_or(0);
        if let Some(id) = self.by_value.get(&key) {
            return *id;
        }
        self.next_ref += 1;
        let id = self.next_ref;
        self.refs.insert(id, v.clone());
        self.by_value.insert(key, id);
        id
    }

    fn drop_refs(&mut self, ids: &[u64]) {
        for id in ids {
            if let Some(v) = self.refs.remove(id) {
                if let Some(key) = address(&v) {
                    if self.by_value.get(&key) == Some(id) {
                        self.by_value.remove(&key);
                    }
                }
            }
        }
    }

    /// A LOVA value as the protocol carries it: data, or a handle.
    pub fn encode(&mut self, v: &Value) -> J {
        match v {
            Value::Int(i) => match i.to_i64() {
                Some(n) if n > -SAFE_INT && n < SAFE_INT => J::from(n),
                _ => json!({ "int": i.to_string() }),
            },
            Value::Nil => J::Null,
            Value::Text(s) => J::from(s.as_str()),
            Value::Cons(_) => {
                let mut out: Vec<J> = Vec::new();
                let mut rest = v.clone();
                while let Value::Cons(cell) = rest {
                    out.push(self.encode(&cell.head));
                    rest = cell.tail.clone();
                }
                J::Array(out)
            }
            other => {
                debug_assert!(
                    !matches!(other, Value::Unset),
                    "an unwritten slot reached the protocol"
                );
                let id = self.ref_for(other);
                json!({ "ref": id })
            }
        }
    }

    /// What the protocol carries, as a LOVA value.
    pub fn decode(&self, data: &J, where_: &str) -> Result<Value, String> {
        match data {
            J::Null => Ok(Value::Nil),
            J::Bool(b) => Ok(Value::Int(Int::from_i64(if *b { 1 } else { 0 }))),
            J::String(s) => Ok(Value::Text(Rc::new(s.clone()))),
            J::Number(n) => {
                if let Some(v) = n.as_i64() {
                    return Ok(Value::Int(Int::from_i64(v)));
                }
                if let Some(f) = n.as_f64() {
                    if f.fract() == 0.0 && f.abs() < 9.3e18 {
                        return Ok(Value::Int(Int::from_i64(f as i64)));
                    }
                    return Err(format!("{}: LOVA has no floating point: {}", where_, f));
                }
                // A u64 past i64: still an integer.
                match n.as_u64() {
                    Some(v) => Ok(Value::Int(Int::from_big(BigInt::from(v)))),
                    None => Err(format!("{}: cannot read {}", where_, n)),
                }
            }
            J::Array(items) => {
                let mut out = Vec::with_capacity(items.len());
                for item in items {
                    out.push(self.decode(item, where_)?);
                }
                Ok(list_from(out))
            }
            J::Object(map) => {
                if let Some(r) = map.get("ref") {
                    let id = r.as_u64();
                    return match id.and_then(|i| self.refs.get(&i)) {
                        Some(v) => Ok(v.clone()),
                        None => Err(format!("no such ref: {}", show(r))),
                    };
                }
                if let Some(t) = map.get("int") {
                    let text = match t {
                        J::String(s) => s.clone(),
                        other => other.to_string(),
                    };
                    return BigInt::from_str(&text)
                        .map(|b| Value::Int(Int::from_big(b)))
                        .map_err(|_| format!("{}: not an integer: {:?}", where_, text));
                }
                Err(format!("{}: cannot read {}", where_, data))
            }
        }
    }
}

/// `None` prints as Python spells it, because the reference server's
/// message for a missing handle is the one a driver will have seen.
fn show(j: &J) -> String {
    match j {
        J::Null => "None".to_string(),
        J::String(s) => format!("{:?}", s),
        other => other.to_string(),
    }
}

// --- the anomaly, as `run` reports it ---------------------------------------

pub fn anomaly_json(a: &Anomaly) -> J {
    let mut an = JMap::new();
    an.insert("kind".into(), J::from(a.kind));
    an.insert("offending_op".into(), a.offending_op.map(J::from).unwrap_or(J::Null));
    an.insert("offending_op_name".into(), J::from(a.offending_op_name.clone()));
    an.insert(
        "position_path".into(),
        J::Array(a.position_path.iter().map(|o| J::from(*o)).collect()),
    );
    an.insert(
        "position_nodes".into(),
        J::Array(a.position_nodes.iter().map(|n| n.map(J::from).unwrap_or(J::Null)).collect()),
    );
    if let Some(b) = &a.body_offender {
        an.insert("body_offender".into(), b.clone());
    }
    an.insert("detail".into(), J::Object(a.detail.clone()));
    an.insert("repair_hint".into(), J::from(a.repair_hint.clone()));
    an.insert("message".into(), J::from(a.message.clone()));
    J::Object(an)
}

fn err(id: &J, message: String) -> J {
    json!({"id": id.clone(), "ok": false, "error": message})
}

fn session_of<'a>(
    sessions: &'a mut HashMap<u64, Session>,
    request: &J,
) -> Result<&'a mut Session, String> {
    let named = request.get("session").cloned().unwrap_or(J::Null);
    match named.as_u64().and_then(move |sid| sessions.get_mut(&sid)) {
        Some(s) => Ok(s),
        None => Err(format!("no such session: {}", show(&named))),
    }
}

// --- get (spec: `map-get` on a held map, no steps) ---------------------------

pub fn get(sessions: &mut HashMap<u64, Session>, request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let s = match session_of(sessions, request) {
        Ok(s) => s,
        Err(e) => return err(&id, e),
    };
    // `ref` is the handle's own id, not an encoded value -- the map is
    // always something the session holds.
    let named = request.get("ref").cloned().unwrap_or(J::Null);
    let target = match s.decode(&json!({ "ref": named }), "ref") {
        Ok(v) => v,
        Err(e) => return err(&id, e),
    };
    let key = match s.decode(request.get("key").unwrap_or(&J::Null), "key") {
        Ok(k) => k,
        Err(e) => return err(&id, e),
    };
    let found = (|| -> Result<Option<Value>, Fault> {
        let table = rt::as_map(&s.arena, &target, "map-get")?;
        let hashed = rt::map_key(&s.arena, &key, "map-get")?;
        Ok(table.get(&hashed).map(|e| e.val))
    })();
    match found {
        Ok(hit) => {
            let encoded = match hit {
                Some(v) => s.encode(&v),
                None => J::Null,
            };
            json!({"id": id, "ok": true, "value": encoded, "steps": 0, "stdout": ""})
        }
        Err(Fault::NotImplemented(m)) => err(&id, format!("NotImplementedError: {}", m)),
        Err(Fault::Trap(t)) => json!({
            "id": id, "ok": false, "anomaly": anomaly_json(&t.anomaly),
            "steps": 0, "stdout": "",
        }),
    }
}

// --- call (spec: steps from zero, one argument at a time) --------------------

pub fn call(sessions: &mut HashMap<u64, Session>, request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let s = match session_of(sessions, request) {
        Ok(s) => s,
        Err(e) => return err(&id, e),
    };
    let mut fnv = match s.decode(request.get("fn").unwrap_or(&J::Null), "fn") {
        Ok(v) => v,
        Err(e) => return err(&id, e),
    };
    let mut args: Vec<Value> = Vec::new();
    if let Some(J::Array(items)) = request.get("args") {
        for item in items {
            match s.decode(item, "args") {
                Ok(v) => args.push(v),
                Err(e) => return err(&id, e),
            }
        }
    }

    s.rt.max_steps = request.get("max_steps").and_then(|v| v.as_u64()).unwrap_or(s.max_steps);
    // A fresh run's accounting: this call's steps, this call's output,
    // and no function in flight from the call before it.
    s.rt.steps = 0;
    s.rt.mark = 0;
    s.rt.current = std::ptr::null();
    s.rt.output.clear();
    s.rt.path.clear();

    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        for arg in args {
            fnv = rt::call(&mut s.arena, &mut s.rt, fnv.clone(), arg)?;
        }
        Ok(fnv)
    }));

    let mut reply = JMap::new();
    reply.insert("id".into(), id);
    match outcome {
        Err(_) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from("panic in the evaluator"));
            reply.insert("steps".into(), J::from(s.rt.steps));
            return J::Object(reply);
        }
        Ok(Ok(v)) => {
            let encoded = s.encode(&v);
            reply.insert("ok".into(), J::Bool(true));
            reply.insert("value".into(), encoded);
        }
        Ok(Err(Fault::NotImplemented(message))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("error".into(), J::from(format!("NotImplementedError: {}", message)));
            reply.insert("steps".into(), J::from(s.rt.steps));
            return J::Object(reply);
        }
        // The session stays open: the drivers catch a trap per tick and
        // go on.
        Ok(Err(Fault::Trap(t))) => {
            reply.insert("ok".into(), J::Bool(false));
            reply.insert("anomaly".into(), anomaly_json(&t.anomaly));
        }
    }
    reply.insert("steps".into(), J::from(s.rt.steps));
    reply.insert("stdout".into(), J::from(s.rt.output.clone()));
    J::Object(reply)
}

// --- release / close ---------------------------------------------------------

pub fn release(sessions: &mut HashMap<u64, Session>, request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let s = match session_of(sessions, request) {
        Ok(s) => s,
        Err(e) => return err(&id, e),
    };
    let mut ids: Vec<u64> = Vec::new();
    if let Some(J::Array(items)) = request.get("refs") {
        for item in items {
            if let Some(r) = item.as_u64() {
                ids.push(r);
            }
        }
    }
    s.drop_refs(&ids);
    json!({"id": id, "ok": true})
}

pub fn close(sessions: &mut HashMap<u64, Session>, request: &J) -> J {
    let id = request.get("id").cloned().unwrap_or(J::Null);
    let named = request.get("session").cloned().unwrap_or(J::Null);
    match named.as_u64().and_then(|sid| sessions.remove(&sid)) {
        Some(_) => json!({"id": id, "ok": true}),
        None => err(&id, format!("no such session: {}", show(&named))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn blank() -> Session {
        Session::new(Arena::new(), rt::Rt::new(1000, 100, 0, ""), Value::Nil, 1000)
    }

    /// The encoded-value table, row by row.
    #[test]
    fn encodes_as_the_table_says() {
        let mut s = blank();
        assert_eq!(s.encode(&Value::Int(Int::from_i64(42))), json!(42));
        assert_eq!(s.encode(&Value::Int(Int::from_i64(-42))), json!(-42));
        // 2^53 and beyond is a decimal string, not a JSON number
        let big = Int::from_i64(1 << 53);
        assert_eq!(s.encode(&Value::Int(big)), json!({"int": "9007199254740992"}));
        assert_eq!(s.encode(&Value::Nil), J::Null);
        assert_eq!(s.encode(&Value::Text(Rc::new("ab".into()))), json!("ab"));
        // a list of codepoints is still an array
        let list = list_from(vec![
            Value::Int(Int::from_i64(1)),
            list_from(vec![Value::Int(Int::from_i64(2)), Value::Int(Int::from_i64(3))]),
        ]);
        assert_eq!(s.encode(&list), json!([1, [2, 3]]));
    }

    /// One value is one handle, and ids start at 1.
    #[test]
    fn one_value_is_one_handle() {
        let mut s = blank();
        let m = Value::Map(MapValue::empty());
        assert_eq!(s.encode(&m), json!({"ref": 1}));
        assert_eq!(s.encode(&m.clone()), json!({"ref": 1}));
        let other = Value::Map(MapValue::empty());
        assert_eq!(s.encode(&other), json!({"ref": 2}));
        s.drop_refs(&[1]);
        assert!(s.decode(&json!({"ref": 1}), "arg").is_err());
        assert!(s.decode(&json!({"ref": 2}), "arg").is_ok());
    }

    #[test]
    fn decodes_what_it_encodes() {
        let s = blank();
        let v = s.decode(&json!([1, [2, "x"], null]), "args").unwrap();
        let items = list_walk(&v);
        assert_eq!(items.len(), 3);
        assert!(matches!(items[2], Value::Nil));
        let n = s.decode(&json!({"int": "170141183460469231731687303715884105727"}), "a");
        assert_eq!(
            match n.unwrap() {
                Value::Int(i) => i.to_string(),
                _ => String::new(),
            },
            "170141183460469231731687303715884105727"
        );
        assert!(s.decode(&json!(1.5), "a").is_err());
    }
}
