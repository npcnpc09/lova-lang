"""Record Neon Alley: a frame at a time, nothing dropped, with its sound.

    python apps/web/neon/record.py [--out demo.mp4] [--portal ../../../docs/assets/neon-480.mp4]

Needs the assembled `site/` (`build.py`), Playwright for Python with its
Chromium, and ffmpeg on the path.

The page is opened with `?record`, where time moves only when this
script calls `__neon.step(1/30)`: each call is one frame of the video,
rendered and captured however long that takes, so the result plays at
full rate on any machine.  A driver in the page plays: it goes for the
nearest spark, jumps for the high ones and over a drone in its way, and
walks out of the gate.  The page writes down every sound it would have
made and when; the sound track is then rendered by the page's own
synthesiser in an OfflineAudioContext on that timeline, and ffmpeg puts
the frames and the sound together.

The choreography: the title for two and a half seconds, the game from
the first step to the gate, the result for three.
"""

from __future__ import annotations

import base64
import functools
import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / "site"
FPS = 30
W, H = 1280, 720

# The driver, installed into the page as the hook it calls before every
# tick.  It only presses keys: what happens is the rules' answer.
DRIVER = r"""
() => {
  const n = window.__neon;
  n.hooks.beforeTick = (s, L) => {
    const g = s.ghost;
    let tx = 0, tz = L.length + 1, high = false, best = 1e9;
    L.sparks.forEach((sp, i) => {
      if (s.sparks[i]) return;
      const d = Math.hypot(sp.x - g.x, sp.z - g.z);
      if (d < best) { best = d; tx = sp.x; tz = sp.z; high = sp.y > 1; }
    });
    n.held.clear();
    const dx = tx - g.x, dz = tz - g.z;
    if (Math.abs(dx) > 0.15) n.held.add(dx > 0 ? "right" : "left");
    if (Math.abs(dz) > 0.15) n.held.add(dz > 0 ? "up" : "down");
    let jump = high && Math.hypot(dx, dz) < 1.6;
    L.drones.forEach((z, i) => {
      const ddz = z - g.z;
      if (ddz > -0.3 && ddz < 1.6 && Math.abs(s.drones[i] - g.x) < 1.4) jump = true;
    });
    if (jump) n.held.add("jump");
  };
}
"""

# The sound track: the page's synthesiser, offline, as 16-bit WAV bytes
# in base64.
RENDER = r"""
async ([seconds, musicFrom]) => {
  const { Sound } = await import("./audio.js");
  const buf = await Sound.render(window.__neon.sound.log, seconds, musicFrom);
  const n = buf.length, ch = buf.numberOfChannels, rate = buf.sampleRate;
  const out = new DataView(new ArrayBuffer(44 + n * ch * 2));
  const str = (o, s) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); out.setUint32(4, 36 + n * ch * 2, true); str(8, "WAVE"); str(12, "fmt ");
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true);
  out.setUint32(24, rate, true); out.setUint32(28, rate * ch * 2, true); out.setUint16(32, ch * 2, true);
  out.setUint16(34, 16, true); str(36, "data"); out.setUint32(40, n * ch * 2, true);
  const data = [...Array(ch).keys()].map(c => buf.getChannelData(c));
  let o = 44;
  for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) {
    const v = Math.max(-1, Math.min(1, data[c][i]));
    out.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true); o += 2;
  }
  const bytes = new Uint8Array(out.buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
"""


def chromium() -> str | None:
    """Playwright's own Chromium if it is there; else the newest one any
    Playwright on this machine installed (`$LOVA_CHROMIUM` wins)."""
    import glob
    import os
    if os.environ.get("LOVA_CHROMIUM"):
        return os.environ["LOVA_CHROMIUM"]
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    found = sorted(glob.glob(str(root / "chromium-*" / "chrome-win*" / "chrome.exe")))
    return found[-1] if found else None


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".wasm": "application/wasm", ".js": "text/javascript"}

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def capture(frames: Path) -> tuple[float, float]:
    """Play and save a JPEG a frame; return (seconds, when the music starts)."""
    from playwright.sync_api import sync_playwright

    httpd, port = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chromium(), args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                              "--autoplay-policy=no-user-gesture-required"])
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            page.on("console", lambda m: m.type == "error" and print("  page:", m.text))
            page.goto(f"http://127.0.0.1:{port}/?record")
            page.wait_for_function("window.__neon && window.__neon.rules", timeout=60_000)
            page.evaluate("document.fonts.ready")
            page.evaluate(DRIVER)
            k = 0

            def shoot(count: int, until: str | None = None) -> None:
                nonlocal k
                for _ in range(count):
                    page.evaluate(f"window.__neon.step({1 / FPS})")
                    page.screenshot(path=str(frames / f"{k:05d}.jpg"), type="jpeg", quality=94)
                    k += 1
                    if k % 60 == 0:
                        print(f"  {k} frames")
                    if until and page.evaluate(until):
                        return

            shoot(int(2.5 * FPS))
            music_from = page.evaluate("window.__neon.time")
            page.evaluate("window.__neon.begin()")
            shoot(60 * FPS, until="window.__neon.state.won === 1")
            state = page.evaluate("({t: __neon.state.t, hits: __neon.state.hits, left: __neon.state.left})")
            print(f"  escaped at {state['t'] / 60:.2f} s of play, {state['hits']} hits, {state['left']} left")
            page.evaluate("window.__neon.hooks.beforeTick = null; window.__neon.held.clear()")
            shoot(3 * FPS)
            seconds = k / FPS
            wav = base64.b64decode(page.evaluate(RENDER, [seconds, music_from]))
            (frames / "sound.wav").write_bytes(wav)
            browser.close()
            return seconds, music_from
    finally:
        httpd.shutdown()


def encode(frames: Path, out: Path, portal: Path | None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is not on the path")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "%05d.jpg"),
                    "-i", str(frames / "sound.wav"), "-c:v", "libx264", "-preset", "slow", "-crf", "24",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", str(out)], check=True)
    print(f"  {out.name}: {out.stat().st_size / 1e6:.1f} MB")
    if portal:
        # The portal's panel: the play only (the title and the result are
        # the page's own words there), 480p, 30 fps, no sound.
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "2.5", "-i", str(out), "-an",
                        "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "slow", "-crf", "28",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(portal)], check=True)
        print(f"  {portal.name}: {portal.stat().st_size / 1e6:.2f} MB")


def main(argv: list[str]) -> None:
    out = HERE / "demo.mp4"
    portal = None
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1]).resolve()
    if "--portal" in argv:
        portal = Path(argv[argv.index("--portal") + 1]).resolve()
    if not (SITE / "index.html").exists():
        raise SystemExit("no site/: run build.py first")
    frames = HERE / "_frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    try:
        seconds, music_from = capture(frames)
        print(f"  {seconds:.1f} s captured, music from {music_from:.1f} s")
        encode(frames, out, portal)
    finally:
        shutil.rmtree(frames, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
