"""Local voice-over: Orpheus TTS served by LM Studio, decoded with SNAC to 24 kHz WAV.

Needs an Orpheus GGUF in LM Studio (e.g. `orpheus-3b-0.1-ft`) and `pip install standin[voice]`.
"""

from __future__ import annotations

import re
import sys
import wave
from pathlib import Path

from .plan import _post, lmstudio_url

RATE = 24000
TOKEN = re.compile(r"<custom_token_(\d+)>")
_decoder = None


def prompt(text: str, voice: str) -> str:
    return f"<|audio|>{voice}: {text}<|eot_id|>"


def parse_tokens(text: str) -> list[int]:
    """Orpheus prints audio as <custom_token_N>; slot k of every 7-token frame is offset by k * 4096."""
    ids = []
    for m in TOKEN.finditer(text):
        i = int(m.group(1)) - 10 - (len(ids) % 7) * 4096
        if 0 < i < 4096:  # as in the Orpheus reference decoder
            ids.append(i)
    return ids[: len(ids) // 7 * 7]


def to_layers(ids: list[int]) -> tuple[list[int], list[int], list[int]]:
    l0, l1, l2 = [], [], []
    for f in range(0, len(ids), 7):
        a = ids[f:f + 7]
        l0.append(a[0])
        l1 += [a[1], a[4]]
        l2 += [a[2], a[3], a[5], a[6]]
    return l0, l1, l2


def decode(layers) -> bytes:
    """SNAC codes -> 16-bit mono PCM at 24 kHz."""
    global _decoder
    try:
        import torch
        from snac import SNAC
    except ImportError as e:
        raise RuntimeError("voice needs the extra: pip install 'standin[voice]'") from e
    if _decoder is None:
        _decoder = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
    codes = [torch.tensor([layer], dtype=torch.int32) for layer in layers]
    with torch.inference_mode():
        audio = _decoder.decode(codes).squeeze().clamp(-1, 1)
    return (audio * 32767).to(torch.int16).numpy().tobytes()


def speak(text: str, voice: str, model: str, post=None, decoder=None) -> bytes:
    body = {"model": model, "prompt": prompt(text, voice), "temperature": 0.6, "top_p": 0.9,
            "repeat_penalty": 1.1, "max_tokens": 2400, "stream": False}
    out = (post or _post)(lmstudio_url() + "/completions", body)
    ids = parse_tokens(out["choices"][0]["text"])
    if not ids:
        raise RuntimeError(f"{model} returned no audio tokens (is it an Orpheus model?)")
    return (decoder or decode)(to_layers(ids))


def fit(pcm: bytes, seconds: float) -> bytes:
    """Pad with silence or cut so a beat's audio lasts exactly `seconds`."""
    n = int(seconds * RATE) * 2
    return pcm[:n] + b"\0" * max(0, n - len(pcm))


def write_wav(path: Path, pcm: bytes) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return path


def voice_over(plan: dict, model: str, out: Path, post=None, decoder=None) -> tuple[Path, list[float]]:
    """One line per beat, each fitted to its beat. Returns the WAV and the spoken seconds per beat."""
    pcm, spoken = b"", []
    for b in plan["beats"]:
        line = speak(b["vo"], plan["voice"], model, post, decoder) if b["vo"] else b""
        said = len(line) / 2 / RATE
        if said > b["duration"] + 0.1:
            print(f"warning: voice line runs {said:.1f}s in a {b['duration']}s beat and is cut;"
                  " shorten the line or lengthen the beat", file=sys.stderr)
        spoken.append(min(said, b["duration"]))
        pcm += fit(line, b["duration"])
    return write_wav(out, pcm), spoken
