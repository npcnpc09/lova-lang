//! `spec/native-runtime-protocol.md`: one JSON request per line in, one
//! JSON reply per line out.  Nothing else goes on stdout.  The protocol
//! itself is `lova_rt::server`; this is the stdio carrier.

use lova_rt::server::{choose_evaluator, handle_line, Sessions};
use std::io::{BufRead, Write};

/// Small allocations -- a cons cell, a closure, a frame -- go through
/// a size-class free list instead of the system heap (`alloc.rs`).
#[global_allocator]
static ALLOCATOR: lova_rt::alloc::Pooled = lova_rt::alloc::Pooled;

fn main() {
    choose_evaluator();
    // A LOVA call is several Rust frames, and the depth ceiling is ten
    // thousand calls; the main thread's stack is not enough.
    #[cfg(feature = "prof")]
    lova_rt::prof::start();
    let worker = std::thread::Builder::new()
        .stack_size(1 << 30)
        .spawn(serve)
        .expect("failed to start the evaluator thread");
    let code = worker.join().unwrap_or(1);
    #[cfg(feature = "prof")]
    lova_rt::prof::stop();
    std::process::exit(code);
}

fn serve() -> i32 {
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    let mut sessions: Sessions = Sessions::new();
    let mut next_session: u64 = 0;
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let reply = handle_line(line, &mut sessions, &mut next_session);
        if writeln!(out, "{}", reply).is_err() {
            break;
        }
        if out.flush().is_err() {
            break;
        }
    }
    0
}

