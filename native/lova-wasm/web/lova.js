// lova.js -- the page side of native/lova-wasm.
//
// The native-runtime protocol (spec/native-runtime-protocol.md) with a
// function call as its carrier: a request is JSON written into the
// module's memory, the reply JSON read back.  `LovaRuntime` keeps the
// shape of the Godot class: open / get / call / release / close.
//
//   const rt = await LovaRuntime.load("lova.wasm");      // or bytes
//   const s = rt.open(hex, {maxSteps: 5e6});
//   const tick = s.get("tick");                           // {ref: n}
//   world = s.call(tick, [world, input]);                 // data or {ref}
//
// A value crosses as the protocol encodes it: an integer a Number (an
// {int: "digits"} past 2^53), a text a String, a list an Array, nil
// null, anything else a {ref: id} the session holds.  A fraction is
// refused before it leaves the page: LOVA has no floating point.

const enc = new TextEncoder();
const dec = new TextDecoder();

export class LovaFault extends Error {
  constructor(reply) {
    const a = reply.anomaly;
    super(a ? `${a.kind || a.code}: ${a.message || JSON.stringify(a)}` : (reply.error || "LOVA fault"));
    this.reply = reply;
    this.anomaly = a || null;
  }
}

function checkNumbers(v, where) {
  if (typeof v === "number" && !Number.isInteger(v))
    throw new TypeError(`${where}: ${v} is not an integer -- LOVA has no floating point`);
  if (Array.isArray(v)) v.forEach((x, i) => checkNumbers(x, `${where}[${i}]`));
}

export class LovaRuntime {
  static async load(source) {
    let module;
    if (source instanceof ArrayBuffer || ArrayBuffer.isView(source)) {
      module = await WebAssembly.compile(source);
    } else if (typeof WebAssembly.compileStreaming === "function" && typeof fetch === "function") {
      const res = await fetch(source);
      module = await WebAssembly.compileStreaming(res).catch(async () =>
        WebAssembly.compile(await (await fetch(source)).arrayBuffer()));
    } else {
      throw new Error("LovaRuntime.load: give the module's bytes");
    }
    const instance = await WebAssembly.instantiate(module, {});
    return new LovaRuntime(instance.exports);
  }

  constructor(exports) {
    this.x = exports;
    this.id = 0;
  }

  // One protocol request, one reply.
  request(obj) {
    const x = this.x;
    const bytes = enc.encode(JSON.stringify(obj));
    const p = x.lova_alloc(bytes.length);
    new Uint8Array(x.memory.buffer, p, bytes.length).set(bytes);
    const r = x.lova_request(p, bytes.length);
    x.lova_free(p, bytes.length);
    const n = x.lova_reply_len();
    // Copy out before decoding: memory.buffer may grow under the view.
    return JSON.parse(dec.decode(new Uint8Array(x.memory.buffer, r, n).slice()));
  }

  ping() { return this.request({ op: "ping" }); }

  open(hex, { maxSteps = 5_000_000, maxDepth = 10_000 } = {}) {
    const reply = this.request({ id: ++this.id, op: "session", bytes: hex,
                                 allow: 0, max_steps: maxSteps, max_depth: maxDepth });
    if (!reply.ok) throw new LovaFault(reply);
    return new LovaSession(this, reply);
  }
}

export class LovaSession {
  constructor(rt, reply) {
    this.rt = rt;
    this.sid = reply.session;
    this.value = reply.value;
    this.steps = reply.steps;
    this.stdout = reply.stdout || "";
  }

  _ask(obj) {
    const reply = this.rt.request({ id: ++this.rt.id, session: this.sid, ...obj });
    if (!reply.ok) throw new LovaFault(reply);
    return reply;
  }

  // A field of the program's value, or of any map the session holds.
  get(key, of = this.value) {
    return this._ask({ op: "get", ref: of.ref, key }).value;
  }

  call(fn, args, maxSteps) {
    checkNumbers(args, "call");
    const req = { op: "call", fn, args };
    if (maxSteps) req.max_steps = maxSteps;
    const reply = this._ask(req);
    this.steps = reply.steps;
    this.stdout = reply.stdout || "";
    return reply.value;
  }

  release(refs) {
    const ids = refs.filter(r => r && typeof r === "object" && "ref" in r).map(r => r.ref);
    if (ids.length) this._ask({ op: "release", refs: ids });
  }

  close() { this._ask({ op: "close" }); }
}
