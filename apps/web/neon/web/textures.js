// textures.js -- every picture in the street, drawn on a canvas.

import * as THREE from "three";

export function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function canvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return [c, c.getContext("2d")];
}

function tex(c, { repeat = false, srgb = true } = {}) {
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
  return t;
}

// A facade's windows: a grid, most dark, some lit warm or cold, a few
// with a blind half down.  Drawn as the emissive map; the wall itself
// is the material's dark colour.
export function windowsTexture(seed, cols = 6, rows = 12) {
  const r = rng(seed);
  const [c, g] = canvas(256, 512);
  g.fillStyle = "#000"; g.fillRect(0, 0, 256, 512);
  const cw = 256 / cols, rh = 512 / rows;
  const palette = ["#ffcf8a", "#ffb36b", "#9fe8ff", "#ff9ad5", "#c9b8ff", "#fff1c9"];
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
    const lit = r() < 0.2;
    const x = i * cw + cw * 0.18, y = j * rh + rh * 0.22, w = cw * 0.64, h = rh * 0.56;
    if (!lit) { g.fillStyle = `rgba(40,30,70,${0.25 + r() * 0.3})`; g.fillRect(x, y, w, h); continue; }
    g.fillStyle = palette[Math.floor(r() * palette.length)];
    g.globalAlpha = 0.35 + r() * 0.5;
    g.fillRect(x, y, w, h);
    if (r() < 0.35) { g.fillStyle = "#000"; g.globalAlpha = 0.7; g.fillRect(x, y, w, h * (0.3 + r() * 0.4)); }
    g.globalAlpha = 1;
  }
  return tex(c, { repeat: true });
}

// A neon sign: the text in a glowing tube colour on black, the black
// made transparent by the material's additive blending.
export function signTexture(text, color, { vertical = false, font = "900 120px Orbitron, 'Microsoft YaHei', sans-serif", frame = true } = {}) {
  const chars = [...text];
  const W = vertical ? 200 : Math.max(256, chars.length * 110 + 80);
  const H = vertical ? chars.length * 150 + 60 : 220;
  const [c, g] = canvas(W, H);
  g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  g.textAlign = "center"; g.textBaseline = "middle"; g.font = font;
  const draw = (blur, alpha, col) => {
    g.shadowColor = color; g.shadowBlur = blur; g.globalAlpha = alpha; g.fillStyle = col;
    if (vertical) chars.forEach((ch, i) => g.fillText(ch, W / 2, 90 + i * 150));
    else g.fillText(text, W / 2, H / 2 + 6);
  };
  draw(40, 0.9, color); draw(12, 1, color); draw(0, 0.9, "#fff");
  if (frame) {
    g.globalAlpha = 0.9; g.shadowBlur = 20; g.shadowColor = color; g.strokeStyle = color; g.lineWidth = 7;
    g.strokeRect(14, 14, W - 28, H - 28);
  }
  const t = tex(c);
  t.userData = { aspect: W / H };
  return t;
}

// The road: asphalt grain, a worn kerb line, and the alpha that decides
// where it is wet -- dark (transparent) where a puddle lets the mirror
// under it show.
export function roadTextures(seed) {
  const r = rng(seed);
  const [c, g] = canvas(512, 512);
  g.fillStyle = "#1a1722"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 9000; i++) {
    const v = 16 + r() * 34;
    g.fillStyle = `rgb(${v},${v - 3},${v + 8})`;
    g.fillRect(r() * 512, r() * 512, 1 + r() * 2, 1 + r() * 2);
  }
  for (let i = 0; i < 26; i++) {           // cracks and patches
    g.strokeStyle = `rgba(0,0,0,${0.3 + r() * 0.4})`; g.lineWidth = 1 + r() * 2;
    g.beginPath(); let x = r() * 512, y = r() * 512; g.moveTo(x, y);
    for (let k = 0; k < 6; k++) { x += (r() - 0.5) * 60; y += (r() - 0.5) * 60; g.lineTo(x, y); }
    g.stroke();
  }
  const color = tex(c, { repeat: true });

  const [a, h] = canvas(256, 256);
  h.fillStyle = "#e8e8e8"; h.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 16; i++) {            // puddles
    const x = r() * 256, y = r() * 256, rad = 14 + r() * 46;
    const grd = h.createRadialGradient(x, y, 0, x, y, rad);
    grd.addColorStop(0, "rgba(20,20,20,1)"); grd.addColorStop(0.65, "rgba(40,40,40,0.9)"); grd.addColorStop(1, "rgba(232,232,232,0)");
    h.fillStyle = grd;
    for (const ox of [-256, 0, 256]) for (const oy of [-256, 0, 256]) {
      h.save(); h.translate(ox, oy); h.beginPath(); h.ellipse(x, y, rad, rad * (0.5 + r() * 0.5), r() * 3, 0, 7); h.fill(); h.restore();
    }
  }
  const alpha = tex(a, { repeat: true, srgb: false });
  return { color, alpha };
}

// A soft round glow, for halos, the ghost's shadow and drone spots.
export function glowTexture(inner = "rgba(255,255,255,1)", outer = "rgba(255,255,255,0)") {
  const [c, g] = canvas(128, 128);
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, inner); grd.addColorStop(1, outer);
  g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
  return tex(c);
}

// A ring, for the circle a drone's beam throws on the road.
export function ringTexture() {
  const [c, g] = canvas(128, 128);
  const grd = g.createRadialGradient(64, 64, 30, 64, 64, 62);
  grd.addColorStop(0, "rgba(255,255,255,0)"); grd.addColorStop(0.75, "rgba(255,255,255,0.9)"); grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
  const g2 = g.createRadialGradient(64, 64, 0, 64, 64, 40);
  g2.addColorStop(0, "rgba(255,255,255,0.35)"); g2.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = g2; g.fillRect(0, 0, 128, 128);
  return tex(c);
}
