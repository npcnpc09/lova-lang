//! A size-class free list in front of the system allocator.
//!
//! The evaluator's working set is a cons cell, a closure, a frame or a
//! small vector at a time, and it makes tens of millions of them in a
//! run.  On Windows every one of those is a `HeapAlloc` with a lock in
//! it, and the sampler put a fifth of the city builder's frame in the
//! activation teardown -- which is mostly freeing what the activation
//! made.
//!
//! `mimalloc` would be the obvious answer, and is what was tried first:
//! it needs a C compiler, and this host's Rust is the `windows-gnu`
//! toolchain whose bundled mingw is a linker only (`cannot execute
//! cc1`).  So the same idea, in Rust and in the crate: blocks up to 256
//! bytes are carved from 256 KiB chunks in sixteen size classes and
//! recycled through a free list; everything else goes straight to the
//! system.  Memory is never returned to the OS, which for a process
//! that runs a program and exits is the point.
//!
//! The lists are global behind a spin lock rather than per thread:
//! `thread_local!` allocates on first touch on this target, which in a
//! global allocator is unbounded recursion.  Two threads exist (the
//! reader and the evaluator) and one of them does all the allocating,
//! so the lock is uncontended.  Every borrow of the pool lives strictly
//! inside one hold of that lock, the hold is released by a guard (so a
//! panic cannot leave it taken), and the system allocation that refills
//! a chunk happens outside it.
//!
//! It changes no value, no step and no anomaly: `tools/differential.py`
//! and the golden set are the check.

use std::alloc::{GlobalAlloc, Layout, System};
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};

/// Blocks are a multiple of this, and this is the alignment they get.
const GRAIN: usize = 16;
/// 16, 32, ... 256 bytes.
const CLASSES: usize = 16;
const MAX_SMALL: usize = CLASSES * GRAIN;
/// One system allocation feeds thousands of blocks.
const CHUNK: usize = 256 * 1024;

struct Pool {
    free: [*mut u8; CLASSES],
    bump: *mut u8,
    left: usize,
}

static LOCK: AtomicBool = AtomicBool::new(false);
static mut POOL: Pool = Pool { free: [ptr::null_mut(); CLASSES], bump: ptr::null_mut(), left: 0 };

/// The lock, released when it goes out of scope -- including by an
/// unwind, so a panic anywhere cannot leave the allocator taken.
struct Hold;

impl Drop for Hold {
    #[inline]
    fn drop(&mut self) {
        LOCK.store(false, Ordering::Release);
    }
}

#[inline]
fn hold() -> Hold {
    while LOCK
        .compare_exchange_weak(false, true, Ordering::Acquire, Ordering::Relaxed)
        .is_err()
    {
        std::hint::spin_loop();
    }
    Hold
}

/// `None` for anything the pool does not serve.
#[inline]
fn index_of(layout: Layout) -> Option<usize> {
    if layout.align() <= GRAIN && layout.size() <= MAX_SMALL {
        // A zero-sized request still gets a block, so its pointer is
        // unique and `dealloc` can put it back.
        Some(layout.size().saturating_sub(1) / GRAIN)
    } else {
        None
    }
}

pub struct Pooled;

unsafe impl GlobalAlloc for Pooled {
    #[inline]
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let index = match index_of(layout) {
            Some(i) => i,
            None => return System.alloc(layout),
        };
        let want = (index + 1) * GRAIN;
        {
            let _taken = hold();
            // The borrow lives and dies inside this hold.
            let pool = &mut *ptr::addr_of_mut!(POOL);
            let head = pool.free[index];
            if !head.is_null() {
                pool.free[index] = *(head as *mut *mut u8);
                return head;
            }
            if pool.left >= want {
                let at = pool.bump;
                pool.bump = at.add(want);
                pool.left -= want;
                return at;
            }
        }
        // Out of chunk: ask the system with the lock free, then install
        // what is left of the new chunk under a fresh hold.
        let chunk = System.alloc(Layout::from_size_align_unchecked(CHUNK, GRAIN));
        if chunk.is_null() {
            // A block the system did not give cannot be recycled as a
            // pool block: `dealloc` would write a pointer into it.
            return ptr::null_mut();
        }
        let at = chunk;
        let bump = chunk.add(want);
        let left = CHUNK - want;
        let _taken = hold();
        let pool = &mut *ptr::addr_of_mut!(POOL);
        // Another thread may have refilled while this one was asking.
        // The block is this thread's either way; the chunk with more
        // room left becomes the pool's, and only the remainder of the
        // other is abandoned (at most one chunk, and only on a race).
        if pool.left < left {
            pool.bump = bump;
            pool.left = left;
        }
        at
    }

    #[inline]
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        match index_of(layout) {
            Some(index) => {
                let _taken = hold();
                let pool = &mut *std::ptr::addr_of_mut!(POOL);
                *(ptr as *mut *mut u8) = pool.free[index];
                pool.free[index] = ptr;
            }
            None => System.dealloc(ptr, layout),
        }
    }
}
