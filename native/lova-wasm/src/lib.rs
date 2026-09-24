//! LOVA in the browser.
//!
//! `lova-rt` linked into a WebAssembly module, speaking the
//! native-runtime protocol (`spec/native-runtime-protocol.md`) as
//! `native/lova-godot` does -- in-process, a request a function call.
//! No wasm-bindgen: the page writes a request's JSON into memory it got
//! from `lova_alloc`, calls `lova_request`, and reads the reply from
//! the pointer and length it is given back.  `web/lova.js` is that page
//! side.
//!
//! The target has no files, clock or network: a program asking for one
//! is refused by its boundary, since the page grants nothing (`allow`
//! 0), and `read` / `explain` / the network are out of scope as in
//! every native build.

use lova_rt::server::{handle_line, Sessions};
use std::cell::RefCell;

struct Host {
    sessions: Sessions,
    next: u64,
    reply: Vec<u8>,
}

thread_local! {
    static HOST: RefCell<Host> = RefCell::new(Host {
        sessions: Sessions::new(),
        next: 0,
        reply: Vec::new(),
    });
}

/// `n` bytes the page may write a request into.
#[no_mangle]
pub extern "C" fn lova_alloc(n: usize) -> *mut u8 {
    let mut buf = Vec::<u8>::with_capacity(n.max(1));
    let p = buf.as_mut_ptr();
    std::mem::forget(buf);
    p
}

/// Give back what `lova_alloc(n)` handed out.
#[no_mangle]
pub unsafe extern "C" fn lova_free(p: *mut u8, n: usize) {
    drop(Vec::from_raw_parts(p, 0, n.max(1)));
}

/// Answer the request of `len` bytes at `p` (UTF-8 JSON, one protocol
/// object).  The reply stays valid until the next request; its length
/// is `lova_reply_len()`.
#[no_mangle]
pub unsafe extern "C" fn lova_request(p: *const u8, len: usize) -> *const u8 {
    let bytes = std::slice::from_raw_parts(p, len);
    let line = String::from_utf8_lossy(bytes);
    HOST.with(|h| {
        let mut h = h.borrow_mut();
        let Host { sessions, next, .. } = &mut *h;
        let reply = handle_line(&line, sessions, next).to_string();
        h.reply = reply.into_bytes();
        h.reply.as_ptr()
    })
}

#[no_mangle]
pub extern "C" fn lova_reply_len() -> usize {
    HOST.with(|h| h.borrow().reply.len())
}
