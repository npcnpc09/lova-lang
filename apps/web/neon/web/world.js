// world.js -- the street: wet road, kerbs, the buildings, their signs,
// the cables over it and the gate at the end.  Nothing here decides
// anything; the rules' layout says how wide and how long.
//
// The rules' x is the three.js -x, so that with the camera looking up
// the street (+z) the rules' right is the screen's right.

import * as THREE from "three";
import { Reflector } from "three/addons/objects/Reflector.js";
import { windowsTexture, signTexture, roadTextures, glowTexture, rng } from "./textures.js";

export const X = x => -x;           // the rules' x, in the scene

const SIGNS = [
  ["LOVA", "#ff2a55"], ["霓虹", "#3ff2ff"], ["ラーメン", "#ffb020"], ["24H", "#7dff6a"],
  ["夜市", "#ff4fd8"], ["GHOST", "#3ff2ff"], ["BAR", "#ff2a55"], ["電脳", "#b48cff"],
  ["OPEN", "#7dff6a"], ["酒", "#ff4fd8"], ["CYBER", "#ffb020"], ["幽灵", "#3ff2ff"],
  ["HOTEL", "#ff2a55"], ["薬", "#7dff6a"], ["KARAOKE", "#b48cff"], ["∞", "#ff4fd8"],
];
const VSIGNS = [["居酒屋", "#ff2a55"], ["ゲーム", "#3ff2ff"], ["不夜城", "#ffb020"], ["整体", "#7dff6a"],
  ["电子", "#ff4fd8"], ["バー", "#b48cff"], ["网吧", "#3ff2ff"], ["カラオケ", "#ff2a55"]];

