"""The shot plan: what each beat shows, how the stand-ins move, what the voice says.

A local LM Studio model writes it; without one, a template plan is used.
"""

from __future__ import annotations

import json
import os
import urllib.request

PRESETS = ("walk_in", "wave", "point", "hand_off", "turn_to_camera", "sit", "idle")
CAMERAS = ("static", "dolly", "orbit", "handheld")
DURATIONS = (4, 6, 8)
ASPECTS = ("9:16", "16:9")
VOICES = ("tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe")
MAX_BEATS = 6

SCHEMA = {
    "type": "object",
    "required": ["title", "cast", "beats"],
    "properties": {
        "title": {"type": "string"},
        "cast": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {"type": "object", "required": ["name", "look"],
                      "properties": {"name": {"type": "string"}, "look": {"type": "string"}}},
        },
        "beats": {
            "type": "array", "minItems": 1, "maxItems": MAX_BEATS,
            "items": {
                "type": "object", "required": ["action", "camera", "duration", "scene", "vo"],
                "properties": {
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
    "You plan short vertical marketing videos. Reply with JSON only. "
    f"Each beat uses one action from {', '.join(PRESETS)} and one camera from {', '.join(CAMERAS)}; "
    "duration is 4, 6 or 8 seconds. 'scene' describes the photoreal setting and what the actor does. "
    "'vo' is the voice-over line for that beat: about 2.5 words per second, plain spoken English. "
    "'look' describes each actor's appearance (age, clothing, hair) without naming real people."
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


def normalize(raw: dict, aspect: str = "9:16") -> dict:
    """Clamp anything a small model gets wrong into a plan the renderer can use."""
    cast = [
        {"name": str(c.get("name") or f"Actor {i + 1}")[:40], "look": str(c.get("look") or "")[:300]}
        for i, c in enumerate((raw.get("cast") or [])[:3]) if isinstance(c, dict)
    ] or [{"name": "Host", "look": "friendly presenter in casual clothes"}]
    beats = []
    for b in (raw.get("beats") or [])[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        beats.append({
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
        "aspect": aspect if aspect in ASPECTS else "9:16",
        "voice": _pick(raw.get("voice"), VOICES, "tara"),
        "cast": cast,
        "beats": beats,
    }


def template_plan(brief: str, aspect: str = "9:16") -> dict:
    """A fixed 3-beat plan that works with no model at all."""
    brief = " ".join(brief.split())
    return normalize({
        "title": brief[:60] or "standin clip",
        "cast": [{"name": "Host", "look": "friendly presenter in their 30s, casual smart clothes"}],
        "beats": [
            {"action": "walk_in", "camera": "dolly", "duration": 4,
             "scene": f"bright modern space; the host walks in. Topic: {brief}",
             "vo": "Here's something worth a look."},
            {"action": "point", "camera": "static", "duration": 6,
             "scene": f"the host points to the side while explaining: {brief}", "vo": brief[:150]},
            {"action": "turn_to_camera", "camera": "orbit", "duration": 4,
             "scene": "the host turns to camera and smiles", "vo": "Try it today."},
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
    """Frame numbers at every beat boundary, starting at 1: N beats -> N + 1 keyframes."""
    frames, t = [1], 0
    for b in plan["beats"]:
        t += b["duration"]
        frames.append(1 + t * fps)
    return frames


def total_seconds(plan: dict) -> int:
    return sum(b["duration"] for b in plan["beats"])
