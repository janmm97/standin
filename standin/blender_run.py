"""Run Blender headless on a plan: a low-res preview video and full-res keyframes."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

SCENE = Path(__file__).parent / "blender" / "scene.py"
BLENDER_GLOBS = (
    "C:/Program Files/Blender Foundation/Blender */blender.exe",
    "/Applications/Blender.app/Contents/MacOS/Blender",
)


def find_exe(name: str, env: str, globs=()) -> str | None:
    if p := os.environ.get(env):
        return p
    if p := shutil.which(name):
        return p
    hits = sorted(h for g in globs for h in glob.glob(g))
    return hits[-1] if hits else None


def find_blender() -> str | None:
    return find_exe("blender", "STANDIN_BLENDER", BLENDER_GLOBS)


def find_ffmpeg() -> str | None:
    return find_exe("ffmpeg", "STANDIN_FFMPEG")


def blender_cmd(blender: str, plan_path: Path, out: Path, mode: str, scale: int | None = None) -> list[str]:
    cmd = [blender, "-b", "--factory-startup", "-P", str(SCENE), "--", str(plan_path), str(out), mode]
    return cmd + ([str(scale)] if scale else [])


def render(plan: dict, out: Path, mode: str, scale: int | None = None, run=subprocess.run) -> list[Path]:
    """mode 'preview' -> PNG sequence in out/preview; 'keys' -> out/keys/k_NN.png (one per beat boundary)."""
    blender = find_blender()
    if not blender:
        raise RuntimeError("Blender not found: install Blender 4.2+ or set STANDIN_BLENDER")
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    p = run(blender_cmd(blender, plan_path, out, mode, scale), capture_output=True, text=True, timeout=3600)
    if p.returncode != 0 or f"STANDIN_DONE {mode}" not in p.stdout:
        tail = (p.stdout + p.stderr)[-1500:]
        raise RuntimeError(f"Blender {mode} render failed:\n{tail}")
    sub = "preview" if mode == "preview" else "keys"
    return sorted((out / sub).glob("*.png"))


def frames_to_mp4(frames_dir: Path, mp4: Path, fps: int = 24, run=subprocess.run) -> Path:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found: install it or set STANDIN_FFMPEG")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-pattern_type", "sequence",
           "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", str(mp4)]
    p = run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")
    return mp4
