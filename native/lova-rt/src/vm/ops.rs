//! The operators' work, over operands the VM has already evaluated.
//!
//! The *work* is the tree-walker's: `nt`, `text`, `value`, the
//! coercions in `rt`.  What is here is the same sequence of calls the
//! tree-walker's own arm makes once its children are values, so that
//! the two evaluators cannot drift on a message, a guard or an order.
//!
//! `coerce_after` is shared with the tree-walker (`rt::eval_text_node`)
//! and with the compiler: it is the one table of which operand the
//! reference coerces *before* the next one is evaluated.

use super::CK;
use crate::int::Int;
use crate::nt;
use crate::rt::{
    as_fn, as_int, as_list, as_map, as_text, as_vec, call, fs_fault, map_key, merge_sort,
    os_error_name, tick, Rt,
};
use crate::text;
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;
use std::rc::Rc;

/// `Some(kind)` when the reference coerces child `i` *before* it
/// evaluates child `i + 1`, so the trap order depends on it.
pub fn coerce_after(op: u8, i: usize) -> Option<CK> {
    match (op, i) {
        (MERGE, 0) | (MUL, 0) | (MOD, 0) | (DIV, 0) | (GCD, 0) => Some(CK::Int),
        (SURPRISE, 0) | (LIST_RANGE, 0) => Some(CK::Int),
        (TEXT_SLICE, 1) => Some(CK::Int),
        (TEXT_FIND, 0) | (TEXT_SPLIT, 0) | (FS_WRITE, 0) => Some(CK::Text),
        (TEXT_MATCH, 0) | (TEXT_MATCH_ALL, 0) => Some(CK::Text),
        (MAP_PUT, 0) | (MAP_GET, 0) => Some(CK::Map),
        (LIST_ZIP, 0) => Some(CK::List),
        (LIST_MAP, 0) | (LIST_FILTER, 0) | (LIST_ANY, 0) | (LIST_SORT_BY, 0) => Some(CK::Fn),
        (LIST_FOLD, 0) => Some(CK::Fn),
        _ => None,
    }
}

pub fn coerce(a: &Arena, v: Value, ck: CK, op: u8) -> R<Value> {
    let ctx = op_name(op);
    Ok(match ck {
        CK::Int => Value::Int(as_int(a, &v, ctx)?),
        CK::Text => Value::Text(as_text(a, &v, ctx)?),
        CK::Fn => as_fn(a, &v, ctx)?,
        CK::List => as_list(a, &v, ctx)?,
        CK::Map => Value::Map(as_map(a, &v, ctx)?),
    })
}

