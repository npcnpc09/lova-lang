//! The text family (spec §5.9).  A text is a sequence of codepoints;
//! every operator that says "characters" means codepoints.

use crate::int::Int;
use crate::rt::{as_int, as_list, as_text, as_vec, sep_of, eval, Rt};
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;
use std::cmp::Ordering;
use std::rc::Rc;

/// D6: Python's `str.isspace` set, fixed.
pub fn is_py_space(c: char) -> bool {
    matches!(c,
        '\u{9}'..='\u{d}' | '\u{1c}'..='\u{1f}' | '\u{20}' | '\u{85}' | '\u{a0}'
        | '\u{1680}' | '\u{2000}'..='\u{200a}' | '\u{2028}' | '\u{2029}'
        | '\u{202f}' | '\u{205f}' | '\u{3000}')
}

fn py_strip(s: &str) -> &str {
    s.trim_matches(is_py_space)
}

fn clamp(i: &Int, len: usize) -> usize {
    if i.is_negative() {
        return 0;
    }
    match i.to_usize() {
        Some(v) => v.min(len),
        None => len,
    }
}

pub fn eval_text(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    match op {
        LIT_TEXT => Ok(Value::Text(a.get(id).sval.clone().unwrap())),
        TEXT_LEN => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let n = match &v {
                Value::Text(s) => s.chars().count(),
                other => as_vec(a, other, "text-len")?.len(),
            };
            Ok(Value::Int(Int::from_usize(n)))
        }
        TEXT_CAT => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let y = eval(a, rt, k1, false)?;
            if let (Value::Text(p), Value::Text(q)) = (&x, &y) {
                let mut out = String::with_capacity(p.len() + q.len());
                out.push_str(p);
                out.push_str(q);
                return Ok(Value::Text(Rc::new(out)));
            }
            let mut xs = as_vec(a, &x, "text-cat")?;
            xs.extend(as_vec(a, &y, "text-cat")?);
            Ok(list_from(xs))
        }
        TEXT_SLICE => {
            let (k0, k1, k2) = (a.kids(id)[0], a.kids(id)[1], a.kids(id)[2]);
            let v = eval(a, rt, k0, false)?;
            let start = eval(a, rt, k1, false)?;
            let start = as_int(a, &start, "text-slice")?;
            let end = eval(a, rt, k2, false)?;
            let end = as_int(a, &end, "text-slice")?;
            if let Value::Text(s) = &v {
                let chars: Vec<char> = s.chars().collect();
                let (i, j) = (clamp(&start, chars.len()), clamp(&end, chars.len()));
                let out: String = if j > i { chars[i..j].iter().collect() } else { String::new() };
                return Ok(Value::Text(Rc::new(out)));
            }
            let xs = as_vec(a, &v, "text-slice")?;
            let (i, j) = (clamp(&start, xs.len()), clamp(&end, xs.len()));
            Ok(list_from(if j > i { xs[i..j].to_vec() } else { Vec::new() }))
        }
        TEXT_FIND => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let t = as_text(a, &v, "text-find")?;
            let n = eval(a, rt, k1, false)?;
            let needle = sep_of(a, &n, "text-find")?;
            Ok(Value::Int(match t.find(needle.as_str()) {
                Some(byte) => Int::from_usize(t[..byte].chars().count()),
                None => Int::from_i64(-1),
            }))
        }
        TEXT_SPLIT => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let t = as_text(a, &v, "text-split")?;
            let s = eval(a, rt, k1, false)?;
            let sep = sep_of(a, &s, "text-split")?;
            let parts: Vec<Value> = if sep.is_empty() {
                t.split(is_py_space)
                    .filter(|p| !p.is_empty())
                    .map(|p| Value::Text(Rc::new(p.to_string())))
                    .collect()
            } else {
                t.split(sep.as_str())
                    .map(|p| Value::Text(Rc::new(p.to_string())))
                    .collect()
            };
            Ok(list_from(parts))
        }
        TEXT_JOIN => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let parts = eval(a, rt, k0, false)?;
            let s = eval(a, rt, k1, false)?;
            let sep = sep_of(a, &s, "text-join")?;
            let parts = match &parts {
                Value::Text(s) => text_chars(s),
                other => other.clone(),
            };
            let items = list_walk(&as_list(a, &parts, "text-join")?);
            let mut out = String::new();
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(&sep);
                }
                out.push_str(&as_text(a, item, "text-join")?);
            }
            Ok(Value::Text(Rc::new(out)))
        }
        TEXT_CHARS => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            match &v {
                Value::Text(s) => Ok(text_chars(s)),
                other => as_list(a, other, "text-chars"),
            }
        }
        TEXT_OF_CHARS => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            Ok(Value::Text(as_text(a, &v, "text-of-chars")?))
        }
        TEXT_CMP => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let x = eval(a, rt, k0, false)?;
            let y = eval(a, rt, k1, false)?;
            if let (Value::Text(p), Value::Text(q)) = (&x, &y) {
                // Python compares strings by code point; UTF-8 byte
                // order is the same order.
                return Ok(Value::Int(Int::from_i64(match p.as_str().cmp(q.as_str()) {
                    Ordering::Less => -1,
                    Ordering::Equal => 0,
                    Ordering::Greater => 1,
                })));
            }
            let xs = list_walk(&x);
            let ys = list_walk(&y);
            Ok(Value::Int(Int::from_i64(match cmp_lists(&xs, &ys)? {
                Ordering::Less => -1,
                Ordering::Equal => 0,
                Ordering::Greater => 1,
            })))
        }
        TEXT_INT => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let raw = as_text(a, &v, "text-int")?;
            let t = py_strip(&raw);
            let body = t.strip_prefix('-').unwrap_or(t);
            // D2: ASCII digits only.
            if body.is_empty() || !body.chars().all(|c| c.is_ascii_digit()) {
                let shown: String = t.chars().take(40).collect();
                return Err(domain(
                    "signalled",
                    format!("text-int: not a number: {}", py_repr_str(&shown)),
                    detail(vec![
                        ("operator", J::from("text-int")),
                        ("code", J::from(16)),
                        ("text", J::from(shown)),
                    ]),
                    "give `text-int` decimal digits, with an optional leading -",
                ));
            }
            Ok(Value::Int(parse_int(t)))
        }
        INT_TEXT => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let n = as_int(a, &v, "int-text")?;
            Ok(Value::Text(Rc::new(n.to_string())))
        }
        IS_TEXT => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            Ok(Value::Int(Int::from_i64(if matches!(v, Value::Text(_)) { 1 } else { 0 })))
        }
        TEXT_TRIM => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let s = as_text(a, &v, "text-trim")?;
            Ok(Value::Text(Rc::new(py_strip(&s).to_string())))
        }
        TEXT_MATCH | TEXT_MATCH_ALL => {
            let ctx = op_name(op);
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let t = as_text(a, &v, ctx)?;
            let p = eval(a, rt, k1, false)?;
            let pat = as_text(a, &p, ctx)?;
            let re = compile_pattern(rt, &pat, ctx)?;
            if op == TEXT_MATCH {
                return Ok(match re.captures(&t) {
                    None => Value::Nil,
                    Some(c) => match_value(&c),
                });
            }
            let mut out = Vec::new();
            for c in re.captures_iter(&t) {
                rt.steps += 1;
                if rt.steps > rt.max_steps {
                    return Err(step_trap(rt.steps, rt.max_steps));
                }
                out.push(match_value(&c));
            }
            Ok(list_from(out))
        }
        _ => unreachable!(),
    }
}

