//! The evaluator: spec §3 (step accounting), §4 (calls), §5 (operators).
//!
//! A tree walk over the decoded arena, with an explicit path stack (D8)
//! in place of the reference's read of the Python call stack.  Every
//! rule here is the reference's; where the reference has both a
//! template and a generic handler for an operator, the template is what
//! is written (spec §0), and the generic shape is reached only through
//! the malformed slots `decode` can still produce.

use crate::evolve;
use crate::int::Int;
use crate::lineage::Lineage;
use crate::meta;
use crate::nt;
use crate::text;
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::{json, Value as J};
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

pub const MAX_NT_INPUT: i64 = 2_000;
pub const MAX_INT_BITS: u64 = 4_096;

pub struct Budget {
    pub limit: Int,
    pub spent: i64,
}

pub struct Rt {
    pub env: Rc<Scope>,
    pub budget_stack: Vec<Budget>,
    pub steps: u64,
    pub max_steps: u64,
    pub call_depth: u32,
    pub max_call_depth: u32,
    /// D8's explicit path stack: the operator of every frame from the
    /// root to the node in hand, and the arena node it came from.  One
    /// vector, because it is pushed and popped on every node (Q124).
    pub path: Vec<(u8, u32)>,
    /// `ordinals[node id]` is the node's preorder place in the decoded
    /// program; ids past its end were made during the run.
    pub ordinals: Rc<Vec<u32>>,
    pub let_chain: Option<(u32, bool)>,
    /// The function whose body is running, for `hot` (spec §4.5).  A
    /// borrowed pointer for the same reason as `ClosureData::owner`:
    /// `named` keeps every candidate alive, and a call is too hot for
    /// two refcount pairs.
    pub current: *const ClosureData,
    pub mark: u64,
    pub named: Vec<Rc<ClosureData>>,
    pub output: String,
    pub input: Vec<String>,
    pub input_pos: usize,
    pub granted: u32,
    pub caps: u32,
    pub enclosed: bool,
    pub patterns: HashMap<String, regex::Regex>,
    /// Call frames nothing closed over, kept for the next call (Q124).
    pub scope_pool: Vec<Rc<Scope>>,
    /// The provenance store, shared with a `trace` sandbox.
    pub lineage: Rc<RefCell<Lineage>>,
    /// The deviations `trace` reports, in emission order.
    pub surprise: Vec<Int>,
    /// The bytecode VM's state; `vm.on` says which evaluator runs.
    pub vm: crate::vm::VmState,
    /// A closure the VM made carries no `Scope`; this stands in the
    /// field the tree-walker's closures use.
    pub empty_env: Rc<Scope>,
}

impl Rt {
    pub fn new(max_steps: u64, max_depth: u32, granted: u32, stdin: &str) -> Rt {
        Rt {
            env: Scope::root(),
            budget_stack: Vec::new(),
            steps: 0,
            max_steps,
            call_depth: 0,
            max_call_depth: max_depth,
            path: Vec::new(),
            ordinals: Rc::new(Vec::new()),
            let_chain: None,
            current: std::ptr::null(),
            mark: 0,
            named: Vec::new(),
            output: String::new(),
            input: split_lines(stdin),
            input_pos: 0,
            granted,
            caps: 0,
            enclosed: false,
            patterns: HashMap::new(),
            scope_pool: Vec::new(),
            lineage: Rc::new(RefCell::new(Lineage::new())),
            surprise: Vec::new(),
            vm: crate::vm::VmState::new(),
            empty_env: Scope::root(),
        }
    }

    /// `emit`: the surprise trace, which only `trace` reads back.
    pub fn emit(&mut self, predicted: &Int, actual: &Int) -> Int {
        let dev = predicted.sub(actual).abs();
        self.surprise.push(dev.clone());
        dev
    }

    /// The node's place in the byte stream, or `None` when the node
    /// was built during the run rather than decoded.
    pub fn ordinal(&self, id: u32) -> Option<u32> {
        self.ordinals.get(id as usize).copied()
    }

    pub fn read_line(&mut self) -> Option<String> {
        if self.input_pos < self.input.len() {
            let line = self.input[self.input_pos].clone();
            self.input_pos += 1;
            // `io.StringIO.readline` yields "" at the end, which is
            // falsy, so an empty piece is end of input.
            if line.is_empty() {
                return None;
            }
            return Some(line);
        }
        None
    }
}

/// `io.StringIO(...).readline` splits on '\n' and keeps it.
fn split_lines(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    for ch in text.chars() {
        cur.push(ch);
        if ch == '\n' {
            out.push(std::mem::take(&mut cur));
        }
    }
    if !cur.is_empty() {
        out.push(cur);
    }
    out
}

// --- accounting (spec §3.1) -------------------------------------------------

#[inline]
fn charge_tick(rt: &mut Rt) -> R<()> {
    if let Some(b) = rt.budget_stack.last_mut() {
        b.spent += 1;
        let over = match b.limit.to_i64() {
            Some(l) => b.spent > l,
            None => Int::from_i64(b.spent) > b.limit,
        };
        if over {
            return Err(budget_trap(&b.limit, b.spent));
        }
    }
    rt.steps += 1;
    if rt.steps > rt.max_steps {
        return Err(step_trap(rt.steps, rt.max_steps));
    }
    Ok(())
}

#[inline]
pub fn tick(rt: &mut Rt, n: u64) -> R<()> {
    rt.steps = rt.steps.saturating_add(n);
    if rt.steps > rt.max_steps {
        return Err(step_trap(rt.steps, rt.max_steps));
    }
    Ok(())
}

// --- coercions (spec §2.4) --------------------------------------------------

pub fn as_int(a: &Arena, v: &Value, ctx: &str) -> R<Int> {
    match v {
        Value::Int(i) => Ok(i.clone()),
        Value::Population(_) => Err(domain(
            "type-violation",
            format!(
                "{}: expected an Int, got a population; `fitness` gives its scores, `select` gives a variant",
                ctx
            ),
            detail(vec![
                ("operator", J::from(ctx)),
                ("expected", J::from("Int")),
                ("got", J::from("Population")),
            ]),
            "use `fitness` for the scores or `select` for a variant",
        )),
        Value::Map(_)
        | Value::Closure(_)
        | Value::Loop(_)
        | Value::Text(_)
        | Value::Tail(_)
        | Value::Unset => {
            Err(domain(
                "type-violation",
                format!(
                    "{}: expected an Int, got a function value ({}); a function can only \
appear in the head slot of `apply` or in a slot typed Fn",
                    ctx,
                    value_repr(a, v)
                ),
                detail(vec![
                    ("operator", J::from(ctx)),
                    ("expected", J::from("Int")),
                    ("got", J::from("Fn")),
                ]),
                "apply the function to get an integer, or use it in an Fn slot",
            ))
        }
        Value::Program(_) => Err(domain(
            "type-violation",
            format!(
                "{}: expected an Int, got a program; `hash` gives its integer, `eval` gives \
its result",
                ctx
            ),
            detail(vec![
                ("operator", J::from(ctx)),
                ("expected", J::from("Int")),
                ("got", J::from("Program")),
            ]),
            "use `hash` for the program's integer or `eval` for its value",
        )),
        Value::Nil | Value::Cons(_) => Err(domain(
            "type-violation",
            format!(
                "{}: expected an Int, got a list ({}); use `head` to take an element out of it",
                ctx,
                value_repr(a, v)
            ),
            detail(vec![
                ("operator", J::from(ctx)),
                ("expected", J::from("Int")),
                ("got", J::from("List")),
            ]),
            "use `head` to take an element out of the list",
        )),
    }
}