/// Every operator whose work happens once its operands are values.
pub fn work(a: &Arena, rt: &mut Rt, op: u8, args: &[Value]) -> R<Value> {
    match op {
        MERGE => {
            let x = as_int(a, &args[0], "merge")?;
            let y = as_int(a, &args[1], "merge")?;
            Ok(Value::Int(x.add(&y)))
        }
        DEVIATION => {
            let (x, y) = (&args[0], &args[1]);
            if matches!(x, Value::Text(_)) || matches!(y, Value::Text(_)) {
                let xs = as_text(a, x, "deviation")?;
                let ys = as_text(a, y, "deviation")?;
                return Ok(Value::Int(Int::from_i64(if *xs == *ys { 0 } else { 1 })));
            }
            let x = as_int(a, x, "deviation")?;
            let y = as_int(a, y, "deviation")?;
            Ok(Value::Int(x.sub(&y)))
        }
        THRESHOLD => {
            let x = as_int(a, &args[0], "threshold")?;
            Ok(Value::Int(Int::from_i64(if x > Int::zero() { 1 } else { 0 })))
        }
        PARTITION => {
            let n = as_int(a, &args[0], "partition")?;
            Ok(Value::Int(n.div_floor(&Int::from_i64(2))))
        }
        IDENTITY => Ok(args[0].clone()),
        MUL => {
            let x = as_int(a, &args[0], "mul")?;
            let y = as_int(a, &args[1], "mul")?;
            if let (Some(p), Some(q)) = (x.to_i64(), y.to_i64()) {
                if let Some(n) = p.checked_mul(q) {
                    return Ok(Value::Int(Int::from_i64(n)));
                }
            }
            let (ab, bb) = (x.bit_length(), y.bit_length());
            if ab + bb > crate::rt::MAX_INT_BITS {
                return Err(domain(
                    "domain-error",
                    format!(
                        "mul result would exceed MAX_INT_BITS={} ({} + {} bits)",
                        crate::rt::MAX_INT_BITS,
                        ab,
                        bb
                    ),
                    detail(vec![
                        ("operator", J::from("mul")),
                        ("limit", J::from(crate::rt::MAX_INT_BITS)),
                    ]),
                    "multiply smaller numbers",
                ));
            }
            Ok(Value::Int(x.mul(&y)))
        }
        DIV | MOD => {
            let name = if op == DIV { "div" } else { "mod" };
            let x = as_int(a, &args[0], name)?;
            let y = as_int(a, &args[1], name)?;
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
        GCD => {
            let x = as_int(a, &args[0], "gcd")?;
            let y = as_int(a, &args[1], "gcd")?;
            Ok(Value::Int(x.gcd(&y)))
        }
        P | TAU | SIGMA | MOBIUS => {
            let ctx = op_name(op);
            let n = as_int(a, &args[0], ctx)?;
            nt::number_theory(op, &n)
        }
        NIL => Ok(Value::Nil),
        CONS => {
            let element = args[0].clone();
            let rest = &args[1];
            let rest = match rest {
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
            let target = &args[0];
            if let Value::Cons(c) = target {
                return Ok(c.head.clone());
            }
            if let Value::Text(s) = target {
                if let Some(c) = s.chars().next() {
                    return Ok(Value::Int(Int::from_i64(c as i64)));
                }
            }
            let target = as_list(a, target, "head")?;
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
            let target = &args[0];
            if let Value::Cons(c) = target {
                return Ok(c.tail.clone());
            }
            if let Value::Text(s) = target {
                if !s.is_empty() {
                    let rest: String = s.chars().skip(1).collect();
                    return Ok(Value::Text(Rc::new(rest)));
                }
            }
            let target = as_list(a, target, "tail")?;
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
        IS_NIL => match &args[0] {
            Value::Nil => Ok(Value::Int(Int::from_i64(1))),
            Value::Cons(_) => Ok(Value::Int(Int::zero())),
            Value::Text(s) => Ok(Value::Int(Int::from_i64(if s.is_empty() { 1 } else { 0 }))),
            other => {
                as_list(a, other, "nil?")?;
                Ok(Value::Int(Int::zero()))
            }
        },
        MAP_PUT => {
            let base = as_map(a, &args[0], "map-put")?;
            let hashed = map_key(a, &args[1], "map-put")?;
            Ok(Value::Map(base.put(hashed, args[1].clone(), args[2].clone())))
        }
        MAP_PAIRS => {
            let m = as_map(a, &args[0], "map-pairs")?;
            Ok(list_from(
                m.pairs().into_iter().map(|e| list_from(vec![e.key, e.val])).collect(),
            ))
        }
        VIOLATE => {
            let x = as_int(a, &args[0], "violate")?;
            Ok(Value::Int(x.add(&Int::from_i64(1))))
        }
        SURPRISE => {
            let p = as_int(a, &args[0], "surprise")?;
            let q = as_int(a, &args[1], "surprise")?;
            Ok(Value::Int(rt.emit(&p, &q)))
        }
        TRACE_SURPRISE => {
            let v = as_int(a, &args[0], "trace-surprise")?;
            rt.emit(&Int::zero(), &v);
            Ok(Value::Int(v))
        }
        SIGNAL => {
            let code = as_int(a, &args[0], "signal")?;
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
                detail(vec![("operator", J::from("signal")), ("code", code.to_json())]),
                "catch it with `when-anomaly` and branch on the code",
            ))
        }
        LOOP_UNTIL => {
            let (pred, step) = (args[0].clone(), args[1].clone());
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
        STDOUT => {
            let t = as_text(a, &args[0], "stdout")?;
            rt.output.push_str(&t);
            Ok(Value::Int(Int::from_usize(t.chars().count())))
        }
        STDIN => match rt.read_line() {
            Some(line) => Ok(Value::Text(Rc::new(line))),
            None => Ok(Value::Nil),
        },
        CLOCK => {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as i64)
                .unwrap_or(0);
            Ok(Value::Int(Int::from_i64(now)))
        }
        FS_READ => {
            let path = as_text(a, &args[0], "fs-read")?;
            match std::fs::read(path.as_str()) {
                Ok(raw) => match String::from_utf8(raw) {
                    Ok(text) => Ok(Value::Text(Rc::new(text))),
                    Err(_) => Err(fs_fault(
                        "fs-read",
                        path.as_str(),
                        "UnicodeDecodeError",
                    )),
                },
                Err(e) => {
                    Err(fs_fault("fs-read", path.as_str(), os_error_name(&e)))
                }
            }
        }
        FS_WRITE => {
            let path = as_text(a, &args[0], "fs-write")?;
            let text = as_text(a, &args[1], "fs-write")?;
            match std::fs::write(path.as_str(), text.as_bytes()) {
                Ok(()) => Ok(Value::Int(Int::from_usize(text.chars().count()))),
                Err(e) => {
                    Err(fs_fault("fs-write", path.as_str(), os_error_name(&e)))
                }
            }
        }
        END => Err(Fault::NotImplemented(
            "operator end (family struct) not implemented in Milestone 1 runtime".into(),
        )),
        _ if (TEXT_LEN..=TEXT_MATCH_ALL).contains(&op) => text::work_text(a, rt, op, args),
        _ => Err(Fault::NotImplemented(
            format!("operator {} is outside this runtime's phase-2 scope", op_name(op)).into(),
        )),
    }
}

/// The list family (spec §5.10): the walkers, which call and charge a
/// step an element.
pub fn list_op(a: &mut Arena, rt: &mut Rt, op: u8, args: &[Value]) -> R<Value> {
    match op {
        LIST_MAP | LIST_FILTER | LIST_ANY => {
            let ctx = op_name(op);
            let f = as_fn(a, &args[0], ctx)?;
            let xs = as_vec(a, &args[1], ctx)?;
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
            let f = as_fn(a, &args[0], "fold")?;
            let mut acc = args[1].clone();
            let xs = as_vec(a, &args[2], "fold")?;
            for x in xs {
                tick(rt, 1)?;
                let step = call(a, rt, f.clone(), acc)?;
                acc = call(a, rt, step, x)?;
            }
            Ok(acc)
        }
        LIST_REVERSE => {
            let mut xs = as_vec(a, &args[0], "reverse")?;
            tick(rt, xs.len() as u64)?;
            xs.reverse();
            Ok(list_from(xs))
        }
        LIST_RANGE => {
            let x = as_int(a, &args[0], "range")?;
            let y = as_int(a, &args[1], "range")?;
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
            let less = as_fn(a, &args[0], "sort-by")?;
            let xs = as_vec(a, &args[1], "sort-by")?;
            Ok(list_from(merge_sort(a, rt, xs, &less)?))
        }
        LIST_ZIP => {
            let xs = as_vec(a, &args[0], "zip")?;
            let ys = as_vec(a, &args[1], "zip")?;
            let n = xs.len().min(ys.len());
            tick(rt, n as u64)?;
            let out: Vec<Value> =
                (0..n).map(|i| list_from(vec![xs[i].clone(), ys[i].clone()])).collect();
            Ok(list_from(out))
        }
        _ => unreachable!(),
    }
}
