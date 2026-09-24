// rules.js -- the game's rules, which are LOVA (lib/neon.lova), held
// in a session of the runtime compiled to WebAssembly.  The page never
// decides anything: it asks `tick` what happens and `scene` what to
// draw, and turns fixed-point integers into metres.

import { LovaRuntime } from "./lova.js";

export const F = 65536;          // a metre, in the rules' units

export class Rules {
  static async load() {
    const [rt, hex] = await Promise.all([
      LovaRuntime.load("lova.wasm"),
      fetch("neon.hex").then(r => r.text()),
    ]);
    return new Rules(rt, hex.trim());
  }

  constructor(rt, hex) {
    this.rt = rt;
    this.version = rt.ping().version;
    const t0 = performance.now();
    this.s = rt.open(hex, { maxSteps: 2_000_000 });
    this.openMs = performance.now() - t0;
    this.bytes = hex.length / 2;
    const s = this.s;
    this.fn = { tick: s.get("tick"), scene: s.get("scene"), input: s.get("input") };

    // What never moves, read once.
    const lay = s.get("layout");
    this.layout = {
      halfW: s.get("half-w", lay) / F,
      length: s.get("length", lay) / F,
      gate: s.get("gate", lay) / F,
      droneY: s.get("drone-y", lay) / F,
      sparks: s.get("sparks", lay).map(([x, y, z]) => ({ x: x / F, y: y / F, z: z / F })),
      drones: s.get("drones", lay).map(z => z / F),
    };
    s.release([lay]);

    // The eighteen things the keys can say, made once and kept, so a
    // tick sends a handle and not a record.
    this.inputs = new Map();
    for (const mx of [-1, 0, 1]) for (const mz of [-1, 0, 1]) for (const j of [0, 1])
      this.inputs.set(`${mx},${mz},${j}`, s.call(this.fn.input, [mx, mz, j]));

    this.lastSteps = 0;
    this.lastMs = 0;
    this.reset();
  }

  reset() {
    if (this.world) this.s.release([this.world]);
    this.world = this.s.get("new");
    this.state = this.read();
  }

  // One sixtieth of a second.
  tick(mx, mz, jump) {
    const t0 = performance.now();
    const next = this.s.call(this.fn.tick, [this.world, this.inputs.get(`${mx},${mz},${jump}`)]);
    const steps = this.s.steps;
    if (next.ref !== this.world.ref) this.s.release([this.world]);
    this.world = next;
    this.state = this.read();
    this.lastSteps = steps + this.s.steps;
    this.lastMs = performance.now() - t0;
    return this.state;
  }

  read() {
    const [g, drones, sparks] = this.s.call(this.fn.scene, [this.world]);
    const [x, y, z, vx, vz, stun, landed, jumped, left, hits, won, t, took, struck] = g;
    return {
      ghost: { x: x / F, y: y / F, z: z / F, vx: vx * 60 / F, vz: vz * 60 / F, stun, landed, jumped },
      left, hits, won, t, took, struck,
      drones: drones.map(dx => dx / F),
      sparks,
    };
  }
}