pub fn as_text(a: &Arena, v: &Value, ctx: &str) -> R<Rc<String>> {
    match v {
        Value::Text(s) => Ok(s.clone()),
        Value::Int(i) => Ok(Rc::new(i.to_string())),
        Value::Program(_) => Err(domain(
            "type-violation",
            format!("{}: cannot write a program directly; `explain` renders it", ctx),
            detail(vec![("operator", J::from(ctx)), ("got", J::from("Program"))]),
            "write `(explain p)` instead of `p`",
        )),
        Value::Map(_) => Err(domain(
            "type-violation",
            format!("{}: cannot write a map; write its `map-pairs`", ctx),
            detail(vec![("operator", J::from(ctx)), ("got", J::from("Map"))]),
            "iterate `(map-pairs m)` and write each entry",
        )),
        Value::Nil | Value::Cons(_) => {
            let items = list_walk(v);
            let mut out = String::new();
            for item in &items {
                let code = match item {
                    Value::Int(i) => i.to_i64().filter(|c| (0..=0x10FFFF).contains(c)),
                    _ => None,
                };
                match code.and_then(|c| char::from_u32(c as u32)) {
                    Some(c) => out.push(c),
                    None => {
                        return Err(domain(
                            "domain-error",
                            format!(
                                "{}: {} is not a codepoint; a list is written as text, so every \
element must be one",
                                ctx,
                                value_repr(a, item)
                            ),
                            detail(vec![
                                ("operator", J::from(ctx)),
                                ("element", value_json(a, item)),
                            ]),
                            "write a list whose elements are all valid codepoints",
                        ))
                    }
                }
            }
            Ok(Rc::new(out))
        }
        _ => Err(domain(
            "type-violation",
            format!(
                "{}: cannot write a function value ({}); write an integer or a list of codepoints",
                ctx,
                value_repr(a, v)
            ),
            detail(vec![("operator", J::from(ctx)), ("got", J::from("Fn"))]),
            "write an integer or a list of codepoints",
        )),
    }
}

fn value_json(a: &Arena, v: &Value) -> J {
    match v {
        Value::Int(i) => i.to_json(),
        Value::Text(s) => J::from(s.as_str()),
        _ => J::from(value_repr(a, v)),
    }
}

pub fn as_list(a: &Arena, v: &Value, ctx: &str) -> R<Value> {
    match v {
        Value::Nil | Value::Cons(_) => Ok(v.clone()),
        Value::Text(s) => Ok(text_chars(s)),
        _ => {
            let kind = kind_of(v);
            let repr = format_repr(a, v);
            let mut hint = format!("`{}` wants a list or a text and got {} {}", ctx, kind, repr);
            if matches!(v, Value::Int(_)) {
                hint.push_str(
                    "; if this came from an input, the argument arrived as an integer -- \
quote it on the command line to pass a text",
                );
            }
            if matches!(v, Value::Map(_)) && matches!(ctx, "nil?" | "head" | "tail") {
                hint.push_str(
                    "; a record and a map are the same kind of value and it is not a list, so \
`(nil)` cannot stand for `absent` beside one -- give the record a field that says so, \
`(rec v 0 ...)`, and test `(get r v)`",
                );
            }
            Err(domain(
                "type-violation",
                format!(
                    "{}: expected a List, got {}; only `nil`, `cons` and `tail` produce list values",
                    ctx,
                    value_repr(a, v)
                ),
                detail(vec![
                    ("operator", J::from(ctx)),
                    ("expected", J::from("List")),
                    ("got", J::from(kind)),
                    ("got_value", J::from(repr.clone())),
                ]),
                &hint,
            ))
        }
    }
}

pub fn as_vec(a: &Arena, v: &Value, ctx: &str) -> R<Vec<Value>> {
    Ok(list_walk(&as_list(a, v, ctx)?))
}

pub fn as_fn(a: &Arena, v: &Value, ctx: &str) -> R<Value> {
    match v {
        Value::Closure(_) | Value::Loop(_) => Ok(v.clone()),
        _ => Err(domain(
            "type-violation",
            format!(
                "{}: the function slot holds {} {}, not a function",
                ctx,
                kind_of(v),
                format_repr(a, v)
            ),
            detail(vec![
                ("operator", J::from(ctx)),
                ("expected", J::from("Fn")),
                ("got", J::from(kind_of(v))),
            ]),
            "pass a `lambda` or the name of a `def`; an operator is not a value -- \
wrap it, `(lambda x (op x))`",
        )),
    }
}

pub fn as_program(a: &Arena, v: &Value, ctx: &str) -> R<u32> {
    match v {
        Value::Program(id) => Ok(*id),
        _ => Err(domain(
            "type-violation",
            format!("{}: expected a Program, got {}; `quote` produces one", ctx, value_repr(a, v)),
            detail(vec![("operator", J::from(ctx)), ("expected", J::from("Program"))]),
            "wrap the expression in `quote`, or pass a program produced by `clone` or `mutate`",
        )),
    }
}

pub fn map_key(a: &Arena, v: &Value, ctx: &str) -> R<MapKey> {
    #[cfg(feature = "prof")]
    crate::prof::mark(crate::prof::R_MAPKEY);
    match v {
        Value::Int(i) => Ok(MapKey::I(i.clone())),
        Value::Text(s) => Ok(MapKey::T(s.clone())),
        // The chain is walked where it lies: a key was costing a vector
        // of cloned values and then a vector of keys (Q124).
        Value::Nil | Value::Cons(_) => {
            // A cell of a grid is the common key, and it needs nothing
            // on the heap.
            if let Value::Cons(first) = v {
                if let (Value::Int(Int::S(x)), Value::Cons(second)) = (&first.head, &first.tail) {
                    if let (Value::Int(Int::S(y)), Value::Nil) = (&second.head, &second.tail) {
                        return Ok(MapKey::P(*x, *y));
                    }
                }
            }
            let mut out = Vec::new();
            let mut rest = v;
            while let Value::Cons(cell) = rest {
                out.push(map_key(a, &cell.head, ctx)?);
                rest = &cell.tail;
            }
            Ok(MapKey::L(out))
        }
        _ => Err(domain(
            "type-violation",
            format!("{}: a map key is an integer or a list, not {}", ctx, type_name(v)),
            detail(vec![("operator", J::from(ctx)), ("got", J::from(type_name(v)))]),
            "key the map by an integer or by text",
        )),
    }
}

