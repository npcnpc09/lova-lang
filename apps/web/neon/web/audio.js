// audio.js -- everything heard, synthesised: a slow minor loop with a
// pad, a bass, an arpeggio through a delay and a soft kit; the rain;
// and the sounds of the game.  Nothing is a recording.

const CHORDS = [   // A minor, F, C, G -- as MIDI roots and a minor/major flag
  [57, 0], [53, 1], [48, 1], [55, 1],
];
const midi = n => 440 * Math.pow(2, (n - 69) / 12);

export class Sound {
  constructor() {
    this.ctx = null;
    this.muted = false;
  }

  start() {
    if (this.ctx) { this.ctx.resume(); return; }
    this.build(new (window.AudioContext || window.webkitAudioContext)());
    this.nextAt = this.ctx.currentTime + 0.1;
    this.timer = setInterval(() => this.schedule(), 25);
  }

  // The same music and the same sounds into an OfflineAudioContext, on a
  // timeline given in advance: `log` is what `?record` wrote down,
  // [seconds, method, argument], and `musicFrom` when the music starts.
  // Returns the rendered AudioBuffer.
  static async render(log, seconds, musicFrom) {
    const rate = 44100;
    const ctx = new OfflineAudioContext(2, Math.ceil(seconds * rate), rate);
    const s = new Sound();
    s.build(ctx);
    s.nextAt = musicFrom;
    const sixteenth = 60 / s.bpm / 4;
    while (s.nextAt < seconds) { s.play(s.step, s.nextAt, sixteenth); s.nextAt += sixteenth; s.step++; }
    for (const [t, name, arg] of log) { s.at = t; s[name](arg); }
    s.at = null;
    return ctx.startRendering();
  }

  now() { return this.at != null ? this.at : this.ctx.currentTime; }

  build(ctx) {
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = 0.7;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -18; comp.ratio.value = 4;
    this.master.connect(comp).connect(ctx.destination);

    this.music = ctx.createGain(); this.music.gain.value = 0.55; this.music.connect(this.master);
    this.sfx = ctx.createGain(); this.sfx.gain.value = 0.9; this.sfx.connect(this.master);

    // A delay the arpeggio goes through, fed back and darkened.
    this.delay = ctx.createDelay(1); this.delay.delayTime.value = 0.375;
    const fb = ctx.createGain(); fb.gain.value = 0.38;
    const tone = ctx.createBiquadFilter(); tone.type = "lowpass"; tone.frequency.value = 2200;
    this.delay.connect(tone).connect(fb).connect(this.delay);
    tone.connect(this.music);

    this.noise = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const d = this.noise.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;

    this.rain();
    this.bpm = 92;
    this.step = 0;
  }

  toggle() {
    this.muted = !this.muted;
    if (this.master) this.master.gain.setTargetAtTime(this.muted ? 0 : 0.7, this.ctx.currentTime, 0.05);
    return this.muted;
  }

  noiseSource() {
    const s = this.ctx.createBufferSource();
    s.buffer = this.noise; s.loop = true;
    return s;
  }

  rain() {
    const ctx = this.ctx, s = this.noiseSource();
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 900;
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 6000;
    const g = ctx.createGain(); g.gain.value = 0.05;
    s.connect(hp).connect(lp).connect(g).connect(this.master);
    s.start(0);
  }

  // --- the loop, a sixteenth at a time, scheduled ahead ---------------
  schedule() {
    const ctx = this.ctx, sixteenth = 60 / this.bpm / 4;
    while (this.nextAt < ctx.currentTime + 0.12) {
      this.play(this.step, this.nextAt, sixteenth);
      this.nextAt += sixteenth;
      this.step++;
    }
  }

  play(step, t, dur) {
    const bar = Math.floor(step / 16) % CHORDS.length, s = step % 16;
    const [root, major] = CHORDS[bar];
    const third = major ? 4 : 3;
    if (s === 0) this.pad(root, third, t, dur * 16);
    if (s % 4 === 0) this.kick(t, s === 0 ? 1 : 0.7);
    if (s === 4 || s === 12) this.snare(t);
    if (s % 2 === 1) this.hat(t, s % 4 === 3 ? 0.5 : 0.3);
    if (s === 0 || s === 6 || s === 10) this.bass(root - 12, t, dur * (s === 0 ? 5 : 3));
    const arp = [0, 7, 12, third + 12, 7, 12 + 7, third + 24, 12];
    if (step >= 32 && s % 2 === 0) this.pluck(root + arp[(s / 2 + bar) % arp.length], t, dur * 1.6);
  }

