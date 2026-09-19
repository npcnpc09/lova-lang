//! The Meta / lineage family (spec §5.8), less `read` and `explain`,
//! which need the Stage-1 surface and stay in Python (decision D7).

use crate::int::Int;
use crate::rt::{as_program, eval, Rt};
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use num_bigint::{BigInt, Sign};
use std::rc::Rc;

pub fn eval_meta(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    match op {
        HASH => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "hash")?;
            // Axiom 1, taken literally: the program *is* this integer.
            let bytes = encode(a, program);
            Ok(Value::Int(Int::from_big(BigInt::from_bytes_be(Sign::Plus, &bytes))))
        }
        UID => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "uid")?;
            let uid = a.get(program).uid.get().unwrap_or(0);
            Ok(Value::Int(Int::from_i64(uid as i64)))
        }
        GENERATION => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "generation")?;
            let generation = match a.get(program).uid.get() {
                Some(uid) if uid != 0 => rt.lineage.borrow().record(uid).generation,
                _ => 0,
            };
            Ok(Value::Int(Int::from_i64(generation)))
        }
        ANCESTOR_OF => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let first = as_program(a, &v, "ancestor-of")?;
            let v = eval(a, rt, k1, false)?;
            let second = as_program(a, &v, "ancestor-of")?;
            let (ua, ub) = (a.get(first).uid.get(), a.get(second).uid.get());
            let answer = match (ua, ub) {
                (Some(x), Some(y)) if x != 0 && y != 0 => {
                    if rt.lineage.borrow().is_ancestor_of(x, y) {
                        1
                    } else {
                        0
                    }
                }
                _ => 0,
            };
            Ok(Value::Int(Int::from_i64(answer)))
        }
        LINEAGE_QUERY => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "lineage-query")?;
            // self -> parent -> ... -> root.  Empty for a program with
            // no history yet.
            match a.get(program).uid.get() {
                Some(uid) if uid != 0 => {
                    let uids = rt.lineage.borrow().ancestors(uid);
                    Ok(list_from(
                        uids.into_iter().map(|u| Value::Int(Int::from_i64(u as i64))).collect(),
                    ))
                }
                _ => Ok(Value::Nil),
            }
        }
        WHY => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "why")?;
            let text = match a.get(program).uid.get() {
                Some(uid) if uid != 0 => {
                    let store = rt.lineage.borrow();
                    let record = store.record(uid);
                    format!("{} {}", record.mutation_kind, record.notes).trim().to_string()
                }
                _ => "unregistered".to_string(),
            };
            Ok(Value::Text(Rc::new(text)))
        }
        TRACE => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "trace")?;
            // A sandbox on what is left of this run's ceilings, so a
            // loop of traces cannot slip past them.  Its own budget
            // stack, output and trace (quirk 23).
            let mut inner = Rt::new(
                std::cmp::max(1, rt.max_steps.saturating_sub(rt.steps)),
                std::cmp::max(1, rt.max_call_depth.saturating_sub(rt.call_depth)),
                0,
                "",
            );
            inner.lineage = rt.lineage.clone();
            inner.ordinals = rt.ordinals.clone();
            for (name, value) in rt.env.flatten() {
                inner.env.set(name, value);
            }
            let outcome = eval(a, &mut inner, program, false);
            // Added after the fact, without a ceiling check (quirk 23).
            rt.steps = rt.steps.saturating_add(inner.steps);
            outcome?;
            Ok(list_from(inner.surprise.into_iter().map(Value::Int).collect()))
        }
        _ => unreachable!(),
    }
}
