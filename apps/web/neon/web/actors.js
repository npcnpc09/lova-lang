// actors.js -- what moves: the ghost, the sparks, the drones, and the
// particles they throw.  Positions come from the rules every tick; what
// is here is only how they look between and around those positions --
// the hem that waves, the squash on landing, the lean into a turn.

import * as THREE from "three";
import { glowTexture, ringTexture } from "./textures.js";
import { X } from "./world.js";

const glow = glowTexture();

// --- particles ------------------------------------------------------

export class Particles {
  constructor(scene, max = 900) {
    this.max = max;
    this.pos = new Float32Array(max * 3);
    this.col = new Float32Array(max * 3);
    this.size = new Float32Array(max);
    this.vel = new Float32Array(max * 3);
    this.life = new Float32Array(max);
    this.span = new Float32Array(max);
    this.base = new Float32Array(max * 3);
    this.drag = new Float32Array(max);
    this.grav = new Float32Array(max);
    this.next = 0;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(this.col, 3));
    g.setAttribute("size", new THREE.BufferAttribute(this.size, 1));
    const m = new THREE.ShaderMaterial({
      uniforms: { map: { value: glow }, scale: { value: window.innerHeight / 2 } },
      vertexShader: `attribute float size; varying vec3 vColor;
        uniform float scale;
        void main(){ vColor = color; vec4 mv = modelViewMatrix * vec4(position,1.);
          gl_PointSize = size * scale / -mv.z; gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `uniform sampler2D map; varying vec3 vColor;
        void main(){ float a = texture2D(map, gl_PointCoord).a; gl_FragColor = vec4(vColor * a, a); }`,
      vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.material = m;
    this.points = new THREE.Points(g, m);
    this.points.frustumCulled = false;
    scene.add(this.points);
  }

  emit(p, v, color, life, size, { drag = 1.5, grav = 0 } = {}) {
    const i = this.next; this.next = (this.next + 1) % this.max;
    this.pos.set([p.x, p.y, p.z], i * 3);
    this.vel.set([v.x, v.y, v.z], i * 3);
    this.base.set([color.r, color.g, color.b], i * 3);
    this.life[i] = life; this.span[i] = life; this.size[i] = size;
    this.drag[i] = drag; this.grav[i] = grav;
  }

  burst(p, color, n, speed, { life = 0.9, size = 0.25, up = 0, grav = 0 } = {}) {
    const c = new THREE.Color(color);
    for (let k = 0; k < n; k++) {
      const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      const s = speed * (0.4 + Math.random() * 0.8);
      this.emit(p, { x: Math.sin(ph) * Math.cos(th) * s, y: Math.cos(ph) * s + up, z: Math.sin(ph) * Math.sin(th) * s },
        c, life * (0.6 + Math.random() * 0.6), size * (0.6 + Math.random() * 0.8), { grav });
    }
  }

  update(dt) {
    for (let i = 0; i < this.max; i++) {
      if (this.life[i] <= 0) { this.size[i] = 0; continue; }
      this.life[i] -= dt;
      const k = Math.max(0, this.life[i] / this.span[i]);
      const d = Math.exp(-this.drag[i] * dt);
      this.vel[i * 3] *= d; this.vel[i * 3 + 1] = this.vel[i * 3 + 1] * d - this.grav[i] * dt; this.vel[i * 3 + 2] *= d;
      this.pos[i * 3] += this.vel[i * 3] * dt; this.pos[i * 3 + 1] += this.vel[i * 3 + 1] * dt; this.pos[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
      for (let c = 0; c < 3; c++) this.col[i * 3 + c] = this.base[i * 3 + c] * k * 2.5;
    }
    const a = this.points.geometry.attributes;
    a.position.needsUpdate = a.color.needsUpdate = a.size.needsUpdate = true;
  }
}

// --- the ghost ------------------------------------------------------

function ghostGeometry() {
  const pts = [];
  const R = 0.42, top = 1.02;
  for (let i = 0; i <= 14; i++) {                    // the dome
    const a = (i / 14) * (Math.PI / 2);
    pts.push(new THREE.Vector2(Math.sin(a) * R + 0.0001, top - (1 - Math.cos(a)) * R));
  }
  for (let i = 1; i <= 10; i++) {                    // the skirt, flaring a little
    const u = i / 10;
    pts.push(new THREE.Vector2(R + 0.07 * u * u, top - R - u * 0.46));
  }
  const g = new THREE.LatheGeometry(pts, 48);
  g.userData.rest = g.attributes.position.array.slice();
  return g;
}

export class Ghost {
  constructor(scene, particles) {
    this.particles = particles;
    this.group = new THREE.Group();
    this.body = new THREE.Group();
    this.group.add(this.body);
    this.geo = ghostGeometry();
    this.mat = new THREE.MeshPhysicalMaterial({ color: 0x8a80a0, roughness: 0.4, metalness: 0.0,
      sheen: 1, sheenRoughness: 0.35, sheenColor: new THREE.Color(0xff3a66),
      emissive: 0x2a1236, clearcoat: 0.4, clearcoatRoughness: 0.4, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.body.add(this.mesh);

    this.eyeMat = new THREE.MeshBasicMaterial({ color: 0xff2a3a, toneMapped: false });
    this.eyeMat.color.multiplyScalar(5);
    const eyeGeo = new THREE.SphereGeometry(0.07, 16, 12);
    this.eyes = [-1, 1].map(s => {
      const e = new THREE.Mesh(eyeGeo, this.eyeMat);
      e.scale.set(1, 1.25, 0.6);
      e.position.set(s * 0.14, 0.76, 0.38);
      this.body.add(e);
      return e;
    });
    const mouth = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.012, 6, 12, Math.PI),
      new THREE.MeshBasicMaterial({ color: 0xff8090, toneMapped: false }));
    mouth.position.set(0, 0.64, 0.405);
    mouth.rotation.z = Math.PI;
    this.body.add(mouth);

    this.light = new THREE.PointLight(0xff5a7a, 5, 5, 1.6);
    this.light.position.set(0, 0.6, 0.4);
    this.group.add(this.light);

    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 1.3),
      new THREE.MeshBasicMaterial({ map: glowTexture("rgba(0,0,0,0.85)", "rgba(0,0,0,0)"), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2;
    this.shadow = shadow;
    const floorGlow = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 2.4),
      new THREE.MeshBasicMaterial({ map: glowTexture("rgba(255,40,80,0.55)", "rgba(255,40,80,0)"),
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    floorGlow.rotation.x = -Math.PI / 2;
    this.floorGlow = floorGlow;
    scene.add(this.group, shadow, floorGlow);

    this.squash = 1; this.squashV = 0;
    this.yaw = Math.PI; this.idle = 0; this.flash = 0; this.trail = 0;
  }

  // Called on a tick's events, not every frame.
  landed() { this.squash = 0.72; this.squashV = 0; }
  jumped() { this.squash = 1.28; this.squashV = 0; }
  struck() { this.flash = 0.9; }

  update(t, dt, p, camPos) {
    // Where the rules put it, bobbing a little: a ghost never quite rests.
    const bob = p.y > 0.001 ? 0 : 0.06 * Math.sin(t * 3.2);
    this.group.position.set(X(p.x), p.y + 0.1 + bob, p.z);

    // Squash and stretch, a spring back to 1.
    this.squashV += (1 - this.squash) * 180 * dt - this.squashV * 12 * dt;
    this.squash += this.squashV * dt;
    const sy = this.squash, sx = 1 / Math.sqrt(Math.max(0.3, sy));
    this.body.scale.set(sx, sy, sx);

    // Facing: where it goes, or back at the camera after a moment still.
    const vx = -p.vx, vz = p.vz, speed = Math.hypot(vx, vz);
    let want;
    if (speed > 0.4) { want = Math.atan2(vx, vz); this.idle = 0; }
    else {
      this.idle += dt;
      want = this.idle > 0.6 ? Math.atan2(camPos.x - this.group.position.x, camPos.z - this.group.position.z) : this.yaw;
    }
    let d = want - this.yaw;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    this.yaw += d * Math.min(1, dt * 8);
    this.body.rotation.y = this.yaw;
    // Lean into the motion.
    this.body.rotation.x = THREE.MathUtils.lerp(this.body.rotation.x, Math.min(speed, 6) * 0.035, dt * 6);
    this.body.rotation.z = THREE.MathUtils.lerp(this.body.rotation.z, d * 0.25, dt * 6);

    // The hem waves, faster when it moves.
    const pos = this.geo.attributes.position, rest = this.geo.userData.rest;
    const wave = 0.05 + Math.min(speed, 6) * 0.01;
    for (let i = 0; i < pos.count; i++) {
      const x = rest[i * 3], y = rest[i * 3 + 1], z = rest[i * 3 + 2];
      if (y > 0.5) continue;
      const k = (0.5 - y) / 0.46;
      const a = Math.atan2(z, x);
      pos.array[i * 3 + 1] = y + k * wave * Math.sin(a * 6 + t * (5 + speed));
      const flare = 1 + k * 0.05 * Math.sin(a * 3 - t * 4);
      pos.array[i * 3] = x * flare; pos.array[i * 3 + 2] = z * flare;
    }
    pos.needsUpdate = true;
    this.geo.computeVertexNormals();

    // Struck: the eyes go white and the body flickers.
    this.flash = Math.max(0, this.flash - dt);
    const hot = this.flash > 0 && Math.floor(this.flash * 20) % 2 === 0;
    this.eyeMat.color.set(hot ? 0xffffff : 0xff2a3a).multiplyScalar(hot ? 6 : 5);
    this.mat.emissive.set(hot ? 0x803040 : 0x2a1236);
    const blink = (t % 4.2) < 0.12 ? 0.12 : 1;
    for (const e of this.eyes) e.scale.y = 1.25 * blink;

    // Shadow and the red glow it throws, on the road under it.
    const h = Math.max(0, p.y);
    this.shadow.position.set(X(p.x), 0.012, p.z);
    this.shadow.scale.setScalar(1 / (1 + h * 0.8));
    this.shadow.material.opacity = 0.8 / (1 + h);
    this.floorGlow.position.set(X(p.x), 0.014, p.z + 0.2);
    this.floorGlow.material.opacity = 0.9 / (1 + h * 0.6);

    // Wisps behind it when it moves.
    this.trail += dt * (4 + speed * 5);
    while (this.trail > 1) {
      this.trail -= 1;
      const a = Math.random() * Math.PI * 2;
      this.particles.emit(
        { x: this.group.position.x + Math.cos(a) * 0.35, y: this.group.position.y + 0.15, z: this.group.position.z + Math.sin(a) * 0.35 },
        { x: -vx * 0.15 + (Math.random() - 0.5) * 0.3, y: 0.3 + Math.random() * 0.3, z: -vz * 0.15 + (Math.random() - 0.5) * 0.3 },
        new THREE.Color(Math.random() < 0.5 ? 0xff2a55 : 0x9a6cff), 0.9, 0.18, { drag: 2 });
    }
  }
}

// --- sparks ---------------------------------------------------------

export class Sparks {
  constructor(scene, spots, particles) {
    this.particles = particles;
    const geo = new THREE.OctahedronGeometry(0.16, 0);
    const halo = glowTexture("rgba(120,240,255,0.9)", "rgba(60,200,255,0)");
    this.items = spots.map((s, i) => {
      const high = s.y > 1;
      const col = high ? 0xffd04a : 0x3ff2ff;
      const m = new THREE.MeshBasicMaterial({ color: col, toneMapped: false });
      m.color.multiplyScalar(2.2);
      const mesh = new THREE.Mesh(geo, m);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo, color: col, blending: THREE.AdditiveBlending,
        depthWrite: false, transparent: true, opacity: 0.5 }));
      sprite.scale.setScalar(0.8);
      const g = new THREE.Group();
      g.add(mesh, sprite);
      g.position.set(X(s.x), s.y + 0.2, s.z);
      scene.add(g);
      return { g, mesh, spot: s, taken: 0, phase: i * 1.7, col };
    });
  }

  reset() { for (const it of this.items) { it.taken = 0; it.g.visible = true; } }

  update(t, dt, taken) {
    for (const [i, it] of this.items.entries()) {
      if (taken[i] && !it.taken) {
        it.taken = 1;
        it.g.visible = false;
        this.particles.burst(it.g.position, it.col, 40, 4, { life: 0.8, size: 0.22 });
        this.particles.burst(it.g.position, 0xffffff, 12, 2, { life: 0.5, size: 0.3 });
      }
      if (it.taken) continue;
      it.mesh.rotation.y = t * 2 + it.phase;
      it.mesh.rotation.x = t * 1.3 + it.phase;
      it.g.position.y = it.spot.y + 0.25 + Math.sin(t * 2.4 + it.phase) * 0.08;
    }
  }
}

// --- drones ---------------------------------------------------------

export class Drones {
  constructor(scene, zs, y) {
    const metal = new THREE.MeshStandardMaterial({ color: 0x1a1720, roughness: 0.35, metalness: 0.8 });
    const redMat = new THREE.MeshBasicMaterial({ color: 0xff2a3a, toneMapped: false });
    redMat.color.multiplyScalar(4);
    const beamMat = new THREE.MeshBasicMaterial({ color: 0xff2a3a, transparent: true, opacity: 0.1,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    const ring = ringTexture();
    this.y = y;
    this.items = zs.map((z, i) => {
      const g = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.36, 0.14, 20), metal);
      const band = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 8, 32), redMat);
      band.rotation.x = Math.PI / 2;
      const eye = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 10), redMat);
      eye.position.set(0, -0.06, 0.28);
      g.add(body, band, eye);
      const rotors = [];
      for (let k = 0; k < 4; k++) {
        const a = k * Math.PI / 2 + Math.PI / 4;
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.05), metal);
        arm.position.set(Math.cos(a) * 0.38, 0.03, Math.sin(a) * 0.38);
        arm.rotation.y = -a;
        const rotor = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.01, 16),
          new THREE.MeshBasicMaterial({ color: 0x806070, transparent: true, opacity: 0.35 }));
        rotor.position.set(Math.cos(a) * 0.58, 0.07, Math.sin(a) * 0.58);
        g.add(arm, rotor);
        rotors.push(rotor);
      }
      const beam = new THREE.Mesh(new THREE.ConeGeometry(0.85, y, 24, 1, true), beamMat);
      beam.position.y = -y / 2;
      g.add(beam);
      const spot = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.9),
        new THREE.MeshBasicMaterial({ map: ring, color: 0xff2a3a, transparent: true, depthWrite: false,
          blending: THREE.AdditiveBlending, opacity: 0.9 }));
      spot.rotation.x = -Math.PI / 2;
      scene.add(g, spot);
      g.position.set(0, y, z);
      return { g, rotors, spot, z, last: null, tilt: 0, phase: i };
    });
  }

  update(t, dt, xs) {
    for (const [i, d] of this.items.entries()) {
      const x = X(xs[i]);
      const dx = d.last === null ? 0 : (x - d.last) / Math.max(dt, 1e-3);
      d.last = x;
      d.tilt = THREE.MathUtils.lerp(d.tilt, THREE.MathUtils.clamp(-dx * 0.06, -0.35, 0.35), dt * 5);
      d.g.position.set(x, this.y + Math.sin(t * 2 + d.phase) * 0.05, d.z);
      d.g.rotation.z = d.tilt;
      for (const r of d.rotors) r.rotation.y += dt * 40;
      d.spot.position.set(x, 0.016, d.z);
      d.spot.material.opacity = 0.7 + 0.3 * Math.sin(t * 9 + d.phase);
    }
  }
}
