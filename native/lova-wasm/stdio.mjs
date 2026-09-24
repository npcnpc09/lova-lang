// The wasm module as a stdio runtime, so tools/conformance.py can hold
// it to the golden set exactly as it holds the native binary:
//
//   python tools/conformance.py --runtime "node native/lova-wasm/stdio.mjs"
import { readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { LovaRuntime } from "./web/lova.js";

const here = fileURLToPath(new URL(".", import.meta.url));
const wasm = readFileSync(here + "target/wasm32-unknown-unknown/release/lova_wasm.wasm");
let rt = await LovaRuntime.load(wasm);
const lines = createInterface({ input: process.stdin });
for await (const line of lines) {
  if (!line.trim()) continue;
  let reply;
  try {
    reply = rt.request(JSON.parse(line));
  } catch (e) {
    reply = { ok: false, error: `wasm: ${e.message}` };
    // A trap (a Rust panic is `unreachable`) leaves the instance
    // unusable: start a fresh one, so one record cannot fail the rest.
    rt = await LovaRuntime.load(wasm);
  }
  process.stdout.write(JSON.stringify(reply) + "\n");
}
