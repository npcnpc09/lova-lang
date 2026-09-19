//! The Evolution family (spec §5.5): a population is a value, and one
//! generation is `core/populations.py`'s rule run from inside.

use crate::int::Int;
use crate::rt::{as_int, as_program, call, eval, Rt};
use crate::tokens::*;
use crate::trap::*;
use crate::value::*;
use serde_json::Value as J;
use std::rc::Rc;

/// The score of a variant whose scorer trapped: it is not scored, it
/// loses.
const UNFIT: i64 = 1 << 62;

const RETIRE_FRACTION: f64 = 0.2;
const CLONE_PROBABILITY: f64 = 0.3;
const EVOLVE_STRENGTH: f64 = 0.3;

fn as_population(a: &Arena, v: &Value, ctx: &str) -> R<Rc<PopulationData>> {
    match v {
        Value::Population(p) => Ok(p.clone()),
        _ => Err(domain(
            "type-violation",
            format!("{}: expected a Population, got {}; `defpop` builds one", ctx, value_repr(a, v)),
            detail(vec![("operator", J::from(ctx)), ("expected", J::from("Population"))]),
            "build a pool with `(defpop scorer program ...)`",
        )),
    }
}

/// Every variant's score, in pool order.  Lower is fitter.  A trap that
/// is not the step ceiling makes the variant unfit instead of ending
/// the run.
fn score_population(a: &mut Arena, rt: &mut Rt, pop: &PopulationData) -> R<Vec<Int>> {
    let mut scores: Vec<Int> = Vec::with_capacity(pop.variants.len());
    for variant in &pop.variants {
        let outcome = match call(a, rt, pop.scorer.clone(), Value::Program(*variant)) {
            Ok(v) => as_int(a, &v, "fitness"),
            Err(e) => Err(e),
        };
        match outcome {
            Ok(score) => scores.push(score),
            Err(Fault::NotImplemented(m)) => return Err(Fault::NotImplemented(m)),
            Err(Fault::Trap(t)) => {
                if t.class == Class::Step {
                    return Err(Fault::Trap(t)); // the ceiling is not a fitness signal
                }
                scores.push(Int::from_i64(UNFIT));
            }
        }
    }
    Ok(scores)
}

/// (scores, indices fittest-first).  Ties keep pool order.
fn rank_population(
    a: &mut Arena,
    rt: &mut Rt,
    pop: &PopulationData,
) -> R<(Vec<Int>, Vec<usize>)> {
    let scores = score_population(a, rt, pop)?;
    let mut order: Vec<usize> = (0..scores.len()).collect();
    order.sort_by(|x, y| scores[*x].cmp(&scores[*y])); // stable: ties keep order
    Ok((scores, order))
}

fn small(v: &Int) -> i64 {
    v.to_i64().unwrap_or(if v.is_negative() { i64::MIN } else { i64::MAX })
}

pub fn eval_evolution(a: &mut Arena, rt: &mut Rt, id: u32, op: u8) -> R<Value> {
    match op {
        DEFPOP => op_defpop(a, rt, id),
        VARIANT | SELECT => {
            let ctx = op_name(op);
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let pop = as_population(a, &v, ctx)?;
            let v = eval(a, rt, k1, false)?;
            let k = small(&as_int(a, &v, ctx)?);
            if op == VARIANT {
                let n = pop.variants.len();
                if k < 0 || k as usize >= n {
                    return Err(domain(
                        "domain-error",
                        format!("variant: index {} out of range for a pool of {}", k, n),
                        detail(vec![
                            ("operator", J::from("variant")),
                            ("index", J::from(k)),
                            ("size", J::from(n)),
                        ]),
                        "index from 0 to one less than the pool size",
                    ));
                }
                return Ok(Value::Program(pop.variants[k as usize]));
            }
            // `select` scores the whole pool before the range check.
            let (_scores, order) = rank_population(a, rt, &pop)?;
            let n = order.len();
            if k < 0 || k as usize >= n {
                return Err(domain(
                    "domain-error",
                    format!("select: rank {} out of range for a pool of {}", k, n),
                    detail(vec![
                        ("operator", J::from("select")),
                        ("rank", J::from(k)),
                        ("size", J::from(n)),
                    ]),
                    "rank 0 is the fittest; the last rank is the pool size less one",
                ));
            }
            Ok(Value::Program(pop.variants[order[k as usize]]))
        }
        FITNESS => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let pop = as_population(a, &v, "fitness")?;
            let scores = score_population(a, rt, &pop)?;
            Ok(list_from(scores.into_iter().map(Value::Int).collect()))
        }
        RETIRE => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let pop = as_population(a, &v, "retire")?;
            if pop.variants.len() < 2 {
                return Err(domain(
                    "domain-error",
                    "retire: cannot retire the last variant".to_string(),
                    detail(vec![
                        ("operator", J::from("retire")),
                        ("size", J::from(pop.variants.len())),
                    ]),
                    "a population keeps at least one variant",
                ));
            }
            let (_scores, order) = rank_population(a, rt, &pop)?;
            let worst = *order.last().unwrap();
            let kept: Vec<u32> = pop
                .variants
                .iter()
                .enumerate()
                .filter(|(i, _)| *i != worst)
                .map(|(_, v)| *v)
                .collect();
            Ok(Value::Population(Rc::new(PopulationData {
                scorer: pop.scorer.clone(),
                variants: kept,
                generation: pop.generation,
            })))
        }
        CLONE => {
            let k = a.kids(id)[0];
            let v = eval(a, rt, k, false)?;
            let program = as_program(a, &v, "clone")?;
            let store = rt.lineage.clone();
            let mut store = store.borrow_mut();
            store.ensure_registered(a, program);
            Ok(Value::Program(store.clone_program(a, program)))
        }
        MUTATE => {
            let (k0, k1) = (a.kids(id)[0], a.kids(id)[1]);
            let v = eval(a, rt, k0, false)?;
            let program = as_program(a, &v, "mutate")?;
            let v = eval(a, rt, k1, false)?;
            let percent = as_int(a, &v, "mutate")?;
            let value = small(&percent);
            if !(0..=100).contains(&value) {
                return Err(domain(
                    "domain-error",
                    format!("mutate: strength {} is not a percentage", percent),
                    detail(vec![
                        ("operator", J::from("mutate")),
                        ("strength", percent.to_json()),
                    ]),
                    "give a strength between 0 and 100",
                ));
            }
            let store = rt.lineage.clone();
            let mut store = store.borrow_mut();
            store.ensure_registered(a, program);
            Ok(Value::Program(store.mutate_program(a, program, value as f64 / 100.0)))
        }
        EVOLVE => op_evolve(a, rt, id),
        _ => unreachable!(),
    }
}

