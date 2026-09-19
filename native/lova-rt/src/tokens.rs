//! The byte encoding (spec §1): opcodes, arities, and `decode`.

use crate::int::Int;
use std::cell::Cell;
use std::rc::Rc;

pub enum Arity {
    N(u8),
    Var,
}

pub struct Sig {
    pub name: &'static str,
    pub arity: Arity,
}

pub use crate::tokens_table::SIGS;

pub fn sig(op: u8) -> Option<&'static Sig> {
    SIGS.get(op as usize)
}

pub fn op_name(op: u8) -> &'static str {
    match sig(op) {
        Some(s) => s.name,
        None => "?",
    }
}

// --- opcodes ----------------------------------------------------------------

pub const END: u8 = 0x00;
pub const LIT_INT: u8 = 0x01;
pub const PARTITION: u8 = 0x02;
pub const MERGE: u8 = 0x03;
pub const CONS: u8 = 0x04;
pub const HEAD: u8 = 0x05;
pub const TAIL: u8 = 0x06;
pub const IDENTITY: u8 = 0x07;
pub const P: u8 = 0x08;
pub const TAU: u8 = 0x09;
pub const SIGMA: u8 = 0x0A;
pub const MUL: u8 = 0x0B;
pub const MOD: u8 = 0x0C;
pub const DIV: u8 = 0x0D;
pub const GCD: u8 = 0x0E;
pub const MOBIUS: u8 = 0x0F;
pub const BUDGET: u8 = 0x10;
pub const CONSERVE: u8 = 0x11;
pub const SIGNAL: u8 = 0x12;
pub const MAP_PUT: u8 = 0x13;
pub const MAP_GET: u8 = 0x14;
pub const NIL: u8 = 0x15;
pub const MAP_PAIRS: u8 = 0x16;
pub const VIOLATE: u8 = 0x17;
pub const SURPRISE: u8 = 0x18;
pub const IS_NIL: u8 = 0x19;
pub const WHEN_ANOMALY: u8 = 0x1A;
pub const THRESHOLD: u8 = 0x1B;
pub const EVAL: u8 = 0x1C;
pub const TRACE_SURPRISE: u8 = 0x1D;
pub const READ: u8 = 0x1E;
pub const DEVIATION: u8 = 0x1F;
pub const DEFPOP: u8 = 0x20;
pub const VARIANT: u8 = 0x21;
pub const EVOLVE: u8 = 0x22;
pub const SELECT: u8 = 0x23;
pub const MUTATE: u8 = 0x24;
pub const CLONE: u8 = 0x25;
pub const FITNESS: u8 = 0x26;
pub const RETIRE: u8 = 0x27;
pub const NET_SEND: u8 = 0x31;
pub const NET_RECV: u8 = 0x32;
pub const FS_READ: u8 = 0x33;
pub const FS_WRITE: u8 = 0x34;
pub const STDOUT: u8 = 0x35;
pub const STDIN: u8 = 0x36;
pub const CLOCK: u8 = 0x37;
pub const SEQ: u8 = 0x28;
pub const QUOTE: u8 = 0x29;
pub const IF_SURPRISE: u8 = 0x2A;
pub const LOOP_UNTIL: u8 = 0x2B;
pub const LAMBDA: u8 = 0x2C;
pub const APPLY: u8 = 0x2D;
pub const LET: u8 = 0x2E;
pub const REF: u8 = 0x2F;
pub const EXTERNAL_BOUNDARY: u8 = 0x30;
pub const LINEAGE_QUERY: u8 = 0x38;
pub const WHY: u8 = 0x39;
pub const TRACE: u8 = 0x3A;
pub const EXPLAIN: u8 = 0x3B;
pub const HASH: u8 = 0x3C;
pub const UID: u8 = 0x3D;
pub const ANCESTOR_OF: u8 = 0x3E;
pub const GENERATION: u8 = 0x3F;
pub const LIT_TEXT: u8 = 0x40;
pub const TEXT_LEN: u8 = 0x41;
pub const TEXT_CAT: u8 = 0x42;
pub const TEXT_SLICE: u8 = 0x43;
pub const TEXT_FIND: u8 = 0x44;
pub const TEXT_SPLIT: u8 = 0x45;
pub const TEXT_JOIN: u8 = 0x46;
pub const TEXT_CHARS: u8 = 0x47;
pub const TEXT_OF_CHARS: u8 = 0x48;
pub const TEXT_CMP: u8 = 0x49;
pub const TEXT_INT: u8 = 0x4A;
pub const INT_TEXT: u8 = 0x4B;
pub const IS_TEXT: u8 = 0x4C;
pub const TEXT_TRIM: u8 = 0x4D;
pub const TEXT_MATCH: u8 = 0x4E;
pub const TEXT_MATCH_ALL: u8 = 0x4F;
pub const LIST_MAP: u8 = 0x50;
pub const LIST_FILTER: u8 = 0x51;
pub const LIST_FOLD: u8 = 0x52;
pub const LIST_REVERSE: u8 = 0x53;
pub const LIST_RANGE: u8 = 0x54;
pub const LIST_ANY: u8 = 0x55;
pub const LIST_SORT_BY: u8 = 0x56;
pub const LIST_ZIP: u8 = 0x57;

