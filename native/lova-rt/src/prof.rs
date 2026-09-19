//! A sampling profiler for the evaluator, built only under
//! `--features prof` (Q124).
//!
//! Windows has no `perf` and the flame-graph back ends want
//! administrator rights, so the evaluator samples itself: it writes the
//! operator it has just entered into one relaxed atomic, and a spinning
//! thread reads that word every ~40us and histograms it.  The two
//! stores cost about a nanosecond a node against ~300, and what comes
//! out is self time per operator -- the time inside an operator's own
//! handler and everything it does before it evaluates a child.

use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};

pub static SLOT: AtomicU32 = AtomicU32::new(NONE);
static RUNNING: AtomicBool = AtomicBool::new(false);

pub const NONE: u32 = 0xFFFF;
/// Regions that are not an operator.
pub const R_CALL: u32 = 0x100;
pub const R_LOOKUP: u32 = 0x101;
pub const R_MAPKEY: u32 = 0x102;
pub const R_REROOT: u32 = 0x103;
pub const R_DROP: u32 = 0x104;
/// The VM's dispatch loop: fetch, stack traffic, loads and stores.
pub const R_VMLOOP: u32 = 0x110;
pub const R_VM_TICK: u32 = 0x111;
pub const R_VM_LOAD: u32 = 0x112;
pub const R_VM_STACK: u32 = 0x113;
pub const R_VM_CALL: u32 = 0x114;
pub const R_VM_CLOSURE: u32 = 0x115;
pub const R_VM_RET: u32 = 0x116;
pub const R_VM_EXIT: u32 = 0x117;
pub const R_VM_DROP: u32 = 0x118;
pub const R_VM_ENTER: u32 = 0x119;
pub const R_VM_MAPGET: u32 = 0x11A;

#[inline(always)]
pub fn mark(what: u32) {
    SLOT.store(what, Ordering::Relaxed);
}

pub fn region_name(code: u32) -> String {
    match code {
        NONE => "(outside the evaluator)".to_string(),
        R_CALL => "call: frame setup".to_string(),
        R_LOOKUP => "scope lookup".to_string(),
        R_MAPKEY => "map key".to_string(),
        R_REROOT => "map reroot".to_string(),
        R_DROP => "value drop".to_string(),
        R_VMLOOP => "vm: dispatch (fetch and branch)".to_string(),
        R_VM_TICK => "vm: tick".to_string(),
        R_VM_LOAD => "vm: load / const".to_string(),
        R_VM_STACK => "vm: store, pop, jump, coerce".to_string(),
        R_VM_CALL => "vm: call instruction".to_string(),
        R_VM_CLOSURE => "vm: make closure".to_string(),
        R_VM_RET => "vm: the return itself".to_string(),
        R_VM_EXIT => "vm: activation teardown".to_string(),
        R_VM_DROP => "vm: dropping the activation's values".to_string(),
        R_VM_ENTER => "vm: activation setup".to_string(),
        R_VM_MAPGET => "vm: map lookup (hash, probe, reroot)".to_string(),
        op if op < 0x100 => format!("{} (0x{:02x})", crate::tokens::op_name(op as u8), op),
        other => format!("region {}", other),
    }
}

/// Start the sampler; it runs until the process ends.
pub fn start() {
    if std::env::var("LOVA_PROF").unwrap_or_default().is_empty() {
        return;
    }
    RUNNING.store(true, Ordering::Relaxed);
    std::thread::spawn(|| {
        let mut counts = vec![0u64; 0x200];
        let mut total = 0u64;
        let tick = std::time::Duration::from_micros(40);
        let mut next = std::time::Instant::now();
        while RUNNING.load(Ordering::Relaxed) {
            while std::time::Instant::now() < next {
                std::hint::spin_loop();
            }
            next += tick;
            let slot = SLOT.load(Ordering::Relaxed);
            if slot != NONE {
                counts[(slot as usize).min(0x1FF)] += 1;
                total += 1;
            }
        }
        let mut rows: Vec<(usize, u64)> =
            counts.iter().enumerate().map(|(i, n)| (i, *n)).filter(|(_, n)| *n > 0).collect();
        rows.sort_by(|a, b| b.1.cmp(&a.1));
        eprintln!("--- sampling profile: {} samples inside the evaluator", total);
        for (code, n) in rows.iter().take(25) {
            eprintln!(
                "{:>6.2}%  {:>8}  {}",
                100.0 * *n as f64 / total.max(1) as f64,
                n,
                region_name(*code as u32)
            );
        }
    });
}

pub fn stop() {
    RUNNING.store(false, Ordering::Relaxed);
    // let the sampler print before the process leaves
    std::thread::sleep(std::time::Duration::from_millis(120));
}