pub fn as_map(a: &Arena, v: &Value, ctx: &str) -> R<MapValue> {
    match v {
        Value::Map(m) => Ok(m.clone()),
        Value::Nil | Value::Cons(_) => {
            let out = MapValue::empty();
            for entry in list_walk(v) {
                if !is_list(&entry) {
                    return Err(domain(
                        "type-violation",
                        format!("{}: a map from a list needs `(list key value)` pairs", ctx),
                        detail(vec![
                            ("operator", J::from(ctx)),
                            ("got", J::from(type_name(&entry))),
                        ]),
                        "build the list with `(list (list k v) ...)`",
                    ));
                }
                let pair = list_walk(&entry);
                if pair.len() != 2 {
                    return Err(domain(
                        "domain-error",
                        format!("{}: a map entry is a two-element list, got {}", ctx, pair.len()),
                        detail(vec![
                            ("operator", J::from(ctx)),
                            ("length", J::from(pair.len())),
                        ]),
                        "give each entry as `(list key value)`",
                    ));
                }
                let k = map_key(a, &pair[0], ctx)?;
                out.insert_owned(k, pair[0].clone(), pair[1].clone());
            }
            Ok(out)
        }
        _ => Err(domain(
            "type-violation",
            format!("{}: expected a Map or a list of pairs, got {}", ctx, value_repr(a, v)),
            detail(vec![("operator", J::from(ctx)), ("expected", J::from("Map"))]),
            "start from `(nil)` and `map-put` into it",
        )),
    }
}

pub fn sep_of(a: &Arena, v: &Value, ctx: &str) -> R<Rc<String>> {
    match v {
        Value::Int(i) => match i.to_i64().and_then(|c| u32::try_from(c).ok()).and_then(char::from_u32)
        {
            Some(c) => Ok(Rc::new(c.to_string())),
            None => Err(domain(
                "domain-error",
                format!("{}: {} is not a codepoint", ctx, i),
                detail(vec![("operator", J::from(ctx))]),
                "give a separator that is a text or a codepoint",
            )),
        },
        _ => as_text(a, v, ctx),
    }
}

/// `_require_capability` (spec 5.7): the innermost boundary must have
/// declared the effect, whatever the host granted.
pub fn require_capability(rt: &Rt, bit: u32, name: &str) -> R<()> {
    if rt.caps & bit != 0 {
        return Ok(());
    }
    let needed = capability_names(bit)[0];
    Err(domain(
        "capability-denied",
        format!("{}: used outside a boundary that declares {}", name, needed),
        detail(vec![
            ("operator", J::from(name)),
            ("needs", J::from(needed)),
            ("declared", J::from(capability_names(rt.caps))),
        ]),
        &format!("wrap the use in (boundary \"{}\" ...)", needed),
    ))
}

/// The `OSError` subclass name Python's `type(exc).__name__` would give.
pub fn os_error_name(e: &std::io::Error) -> &'static str {
    match e.kind() {
        std::io::ErrorKind::NotFound => "FileNotFoundError",
        std::io::ErrorKind::PermissionDenied => "PermissionError",
        std::io::ErrorKind::AlreadyExists => "FileExistsError",
        _ => "OSError",
    }
}

pub fn fs_fault(op: &str, path: &str, reason: &str) -> Fault {
    let hint = if op == "fs-read" {
        "give `fs-read` the path of a readable UTF-8 file"
    } else {
        "give `fs-write` a path in a directory that exists"
    };
    domain(
        "domain-error",
        format!("{}: {}: {}", op, path, reason),
        detail(vec![
            ("operator", J::from(op)),
            ("path", J::from(path)),
            ("reason", J::from(reason)),
        ]),
        hint,
    )
}

pub fn not_callable(a: &Arena, fnv: &Value) -> Fault {
    domain(
        "type-violation",
        format!(
            "apply: head slot is not a function (got {}); only `lambda` and `loop-until` \
produce callable values",
            value_repr(a, fnv)
        ),
        detail(vec![("operator", J::from("apply")), ("expected", J::from("Fn"))]),
        "apply a `lambda` or a `loop-until`, or a name bound to one",
    )
}

fn unbound(rt: &Rt, name_id: i64) -> Fault {
    let mut names: Vec<i64> = rt.env.flatten().keys().copied().collect();
    names.sort_unstable();
    unbound_with(name_id, &names)
}

/// The same anomaly from a name list the VM's compiler already knows:
/// the binders its resolver walked, which is `flatten_env`'s key set.
pub fn unbound_with(name_id: i64, names: &[i64]) -> Fault {
    domain(
        "unbound-ref",
        format!("unbound ref: {}", name_id),
        detail(vec![
            ("name_id", J::from(name_id)),
            ("bound_names", J::from(names.to_vec())),
        ]),
        "bind the name with a `let`, or reference one that is bound",
    )
}

// --- enrichment (spec §6.2) -------------------------------------------------

fn cost_by_function(rt: &Rt) -> J {
    let open_steps = rt.steps - rt.mark;
    let mut order: Vec<i64> = Vec::new();
    let mut steps: HashMap<i64, u64> = HashMap::new();
    let mut calls: HashMap<i64, u64> = HashMap::new();
    for f in &rt.named {
        let name = match f.name.get() {
            Some(n) => n,
            None => continue,
        };
        let same_as_current = std::ptr::eq(Rc::as_ptr(f), rt.current);
        let own = f.own.get() + if same_as_current { open_steps } else { 0 };
        if !steps.contains_key(&name) {
            order.push(name);
        }
        *steps.entry(name).or_insert(0) += own;
        *calls.entry(name).or_insert(0) += f.calls.get();
    }
    let mut rows: Vec<(i64, u64)> = order.iter().map(|n| (*n, steps[n])).collect();
    rows.sort_by(|x, y| y.1.cmp(&x.1)); // stable: ties keep first-seen order
    rows.truncate(8);
    J::Array(
        rows.iter()
            .filter(|(_, n)| *n > 0)
            .map(|(name, n)| json!([name, n, calls[name]]))
            .collect(),
    )
}

fn enrich(a: &Arena, rt: &Rt, t: &mut Trap) {
    if rt.vm.frames.is_empty() {
        let path = rt.path.clone();
        enrich_with(rt, t, &path);
    } else {
        // The VM is below this tree-walk: its activations' chains and
        // the nodes on `rt.path` interleave (vm/path.rs).
        let full = crate::vm::path::full(a, rt, None);
        enrich_with(rt, t, &full);
    }
}

