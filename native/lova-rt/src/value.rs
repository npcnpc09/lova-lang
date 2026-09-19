//! The value model (spec §2) and how values print (`core.cli.format_value`).

use crate::int::Int;
use crate::tokens::{pretty, Arena};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::rc::Rc;

#[derive(Clone)]
pub enum Value {
    Int(Int),
    Text(Rc<String>),
    Nil,
    Cons(Rc<ConsCell>),
    Map(MapValue),
    Closure(Rc<ClosureData>),
    Loop(Rc<LoopFn>),
    Program(u32),
    /// A call in tail position, handed back to `call` (spec §4.4).
    /// Never escapes a call frame.
    Tail(Rc<(Value, Value)>),
}

pub struct ConsCell {
    pub head: Value,
    pub tail: Value,
}

// A list of a hundred thousand cells is dropped by unlinking it, not by
// recursing down it.
impl Drop for ConsCell {
    fn drop(&mut self) {
        let mut cur = std::mem::replace(&mut self.tail, Value::Nil);
        loop {
            match cur {
                Value::Cons(rc) => match Rc::try_unwrap(rc) {
                    Ok(mut cell) => {
                        cur = std::mem::replace(&mut cell.tail, Value::Nil);
                    }
                    Err(_) => break,
                },
                _ => break,
            }
        }
    }
}

pub struct ClosureData {
    pub param: i64,
    pub body: u32,
    pub env: Rc<Scope>,
    pub caps: u32,
    pub enclosed: bool,
    pub name: Cell<Option<i64>>,
    pub calls: Cell<u64>,
    pub own: Cell<u64>,
    pub owner: RefCell<Option<Rc<ClosureData>>>,
}

pub struct LoopFn {
    pub pred: Value,
    pub step: Value,
}

// --- environment (spec §4.2) ------------------------------------------------

pub struct Scope {
    pub vars: RefCell<HashMap<i64, Value>>,
    pub parent: Option<Rc<Scope>>,
    /// The root environment is a plain dict in the reference, not a
    /// `Scope`; the `let` chain rule tests exactly that (spec §4.3).
    pub root: bool,
}

impl Scope {
    pub fn root() -> Rc<Scope> {
        Rc::new(Scope { vars: RefCell::new(HashMap::new()), parent: None, root: true })
    }

    pub fn open(parent: &Rc<Scope>) -> Rc<Scope> {
        Rc::new(Scope {
            vars: RefCell::new(HashMap::new()),
            parent: Some(parent.clone()),
            root: false,
        })
    }

    pub fn lookup(&self, key: i64) -> Option<Value> {
        if let Some(v) = self.vars.borrow().get(&key) {
            return Some(v.clone());
        }
        let mut env = self.parent.as_ref();
        while let Some(s) = env {
            if let Some(v) = s.vars.borrow().get(&key) {
                return Some(v.clone());
            }
            env = s.parent.as_ref();
        }
        None
    }

    /// `Scope.bound`: this frame or any it extends.
    pub fn bound(&self, key: i64) -> bool {
        if self.vars.borrow().contains_key(&key) {
            return true;
        }
        let mut env = self.parent.as_ref();
        while let Some(s) = env {
            if s.vars.borrow().contains_key(&key) {
                return true;
            }
            env = s.parent.as_ref();
        }
        false
    }

    pub fn set(&self, key: i64, value: Value) {
        self.vars.borrow_mut().insert(key, value);
    }

    /// `flatten_env`: every visible binding, inner frames winning.
    pub fn flatten(self: &Rc<Scope>) -> HashMap<i64, Value> {
        let mut frames: Vec<&Rc<Scope>> = Vec::new();
        let mut env = Some(self);
        while let Some(s) = env {
            frames.push(s);
            env = s.parent.as_ref();
        }
        let mut out = HashMap::new();
        for frame in frames.iter().rev() {
            for (k, v) in frame.vars.borrow().iter() {
                out.insert(*k, v.clone());
            }
        }
        out
    }
}

// --- map keys (spec §2.7) ---------------------------------------------------

#[derive(Clone, PartialEq, Eq, Hash)]
pub enum MapKey {
    I(Int),
    L(Vec<MapKey>),
}

// --- the persistent map (spec §2.8) -----------------------------------------

#[derive(Clone)]
pub struct Entry {
    pub key: Value,
    pub val: Value,
}

/// Insertion-ordered, with removal: `map-pairs` is the order keys were
/// first inserted, and rerooting removes and re-appends.
#[derive(Default)]
pub struct OrderedMap {
    slots: Vec<Option<(MapKey, Entry)>>,
    index: HashMap<MapKey, usize>,
    live: usize,
}

impl OrderedMap {
    pub fn len(&self) -> usize {
        self.live
    }

    pub fn get(&self, key: &MapKey) -> Option<&Entry> {
        self.index.get(key).and_then(|i| self.slots[*i].as_ref()).map(|(_, e)| e)
    }