fn parse_int(t: &str) -> Int {
    match t.parse::<i64>() {
        Ok(v) => Int::from_i64(v),
        Err(_) => match t.parse::<num_bigint::BigInt>() {
            Ok(b) => Int::from_big(b),
            Err(_) => Int::zero(),
        },
    }
}

fn match_value(c: &regex::Captures) -> Value {
    let mut out: Vec<Value> = Vec::with_capacity(c.len());
    out.push(Value::Text(Rc::new(c.get(0).map(|m| m.as_str()).unwrap_or("").to_string())));
    for i in 1..c.len() {
        let g = c.get(i).map(|m| m.as_str()).unwrap_or("");
        out.push(Value::Text(Rc::new(g.to_string())));
    }
    list_from(out)
}

// --- the pattern subset (spec §5.9) -----------------------------------------

const ESCAPES: &str = "dDwWsSnt";

fn compile_pattern(rt: &mut Rt, text: &str, ctx: &str) -> R<regex::Regex> {
    if let Some(re) = rt.patterns.get(text) {
        return Ok(re.clone());
    }
    // `_PATTERN_SCAN`: `\\\\` skipped, `(?` and an escape outside the
    // subset refused.
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0usize;
    while i < chars.len() {
        if chars[i] == '\\' && i + 1 < chars.len() && chars[i + 1] == '\\' {
            i += 2;
            continue;
        }
        if chars[i] == '(' && i + 1 < chars.len() && chars[i + 1] == '?' {
            return Err(subset_fault(ctx, "(?", text, i));
        }
        if chars[i] == '\\' && i + 1 < chars.len() && chars[i + 1].is_ascii_alphanumeric() {
            if !ESCAPES.contains(chars[i + 1]) {
                let tok: String = chars[i..i + 2].iter().collect();
                return Err(subset_fault(ctx, &tok, text, i));
            }
            i += 2;
            continue;
        }
        i += 1;
    }
    let re = match regex::Regex::new(text) {
        Ok(re) => re,
        Err(e) => {
            return Err(domain(
                "domain-error",
                format!("{}: the pattern does not parse: {}", ctx, e),
                detail(vec![
                    ("operator", J::from(ctx)),
                    ("pattern", J::from(text)),
                    ("at", J::Null),
                ]),
                "fix the pattern; a literal `(`, `[`, `.` or `*` needs a backslash",
            ))
        }
    };
    if rt.patterns.len() > 256 {
        rt.patterns.clear();
    }
    rt.patterns.insert(text.to_string(), re.clone());
    Ok(re)
}

