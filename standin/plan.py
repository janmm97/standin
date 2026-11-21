"""The shot plan: what each beat shows, how the stand-ins move, what the voice says.

A local LM Studio model writes it; without one, a template plan is used.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .direction import ANGLES, DEFAULT_LOOK, SHOTS

PRESETS = ("walk_in", "wave", "point", "hand_off", "turn_to_camera", "sit", "idle")
CAMERAS = ("static", "dolly", "orbit", "handheld")
DURATIONS = (4, 6, 8)
ASPECTS = ("9:16", "16:9")
VOICES = ("tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe")
MAX_BEATS = 6

SCHEMA = {
    "type": "object",
    "required": ["title", "location", "look", "cast", "beats"],
    "properties": {
        "title": {"type": "string"},
        "location": {"type": "string"},
        "look": {"type": "string"},
        "cast": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {"type": "object", "required": ["name", "look"],
                      "properties": {"name": {"type": "string"}, "look": {"type": "string"}}},
        },
        "beats": {
            "type": "array", "minItems": 1, "maxItems": MAX_BEATS,
            "items": {
                "type": "object",
                "required": ["shot", "angle", "action", "camera", "duration", "scene", "vo"],
                "properties": {
                    "shot": {"type": "string", "enum": list(SHOTS)},
                    "angle": {"type": "string", "enum": list(ANGLES)},
                    "action": {"type": "string", "enum": list(PRESETS)},
                    "camera": {"type": "string", "enum": list(CAMERAS)},
                    "duration": {"type": "integer", "enum": list(DURATIONS)},
                    "scene": {"type": "string"},
                    "vo": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = (
    "You are the director and cinematographer of a short vertical ad. Reply with JSON only. "
    "'location' is ONE specific, real-feeling place used for every beat (materials, time of day, practical "
    "lights), e.g. 'narrow corner cafe, worn oak counter, snow outside the window, 7am'. "
    "'look' is the visual style for the whole film: light, palette, lens feel and grain, e.g. 'soft cold "
    "window key, warm tungsten practicals, muted creams and browns, 35mm film grain'. "
    f"Each beat: 'shot' is one of {', '.join(SHOTS)}; vary them (open wide, then go closer, and use a "
    f"'detail' insert on the product). 'angle' is one of {', '.join(ANGLES)}. 'action' is one of "
    f"{', '.join(PRESETS)}; 'camera' is one of {', '.join(CAMERAS)}; duration is 4, 6 or 8 seconds. "
    "'scene' says exactly what we see in this frame: who does what, with which object, where the light "
    "falls. Be concrete; never use filler words like 'modern space', 'stunning' or 'vibrant'. "
    "'vo' is the spoken line for that beat, about 2.5 words per second: hook the viewer in the first "
    "line, never just repeat the brief, end on a clear call to action; a beat may have an empty 'vo'. "
    "'look' on each cast member describes their appearance (age, clothing, hair) without naming real people."
)


def _pick(value, allowed, default):
    value = str(value).strip().lower() if value is not None else ""
    return value if value in allowed else default


def _duration(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 6
    return min(DURATIONS, key=lambda d: abs(d - n))


def _list(x) -> list:
    return x if isinstance(x, list) else []


def normalize(raw: dict, aspect: str = "9:16") -> dict:
    """Clamp anything a small model gets wrong into a plan the renderer can use."""
    cast = [
        {"name": str(c.get("name") or f"Actor {i + 1}")[:40], "look": str(c.get("look") or "")[:300]}
        for i, c in enumerate(_list(raw.get("cast"))[:3]) if isinstance(c, dict)
    ] or [{"name": "Host", "look": "friendly presenter in casual clothes"}]
    beats = []
    for b in _list(raw.get("beats"))[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        beats.append({
            "shot": _pick(b.get("shot"), SHOTS, "medium"),
            "angle": _pick(b.get("angle"), ANGLES, "eye"),
            "action": _pick(b.get("action"), PRESETS, "idle"),
            "camera": _pick(b.get("camera"), CAMERAS, "static"),
            "duration": _duration(b.get("duration")),
            "scene": str(b.get("scene") or "")[:500],
            "vo": " ".join(str(b.get("vo") or "").split())[:400],
        })
    if not beats:
        raise ValueError("plan has no beats")
    return {
        "title": str(raw.get("title") or "untitled")[:80],
        "location": " ".join(str(raw.get("location") or "").split())[:300],
        "look": " ".join(str(raw.get("look") or "").split())[:300] or DEFAULT_LOOK,
        "aspect": aspect if aspect in ASPECTS else "9:16",
        "voice": _pick(raw.get("voice"), VOICES, "tara"),
        "cast": cast,
        "beats": beats,
    }


def template_plan(brief: str, aspect: str = "9:16") -> dict:
    """A fixed 3-beat plan that works with no model: wide, detail, close. Its only line is the brief, so
    rewrite the 'vo' (and 'location') in plan.json, or let a model write the plan, for real copy."""
    brief = " ".join(brief.split())
    return normalize({
        "title": brief[:60] or "standin clip",
        "location": f"a specific, lived-in real-world place where this naturally happens: {brief}",
        "look": DEFAULT_LOOK,
        "cast": [{"name": "Host",
                  "look": "a person in their 30s, understated everyday clothes, natural hair"}],
        "beats": [
            {"shot": "wide", "angle": "eye", "action": "walk_in", "camera": "dolly", "duration": 4,
             "scene": "the host walks into frame through the space, light falling across them", "vo": ""},
            {"shot": "detail", "angle": "high", "action": "point", "camera": "static", "duration": 6,
             "scene": f"the host's hand gestures to the product, sharp in the foreground. Subject: {brief}",
             "vo": brief[:150]},
            {"shot": "close", "angle": "low", "action": "turn_to_camera", "camera": "orbit", "duration": 4,
             "scene": "the host turns toward the camera with a small, unforced smile", "vo": ""},
        ],
    }, aspect)


def lmstudio_url() -> str:
    return os.environ.get("STANDIN_LMSTUDIO_URL", "http://localhost:1234/v1").rstrip("/")


def chat_json(model: str, system: str, user: str, schema: dict, post=None) -> dict:
    """Ask LM Studio's OpenAI-compatible server for JSON that matches `schema`."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.4,
        "max_tokens": 1500,
        # Thinking models (Qwen3.x) otherwise spend the whole budget reasoning; LM Studio honours this.
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "plan", "strict": True, "schema": schema},
        },
    }
    data = (post or _post)(lmstudio_url() + "/chat/completions", body)
    text = data["choices"][0]["message"]["content"]
    # Reasoning models may wrap the JSON; take the outermost object.
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:  # noqa: S310 (local LM Studio URL)
        return json.loads(r.read())


def make_plan(brief: str, model: str | None, aspect: str = "9:16", post=None) -> tuple[dict, str]:
    """Returns (plan, source). Falls back to the template if no model or the model fails."""
    if model:
        try:
            raw = chat_json(model, SYSTEM, f"Brief: {brief}\nAspect: {aspect}", SCHEMA, post=post)
            return normalize(raw, aspect), f"LM Studio ({model})"
        except Exception as e:  # noqa: BLE001 (any model/server failure falls back)
            return template_plan(brief, aspect), f"template (LM Studio failed: {type(e).__name__}: {e})"[:200]
    return template_plan(brief, aspect), "template (no chat model)"


def keyframe_frames(plan: dict, fps: int = 24) -> list[int]:
    """The first and last frame of every beat: N beats -> 2N keyframes. Beats cut from one shot to the
    next (frame s ends beat i-1, frame s + 1 opens beat i), so each video segment gets its own pair."""
    frames, s = [], 1
    for i, b in enumerate(plan["beats"]):
        e = s + b["duration"] * fps
        frames += [s if i == 0 else s + 1, e]
        s = e
    return frames


def total_seconds(plan: dict) -> int:
    return sum(b["duration"] for b in plan["beats"])