// --- capabilities (spec §5.7) ----------------------------------------------

pub const CAP_FS_READ: u32 = 1;
pub const CAP_FS_WRITE: u32 = 2;
pub const CAP_CLOCK: u32 = 4;
pub const CAP_NET: u32 = 8;

pub fn capability_names(mask: u32) -> Vec<&'static str> {
    let mut out = Vec::new();
    if mask & CAP_FS_READ != 0 {
        out.push("fs-read");
    }
    if mask & CAP_FS_WRITE != 0 {
        out.push("fs-write");
    }
    if mask & CAP_CLOCK != 0 {
        out.push("clock");
    }
    if mask & CAP_NET != 0 {
        out.push("net");
    }
    out
}

/// A Python list of names, formatted as `str(list)` renders it.
pub fn py_name_list(names: &[&str]) -> String {
    let inner: Vec<String> = names.iter().map(|n| format!("'{}'", n)).collect();
    format!("[{}]", inner.join(", "))
}

// --- the node arena ---------------------------------------------------------

pub struct Node {
    pub op: u8,
    pub kids: Vec<u32>,
    pub ival: Option<Int>,
    pub sval: Option<Rc<String>>,
    /// The lineage uid, set by `register_root` / `_register_child`.
    /// Metadata on the node, never in the bytes (spec §5.5).
    pub uid: Cell<Option<u64>>,
}

pub fn node(op: u8, kids: Vec<u32>, ival: Option<Int>, sval: Option<Rc<String>>) -> Node {
    Node { op, kids, ival, sval, uid: Cell::new(None) }
}

pub struct Arena {
    pub nodes: Vec<Node>,
}

impl Arena {
    pub fn new() -> Arena {
        Arena { nodes: Vec::new() }
    }

    #[inline]
    pub fn get(&self, id: u32) -> &Node {
        &self.nodes[id as usize]
    }

    #[inline]
    pub fn op(&self, id: u32) -> u8 {
        self.nodes[id as usize].op
    }

    #[inline]
    pub fn kids(&self, id: u32) -> &[u32] {
        &self.nodes[id as usize].kids
    }

    pub fn push(&mut self, node: Node) -> u32 {
        self.nodes.push(node);
        (self.nodes.len() - 1) as u32
    }

    /// `_deep_copy_node`: a fresh tree, sharing a `LIT_TEXT`'s text.
    pub fn deep_copy(&mut self, id: u32) -> u32 {
        let (op, kids, ival, sval) = {
            let n = self.get(id);
            (n.op, n.kids.clone(), n.ival.clone(), n.sval.clone())
        };
        let new_kids: Vec<u32> = kids.iter().map(|k| self.deep_copy(*k)).collect();
        // `_deep_copy_node` clears the uid on the copy (quirk 29).
        self.push(node(op, new_kids, ival, sval))
    }
}

// --- decode (spec §1.1) -----------------------------------------------------

pub fn decode(arena: &mut Arena, data: &[u8]) -> Result<u32, String> {
    let (id, pos) = decode_one(arena, data, 0)?;
    if pos != data.len() {
        return Err(format!("trailing bytes after decode: {}", hex::encode(&data[pos..])));
    }
    Ok(id)
}