  env(g, t, a, peak, dec) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t + a + dec);
  }

  pad(root, third, t, len) {
    const ctx = this.ctx;
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 700; lp.Q.value = 2;
    lp.frequency.setValueAtTime(500, t); lp.frequency.linearRampToValueAtTime(1300, t + len / 2);
    lp.frequency.linearRampToValueAtTime(500, t + len);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.09, t + 1.2);
    g.gain.setValueAtTime(0.09, t + len - 0.6);
    g.gain.exponentialRampToValueAtTime(0.0001, t + len + 0.4);
    lp.connect(g).connect(this.music);
    for (const [n, det] of [[root, -7], [root, 7], [root + third, 0], [root + 7, 4], [root + 12, -4]]) {
      const o = ctx.createOscillator();
      o.type = "sawtooth"; o.frequency.value = midi(n); o.detune.value = det;
      o.connect(lp); o.start(t); o.stop(t + len + 0.5);
    }
  }

  bass(n, t, len) {
    const ctx = this.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 420;
    o.type = "triangle"; o.frequency.value = midi(n);
    this.env(g, t, 0.01, 0.35, len);
    o.connect(lp).connect(g).connect(this.music); o.start(t); o.stop(t + len + 0.1);
  }

  pluck(n, t, len) {
    const ctx = this.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass";
    lp.frequency.setValueAtTime(3200, t); lp.frequency.exponentialRampToValueAtTime(500, t + len);
    o.type = "square"; o.frequency.value = midi(n);
    this.env(g, t, 0.005, 0.06, len);
    o.connect(lp).connect(g);
    g.connect(this.music); g.connect(this.delay);
    o.start(t); o.stop(t + len + 0.05);
  }

  kick(t, v) {
    const ctx = this.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.setValueAtTime(130, t); o.frequency.exponentialRampToValueAtTime(42, t + 0.18);
    this.env(g, t, 0.003, 0.55 * v, 0.28);
    o.connect(g).connect(this.music); o.start(t); o.stop(t + 0.35);
  }

  snare(t) {
    const ctx = this.ctx, s = this.noiseSource(), g = ctx.createGain();
    const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1800; bp.Q.value = 0.8;
    this.env(g, t, 0.002, 0.16, 0.16);
    s.connect(bp).connect(g).connect(this.music); s.start(t, Math.random()); s.stop(t + 0.2);
  }

  hat(t, v) {
    const ctx = this.ctx, s = this.noiseSource(), g = ctx.createGain();
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 7000;
    this.env(g, t, 0.001, 0.07 * v, 0.05);
    s.connect(hp).connect(g).connect(this.music); s.start(t, Math.random()); s.stop(t + 0.08);
  }

  // --- the game's sounds ----------------------------------------------
  tone(type, f0, f1, len, vol, when = 0) {
    if (!this.ctx) return;
    const ctx = this.ctx, t = this.now() + when, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + len);
    this.env(g, t, 0.005, vol, len);
    o.connect(g).connect(this.sfx); o.start(t); o.stop(t + len + 0.05);
  }

  jump() { this.tone("sine", 320, 760, 0.18, 0.22); }
  land() { this.tone("sine", 140, 70, 0.1, 0.18); }

  spark(k) {                   // higher with every spark gathered
    const base = midi(76 + [0, 2, 4, 7, 9][k % 5] + 12 * Math.floor(k / 5));
    this.tone("triangle", base, base * 1.01, 0.12, 0.2);
    this.tone("triangle", base * 1.5, base * 1.5, 0.22, 0.14, 0.06);
  }

  hit() {
    if (!this.ctx) return;
    const ctx = this.ctx, t = this.now(), s = this.noiseSource(), g = ctx.createGain();
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 1200;
    this.env(g, t, 0.002, 0.4, 0.3);
    s.connect(lp).connect(g).connect(this.sfx); s.start(t); s.stop(t + 0.35);
    this.tone("sawtooth", 220, 55, 0.35, 0.25);
  }

  gate() { [0, 4, 7, 12].forEach((d, i) => this.tone("triangle", midi(69 + d), midi(69 + d), 0.5, 0.16, i * 0.09)); }
  win() { [0, 4, 7, 12, 16, 19, 24].forEach((d, i) => this.tone("square", midi(69 + d), midi(69 + d), 0.3, 0.08, i * 0.08)); }
}
