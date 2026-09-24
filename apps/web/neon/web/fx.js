// fx.js -- the renderer, the passes after it, and the rain.

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// Quality by what the machine is likely to carry; lowered on the fly
// if frames run long.
export function pickQuality() {
  const small = Math.min(window.innerWidth, window.innerHeight) < 700;
  const mobile = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
  if (mobile || small) return { name: "low", pixel: Math.min(devicePixelRatio, 1.25), reflect: 0.35, lights: 5, rain: 700 };
  return { name: "high", pixel: Math.min(devicePixelRatio, 1.5), reflect: 0.5, lights: 10, rain: 1800 };
}

// The screen: a slight barrel, colour pulled apart at the edges, lines,
// grain and a vignette -- a monitor at night.
const CRT = {
  uniforms: { tDiffuse: { value: null }, time: { value: 0 }, res: { value: new THREE.Vector2(1, 1) },
    hit: { value: 0 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float time; uniform vec2 res; uniform float hit; varying vec2 vUv;
    float rand(vec2 c){ return fract(sin(dot(c, vec2(12.9898,78.233))) * 43758.5453); }
    void main(){
      vec2 c = vUv - .5;
      vec2 uv = .5 + c * (1. + .035 * dot(c, c));
      float ab = .0006 + .0022 * dot(c, c) + hit * .01;
      vec3 col;
      col.r = texture2D(tDiffuse, uv + vec2(ab, 0.)).r;
      col.g = texture2D(tDiffuse, uv).g;
      col.b = texture2D(tDiffuse, uv - vec2(ab, 0.)).b;
      float line = .93 + .07 * sin(uv.y * res.y * 1.5708 + time * 2.);
      col *= line;
      col += (rand(uv * res + time) - .5) * .045;
      float v = smoothstep(.95, .25, length(c * vec2(1., .9)));
      col *= mix(.45, 1., v);
      col = mix(col, col * vec3(1.3, .6, .7), hit * .5);
      if (uv.x < 0. || uv.x > 1. || uv.y < 0. || uv.y > 1.) col = vec3(0.);
      gl_FragColor = vec4(col, 1.);
    }`,
};

export function makeRenderer(canvas, quality) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(quality.pixel);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  return renderer;
}

export function makeComposer(renderer, scene, camera) {
  const size = new THREE.Vector2();
  renderer.getSize(size);
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(size.x, size.y), 0.55, 0.45, 0.82);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  const crt = new ShaderPass(CRT);
  composer.addPass(crt);
  const resize = () => {
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    composer.setSize(window.innerWidth, window.innerHeight);
    const pr = renderer.getPixelRatio();
    crt.uniforms.res.value.set(window.innerWidth * pr, window.innerHeight * pr);
  };
  resize();
  return { composer, bloom, crt, resize };
}

// Rain: streaks that fall past the camera and start again above it.
export class Rain {
  constructor(scene, n) {
    this.n = n;
    this.pos = new Float32Array(n * 6);
    this.drops = [];
    for (let i = 0; i < n; i++) this.drops.push({ x: 0, y: 0, z: 0, v: 0 });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    this.lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x9aa4ff, transparent: true,
      opacity: 0.28, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.lines.frustumCulled = false;
    scene.add(this.lines);
    this.seeded = false;
  }

  spawn(d, c, anyHeight) {
    d.x = c.x + (Math.random() - 0.5) * 24;
    d.z = c.z + Math.random() * 30 - 4;
    d.y = anyHeight ? Math.random() * 14 : 12 + Math.random() * 3;
    d.v = 16 + Math.random() * 6;
  }

  update(dt, c) {
    for (let i = 0; i < this.n; i++) {
      const d = this.drops[i];
      if (!this.seeded) this.spawn(d, c, true);
      d.y -= d.v * dt;
      if (d.y < 0 || d.z < c.z - 6 || d.z > c.z + 30) this.spawn(d, c, false);
      const k = i * 6;
      this.pos[k] = d.x; this.pos[k + 1] = d.y; this.pos[k + 2] = d.z;
      this.pos[k + 3] = d.x + 0.02; this.pos[k + 4] = d.y + 0.35; this.pos[k + 5] = d.z;
    }
    this.seeded = true;
    this.lines.geometry.attributes.position.needsUpdate = true;
  }
}