function neonMaterial(map, strength = 1.5) {
  const m = new THREE.MeshBasicMaterial({ map, transparent: true, blending: THREE.AdditiveBlending,
    depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  m.color.setScalar(strength);
  m.userData.base = strength;
  return m;
}

export function buildWorld(scene, layout, quality) {
  const r = rng(20260924);
  const W = layout.halfW, L = layout.length;
  const flicker = [];
  const group = new THREE.Group();
  scene.add(group);

  scene.background = new THREE.Color(0x0a0714);
  scene.fog = new THREE.FogExp2(0x0d0818, 0.03);
  group.add(new THREE.HemisphereLight(0x6a54b8, 0x080510, 1.4));

  // --- the ground: a mirror under a road that is transparent where wet
  const span = L + 40;
  const mirror = new Reflector(new THREE.PlaneGeometry(40, span), {
    clipBias: 0.003, color: 0x8a8a9a,
    textureWidth: Math.round(window.innerWidth * quality.reflect),
    textureHeight: Math.round(window.innerHeight * quality.reflect),
  });
  mirror.rotation.x = -Math.PI / 2;
  mirror.position.set(0, -0.02, L / 2);
  mirror.material.uniforms.color.value.set(0x55506a);
  group.add(mirror);

  const road = roadTextures(7);
  road.color.repeat.set(4, span / 4);
  road.alpha.repeat.set(1.3, span / 11);
  const roadMat = new THREE.MeshStandardMaterial({ map: road.color, alphaMap: road.alpha, transparent: true,
    roughness: 0.55, metalness: 0.2, color: 0xb0a8c0 });
  const roadMesh = new THREE.Mesh(new THREE.PlaneGeometry(2 * W + 1.2, span), roadMat);
  roadMesh.rotation.x = -Math.PI / 2;
  roadMesh.position.set(0, 0, L / 2);
  group.add(roadMesh);

  // Pavements either side, a step up, and the kerb lines lit.
  const paveMat = new THREE.MeshStandardMaterial({ color: 0x1d1a26, roughness: 0.7, metalness: 0.1 });
  for (const side of [-1, 1]) {
    const pave = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.16, span), paveMat);
    pave.position.set(side * (W + 0.6 + 1.7), 0.08, L / 2);
    group.add(pave);
    const kerb = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, span),
      new THREE.MeshBasicMaterial({ color: side < 0 ? 0x3ff2ff : 0xff2a55, toneMapped: false }));
    kerb.material.color.multiplyScalar(1.1);
    kerb.position.set(side * (W + 0.6), 0.17, L / 2);
    group.add(kerb);
  }

  // --- the buildings: a row each side, facades toward the street
  const wallMat = () => new THREE.MeshStandardMaterial({ color: 0x2a2436, roughness: 0.8, metalness: 0.2,
    emissive: 0xffffff, emissiveIntensity: 0.42 });
  const trimMats = ["#ff2a55", "#3ff2ff", "#b48cff"].map(c => {
    const m = new THREE.MeshBasicMaterial({ color: c, toneMapped: false });
    m.color.multiplyScalar(1.3);
    return m;
  });
  const facades = [windowsTexture(1), windowsTexture(2, 5, 10), windowsTexture(3, 8, 14), windowsTexture(4, 4, 9)];
  const face = W + 0.6 + 3.4;               // the facades' distance from the middle
  const lights = [];
  let si = 0, vi = 0;
  for (const side of [-1, 1]) {
    let z = -14;
    while (z < L + 22) {
      const len = 5 + r() * 6, h = 8 + r() * 20, depth = 7 + r() * 5;
      const m = wallMat();
      const t = facades[Math.floor(r() * facades.length)].clone();
      t.needsUpdate = true;
      t.repeat.set(Math.max(1, Math.round(len / 2.5)), Math.max(1, Math.round(h / 5)));
      m.emissiveMap = t;
      const b = new THREE.Mesh(new THREE.BoxGeometry(depth, h, len), m);
      b.position.set(side * (face + depth / 2), h / 2, z + len / 2);
      group.add(b);
      // A lit trim up the street corner, sometimes, and a ledge every
      // few storeys, so a facade reads as a wall and not as windows
      // floating in the dark.
      if (r() < 0.45) {
        const trim = new THREE.Mesh(new THREE.BoxGeometry(0.06, h, 0.06), trimMats[Math.floor(r() * trimMats.length)]);
        trim.position.set(side * (face + 0.03), h / 2, z + (r() < 0.5 ? 0.03 : len - 0.03));
        group.add(trim);
      }
      for (let yy = 3.2; yy < h - 1; yy += 3.2 * (1 + Math.floor(r() * 2))) {
        const ledge = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.12, len), paveMat);
        ledge.position.set(side * (face + 0.05), yy, z + len / 2);
        group.add(ledge);
      }

      // A sign flat on the facade, sometimes.
      if (r() < 0.8) {
        const [text, col] = SIGNS[si++ % SIGNS.length];
        const tx = signTexture(text, col);
        const height = 0.9 + r() * 0.6, width = height * tx.userData.aspect;
        const sign = new THREE.Mesh(new THREE.PlaneGeometry(Math.min(width, len * 0.9), height), neonMaterial(tx));
        sign.position.set(side * (face - 0.03), 2.6 + r() * 4.5, z + len / 2);
        sign.rotation.y = side > 0 ? -Math.PI / 2 : Math.PI / 2;
        group.add(sign);
        if (r() < 0.3) flicker.push({ m: sign.material, seed: r() * 100 });
        lights.push({ x: side * (face - 1.2), y: sign.position.y, z: sign.position.z, color: col });
      }
      // A tall sign standing out from the wall, seen along the street.
      if (r() < 0.55) {
        const [text, col] = VSIGNS[vi++ % VSIGNS.length];
        const tx = signTexture(text, col, { vertical: true });
        const width = 0.8, height = width / tx.userData.aspect;
        const sign = new THREE.Mesh(new THREE.PlaneGeometry(width, height), neonMaterial(tx, 1.4));
        sign.position.set(side * (face - 0.55), 3.5 + height / 2 + r() * 3, z + 0.6 + r() * (len - 1.2));
        sign.rotation.y = Math.PI;
        group.add(sign);
        const bracket = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.06, 0.06), paveMat);
        bracket.position.set(side * (face - 0.45), sign.position.y + height / 2, sign.position.z);
        group.add(bracket);
        if (r() < 0.25) flicker.push({ m: sign.material, seed: r() * 100 });
      }
      z += len + 0.3 + r() * 1.2;
    }
  }

  // The ends of the street: a block across it behind the start, and one
  // beyond the gate with the biggest sign in the street.
  for (const [z, text, col] of [[-16, "START", "#3ff2ff"], [L + 16, "出口 EXIT", "#7dff6a"]]) {
    const m = wallMat();
    const t = facades[0].clone(); t.needsUpdate = true; t.repeat.set(6, 3); m.emissiveMap = t;
    const b = new THREE.Mesh(new THREE.BoxGeometry(40, 30, 6), m);
    b.position.set(0, 15, z);
    group.add(b);
    const tx = signTexture(text, col);
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(2.2 * tx.userData.aspect, 2.2), neonMaterial(tx, 1.7));
    sign.position.set(0, 8, z < 0 ? z + 3.05 : z - 3.05);
    sign.rotation.y = z < 0 ? 0 : Math.PI;
    group.add(sign);
  }

  // Coloured light from the signs onto the road: a few point lights,
  // the budget set by the quality level.
  const chosen = lights.filter((_, i) => i % Math.max(1, Math.round(lights.length / quality.lights)) === 0);
  for (const l of chosen) {
    const p = new THREE.PointLight(l.color, 34, 14, 1.5);
    p.position.set(l.x, l.y, l.z);
    group.add(p);
  }

  // Cables across the street, with paper lanterns hung from them.
  const cableMat = new THREE.LineBasicMaterial({ color: 0x05040a });
  const lanternGeo = new THREE.SphereGeometry(0.22, 12, 10);
  const lanternGlow = glowTexture("rgba(255,120,80,0.9)", "rgba(255,60,40,0)");
  for (let z = 4; z < L + 10; z += 7 + r() * 5) {
    const pts = [];
    const sag = 0.8 + r() * 0.8, h = 6 + r() * 2.5;
    for (let i = 0; i <= 24; i++) {
      const u = i / 24, x = -face + 2 * face * u;
      pts.push(new THREE.Vector3(x, h - sag * 4 * u * (1 - u), z + (r() - 0.5) * 0.3));
    }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), cableMat));
    if (r() < 0.75) {
      for (let i = 3; i < 22; i += 4 + Math.floor(r() * 3)) {
        const warm = r() < 0.7;
        const lm = new THREE.MeshBasicMaterial({ color: warm ? 0xff6a3d : 0xff2a55, toneMapped: false });
        lm.color.multiplyScalar(1.15);
        const lan = new THREE.Mesh(lanternGeo, lm);
        lan.scale.y = 1.25;
        lan.position.copy(pts[i]).add(new THREE.Vector3(0, -0.45, 0));
        group.add(lan);
        const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: lanternGlow, blending: THREE.AdditiveBlending,
          depthWrite: false, transparent: true, opacity: 0.35 }));
        halo.scale.setScalar(1.1);
        halo.position.copy(lan.position);
        group.add(halo);
      }
    }
  }

  return {
    mirror,
    update(t) {
      for (const f of flicker) {
        const k = Math.sin(t * 13 + f.seed) + Math.sin(t * 29.7 + f.seed * 2);
        const off = k > 1.55 || (Math.sin(t * 0.7 + f.seed) > 0.97);
        f.m.color.setScalar(off ? f.m.userData.base * 0.15 : f.m.userData.base);
      }
    },
  };
}

