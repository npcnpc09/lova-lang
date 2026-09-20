//! `lova-rt` as a library: the byte sequence evaluated step for step
//! as `core/runtime.py` does, behind the protocol in `server.rs`.  The
//! binary in `main.rs` carries that protocol over stdio; a host that
//! links this crate calls `server::handle` directly.

pub mod alloc;
pub mod conserve;
pub mod evolve;
pub mod fx;
pub mod int;
pub mod lineage;
pub mod meta;
pub mod nt;
#[cfg(feature = "prof")]
pub mod prof;
pub mod rng;
pub mod rt;
pub mod session;
pub mod text;
pub mod tokens;
pub mod tokens_table;
pub mod trap;
pub mod value;
pub mod vm;
pub mod server;