pub fn enrich_with(rt: &Rt, t: &mut Trap, path: &[(u8, u32)]) {
    let op = path.last().map(|f| f.0);
    let alts = op.map(suggest_alternatives).unwrap_or_default();
    t.anomaly.position_path = path.iter().map(|f| f.0).collect();
    t.anomaly.position_nodes = path.iter().map(|f| rt.ordinal(f.1)).collect();
    t.anomaly.offending_op = op;
    t.anomaly.offending_op_name = op.map(op_name).unwrap_or("").to_string();
    t.anomaly.valid_alternatives = alts.clone();
    if t.anomaly.kind == "step-limit-exceeded" || t.anomaly.kind == "recursion-depth-exceeded" {
        let hot = cost_by_function(rt);
        if !hot.as_array().map(|v| v.is_empty()).unwrap_or(true) {
            t.anomaly.detail.insert("calls".to_string(), hot);
        }
    }
    if t.anomaly.kind == "conservation-violated" {
        let specific = t.anomaly.body_offender.is_some();
        if let (Some(o), false) = (op, specific) {
            let names: Vec<String> =
                alts.iter().map(|x| format!("'{}'", op_name(*x))).collect();
            t.anomaly.repair_hint = format!(
                "replace operator `{}` with one of [{}] to keep the body in the conserve invariant",
                op_name(o),
                names.join(", ")
            );
        }
        if specific {
            if let Some(J::Number(n)) = t.anomaly.body_offender.as_ref().and_then(|b| b.get("op")) {
                t.anomaly.valid_alternatives = suggest_alternatives(n.as_u64().unwrap_or(0) as u8);
            }
        }
    }
    t.anomaly.enriched = true;
}

// --- the evaluator ----------------------------------------------------------

pub fn eval(a: &mut Arena, rt: &mut Rt, id: u32, tail: bool) -> R<Value> {
    let op = a.op(id);
    // A literal takes no position-path entry (spec §6.2).
    if op == LIT_INT {
        charge_tick(rt)?;
        return Ok(Value::Int(a.get(id).ival.clone().unwrap()));
    }
    if op == LIT_TEXT {
        charge_tick(rt)?;
        return Ok(Value::Text(a.get(id).sval.clone().unwrap()));
    }
    rt.path.push((op, id));
    #[cfg(feature = "prof")]
    crate::prof::mark(op as u32);
    let mut out = eval_node(a, rt, id, tail, op);
    if let Err(Fault::Trap(t)) = &mut out {
        if !t.anomaly.enriched {
            enrich(a, rt, t);
        }
    }
    rt.path.pop();
    #[cfg(feature = "prof")]
    crate::prof::mark(rt.path.last().map(|f| f.0 as u32).unwrap_or(crate::prof::NONE));
    out
}