fn decode_one(arena: &mut Arena, data: &[u8], mut pos: usize) -> Result<(u32, usize), String> {
    if pos >= data.len() {
        return Err("unexpected end of stream".to_string());
    }
    let op = data[pos];
    let s = match sig(op) {
        Some(s) => s,
        None => return Err(format!("unknown token 0x{:02X} at position {}", op, pos)),
    };
    if op == LIT_INT {
        if pos + 1 >= data.len() {
            return Err("LIT_INT: missing length byte".to_string());
        }
        let length = data[pos + 1] as usize;
        if pos + 2 + length > data.len() {
            return Err("LIT_INT: truncated payload".to_string());
        }
        let val = Int::from_signed_bytes_be(&data[pos + 2..pos + 2 + length]);
        let id = arena.push(node(op, Vec::new(), Some(val), None));
        return Ok((id, pos + 2 + length));
    }
    if op == LIT_TEXT {
        if pos + 3 > data.len() {
            return Err("LIT_TEXT: missing length".to_string());
        }
        let length = ((data[pos + 1] as usize) << 8) | data[pos + 2] as usize;
        if pos + 3 + length > data.len() {
            return Err("LIT_TEXT: truncated payload".to_string());
        }
        let text = match std::str::from_utf8(&data[pos + 3..pos + 3 + length]) {
            Ok(t) => t.to_string(),
            Err(e) => return Err(format!("LIT_TEXT: invalid utf-8: {}", e)),
        };
        let id = arena.push(node(op, Vec::new(), None, Some(Rc::new(text))));
        return Ok((id, pos + 3 + length));
    }
    pos += 1;
    let mut kids: Vec<u32> = Vec::new();
    match s.arity {
        Arity::Var => {
            while pos < data.len() && data[pos] != END {
                let (child, next) = decode_one(arena, data, pos)?;
                kids.push(child);
                pos = next;
            }
            if pos >= data.len() {
                return Err(format!("{}: missing END terminator", s.name));
            }
            pos += 1;
        }
        Arity::N(n) => {
            for _ in 0..n {
                let (child, next) = decode_one(arena, data, pos)?;
                kids.push(child);
                pos = next;
            }
        }
    }
    let id = arena.push(node(op, kids, None, None));
    Ok((id, pos))
}

// --- encode (core/tokens.py) ------------------------------------------------

/// `encode(node)`: the byte stream `hash` turns into an integer.
pub fn encode(arena: &Arena, id: u32) -> Vec<u8> {
    let mut buf = Vec::new();
    encode_into(arena, id, &mut buf);
    buf
}

fn encode_into(arena: &Arena, id: u32, buf: &mut Vec<u8>) {
    let n = arena.get(id);
    buf.push(n.op);
    if n.op == LIT_TEXT {
        let data = n.sval.as_ref().unwrap().as_bytes();
        buf.push((data.len() >> 8) as u8);
        buf.push((data.len() & 0xFF) as u8);
        buf.extend_from_slice(data);
        return;
    }
    if n.op == LIT_INT {
        let value = n.ival.as_ref().unwrap();
        // `bit_length() + 1` for the sign, rounded up to whole bytes.
        let bits = value.bit_length() + 1;
        let n_bytes = std::cmp::max(1, ((bits + 7) / 8) as usize);
        let mut bytes = value.to_big().to_signed_bytes_be();
        if bytes.len() < n_bytes {
            let fill = if value.is_negative() { 0xFF } else { 0x00 };
            let mut padded = vec![fill; n_bytes - bytes.len()];
            padded.extend_from_slice(&bytes);
            bytes = padded;
        }
        buf.push(n_bytes as u8);
        buf.extend_from_slice(&bytes[bytes.len() - n_bytes..]);
        return;
    }
    for k in &n.kids {
        encode_into(arena, *k, buf);
    }
    if matches!(sig(n.op).map(|s| &s.arity), Some(Arity::Var)) {
        buf.push(END);
    }
}

/// `core.surface.pretty` -- the Stage-1 projection, which
/// `format_value` needs for a program value.
pub fn pretty(arena: &Arena, id: u32) -> String {
    let n = arena.get(id);
    if n.op == LIT_INT {
        return n.ival.as_ref().unwrap().to_string();
    }
    if n.op == LIT_TEXT {
        return crate::value::quote_text(n.sval.as_ref().unwrap());
    }
    let name = op_name(n.op);
    if n.kids.is_empty() {
        return format!("({})", name);
    }
    let kids: Vec<String> = n.kids.iter().map(|k| pretty(arena, *k)).collect();
    format!("({} {})", name, kids.join(" "))
}

/// `ordinals[node id]` = the node's 0-based place in the byte stream,
/// which is preorder with literals counted -- the order
/// `core.tokens.decode` meets them in.  Only the decoded tree is in the
/// table; a node made later (`quote`, `clone`, `mutate`, a probe) is
/// past its end and has no place in the program's text.
pub fn preorder_ordinals(arena: &Arena, root: u32) -> Vec<u32> {
    let mut out = vec![0u32; arena.nodes.len()];
    let mut next = 0u32;
    fill(arena, root, &mut next, &mut out);
    out
}

fn fill(arena: &Arena, id: u32, next: &mut u32, out: &mut Vec<u32>) {
    out[id as usize] = *next;
    *next += 1;
    for k in arena.kids(id) {
        fill(arena, *k, next, out);
    }
}

/// The set of operators a tree uses -- the scan D7 asks for before a run.
pub fn operators_used(arena: &Arena, id: u32, seen: &mut [bool; 0x58]) {
    let n = arena.get(id);
    seen[n.op as usize] = true;
    for k in &n.kids {
        operators_used(arena, *k, seen);
    }
}