fn op_defpop(a: &mut Arena, rt: &mut Rt, id: u32) -> R<Value> {
    let kids = a.kids(id).to_vec();
    if kids.is_empty() {
        return Err(domain(
            "malformed",
            "defpop: missing scorer".to_string(),
            detail(vec![("operator", J::from("defpop"))]),
            "give `defpop` a scorer function and at least one program",
        ));
    }
    let scorer = eval(a, rt, kids[0], false)?;
    if !matches!(scorer, Value::Closure(_) | Value::Loop(_)) {
        return Err(domain(
            "type-violation",
            format!("defpop: the scorer must be a function, got {}", value_repr(a, &scorer)),
            detail(vec![("operator", J::from("defpop")), ("expected", J::from("Fn"))]),
            "pass a lambda from Program to Int as the first argument",
        ));
    }
    let mut variants: Vec<u32> = Vec::new();
    for k in &kids[1..] {
        let value = eval(a, rt, *k, false)?;
        if is_list(&value) {
            // A list of programs is spliced in (M18).
            for item in list_walk(&value) {
                variants.push(as_program(a, &item, "defpop")?);
            }
        } else {
            variants.push(as_program(a, &value, "defpop")?);
        }
    }
    if variants.is_empty() {
        return Err(domain(
            "domain-error",
            "defpop: a population needs at least one variant".to_string(),
            detail(vec![("operator", J::from("defpop"))]),
            "quote at least one program",
        ));
    }
    {
        let store = rt.lineage.clone();
        let mut store = store.borrow_mut();
        for variant in &variants {
            store.ensure_registered(a, *variant);
        }
    }
    Ok(Value::Population(Rc::new(PopulationData {
        scorer,
        variants,
        generation: 0,
    })))
}

/// One generation: the bottom fraction go, and each vacated slot is
/// refilled from the survivors with sharply fitness-weighted odds.
fn op_evolve(a: &mut Arena, rt: &mut Rt, id: u32) -> R<Value> {
    let k = a.kids(id)[0];
    let v = eval(a, rt, k, false)?;
    let pop = as_population(a, &v, "evolve")?;
    let size = pop.variants.len();
    if size < 2 {
        return Err(domain(
            "domain-error",
            "evolve: a population of one cannot evolve".to_string(),
            detail(vec![("operator", J::from("evolve")), ("size", J::from(size))]),
            "start with at least two variants",
        ));
    }
    let (scores, order) = rank_population(a, rt, &pop)?;
    let n_retire = std::cmp::max(1, (size as f64 * RETIRE_FRACTION) as usize);
    let survivors: Vec<usize> = order[..size - n_retire].to_vec();
    let cap: i128 = 1_000_000_000;
    let clamp: Vec<i128> = survivors
        .iter()
        .map(|i| std::cmp::min(small(&scores[*i]) as i128, cap))
        .collect();
    let worst_kept = *clamp.iter().max().unwrap();
    // SELECTION_SHARPNESS = 3.
    let weights: Vec<i128> = clamp
        .iter()
        .map(|c| {
            let d = worst_kept.saturating_sub(*c).saturating_add(1);
            d.saturating_mul(d).saturating_mul(d)
        })
        .collect();
    let total: i128 = weights.iter().fold(0i128, |acc, w| acc.saturating_add(*w));

    let store = rt.lineage.clone();
    let mut store = store.borrow_mut();
    let mut children: Vec<u32> = Vec::with_capacity(n_retire);
    for _ in 0..n_retire {
        let pick = store.rng.random() * total as f64;
        let mut acc = 0.0f64;
        let mut chosen = *survivors.last().unwrap();
        for (index, weight) in survivors.iter().zip(weights.iter()) {
            acc += *weight as f64;
            if pick <= acc {
                chosen = *index;
                break;
            }
        }
        let parent = pop.variants[chosen];
        if store.rng.random() < CLONE_PROBABILITY {
            children.push(store.clone_program(a, parent));
        } else {
            children.push(store.mutate_program(a, parent, EVOLVE_STRENGTH));
        }
    }
    let mut kept: Vec<u32> = pop
        .variants
        .iter()
        .enumerate()
        .filter(|(i, _)| survivors.contains(i))
        .map(|(_, v)| *v)
        .collect();
    kept.extend(children);
    Ok(Value::Population(Rc::new(PopulationData {
        scorer: pop.scorer.clone(),
        variants: kept,
        generation: pop.generation + 1,
    })))
}