fn eval_node(a: &mut Arena, rt: &mut Rt, id: u32, tail: bool, op: u8) -> R<Value> {
    // `let` reads the chain flag before anything else (spec §4.3).
    if op == LET {
        return eval_let(a, rt, id, tail);
    }
    charge_tick(rt)?;
    match op {
        REF => {
            let slot = a.kids(id)[0];
            let holder = a.get(slot);
            if holder.op != LIT_INT {
                return Err(domain(
                    "malformed",
                    "REF: name slot must be a literal integer id".to_string(),
                    detail(vec![("operator", J::from("ref")), ("slot", J::from(0))]),
                    "put a literal integer in REF's slot",
                ));
            }
            let name = match &holder.ival {
                Some(Int::S(v)) => *v,
                _ => i64::MIN,
            };
            match rt.env.lookup(name) {
                Some(v) => Ok(v),
                None => Err(unbound(rt, name)),
            }
        }
        IDENTITY => {
            let k = a.kids(id)[0];
            eval(a, rt, k, false)
        }
        MERGE => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let x = as_int(a, &x, "merge")?;
            let y = eval(a, rt, k1, false)?;
            let y = as_int(a, &y, "merge")?;
            Ok(Value::Int(x.add(&y)))
        }
        DEVIATION => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let y = eval(a, rt, k1, false)?;
            if matches!(x, Value::Text(_)) || matches!(y, Value::Text(_)) {
                let xs = as_text(a, &x, "deviation")?;
                let ys = as_text(a, &y, "deviation")?;
                return Ok(Value::Int(Int::from_i64(if *xs == *ys { 0 } else { 1 })));
            }
            let x = as_int(a, &x, "deviation")?;
            let y = as_int(a, &y, "deviation")?;
            Ok(Value::Int(x.sub(&y)))
        }
        THRESHOLD => {
            let k = a.kids(id)[0];
            let x = eval(a, rt, k, false)?;
            let x = as_int(a, &x, "threshold")?;
            Ok(Value::Int(Int::from_i64(
                if x > Int::zero() { 1 } else { 0 },
            )))
        }
        MUL => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let x = as_int(a, &x, "mul")?;
            let y = eval(a, rt, k1, false)?;
            let y = as_int(a, &y, "mul")?;
            // Two `i64`s cannot reach 4096 bits between them, so a
            // product that fits one is past the ceiling check.
            if let (Some(p), Some(q)) = (x.to_i64(), y.to_i64()) {
                if let Some(n) = p.checked_mul(q) {
                    return Ok(Value::Int(Int::from_i64(n)));
                }
            }
            let (ab, bb) = (x.bit_length(), y.bit_length());
            if ab + bb > MAX_INT_BITS {
                return Err(domain(
                    "domain-error",
                    format!(
                        "mul result would exceed MAX_INT_BITS={} ({} + {} bits)",
                        MAX_INT_BITS, ab, bb
                    ),
                    detail(vec![
                        ("operator", J::from("mul")),
                        ("limit", J::from(MAX_INT_BITS)),
                    ]),
                    "multiply smaller numbers",
                ));
            }
            Ok(Value::Int(x.mul(&y)))
        }
        DIV | MOD => {
            let name = if op == DIV { "div" } else { "mod" };
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let x = as_int(a, &x, name)?;
            let y = eval(a, rt, k1, false)?;
            let y = as_int(a, &y, name)?;
            if y.is_zero() {
                return Err(domain(
                    "domain-error",
                    format!("{}: division by zero", name),
                    detail(vec![("operator", J::from(name))]),
                    &format!("guard the divisor with `(if d ({} a d) fallback)`", name),
                ));
            }
            Ok(Value::Int(if op == DIV { x.div_floor(&y) } else { x.mod_floor(&y) }))
        }
        NIL => Ok(Value::Nil),
        CONS => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let element = eval(a, rt, k0, false)?;
            let rest = eval(a, rt, k1, false)?;
            let rest = match &rest {
                Value::Text(s) => {
                    if let Value::Int(i) = &element {
                        if let Some(c) = i.to_i64() {
                            if (0..=0x10FFFF).contains(&c) {
                                if let Some(ch) = char::from_u32(c as u32) {
                                    let mut out = String::with_capacity(s.len() + 4);
                                    out.push(ch);
                                    out.push_str(s);
                                    return Ok(Value::Text(Rc::new(out)));
                                }
                            }
                        }
                    }
                    text_chars(s)
                }
                Value::Nil | Value::Cons(_) => rest.clone(),
                other => as_list(a, other, "cons")?,
            };
            Ok(Value::Cons(Rc::new(ConsCell { head: element, tail: rest })))
        }
        HEAD => {
            let k = a.kids(id)[0];
            let target = eval(a, rt, k, false)?;
            if let Value::Cons(c) = &target {
                return Ok(c.head.clone());
            }
            if let Value::Text(s) = &target {
                if let Some(c) = s.chars().next() {
                    return Ok(Value::Int(Int::from_i64(c as i64)));
                }
            }
            let target = as_list(a, &target, "head")?;
            match target {
                Value::Cons(c) => Ok(c.head.clone()),
                _ => Err(domain(
                    "domain-error",
                    "head: the list is empty; guard with `nil?` before taking a head".to_string(),
                    detail(vec![("operator", J::from("head"))]),
                    "guard with `(if (nil? xs) fallback (head xs))`; reached through `nth` or \
`last`, the index is past the end",
                )),
            }
        }
        TAIL => {
            let k = a.kids(id)[0];
            let target = eval(a, rt, k, false)?;
            if let Value::Cons(c) = &target {
                return Ok(c.tail.clone());
            }
            if let Value::Text(s) = &target {
                if !s.is_empty() {
                    let rest: String = s.chars().skip(1).collect();
                    return Ok(Value::Text(Rc::new(rest)));
                }
            }
            let target = as_list(a, &target, "tail")?;
            match target {
                Value::Cons(c) => Ok(c.tail.clone()),
                _ => Err(domain(
                    "domain-error",
                    "tail: the list is empty; guard with `nil?` before taking a tail".to_string(),
                    detail(vec![("operator", J::from("tail"))]),
                    "guard with `(if (nil? xs) fallback (tail xs))`",
                )),
            }
        }
        IS_NIL => {
            let k = a.kids(id)[0];
            let target = eval(a, rt, k, false)?;
            match &target {
                Value::Nil => Ok(Value::Int(Int::from_i64(1))),
                Value::Cons(_) => Ok(Value::Int(Int::zero())),
                Value::Text(s) => Ok(Value::Int(Int::from_i64(if s.is_empty() { 1 } else { 0 }))),
                other => {
                    as_list(a, other, "nil?")?;
                    Ok(Value::Int(Int::zero()))
                }
            }
        }
        MAP_PUT => {
            let (k0, k1, k2) = (a.kids(id)[0], a.kids(id)[1], a.kids(id)[2]);
            let base = eval(a, rt, k0, false)?;
            let base = as_map(a, &base, "map-put")?;
            let key = eval(a, rt, k1, false)?;
            let value = eval(a, rt, k2, false)?;
            let hashed = map_key(a, &key, "map-put")?;
            Ok(Value::Map(base.put(hashed, key, value)))
        }
        MAP_GET => {
            let (k0, k1, k2) = (a.kids(id)[0], a.kids(id)[1], a.kids(id)[2]);
            let m = eval(a, rt, k0, false)?;
            let m = as_map(a, &m, "map-get")?;
            let key = eval(a, rt, k1, false)?;
            let hashed = map_key(a, &key, "map-get")?;
            match m.get(&hashed) {
                Some(e) => Ok(e.val),
                None => eval(a, rt, k2, false),
            }
        }
        SEQ => {
            let n = a.kids(id).len();
            let mut last = Value::Int(Int::zero());
            for i in 0..n {
                let k = a.kids(id)[i];
                last = eval(a, rt, k, tail && i + 1 == n)?;
            }
            Ok(last)
        }
        IF_SURPRISE => {
            let (k0, k1, k2) = (a.kids(id)[0], a.kids(id)[1], a.kids(id)[2]);
            let s = eval(a, rt, k0, false)?;
            let s = as_int(a, &s, "if-surprise")?;
            if !s.is_zero() {
                eval(a, rt, k1, tail)
            } else {
                eval(a, rt, k2, tail)
            }
        }
        LAMBDA => {
            let slot = a.kids(id)[0];
            if a.op(slot) != LIT_INT {
                return Err(domain(
                    "malformed",
                    "LAMBDA: param slot must be a literal integer id".to_string(),
                    detail(vec![("operator", J::from("lambda")), ("slot", J::from(0))]),
                    "put a literal integer in LAMBDA's first slot",
                ));
            }
            let param = a.get(slot).ival.as_ref().unwrap().to_i64().unwrap_or(i64::MIN);
            let body = a.kids(id)[1];
            Ok(Value::Closure(Rc::new(ClosureData {
                param,
                body,
                env: rt.env.clone(),
                caps: rt.caps,
                enclosed: rt.enclosed,
                name: std::cell::Cell::new(None),
                calls: std::cell::Cell::new(0),
                own: std::cell::Cell::new(0),
                owner: std::cell::Cell::new(rt.current),
                vm: None,
            })))
        }
        APPLY => {
            let n = a.kids(id).len();
            if n == 0 {
                return Err(domain(
                    "malformed",
                    "APPLY: missing function in head slot".to_string(),
                    detail(vec![("operator", J::from("apply"))]),
                    "give `apply` a function to call",
                ));
            }
            let head = a.kids(id)[0];
            let mut fnv = eval(a, rt, head, false)?;
            if tail && n > 1 {
                for i in 1..n - 1 {
                    let k = a.kids(id)[i];
                    let arg = eval(a, rt, k, false)?;
                    fnv = call(a, rt, fnv, arg)?;
                }
                if !matches!(fnv, Value::Closure(_) | Value::Loop(_)) {
                    return Err(not_callable(a, &fnv));
                }
                let k = a.kids(id)[n - 1];
                let last = eval(a, rt, k, false)?;
                return Ok(Value::Tail(Rc::new((fnv, last))));
            }
            for i in 1..n {
                let k = a.kids(id)[i];
                let arg = eval(a, rt, k, false)?;
                fnv = call(a, rt, fnv, arg)?;
            }
            Ok(fnv)
        }
        LOOP_UNTIL => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let pred = eval(a, rt, k0, false)?;
            let step = eval(a, rt, k1, false)?;
            let ok = |v: &Value| matches!(v, Value::Closure(_) | Value::Loop(_));
            if !ok(&pred) || !ok(&step) {
                return Err(domain(
                    "type-violation",
                    format!(
                        "LOOP_UNTIL: both slots must be functions (type Fn); got pred={}, step={}",
                        value_repr(a, &pred),
                        value_repr(a, &step)
                    ),
                    detail(vec![
                        ("operator", J::from("loop-until")),
                        ("expected", J::from("Fn")),
                    ]),
                    "pass two lambdas: a predicate and a step",
                ));
            }
            Ok(Value::Loop(Rc::new(LoopFn { pred, step })))
        }
        _ => eval_generic(a, rt, id, op),
    }
}

