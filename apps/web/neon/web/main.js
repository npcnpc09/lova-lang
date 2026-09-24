// main.js -- Neon Alley.  The rules tick sixty times a second in LOVA;
// between ticks the picture interpolates, and everything the player
// sees or hears is a reaction to what a tick reported.

import * as THREE from "three";
import { Rules } from "./rules.js";
import { buildWorld, buildGate, X } from "./world.js";
import { Ghost, Sparks, Drones, Particles } from "./actors.js";
import { pickQuality, makeRenderer, makeComposer, Rain } from "./fx.js";
import { Sound } from "./audio.js";

const $ = id => document.getElementById(id);
const TICK = 1 / 60;

function fault(e) {
  console.error(e);
  $("fault").classList.remove("hidden");
  $("fault-text").textContent = (e && e.anomaly) ? JSON.stringify(e.anomaly, null, 2) : String(e && e.stack || e);
}

async function boot() {
  const quality = pickQuality();
  const renderer = makeRenderer($("view"), quality);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(58, window.innerWidth / window.innerHeight, 0.1, 160);

  const rules = await Rules.load();
  const L = rules.layout;

  const world = buildWorld(scene, L, quality);
  const gate = buildGate(scene, L);
  const particles = new Particles(scene);
  const ghost = new Ghost(scene, particles);
  const sparks = new Sparks(scene, L.sparks, particles);
  const drones = new Drones(scene, L.drones, L.droneY);
  const rain = new Rain(scene, quality.rain);
  const post = makeComposer(renderer, scene, camera);
  const sound = new Sound();

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    post.resize();
    particles.material.uniforms.scale.value = window.innerHeight / 2;
  });

  // --- input -----------------------------------------------------------
  const held = new Set();
  const KEYS = { KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down", KeyA: "left", ArrowLeft: "left",
    KeyD: "right", ArrowRight: "right", Space: "jump" };
  addEventListener("keydown", e => {
    if (KEYS[e.code]) { held.add(KEYS[e.code]); e.preventDefault(); }
    if (e.code === "KeyR" && mode === "play") restart();
    if (e.code === "KeyM") sound.toggle();
    if ((e.code === "Enter" || e.code === "Space") && mode === "title" && !$("start").disabled) begin();
    if ((e.code === "Enter") && mode === "won") restart();
  });
  addEventListener("keyup", e => { if (KEYS[e.code]) held.delete(KEYS[e.code]); });
  addEventListener("blur", () => held.clear());
  const touchy = matchMedia("(pointer: coarse)").matches;
  for (const b of document.querySelectorAll("#touch button")) {
    const k = b.dataset.k;
    b.addEventListener("pointerdown", e => { held.add(k); b.classList.add("on"); e.preventDefault(); });
    for (const ev of ["pointerup", "pointerleave", "pointercancel"])
      b.addEventListener(ev, () => { held.delete(k); b.classList.remove("on"); });
  }
  const stick = () => [
    (held.has("right") ? 1 : 0) - (held.has("left") ? 1 : 0),
    (held.has("up") ? 1 : 0) - (held.has("down") ? 1 : 0),
    held.has("jump") ? 1 : 0,
  ];

  // --- game state --------------------------------------------------------
  let mode = "title";          // title | play | won
  let prev = rules.state, cur = rules.state;
  let acc = 0, toastTimer = 0, hitPulse = 0;
  let wasOpen = false, collected = 0;

  function toast(text, secs = 1.8) {
    $("toast").textContent = text;
    $("toast").classList.add("on");
    toastTimer = secs;
  }

  function begin() {
    mode = "play";
    $("title").classList.add("hidden");
    $("hud").classList.remove("hidden");
    if (touchy) $("touch").classList.remove("hidden");
    sound.start();
    toast("收集全部火花", 2.2);
  }

  function restart() {
    rules.reset();
    prev = cur = rules.state;
    sparks.reset();
    wasOpen = false; collected = 0; acc = 0;
    mode = "play";
    $("win").classList.add("hidden");
    toast("RESTART", 1);
  }

  $("start").addEventListener("click", begin);
  $("again").addEventListener("click", restart);

  // What a tick reported, turned into sights and sounds.
  function react(s) {
    if (s.ghost.jumped) { ghost.jumped(); sound.jump(); }
    if (s.ghost.landed) { ghost.landed(); sound.land(); }
    if (s.took > 0) { for (let k = 0; k < s.took; k++) sound.spark(collected++); }
    if (s.struck) {
      ghost.struck(); sound.hit(); hitPulse = 1;
      particles.burst({ x: X(s.ghost.x), y: s.ghost.y + 0.6, z: s.ghost.z }, 0xff2a3a, 50, 5, { life: 0.6, size: 0.2 });
    }
    const open = s.left === 0;
    if (open && !wasOpen) { toast("GATE OPEN"); sound.gate(); }
    wasOpen = open;
    if (s.won && mode === "play") {
      mode = "won";
      sound.win();
      $("win-time").textContent = (s.t / 60).toFixed(2);
      $("win-hits").textContent = s.hits;
      setTimeout(() => $("win").classList.remove("hidden"), 700);
      const p = { x: X(s.ghost.x), y: 1.2, z: s.ghost.z + 1 };
      particles.burst(p, 0x7dff6a, 120, 7, { life: 1.4, size: 0.25 });
      particles.burst(p, 0x3ff2ff, 80, 5, { life: 1.2, size: 0.2 });
    }
  }

  // --- the loop ------------------------------------------------------
  const clock = new THREE.Clock();
  const camPos = new THREE.Vector3(0, 3, -6), camLook = new THREE.Vector3(0, 1, 4);
  camera.position.copy(camPos);
  let frames = 0, fpsT = 0, fps = 60, slow = 0, tickMs = 0, tickSteps = 0;
  const lerp = THREE.MathUtils.lerp;

  function frame() {
    const dt = Math.min(clock.getDelta(), 0.1);
    const t = clock.elapsedTime;
    try {
      if (mode === "play") {
        acc += dt;
        let n = 0;
        while (acc >= TICK && n < 5) {
          const [mx, mz, j] = stick();
          prev = cur;
          cur = rules.tick(mx, mz, j);
          tickMs = tickMs * 0.9 + rules.lastMs * 0.1;
          tickSteps = rules.lastSteps;
          react(cur);
          acc -= TICK; n++;
          if (mode !== "play") break;
        }
        if (n === 5) acc = 0;
      }
    } catch (e) { mode = "fault"; fault(e); }

    // Interpolate between the last two ticks.
    const a = mode === "play" ? Math.min(1, acc / TICK) : 1;
    const g = {
      ...cur.ghost,
      x: lerp(prev.ghost.x, cur.ghost.x, a), y: lerp(prev.ghost.y, cur.ghost.y, a), z: lerp(prev.ghost.z, cur.ghost.z, a),
    };
    const dxs = cur.drones.map((x, i) => lerp(prev.drones[i], x, a));

    // Camera: behind and above, looking ahead; on the title, drifting.
    let wantPos, wantLook;
    if (mode === "title") {
      const k = t * 0.12;
      wantPos = new THREE.Vector3(Math.sin(k) * 2.5, 2.2 + Math.sin(k * 0.7) * 0.4, -3.5 + Math.cos(k) * 1.2);
      wantLook = new THREE.Vector3(0, 1.3, 8);
    } else {
      wantPos = new THREE.Vector3(X(g.x) * 0.55, 2.9 + g.y * 0.35, g.z - 6.3);
      wantLook = new THREE.Vector3(X(g.x) * 0.75, 1.0 + g.y * 0.5, g.z + 4.5);
    }
    camPos.lerp(wantPos, 1 - Math.exp(-dt * 4));
    camLook.lerp(wantLook, 1 - Math.exp(-dt * 5));
    camera.position.copy(camPos);
    camera.position.y += Math.sin(t * 0.9) * 0.03;
    camera.lookAt(camLook);

    world.update(t);
    gate.update(t, cur.left === 0, dt);
    ghost.update(t, dt, g, camera.position);
    sparks.update(t, dt, cur.sparks);
    drones.update(t, dt, dxs);
    particles.update(dt);
    rain.update(dt, camera.position);

    hitPulse = Math.max(0, hitPulse - dt * 2.5);
    post.crt.uniforms.time.value = t;
    post.crt.uniforms.hit.value = hitPulse;
    post.composer.render(dt);

    // HUD.
    if (toastTimer > 0 && (toastTimer -= dt) <= 0) $("toast").classList.remove("on");
    $("sparks").textContent = `${L.sparks.length - cur.left}/${L.sparks.length}`;
    $("time").textContent = (cur.t / 60).toFixed(2);
    $("hits").textContent = cur.hits;
    frames++; fpsT += dt;
    if (fpsT >= 0.5) {
      fps = Math.round(frames / fpsT); frames = 0; fpsT = 0;
      $("debug").textContent =
        `Rules: LOVA → WebAssembly (${rules.version}) · ${rules.bytes} bytes\n` +
        `Tick: ${tickMs.toFixed(3)} ms · ${tickSteps} steps · Frame: ${fps} FPS · ${quality.name}`;
      // Frames running long: draw fewer pixels.
      if (fps < 40 && mode === "play") { if (++slow >= 4 && renderer.getPixelRatio() > 0.75) {
        renderer.setPixelRatio(renderer.getPixelRatio() * 0.8); post.resize(); slow = 0; } } else slow = 0;
    }
    requestAnimationFrame(frame);
  }

  $("start").disabled = false;
  $("start").textContent = "START";
  window.__neon = { rules, held, begin, restart, get mode() { return mode; }, get state() { return cur; } };
  requestAnimationFrame(frame);
}

boot().catch(fault);
