"""Captions and the final ffmpeg edit: join segments, add the voice-over, burn captions and an AI label."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .blender_run import find_ffmpeg

LABEL = "AI-generated"
FONTS = ("C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font() -> str | None:
    """drawtext needs a font file where fontconfig isn't set up (Windows ffmpeg builds)."""
    return next((f for f in (os.environ.get("STANDIN_FONT"), *FONTS) if f and Path(f).is_file()), None)


def chunks(plan: dict, spoken: list[float] | None = None, words: int = 3) -> list[tuple[float, float, str]]:
    """Caption cues: each beat's line in ~3-word pieces, spread over the time it is spoken."""
    cues, start = [], 0.0
    for i, b in enumerate(plan["beats"]):
        w = b["vo"].split()
        talk = (spoken[i] if spoken else 0) or b["duration"] * 0.9
        parts = [" ".join(w[j:j + words]) for j in range(0, len(w), words)]
        for k, text in enumerate(parts):
            step = talk / len(parts)
            cues.append((round(start + k * step, 3), round(start + (k + 1) * step, 3), text))
        start += b["duration"]
    return cues


def _ts(s: float) -> str:
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def srt(cues) -> str:
    return "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1))


def _ffmpeg(args: list[str], cwd: Path, run) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found: install it or set STANDIN_FFMPEG")
    cmd = [ffmpeg, "-y", "-loglevel", "error", *args]
    p = run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")


def concat(segments: list[Path], out: Path, run=subprocess.run) -> Path:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in segments), encoding="utf-8")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", lst.name, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-r", "24", out.name], out.parent, run)
    return out


def finish(video: Path, out: Path, audio: Path | None, captions: Path | None, run=subprocess.run) -> Path:
    """All paths must sit in out.parent: ffmpeg runs there so the subtitles path needs no escaping."""
    vf = [f"subtitles={captions.name}:force_style='Fontsize=14,MarginV=60'"] if captions else []
    f = font()
    ff = ":fontfile='" + f.replace(":", "\\:") + "'" if f else ""  # escape C: for the filter
    vf.append(f"drawtext=text='{LABEL}'{ff}:x=w-tw-20:y=20:fontsize=h/45:fontcolor=white@0.85"
              ":box=1:boxcolor=black@0.45:boxborderw=6")
    args = ["-i", video.name] + (["-i", audio.name] if audio else [])
    args += ["-vf", ",".join(vf), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-shortest"] if audio else ["-an"]
    _ffmpeg(args + [out.name], out.parent, run)
    return out
