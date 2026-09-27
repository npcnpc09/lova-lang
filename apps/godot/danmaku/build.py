"""Assemble and run the Godot project of the danmaku duel.

    python apps/godot/danmaku/build.py [--smoke | --run | --shot=out.png | --movie=out.mp4]
                                       [--phase=N] [--at=TICKS] [--ticks=N] [--gl]

What it makes, in `apps/godot/danmaku/project/` (not tracked):

- a copy of `game/` -- the project file, the one scene and `main.gd`,
  which builds everything drawn and heard in code;
- `bin/lova_godot.dll`, the native runtime as a GDExtension class,
  built by `cargo build --release` in `native/lova-godot`;
- `lova/danmaku_godot.hex`: `danmaku_godot.lova` (which is
  `lib/danmaku.lova` and the names Godot takes) compiled and encoded
  to its byte sequence.

`--smoke` plays ten seconds headless with nobody at the keys and prints
what the ticks cost; `--run` plays; `--shot=out.png` lets the autopilot
play `--at` ticks (600 by default) from `--phase` and saves the
picture; `--movie=out.mp4` records `--ticks` ticks (1800) of the
autopilot in Godot's movie-maker mode and converts with ffmpeg.  `--gl`
is accepted for symmetry with the FPS build; the project is on the
compatibility renderer already.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from core.cli import build  # noqa: E402
from core.tokens import encode  # noqa: E402

PROJECT = HERE / "project"
GAME = HERE / "game"
CRATE = ROOT / "native" / "lova-godot"
GODOT_DEFAULTS = [Path(r"D:\game\godot\Godot_v4.7.2-stable_win64_console.exe"),
                  Path(r"D:\game\godot\Godot_v4.7.2-stable_win64.exe")]


def library() -> Path:
    for name in ("lova_godot.dll", "liblova_godot.so", "liblova_godot.dylib"):
        p = CRATE / "target" / "release" / name
        if p.exists():
            return p
    raise SystemExit("no built extension: run `cargo build --release` in native/lova-godot")


def godot() -> Path | None:
    env = os.environ.get("GODOT")
    if env and Path(env).exists():
        return Path(env)
    return next((p for p in GODOT_DEFAULTS if p.exists()), None)


def compile_program() -> str:
    source = (HERE / "danmaku_godot.lova").read_text(encoding="utf-8")
    tree, _report = build(source)
    data = encode(tree)
    print(f"  danmaku_godot.lova -> {len(data)} bytes")
    return data.hex()


def assemble() -> None:
    keep = PROJECT / ".godot"
    PROJECT.mkdir(exist_ok=True)
    for src in GAME.rglob("*"):
        if src.is_file():
            dst = PROJECT / src.relative_to(GAME)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    lib = library()
    (PROJECT / "bin").mkdir(exist_ok=True)
    shutil.copy2(lib, PROJECT / "bin" / lib.name)
    print(f"  runtime: {lib.name}, {lib.stat().st_size // 1024} KB")
    (PROJECT / "lova").mkdir(exist_ok=True)
    (PROJECT / "lova" / "danmaku_godot.hex").write_text(compile_program() + "\n", encoding="ascii")
    keep.mkdir(exist_ok=True)
    (keep / "extension_list.cfg").write_text("res://lova.gdextension\n", encoding="ascii")


def import_resources(exe: Path) -> None:
    cmd = [str(exe), "--headless", "--editor", "--import", "--path", str(PROJECT), "--quit"]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print("  resources imported")


def record(exe: Path, out: Path, user: list[str]) -> int:
    avi = out.with_suffix(".avi")
    cmd = [str(exe), "--path", str(PROJECT), "--write-movie", str(avi), "--fixed-fps", "60", "--"] + user
    print("  " + " ".join(cmd))
    code = subprocess.call(cmd)
    if code != 0 or not avi.exists():
        return code or 1
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or avi == out:
        print(f"  the recording is {avi}")
        return 0
    conv = [ffmpeg, "-y", "-i", str(avi), "-c:v", "libx264", "-preset", "slow", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    code = subprocess.call(conv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if code == 0:
        avi.unlink()
        print(f"  recorded: {out} ({out.stat().st_size // 1024} KB)")
    return code


def main(argv: list[str]) -> int:
    flags = [a for a in argv if a.startswith("--")]
    value = lambda name, default=None: next((a.split("=", 1)[1] for a in flags if a.startswith(name + "=")), default)  # noqa: E731
    assemble()
    exe = godot()
    if exe is None:
        print(f"  ready: {PROJECT} (no Godot binary: set $GODOT)")
        return 0
    import_resources(exe)
    user: list[str] = []
    if value("--phase") is not None:
        user.append(f"--phase={value('--phase')}")
    if "--smoke" in flags:
        cmd = [str(exe), "--headless", "--path", str(PROJECT), "--", "--smoke", "--demo"] + user
        print("  " + " ".join(cmd))
        return subprocess.call(cmd)
    if "--run" in flags:
        return subprocess.call([str(exe), "--path", str(PROJECT), "--"] + user)
    shot = value("--shot")
    if shot:
        out = Path(shot).resolve()
        cmd = [str(exe), "--path", str(PROJECT), "--", f"--shot={out}", f"--at={value('--at', '600')}"] + user
        print("  " + " ".join(cmd))
        return subprocess.call(cmd)
    movie = value("--movie")
    if movie:
        return record(exe, Path(movie).resolve(), [f"--movie={value('--ticks', '1800')}"] + user)
    print(f"  ready: {PROJECT}\n  run:   {exe} --path {PROJECT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