    pub fn insert(&mut self, key: MapKey, entry: Entry) -> Option<Entry> {
        if let Some(&i) = self.index.get(&key) {
            let previous = self.slots[i].take().map(|(_, e)| e);
            self.slots[i] = Some((key, entry));
            previous
        } else {
            self.index.insert(key.clone(), self.slots.len());
            self.slots.push(Some((key, entry)));
            self.live += 1;
            None
        }
    }

    pub fn remove(&mut self, key: &MapKey) -> Option<Entry> {
        match self.index.remove(key) {
            Some(i) => {
                self.live -= 1;
                let gone = self.slots[i].take().map(|(_, e)| e);
                if self.slots.len() > 64 && self.slots.len() > self.live * 2 {
                    self.compact();
                }
                gone
            }
            None => None,
        }
    }

    fn compact(&mut self) {
        let old = std::mem::take(&mut self.slots);
        self.index.clear();
        for slot in old.into_iter().flatten() {
            self.index.insert(slot.0.clone(), self.slots.len());
            self.slots.push(Some(slot));
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = &Entry> {
        self.slots.iter().filter_map(|s| s.as_ref()).map(|(_, e)| e)
    }
}

pub enum MapNode {
    Owner(OrderedMap),
    Diff { key: MapKey, wanted: Option<Entry>, next: MapValue },
}

#[derive(Clone)]
pub struct MapValue(pub Rc<RefCell<MapNode>>);

impl MapValue {
    pub fn empty() -> MapValue {
        MapValue(Rc::new(RefCell::new(MapNode::Owner(OrderedMap::default()))))
    }

    fn is_owner(&self) -> bool {
        matches!(&*self.0.borrow(), MapNode::Owner(_))
    }

    /// Baker rerooting: make this version the one holding the map.
    fn reroot(&self) {
        if self.is_owner() {
            return;
        }
        let mut path: Vec<MapValue> = Vec::new();
        let mut version = self.clone();
        loop {
            let next = match &*version.0.borrow() {
                MapNode::Owner(_) => None,
                MapNode::Diff { next, .. } => Some(next.clone()),
            };
            match next {
                Some(n) => {
                    path.push(version.clone());
                    version = n;
                }
                None => break,
            }
        }
        let mut entries = match &mut *version.0.borrow_mut() {
            MapNode::Owner(m) => std::mem::take(m),
            _ => unreachable!(),
        };
        let mut owner = version;
        for step in path.iter().rev() {
            let (key, wanted) = match &*step.0.borrow() {
                MapNode::Diff { key, wanted, .. } => (key.clone(), wanted.clone()),
                MapNode::Owner(_) => unreachable!(),
            };
            let current = match &wanted {
                None => entries.remove(&key),
                Some(e) => entries.insert(key.clone(), e.clone()),
            };
            *owner.0.borrow_mut() =
                MapNode::Diff { key, wanted: current, next: step.clone() };
            owner = step.clone();
        }
        *owner.0.borrow_mut() = MapNode::Owner(entries);
    }

    pub fn get(&self, key: &MapKey) -> Option<Entry> {
        self.reroot();
        match &*self.0.borrow() {
            MapNode::Owner(m) => m.get(key).cloned(),
            _ => unreachable!(),
        }
    }

    pub fn len(&self) -> usize {
        self.reroot();
        match &*self.0.borrow() {
            MapNode::Owner(m) => m.len(),
            _ => unreachable!(),
        }
    }

    pub fn pairs(&self) -> Vec<Entry> {
        self.reroot();
        match &*self.0.borrow() {
            MapNode::Owner(m) => m.iter().cloned().collect(),
            _ => unreachable!(),
        }
    }

    pub fn put(&self, key: MapKey, k: Value, v: Value) -> MapValue {
        self.reroot();
        let mut entries = match &mut *self.0.borrow_mut() {
            MapNode::Owner(m) => std::mem::take(m),
            _ => unreachable!(),
        };
        let previous = entries.insert(key.clone(), Entry { key: k, val: v });
        let successor = MapValue(Rc::new(RefCell::new(MapNode::Owner(entries))));
        *self.0.borrow_mut() =
            MapNode::Diff { key, wanted: previous, next: successor.clone() };
        successor
    }

    /// Only for `_as_map` building a fresh map from a list of pairs.
    pub fn insert_owned(&self, key: MapKey, k: Value, v: Value) {
        match &mut *self.0.borrow_mut() {
            MapNode::Owner(m) => {
                m.insert(key, Entry { key: k, val: v });
            }
            _ => unreachable!(),
        }
    }
}

// --- list helpers -----------------------------------------------------------

pub fn list_from(values: Vec<Value>) -> Value {
    let mut out = Value::Nil;
    for v in values.into_iter().rev() {
        out = Value::Cons(Rc::new(ConsCell { head: v, tail: out }));
    }
    out
}

pub fn text_chars(s: &str) -> Value {
    list_from(s.chars().map(|c| Value::Int(Int::from_i64(c as i64))).collect())
}

// --- printing ---------------------------------------------------------------

/// `core.surface.quote_text`.
pub fn quote_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Python `repr` of a `str`, near enough for a message a human reads.
pub fn py_repr_str(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') { '"' } else { '\'' };
    let mut out = String::new();
    out.push(quote);
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

pub fn value_repr(a: &Arena, v: &Value) -> String {
    match v {
        Value::Int(i) => i.to_string(),
        Value::Text(s) => py_repr_str(s),
        Value::Nil => "()".to_string(),
        Value::Cons(_) => {
            let items = list_walk(v);
            let parts: Vec<String> = items.iter().map(|i| value_repr(a, i)).collect();
            format!("({})", parts.join(" "))
        }
        Value::Map(m) => {
            let parts: Vec<String> = m
                .pairs()
                .iter()
                .map(|e| format!("{}: {}", value_repr(a, &e.key), value_repr(a, &e.val)))
                .collect();
            format!("MapValue({{{}}})", parts.join(", "))
        }
        Value::Closure(c) => match c.name.get() {
            Some(n) => format!("<closure param={} name={}>", c.param, n),
            None => format!("<closure param={}>", c.param),
        },
        Value::Loop(_) => "<loop-until>".to_string(),
        Value::Program(id) => format!("Node(op={}, {})", a.op(*id), pretty(a, *id)),
        Value::Tail(_) => "<tail-call>".to_string(),
    }
}

pub fn format_repr(a: &Arena, v: &Value) -> String {
    let text = value_repr(a, v);
    if text.chars().count() <= 40 {
        text
    } else {
        let head: String = text.chars().take(37).collect();
        format!("{}...", head)
    }
}

/// Walk a cons chain into a Vec.  A text is its codepoints.  The caller
/// has already made sure the value is a list (or a text).
pub fn list_walk(v: &Value) -> Vec<Value> {
    match v {
        Value::Text(s) => s.chars().map(|c| Value::Int(Int::from_i64(c as i64))).collect(),
        _ => {
            let mut out = Vec::new();
            let mut rest = v.clone();
            while let Value::Cons(cell) = rest {
                out.push(cell.head.clone());
                rest = cell.tail.clone();
            }
            out
        }
    }
}

pub fn is_list(v: &Value) -> bool {
    matches!(v, Value::Nil | Value::Cons(_))
}

/// `_kind_of`.  A `Closure` and a `LoopFn` are not Python-callable, so
/// they report "a value" (spec quirk 16).
pub fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Int(_) => "an integer",
        Value::Text(_) => "a text",
        Value::Nil | Value::Cons(_) => "a list",
        _ => "a value",
    }
}

/// The Python type name, which `_map_key`'s fault quotes verbatim.
pub fn type_name(v: &Value) -> &'static str {
    match v {
        Value::Int(_) => "int",
        Value::Text(_) => "str",
        Value::Nil => "_Nil",
        Value::Cons(_) => "Cons",
        Value::Map(_) => "MapValue",
        Value::Closure(_) => "Closure",
        Value::Loop(_) => "LoopFn",
        Value::Program(_) => "Node",
        Value::Tail(_) => "TailCall",
    }
}

