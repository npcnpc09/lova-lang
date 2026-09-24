"""Assemble Neon Alley: the page, the runtime, the rules.

    python apps/web/neon/build.py [--no-cargo] [--serve [PORT]]

What it makes, in `apps/web/neon/site/` (not tracked):

- `web/`'s page -- `index.html`, the three.js scene and its modules --
  copied as they are;
- `lova.wasm`, the native runtime compiled to WebAssembly by
  `cargo build --release --target wasm32-unknown-unknown` in
  `native/lova-wasm`, and `lova.js`, the page side of its protocol;
- `neon.hex`: `neon_web.lova` (which is `lib/neon.lova` and the record
  the page takes its functions from) parsed, expanded, compiled and
  encoded to its byte sequence.

The page needs no build step of its own: three.js comes from a CDN by
an import map, and the modules are plain ES modules.  It must be served
over http (a browser will not fetch a .wasm from file://): `--serve`
does that on localhost, port 8765 unless one is given.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.tokens import encode  # noqa: E402

SITE = HERE / "site"
PAGE = HERE / "web"
CRATE = ROOT / "native" / "lova-wasm"
WASM = CRATE / "target" / "wasm32-unknown-unknown" / "release" / "lova_wasm.wasm"


def compile_program() -> str:
    source = (HERE / "neon_web.lova").read_text(encoding="utf-8")
    tree, _report = build(source)
    data = encode(tree)
    print(f"  neon_web.lova -> {len(data)} bytes")
    return data.hex()


def cargo() -> None:
    print("  cargo build --release --target wasm32-unknown-unknown")
    subprocess.run(["cargo", "build", "--release", "--target", "wasm32-unknown-unknown"],
                   cwd=CRATE, check=True)


def assemble(run_cargo: bool) -> None:
    if run_cargo:
        cargo()
    if not WASM.exists():
        raise SystemExit(f"no {WASM.name}: run without --no-cargo, or build native/lova-wasm")
    # Empty it rather than remove it: a server may be standing in it.
    SITE.mkdir(exist_ok=True)
    for p in SITE.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(PAGE, SITE, dirs_exist_ok=True)
    shutil.copy2(WASM, SITE / "lova.wasm")
    shutil.copy2(CRATE / "web" / "lova.js", SITE / "lova.js")
    (SITE / "neon.hex").write_text(compile_program(), encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"  site/ -> {size / 1024:.0f} KiB ({(SITE / 'lova.wasm').stat().st_size / 1024:.0f} KiB of it the runtime)")


def serve(port: int) -> None:
    import http.server
    import functools

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".wasm": "application/wasm", ".js": "text/javascript"}

        def log_message(self, *args):  # quiet
            pass

    handler = functools.partial(Handler, directory=str(SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"  http://127.0.0.1:{port}/")
        httpd.serve_forever()


def main(argv: list[str]) -> None:
    assemble(run_cargo="--no-cargo" not in argv)
    if "--serve" in argv:
        i = argv.index("--serve")
        port = int(argv[i + 1]) if i + 1 < len(argv) and argv[i + 1].isdigit() else 8765
        serve(port)


if __name__ == "__main__":
    main(sys.argv[1:])