fn eval_let(a: &mut Arena, rt: &mut Rt, id: u32, tail: bool) -> R<Value> {
    let chained = rt.let_chain == Some((id, tail));
    let kids = a.kids(id);
    let (slot, value_node, body_node) = (kids[0], kids[1], kids[2]);
    let holder = a.get(slot);
    if holder.op != LIT_INT {
        charge_tick(rt)?;
        return Err(domain(
            "malformed",
            "LET: name slot must be a literal integer id".to_string(),
            detail(vec![("operator", J::from("let")), ("slot", J::from(0))]),
            "put a literal integer in LET's first slot",
        ));
    }
    let name = match &holder.ival {
        Some(Int::S(v)) => *v,
        _ => i64::MIN,
    };
    charge_tick(rt)?;
    let saved_env = rt.env.clone();
    let extend = chained && !saved_env.root && !saved_env.bound(name);
    if !extend {
        let fresh = open_frame(rt, &saved_env);
        rt.env = fresh;
    }
    // The frame the binding goes in is `rt.env`: the value's own
    // evaluation puts back what it borrowed, so this is the frame
    // opened (or extended) just above, and it need not be held twice.
    let result = (|| -> R<Value> {
        let value = eval(a, rt, value_node, false)?;
        if let Value::Closure(c) = &value {
            if c.name.get().is_none() {
                c.name.set(Some(name));
                rt.named.push(c.clone());
            }
        }
        rt.env.vars.borrow_mut().insert(name, value);
        rt.let_chain = Some((body_node, tail));
        eval(a, rt, body_node, tail)
    })();
    rt.let_chain = None;
    if !extend {
        let spent = std::mem::replace(&mut rt.env, saved_env);
        recycle_frame(rt, spent);
    }
    result
}

#[inline(never)]
fn eval_generic(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    match op {
        PARTITION => {
            let k = a.kids(id)[0];
            let n = eval(a, rt, k, false)?;
            let n = as_int(a, &n, "partition")?;
            Ok(Value::Int(n.div_floor(&Int::from_i64(2))))
        }
        P | TAU | SIGMA | MOBIUS => {
            let k = a.kids(id)[0];
            let ctx = op_name(op);
            let n = eval(a, rt, k, false)?;
            let n = as_int(a, &n, ctx)?;
            nt::number_theory(op, &n)
        }
        GCD => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let x = as_int(a, &x, "gcd")?;
            let y = eval(a, rt, k1, false)?;
            let y = as_int(a, &y, "gcd")?;
            Ok(Value::Int(x.gcd(&y)))
        }
        BUDGET => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let limit = eval(a, rt, k0, false)?;
            let limit = as_int(a, &limit, "budget")?;
            rt.budget_stack.push(Budget { limit, spent: 0 });
            let out = eval(a, rt, k1, false);
            rt.budget_stack.pop();
            out
        }
        CONSERVE => crate::conserve::op_conserve(a, rt, id),
        SIGNAL => {
            let k = a.kids(id)[0];
            let code = eval(a, rt, k, false)?;
            let code = as_int(a, &code, "signal")?;
            let small = code.to_i64().unwrap_or(i64::MAX);
            if small < FIRST_PROGRAM_SIGNAL {
                return Err(domain(
                    "domain-error",
                    format!(
                        "signal: codes below {} are the substrate's own kinds",
                        FIRST_PROGRAM_SIGNAL
                    ),
                    detail(vec![
                        ("operator", J::from("signal")),
                        ("code", code.to_json()),
                        ("first_allowed", J::from(FIRST_PROGRAM_SIGNAL)),
                    ]),
                    &format!("signal with a code of {} or more", FIRST_PROGRAM_SIGNAL),
                ));
            }
            Err(domain(
                "signalled",
                format!("signal {}", code),
                detail(vec![
                    ("operator", J::from("signal")),
                    ("code", code.to_json()),
                ]),
                "catch it with `when-anomaly` and branch on the code",
            ))
        }
        MAP_PAIRS => {
            let k = a.kids(id)[0];
            let m = eval(a, rt, k, false)?;
            let m = as_map(a, &m, "map-pairs")?;
            Ok(list_from(
                m.pairs()
                    .into_iter()
                    .map(|e| list_from(vec![e.key, e.val]))
                    .collect(),
            ))
        }
        VIOLATE => {
            let k = a.kids(id)[0];
            let x = eval(a, rt, k, false)?;
            let x = as_int(a, &x, "violate")?;
            Ok(Value::Int(x.add(&Int::from_i64(1))))
        }
        SURPRISE => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let p = eval(a, rt, k0, false)?;
            let p = as_int(a, &p, "surprise")?;
            let q = eval(a, rt, k1, false)?;
            let q = as_int(a, &q, "surprise")?;
            Ok(Value::Int(rt.emit(&p, &q)))
        }
        TRACE_SURPRISE => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let v = as_int(a, &v, "trace-surprise")?;
            rt.emit(&Int::zero(), &v);
            Ok(Value::Int(v))
        }
        WHEN_ANOMALY => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            match eval(a, rt, k0, false) {
                Ok(v) => Ok(v),
                Err(Fault::NotImplemented(m)) => Err(Fault::NotImplemented(m)),
                Err(Fault::Trap(t)) => {
                    if t.class == Class::Step {
                        return Err(Fault::Trap(t));
                    }
                    let code = anomaly_code(&t.anomaly);
                    // A handled fault is still observed (spec 5.4).
                    rt.emit(&Int::zero(), &Int::from_i64(code));
                    let handler = eval(a, rt, k1, false)?;
                    call(a, rt, handler, Value::Int(Int::from_i64(code)))
                }
            }
        }
        EVAL => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let p = as_program(a, &v, "eval")?;
            eval(a, rt, p, false)
        }
        QUOTE => {
            let k = a.kids(id)[0];
            Ok(Value::Program(a.deep_copy(k)))
        }
        STDOUT => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let t = as_text(a, &v, "stdout")?;
            rt.output.push_str(&t);
            Ok(Value::Int(Int::from_usize(t.chars().count())))
        }
        STDIN => match rt.read_line() {
            Some(line) => Ok(Value::Text(Rc::new(line))),
            None => Ok(Value::Nil),
        },
        EXTERNAL_BOUNDARY => {
            let slot = a.kids(id)[0];
            if a.op(slot) != LIT_INT {
                return Err(domain(
                    "malformed",
                    "external-boundary: capability slot must be a literal".to_string(),
                    detail(vec![
                        ("operator", J::from("external-boundary")),
                        ("slot", J::from(0)),
                    ]),
                    "put a literal capability mask in the first slot",
                ));
            }
            let declared =
                a.get(slot).ival.as_ref().unwrap().to_i64().unwrap_or(0) as u32;
            let excess = declared & !rt.caps;
            if rt.enclosed && excess != 0 {
                return Err(domain(
                    "capability-denied",
                    format!(
                        "external-boundary: nested boundary declares {} beyond the enclosing {}",
                        py_name_list(&capability_names(excess)),
                        py_name_list(&capability_names(rt.caps))
                    ),
                    detail(vec![
                        ("operator", J::from("external-boundary")),
                        ("declared", J::from(capability_names(declared))),
                        ("enclosing", J::from(capability_names(rt.caps))),
                        ("excess", J::from(capability_names(excess))),
                    ]),
                    "a nested boundary may only narrow; declare it in the enclosing one",
                ));
            }
            let missing = declared & !rt.granted;
            if missing != 0 {
                let granted = capability_names(rt.granted);
                let shown = if granted.is_empty() {
                    "nothing".to_string()
                } else {
                    py_name_list(&granted)
                };
                return Err(domain(
                    "capability-denied",
                    format!(
                        "external-boundary: declares {} but the host granted {}",
                        py_name_list(&capability_names(declared)),
                        shown
                    ),
                    detail(vec![
                        ("operator", J::from("external-boundary")),
                        ("declared", J::from(capability_names(declared))),
                        ("granted", J::from(capability_names(rt.granted))),
                        ("missing", J::from(capability_names(missing))),
                    ]),
                    &format!(
                        "run with `--allow {}`, or declare less",
                        capability_names(missing).join(",")
                    ),
                ));
            }
            let (saved_caps, saved_enclosed) = (rt.caps, rt.enclosed);
            rt.caps = declared;
            rt.enclosed = true;
            let body = a.kids(id)[1];
            let out = eval(a, rt, body, false);
            rt.caps = saved_caps;
            rt.enclosed = saved_enclosed;
            out
        }
        FS_READ => {
            require_capability(rt, CAP_FS_READ, "fs-read")?;
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let path = as_text(a, &v, "fs-read")?;
            match std::fs::read(path.as_str()) {
                Ok(raw) => match String::from_utf8(raw) {
                    Ok(text) => Ok(Value::Text(Rc::new(text))),
                    Err(_) => Err(fs_fault("fs-read", path.as_str(), "UnicodeDecodeError")),
                },
                Err(e) => Err(fs_fault("fs-read", path.as_str(), os_error_name(&e))),
            }
        }
        FS_WRITE => {
            require_capability(rt, CAP_FS_WRITE, "fs-write")?;
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let path = as_text(a, &v, "fs-write")?;
            let v = eval(a, rt, k1, false)?;
            let text = as_text(a, &v, "fs-write")?;
            // `newline=""` on the Python side: the text goes out as it is.
            match std::fs::write(path.as_str(), text.as_bytes()) {
                Ok(()) => Ok(Value::Int(Int::from_usize(text.chars().count()))),
                Err(e) => Err(fs_fault("fs-write", path.as_str(), os_error_name(&e))),
            }
        }
        CLOCK => {
            require_capability(rt, CAP_CLOCK, "clock")?;
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as i64)
                .unwrap_or(0);
            Ok(Value::Int(Int::from_i64(now)))
        }
        LINEAGE_QUERY | WHY | TRACE | HASH | UID | ANCESTOR_OF | GENERATION => {
            meta::eval_meta(a, rt, id, op)
        }
        DEFPOP | VARIANT | EVOLVE | SELECT | MUTATE | CLONE | FITNESS | RETIRE => {
            evolve::eval_evolution(a, rt, id, op)
        }
        END => Err(Fault::NotImplemented(
            "operator end (family struct) not implemented in Milestone 1 runtime".into(),
        )),
        _ if (0x40..=0x4F).contains(&op) => eval_text_node(a, rt, id, op),
        _ if (0x50..=0x57).contains(&op) => eval_list(a, rt, id, op),
        _ => Err(Fault::NotImplemented(
            format!("operator {} is outside this runtime's phase-2 scope", op_name(op)).into(),
        )),
    }
}