/// `core.cli.format_value` -- character for character.
pub fn format_value(a: &Arena, v: &Value) -> String {
    match v {
        Value::Text(s) => quote_text(s),
        Value::Map(m) => {
            let entries = m.pairs();
            let shown: Vec<String> = entries
                .iter()
                .take(8)
                .map(|e| format!("{}: {}", format_value(a, &e.key), format_value(a, &e.val)))
                .collect();
            let more = if entries.len() <= 8 { "" } else { " ..." };
            format!("#<map n={} {{{}{}}}>", entries.len(), shown.join(" "), more)
        }
        Value::Program(id) => format!("#<program {}>", pretty(a, *id)),
        Value::Nil | Value::Cons(_) => {
            let items = list_walk(v);
            let parts: Vec<String> = items
                .iter()
                .map(|i| match i {
                    Value::Int(n) => n.to_string(),
                    other => format_value(a, other),
                })
                .collect();
            let shown = format!("({})", parts.join(" "));
            if !items.is_empty()
                && items.iter().all(|i| match i {
                    Value::Int(n) => match n.to_i64() {
                        Some(c) => (32..=0x10FFFF).contains(&c),
                        None => false,
                    },
                    _ => false,
                })
            {
                let mut text = String::new();
                for i in &items {
                    if let Value::Int(n) = i {
                        match char::from_u32(n.to_i64().unwrap() as u32) {
                            Some(c) => text.push(c),
                            // chr() of a surrogate raises in Python, and
                            // `format_value` falls back to the bare list.
                            None => return shown,
                        }
                    }
                }
                return format!("{}  \"{}\"", shown, text);
            }
            shown
        }
        Value::Int(n) => n.to_string(),
        other => value_repr(a, other),
    }
}