// The gate at the end: two pillars, a beam with a sign, and laser bars
// that hold while a spark is left and fold away when none is.
export function buildGate(scene, layout) {
  const W = layout.halfW, z = layout.length;
  const g = new THREE.Group();
  g.position.set(0, 0, z);
  scene.add(g);
  const dark = new THREE.MeshStandardMaterial({ color: 0x14111c, roughness: 0.5, metalness: 0.6 });
  for (const side of [-1, 1]) {
    const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.5, 4.2, 0.5), dark);
    pillar.position.set(side * (W + 0.35), 2.1, 0);
    g.add(pillar);
  }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(2 * W + 1.2, 0.5, 0.5), dark);
  beam.position.set(0, 4.2, 0);
  g.add(beam);
  const red = signTexture("LOCKED", "#ff2a55", { frame: false });
  const green = signTexture("OPEN", "#7dff6a", { frame: false });
  const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.62 * red.userData.aspect, 0.62), neonMaterial(red, 1.8));
  sign.position.set(0, 4.2, -0.27);
  sign.rotation.y = Math.PI;
  g.add(sign);

  const bars = [];
  const barMat = new THREE.MeshBasicMaterial({ color: 0xff2a55, toneMapped: false, transparent: true });
  barMat.color.multiplyScalar(3);
  for (let i = 0; i < 6; i++) {
    const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 2 * W + 0.6, 6), barMat);
    bar.rotation.z = Math.PI / 2;
    bar.position.set(0, 0.35 + i * 0.6, 0);
    g.add(bar);
    bars.push(bar);
  }
  const glow = new THREE.PointLight(0xff2a55, 12, 10, 1.5);
  glow.position.set(0, 2, -1);
  g.add(glow);

  let open = 0;       // 0 shut .. 1 open, eased
  return {
    update(t, isOpen, dt) {
      open += ((isOpen ? 1 : 0) - open) * Math.min(1, dt * 3);
      for (const [i, bar] of bars.entries()) {
        bar.scale.y = Math.max(0.001, 1 - open);
        bar.visible = open < 0.99;
        bar.position.y = 0.35 + i * 0.6 + Math.sin(t * 6 + i) * 0.01;
      }
      barMat.opacity = 0.75 + 0.25 * Math.sin(t * 20);
      const target = isOpen ? green : red;
      if (sign.material.map !== target) {
        sign.material.map = target;
        sign.geometry.dispose();
        sign.geometry = new THREE.PlaneGeometry(0.62 * target.userData.aspect, 0.62);
        glow.color.set(isOpen ? 0x7dff6a : 0xff2a55);
      }
    },
  };
}
