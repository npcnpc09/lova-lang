# lova-wasm -- the native runtime in a web page

`lova-rt` linked into a WebAssembly module.  The page speaks the same
protocol as the stdio binary and the Godot class
(`spec/native-runtime-protocol.md`); a request is a function call.

```bash
cd native/lova-wasm
cargo build --release --target wasm32-unknown-unknown
# target/wasm32-unknown-unknown/release/lova_wasm.wasm, ~1.8 MB, no imports
```

No wasm-bindgen.  The module exports `memory`, `lova_alloc(n)`,
`lova_free(p, n)`, `lova_request(p, len) -> reply pointer` and
`lova_reply_len()`.  `web/lova.js` wraps them:

```js
import { LovaRuntime } from "./lova.js";
const rt = await LovaRuntime.load("lova.wasm");          // a URL or the bytes
const s = rt.open(hex, { maxSteps: 2_000_000 });          // the program's bytes, as hex
const tick = s.get("tick");                               // {ref: n}
world = s.call(tick, [world, input]);                     // data, or {ref: n}
s.release([oldWorld]);
```

Values cross as the protocol encodes them: an integer a Number (past
2^53 `{int: "digits"}`), a text a String, a list an Array, nil null,
anything else a `{ref: id}`.  A fraction is refused before it is sent.
A trap throws `LovaFault` with the anomaly; the session stays open.

**What a page does not have.** Files, the clock and the network:
`fs-read`, `fs-write`, `clock`, `net-send`, `net-recv` are refused by
name, as are `read` / `explain` (every native build).  The page grants
no capability.  Deep recursion meets the browser's own stack well
before the runtime's ten-thousand-call ceiling (Q147); a panic ends the
instance, so a host that must survive one loads a fresh instance.

**Checked against the golden set** through `stdio.mjs`, which carries
the module over stdin/stdout the way the binary is carried:

```bash
python tools/conformance.py --runtime "node --stack-size=60000 native/lova-wasm/stdio.mjs"
```

Every in-scope record matches, value and step count.
