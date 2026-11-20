"""Find the user's LM Studio models and pick the most powerful chat model that fits."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

VOICE_HINTS = ("orpheus",)


@dataclass
class Model:
    key: str
    type: str
    params_b: float
    size_bytes: int


def parse_params(text: str) -> float:
    """'4B' -> 4.0, '8x7B' -> 56.0, '270M' -> 0.27, 'qwen/qwen3.5-4b' -> 4.0; 0 if unknown."""
    m = re.search(r"(?:(\d+)x)?(\d+(?:\.\d+)?)\s*([bm])(?![a-z])", text.lower())
    if not m:
        return 0.0
    n = float(m.group(2)) * int(m.group(1) or 1)
    return n / 1000 if m.group(3) == "m" else n


def parse_ls(text: str) -> list[Model]:
    """Parse `lms ls --json`."""
    out = []
    for item in json.loads(text or "[]"):
        key = item.get("modelKey") or item.get("path") or ""
        params = parse_params(item.get("paramsString") or "") or parse_params(key.split("/")[-1])
        out.append(Model(key, item.get("type", ""), params, int(item.get("sizeBytes") or 0)))
    return out


def is_voice(m: Model) -> bool:
    return any(h in m.key.lower() for h in VOICE_HINTS)


def list_models(run=subprocess.run) -> list[Model]:
    exe = shutil.which("lms")
    if not exe:
        return []
    p = run([exe, "ls", "--json"], capture_output=True, text=True, timeout=60)
    return parse_ls(p.stdout) if p.returncode == 0 else []


def fits(key: str, run=subprocess.run) -> bool:
    """Ask LM Studio whether the model can load on this machine (no load happens)."""
    exe = shutil.which("lms")
    if not exe:
        return True
    p = run([exe, "load", key, "--estimate-only"], capture_output=True, text=True, timeout=120)
    text = (p.stdout + p.stderr).lower()
    return p.returncode == 0 and "may not" not in text and "will not" not in text and "cannot" not in text


def ensure_loaded(key: str, run=subprocess.run) -> bool:
    """Start LM Studio's local server and load `key` (both are no-ops if already done)."""
    exe = shutil.which("lms")
    if not exe:
        return False
    run([exe, "server", "start"], capture_output=True, text=True, timeout=120)
    p = run([exe, "load", key, "-y"], capture_output=True, text=True, timeout=600)
    return p.returncode == 0


def pick_chat(models: list[Model], fits=fits) -> tuple[Model | None, str]:
    """Most parameters first (then file size); the first one LM Studio says fits wins."""
    if forced := os.environ.get("STANDIN_CHAT_MODEL"):
        return Model(forced, "llm", parse_params(forced), 0), "set by STANDIN_CHAT_MODEL"
    chat = [m for m in models if m.type == "llm" and not is_voice(m)]
    chat.sort(key=lambda m: (m.params_b, m.size_bytes), reverse=True)
    for m in chat:
        if fits(m.key):
            skipped = chat.index(m)
            why = f"largest of {len(chat)} chat model(s) that fits"
            return m, why + (f" ({skipped} bigger one(s) don't fit)" if skipped else "")
    if chat:
        return chat[-1], "nothing reported a fit; using the smallest (expect CPU offload)"
    return None, "no LM Studio chat model installed"


def pick_voice(models: list[Model]) -> Model | None:
    if forced := os.environ.get("STANDIN_VOICE_MODEL"):
        return Model(forced, "llm", 3.0, 0)
    return next((m for m in models if is_voice(m)), None)
