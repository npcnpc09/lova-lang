"""A compiled program, kept on disk, so a run does not pay for the parse twice.

The native runtime (M33) made the Python side's parse and compile the
larger half of a run's wall clock: `tools/bench_native.py` prints a
``floor`` column -- what ``lova analyze`` costs, which is parse plus
compile and nothing else -- and for the 3D libraries, where one
``(use "citybuilder")`` pulls in thousands of lines, that floor is one
to two seconds against an evaluator that now finishes in a third of
one.  Q125: cache it.

The unit is ``core.cli.build`` -- source text in, ``(tree, report)``
out -- so every caller of it wins at once: ``lova run``, ``lova
check``, ``lova analyze``, the MCP server, the apps' drivers.

**The key** is a SHA-256 over

* the source *after* ``expand_uses``, so editing a library a program
  uses changes the key of every program that uses it;
* the three flags that change what ``build`` does (``prelude``,
  ``stage2``, ``do_compile``);
* a *core fingerprint*: the contents of every ``core/*.py`` and of
  ``lib/prelude.lova``, hashed once per process.  A change to the
  parser, the compiler or the standard library therefore invalidates
  every entry that exists, which is the only honest way to cache the
  output of code that is itself under development.

**The value** is the built tree exactly as ``build`` returns it --
source spans, ``symbols`` table, examples and all -- pickled with the
report beside it.  ``pickle`` is the stdlib's and the tree is plain
data; ``tests/test_cache.py`` pins the round trip (the byte encoding,
the spans, the symbol table) and ``tests/test_diagnostics.py`` that a
trap in a cached program still reports the same ``at: line:col``.

**Where**: ``$LOVA_CACHE`` if it is set, else ``%LOCALAPPDATA%\\lova\\cache``
on Windows and ``~/.cache/lova`` elsewhere.  ``LOVA_CACHE=off``
disables it.  One file per key, named by the key's hex, written to a
temporary name in the same directory and moved into place, so a reader
never sees half an entry.

**What it never does is fail a build.**  Every path here is wrapped:
an unreadable directory, a truncated file, a pickle that cannot be
loaded, a tree too deep for ``pickle``'s recursion limit -- each of
them means "no cache", and the build proceeds as if there were none.
An entry that cannot be unpickled is deleted on the way past.

**Size**: there is no eviction.  Entries are small (a megabyte for the
largest of the 3D libraries) and a stale one is never read, because
the key names its inputs; a directory that has grown unwelcome is
deleted, and nothing is lost but the time to build again.  Trivial
builds are not written at all -- an entry is stored only when the
build took at least ``LOVA_CACHE_MIN_MS`` milliseconds (50 by
default), which keeps the thousands of one-line programs a test run or
a generation experiment builds out of the directory, where reading the
entry would have cost more than the parse.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
from typing import Any, Optional, Tuple


CACHE_VERSION = "1"

_fingerprint: Optional[str] = None


def _core_fingerprint() -> str:
    """A hash of the implementation itself: every ``core/*.py`` and the
    prelude.  Computed once per process."""
    global _fingerprint
    if _fingerprint is not None:
        return _fingerprint
    digest = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    paths = sorted(
        os.path.join(here, name) for name in os.listdir(here)
        if name.endswith(".py")
    )
    paths.append(os.path.join(root, "lib", "prelude.lova"))
    for path in paths:
        digest.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as handle:
            digest.update(handle.read())
    _fingerprint = digest.hexdigest()
    return _fingerprint


def cache_dir() -> Optional[str]:
    """Where entries live, or ``None`` when the cache is off."""
    named = os.environ.get("LOVA_CACHE")
    if named is not None:
        named = named.strip()
        if named.lower() in ("off", "0", "none") or not named:
            return None
        return named
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return os.path.join(local, "lova", "cache")
    return os.path.join(os.path.expanduser("~"), ".cache", "lova")


def _min_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("LOVA_CACHE_MIN_MS", "50")) / 1000.0)
    except ValueError:
        return 0.05


def key_for(source: str, *, prelude: bool, stage2: bool,
            do_compile: bool) -> Optional[str]:
    """The key of this build, or ``None`` if there is to be no cache."""
    if cache_dir() is None:
        return None
    try:
        if stage2:
            expanded = source          # the Stage-2 surface has no `use` form
        else:
            from core.surface import expand_uses
            expanded = expand_uses(source)
        digest = hashlib.sha256()
        digest.update(b"lova-build-" + CACHE_VERSION.encode("ascii"))
        digest.update(_core_fingerprint().encode("ascii"))
        digest.update(f"|{int(prelude)}{int(stage2)}{int(do_compile)}|".encode("ascii"))
        digest.update(expanded.encode("utf-8", "surrogatepass"))
        return digest.hexdigest()
    except Exception:                  # noqa: BLE001 -- a key is a courtesy
        return None


def _path(key: str) -> Optional[str]:
    directory = cache_dir()
    if directory is None:
        return None
    return os.path.join(directory, key + ".pkl")


def load(key: str) -> Optional[Tuple[Any, Any]]:
    """The entry for ``key``, or ``None``.  A corrupt entry is deleted."""
    path = _path(key)
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            blob = handle.read()
    except OSError:
        return None
    try:
        value = pickle.loads(blob)
    except RecursionError:
        # A tree too deep for pickle to walk; it was written by a
        # process with a taller stack.  Leave it, and build.
        return None
    except Exception:                  # noqa: BLE001 -- truncated, or from another world
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    if not (isinstance(value, tuple) and len(value) == 2):
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    return value


def store(key: str, value: Tuple[Any, Any], elapsed: float = 1.0) -> bool:
    """Write an entry.  ``True`` if it landed; every failure is silent.

    ``elapsed`` is what the build cost: a build cheaper than
    ``LOVA_CACHE_MIN_MS`` is not worth a file.
    """
    if elapsed < _min_seconds():
        return False
    path = _path(key)
    if path is None:
        return False
    directory = os.path.dirname(path)
    try:
        blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:                  # noqa: BLE001 -- RecursionError on a deep tree, mostly
        return False
    handle = None
    temp = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".pkl")
        handle = os.fdopen(fd, "wb")
        handle.write(blob)
        handle.close()
        handle = None
        os.replace(temp, path)          # atomic: no reader sees a half-written entry
        temp = None
        return True
    except Exception:                  # noqa: BLE001 -- a cache that cannot write is no cache
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if temp is not None:
            try:
                os.remove(temp)
            except OSError:
                pass
        return False


def clear() -> int:
    """Delete every entry; the number removed.  For the tests and for a
    human who wants the directory back."""
    directory = cache_dir()
    if directory is None or not os.path.isdir(directory):
        return 0
    removed = 0
    for name in os.listdir(directory):
        if not name.endswith(".pkl"):
            continue
        try:
            os.remove(os.path.join(directory, name))
            removed += 1
        except OSError:
            pass
    return removed
