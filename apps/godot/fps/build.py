"""Assemble the Godot project: the kit, the LOVA rules, the runtime.

    python apps/godot/fps/build.py [path/to/Starter-Kit-FPS] [--smoke | --run | --shot=out.png] [--gl]

What it makes, in `apps/godot/fps/project/` (not tracked):

- a copy of KenneyNL/Starter-Kit-FPS (MIT) -- its scenes, models,
  sounds and project settings, untouched;
- over it, `overlay/`: `objects/player.gd` and `objects/enemy.gd` with
  the kit's rules taken out and calls into the runtime put in, the
  `.gdextension` manifest, and the headless smoke script;
- `bin/lova_godot.dll`, the native runtime as a GDExtension class,
  built by `cargo build --release` in `native/lova-godot`;
- `lova/fps_godot.hex`: `fps_godot.lova` (which is `lib/fps.lova` and
  a `scene` function) parsed, expanded, compiled and encoded to its
  byte sequence, as the hex the runtime's protocol takes.

`--smoke` then runs `lova_smoke.gd` under `godot --headless`; `--run`
plays the game; `--shot=out.png` plays a scripted two seconds with
nobody at the keys, saves the picture and quits.  `--gl` runs Godot on
the OpenGL compatibility renderer, for a machine whose Vulkan driver
cannot build the Forward+ shaders.  The Godot binary is `$GODOT` or
the one in `D:/game/godot`; the project's resources are imported once,
headlessly, after it is assembled.
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
OVERLAY = HERE / "overlay"
CRATE = ROOT / "native" / "lova-godot"
KIT_DEFAULTS = [Path(r"D:\SSH\Starter-Kit-FPS"), Path(r"C:\Users\LI\AppData\Local\Temp\Starter-Kit-FPS")]
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
    for p in GODOT_DEFAULTS:
        if p.exists():
            return p
    return None


def compile_program() -> str:
    source = (HERE / "fps_godot.lova").read_text(encoding="utf-8")
    tree, _report = build(source)
    data = encode(tree)
    print(f"  fps_godot.lova -> {len(data)} bytes")
    return data.hex()


def assemble(kit: Path) -> None:
    if not (kit / "project.godot").exists():
        raise SystemExit(f"{kit}: not a Godot project (no project.godot)")
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    shutil.copytree(kit, PROJECT, ignore=shutil.ignore_patterns(".git", ".godot"))
    print(f"  kit copied from {kit}")
    for src in OVERLAY.rglob("*"):
        if src.is_file():
            dst = PROJECT / src.relative_to(OVERLAY)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print(f"  overlay: {sum(1 for s in OVERLAY.rglob('*') if s.is_file())} files")
    lib = library()
    (PROJECT / "bin").mkdir(exist_ok=True)
    shutil.copy2(lib, PROJECT / "bin" / lib.name)
    print(f"  runtime: {lib.name}, {lib.stat().st_size // 1024} KB")
    (PROJECT / "lova").mkdir(exist_ok=True)
    (PROJECT / "lova" / "fps_godot.hex").write_text(compile_program() + "\n", encoding="ascii")
    # The editor writes this list when it imports the project; a run
    # with no editor needs it to load the extension at all.
    (PROJECT / ".godot").mkdir(exist_ok=True)
    (PROJECT / ".godot" / "extension_list.cfg").write_text("res://lova.gdextension\n", encoding="ascii")


def import_resources(exe: Path) -> None:
    """The editor's import pass, with no window: models, textures and
    fonts become what the player loads."""
    cmd = [str(exe), "--headless", "--editor", "--import", "--path", str(PROJECT), "--quit"]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print("  resources imported")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    kit = Path(args[0]) if args else next((k for k in KIT_DEFAULTS if k.exists()), None)
    if kit is None:
        raise SystemExit("where is Starter-Kit-FPS?  build.py path/to/Starter-Kit-FPS")
    assemble(kit)
    exe = godot()
    if exe is not None:
        import_resources(exe)
    renderer = ["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"] if "--gl" in flags else []
    if "--smoke" in flags:
        if exe is None:
            raise SystemExit("no Godot binary: set $GODOT")
        cmd = [str(exe), "--headless", "--path", str(PROJECT), "--script", "res://lova_smoke.gd"]
        print("  " + " ".join(cmd))
        return subprocess.call(cmd)
    if "--run" in flags:
        if exe is None:
            raise SystemExit("no Godot binary: set $GODOT")
        return subprocess.call([str(exe), "--path", str(PROJECT)] + renderer)
    shot = next((a for a in flags if a.startswith("--shot=")), None)
    if shot:
        if exe is None:
            raise SystemExit("no Godot binary: set $GODOT")
        out = Path(shot[7:]).resolve()
        cmd = [str(exe), "--path", str(PROJECT)] + renderer + ["--", f"--shot={out}"]
        print("  " + " ".join(cmd))
        return subprocess.call(cmd)
    print(f"  ready: {PROJECT}")
    if exe:
        print(f"  run:   {exe} --path {PROJECT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