/// The text family's operands, evaluated left to right with the
/// coercions the reference performs between them (`vm::ops`), then the
/// work -- which both evaluators share.
fn eval_text_node(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    let kids = a.kids(id).to_vec();
    let mut args: Vec<Value> = Vec::with_capacity(kids.len());
    for (i, k) in kids.iter().enumerate() {
        let v = eval(a, rt, *k, false)?;
        args.push(match crate::vm::ops::coerce_after(op, i) {
            Some(ck) => crate::vm::ops::coerce(a, v, ck, op)?,
            None => v,
        });
    }
    text::work_text(a, rt, op, &args)
}

// --- the list family (spec §5.10) -------------------------------------------

fn eval_list(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    match op {
        LIST_MAP | LIST_FILTER | LIST_ANY => {
            let ctx = op_name(op);
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let f = eval(a, rt, k0, false)?;
            let f = as_fn(a, &f, ctx)?;
            let xs = eval(a, rt, k1, false)?;
            let xs = as_vec(a, &xs, ctx)?;
            let mut out = Vec::new();
            for x in xs {
                tick(rt, 1)?;
                let got = call(a, rt, f.clone(), x.clone())?;
                match op {
                    LIST_MAP => out.push(got),
                    LIST_FILTER => {
                        if !as_int(a, &got, ctx)?.is_zero() {
                            out.push(x);
                        }
                    }
                    _ => {
                        if !as_int(a, &got, ctx)?.is_zero() {
                            return Ok(Value::Int(Int::from_i64(1)));
                        }
                    }
                }
            }
            if op == LIST_ANY {
                Ok(Value::Int(Int::zero()))
            } else {
                Ok(list_from(out))
            }
        }
        LIST_FOLD => {
            let (k0, k1, k2) = (a.kids(id)[0], a.kids(id)[1], a.kids(id)[2]);
            let f = eval(a, rt, k0, false)?;
            let f = as_fn(a, &f, "fold")?;
            let mut acc = eval(a, rt, k1, false)?;
            let xs = eval(a, rt, k2, false)?;
            let xs = as_vec(a, &xs, "fold")?;
            for x in xs {
                tick(rt, 1)?;
                let step = call(a, rt, f.clone(), acc)?;
                acc = call(a, rt, step, x)?;
            }
            Ok(acc)
        }
        LIST_REVERSE => {
            let k = a.kids(id)[0];
            let xs = eval(a, rt, k, false)?;
            let mut xs = as_vec(a, &xs, "reverse")?;
            tick(rt, xs.len() as u64)?;
            xs.reverse();
            Ok(list_from(xs))
        }
        LIST_RANGE => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let x = as_int(a, &x, "range")?;
            let y = eval(a, rt, k1, false)?;
            let y = as_int(a, &y, "range")?;
            let span = y.sub(&x);
            let n: u64 = if span > Int::zero() {
                match span.to_i64() {
                    Some(v) => v as u64,
                    None => u64::MAX,
                }
            } else {
                0
            };
            tick(rt, n)?;
            let start = x.to_i64().unwrap_or(0);
            let mut out = Vec::with_capacity(n as usize);
            for i in 0..n {
                out.push(Value::Int(Int::from_i64(start + i as i64)));
            }
            Ok(list_from(out))
        }
        LIST_SORT_BY => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let less = eval(a, rt, k0, false)?;
            let less = as_fn(a, &less, "sort-by")?;
            let xs = eval(a, rt, k1, false)?;
            let xs = as_vec(a, &xs, "sort-by")?;
            Ok(list_from(merge_sort(a, rt, xs, &less)?))
        }
        LIST_ZIP => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let xs = eval(a, rt, k0, false)?;
            let xs = as_vec(a, &xs, "zip")?;
            let ys = eval(a, rt, k1, false)?;
            let ys = as_vec(a, &ys, "zip")?;
            let n = xs.len().min(ys.len());
            tick(rt, n as u64)?;
            let out: Vec<Value> = (0..n)
                .map(|i| list_from(vec![xs[i].clone(), ys[i].clone()]))
                .collect();
            Ok(list_from(out))
        }
        _ => unreachable!(),
    }
}