fn subset_fault(ctx: &str, tok: &str, text: &str, at: usize) -> Fault {
    domain(
        "domain-error",
        format!(
            "{}: `{}` is outside the pattern subset (literals, `.`, `[...]`, `\\d \\w \\s`, \
`* + ? {{m,n}}`, `( )`, `|`, `^ $`)",
            ctx, tok
        ),
        detail(vec![
            ("operator", J::from(ctx)),
            ("pattern", J::from(text)),
            ("at", J::from(at)),
        ]),
        "rewrite the pattern in the subset; match twice rather than refer back",
    )
}

// --- Python's list comparison, for `text-cmp` (spec §2.6, D3) ---------------

fn py_eq(x: &Value, y: &Value) -> bool {
    match (x, y) {
        (Value::Int(p), Value::Int(q)) => p == q,
        (Value::Text(p), Value::Text(q)) => p == q,
        (Value::Nil, Value::Nil) => true,
        (Value::Cons(p), Value::Cons(q)) => {
            Rc::ptr_eq(p, q) || (py_eq(&p.head, &q.head) && py_eq(&p.tail, &q.tail))
        }
        (Value::Closure(p), Value::Closure(q)) => Rc::ptr_eq(p, q),
        (Value::Loop(p), Value::Loop(q)) => Rc::ptr_eq(p, q),
        (Value::Program(p), Value::Program(q)) => p == q,
        _ => false,
    }
}

fn incomparable() -> Fault {
    domain(
        "type-violation",
        "text-cmp: the elements are not comparable (an integer against a text or a list)"
            .to_string(),
        detail(vec![
            ("operator", J::from("text-cmp")),
            ("expected", J::from("two texts, or two lists of integers")),
        ]),
        "compare two texts, or two lists whose elements are integers",
    )
}

fn cmp_lists(xs: &[Value], ys: &[Value]) -> R<Ordering> {
    let n = xs.len().min(ys.len());
    for i in 0..n {
        if py_eq(&xs[i], &ys[i]) {
            continue;
        }
        return match (&xs[i], &ys[i]) {
            (Value::Int(p), Value::Int(q)) => Ok(p.cmp(q)),
            (Value::Text(p), Value::Text(q)) => Ok(p.as_str().cmp(q.as_str())),
            _ => Err(incomparable()),
        };
    }
    Ok(xs.len().cmp(&ys.len()))
}