/// D1: the specified merge sort.  The comparator call order is the
/// language's, not the host sort's.
pub fn merge_sort(a: &mut Arena, rt: &mut Rt, xs: Vec<Value>, less: &Value) -> R<Vec<Value>> {
    if xs.len() <= 1 {
        return Ok(xs);
    }
    let mid = xs.len() / 2;
    let right_src = xs[mid..].to_vec();
    let left_src = xs[..mid].to_vec();
    let left = merge_sort(a, rt, left_src, less)?;
    let right = merge_sort(a, rt, right_src, less)?;
    let mut out = Vec::with_capacity(left.len() + right.len());
    let (mut i, mut j) = (0usize, 0usize);
    while i < left.len() && j < right.len() {
        if before(a, rt, less, &right[j], &left[i])? {
            out.push(right[j].clone());
            j += 1;
        } else {
            out.push(left[i].clone());
            i += 1;
        }
    }
    out.extend_from_slice(&left[i..]);
    out.extend_from_slice(&right[j..]);
    Ok(out)
}

fn before(a: &mut Arena, rt: &mut Rt, less: &Value, x: &Value, y: &Value) -> R<bool> {
    tick(rt, 1)?;
    let step = call(a, rt, less.clone(), x.clone())?;
    let ab = call(a, rt, step, y.clone())?;
    let ab = !as_int(a, &ab, "sort-by")?.is_zero();
    let step = call(a, rt, less.clone(), y.clone())?;
    let ba = call(a, rt, step, x.clone())?;
    let ba = !as_int(a, &ba, "sort-by")?.is_zero();
    Ok(ab && !ba)
}

// --- calls (spec §4.1) ------------------------------------------------------

pub fn call(a: &mut Arena, rt: &mut Rt, mut fnv: Value, mut arg: Value) -> R<Value> {
    loop {
        if let Value::Loop(lf) = &fnv {
            let lf = lf.clone();
            let mut value = arg;
            loop {
                rt.steps += 1;
                if rt.steps > rt.max_steps {
                    return Err(step_trap(rt.steps, rt.max_steps));
                }
                let verdict = call(a, rt, lf.pred.clone(), value.clone())?;
                let verdict = as_int(a, &verdict, "loop-until predicate")?;
                if !verdict.is_zero() {
                    return Ok(value);
                }
                value = call(a, rt, lf.step.clone(), value)?;
            }
        }
        let cl = match fnv {
            Value::Closure(c) => c,
            other => return Err(not_callable(a, &other)),
        };

        // Who the steps belong to (Exp 20).  The reference compares two
        // closures by identity, so the addresses decide it and nothing
        // is cloned unless the function in flight actually changes.
        let named = cl.name.get().is_some();
        if named {
            cl.calls.set(cl.calls.get() + 1);
        }
        let me_at: *const ClosureData =
            if named { Rc::as_ptr(&cl) } else { cl.owner.get() };
        let now_at: *const ClosureData = rt.current;
        let changed = me_at != now_at;
        let mut outer: *const ClosureData = std::ptr::null();
        if changed {
            let s = rt.steps;
            outer = std::mem::replace(&mut rt.current, me_at);
            if !outer.is_null() {
                // Safety: `named` holds it, and this runtime outlives
                // the call.
                let o = unsafe { &*outer };
                o.own.set(o.own.get() + (s - rt.mark));
            }
            rt.mark = s;
        }

        rt.call_depth += 1;
        if rt.call_depth > rt.max_call_depth {
            let depth = rt.call_depth;
            rt.call_depth -= 1;
            // The reference leaves the function in flight as it is on
            // this path, and `hot` in the trap reads it.
            return Err(depth_trap(depth, rt.max_call_depth));
        }

        #[cfg(feature = "prof")]
        crate::prof::mark(crate::prof::R_CALL);
        let saved_caps = rt.caps;
        let saved_enclosed = rt.enclosed;
        rt.caps = cl.caps;
        rt.enclosed = cl.enclosed;

        // The frame is the evaluator's: a `Scope` the tree-walker looks
        // up by name, or a slotted VM frame.
        let result = if cl.vm.is_some() {
            crate::vm::exec::enter_closure(a, rt, &cl, arg)
        } else {
            let scope = open_frame(rt, &cl.env);
            scope.vars.borrow_mut().insert(cl.param, arg);
            let saved_env = std::mem::replace(&mut rt.env, scope);
            let out = eval(a, rt, cl.body, true);
            let spent = std::mem::replace(&mut rt.env, saved_env);
            recycle_frame(rt, spent);
            out
        };
        #[cfg(feature = "prof")]
        crate::prof::mark(crate::prof::R_CALL);

        rt.caps = saved_caps;
        rt.enclosed = saved_enclosed;
        rt.call_depth -= 1;
        if changed {
            let s = rt.steps;
            if !rt.current.is_null() {
                let m = unsafe { &*rt.current };
                m.own.set(m.own.get() + (s - rt.mark));
            }
            rt.mark = s;
            rt.current = outer;
        }

        match result? {
            // The VM's marker: the pair is on the runtime, so a tail
            // call costs no allocation at all.
            Value::Unset => match rt.vm.tail.take() {
                Some((f, next)) => {
                    fnv = f;
                    arg = next;
                }
                None => {
                    // The marker is made by `TailApply` and taken
                    // here; an unwritten slot can never be a value.
                    debug_assert!(false, "an unwritten slot escaped a unit as its value");
                    return Ok(Value::Unset);
                }
            },
            // The tree-walker's marker is made fresh by `apply` and
            // nothing else holds it, so its two values move out rather
            // than clone.
            Value::Tail(t) => match Rc::try_unwrap(t) {
                Ok((f, next)) => {
                    fnv = f;
                    arg = next;
                }
                Err(shared) => {
                    fnv = shared.0.clone();
                    arg = shared.1.clone();
                }
            },
            other => return Ok(other),
        }
    }
}

/// A call frame, from the pool when one is free (Q124).
///
/// A frame is one allocation and a program makes millions of them, and
/// most are dead the moment the call returns -- nothing closed over
/// them.  Those come back here instead of to the allocator.  A frame a
/// closure captured is not recycled: `strong_count` says so.
#[inline]
fn open_frame(rt: &mut Rt, parent: &Rc<Scope>) -> Rc<Scope> {
    while let Some(mut free) = rt.scope_pool.pop() {
        if let Some(frame) = Rc::get_mut(&mut free) {
            frame.parent = Some(parent.clone());
            return free;
        }
    }
    Scope::open(parent)
}

#[inline]
fn recycle_frame(rt: &mut Rt, mut frame: Rc<Scope>) {
    if rt.scope_pool.len() < SCOPE_POOL && Rc::strong_count(&frame) == 1 {
        if let Some(f) = Rc::get_mut(&mut frame) {
            // emptied now, not on the way out: a pooled frame must not
            // keep a world alive.
            f.parent = None;
            f.vars.get_mut().clear();
            rt.scope_pool.push(frame);
        }
    }
}

const SCOPE_POOL: usize = 1024;
