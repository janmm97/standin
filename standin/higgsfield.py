"""Higgsfield through One: cast stills (Soul), put actors into keyframes (Nano Banana),
and animate between keyframes (Veo 3.1 first/last frame). Every call here costs money."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import one

PLATFORM = "higgsfield-ai"
KEY_ENV = "STANDIN_HIGGSFIELD_KEY"
ACTIONS = {
    "soul": "conn_mod_def::GLMJmLlKvDA::IsJAd2nGRUuNO4TEAJUq1w",
    "nano_banana": "conn_mod_def::GLMJlkVhLik::ELbDTgsMRuC82s7SV_PI-Q",
    "veo": "conn_mod_def::GLMJmlOMLZ4::Bjzx-t6LT1-24U6in0cBEw",
    "veo_fast": "conn_mod_def::GLMJmcpOsS8::8ykS6oPWRQKMObZlNxGBEA",
    "status": "conn_mod_def::GLMJljPc0Ck::kvGINkpWRMSU7aHg_Uy-AA",
}
# USD, rough public prices (2026-11); shown before any paid run.
PRICE = {"soul": 0.02, "nano_banana": 0.04, "veo_per_s": 0.40, "veo_fast_per_s": 0.10}
MAX_POLL_ERRORS = 3
DONE, BAD = "completed", ("failed", "nsfw", "canceled")
MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm")


def estimate(plan: dict, draft: bool = True) -> dict:
    n_cast, n_keys = len(plan["cast"]), len(plan["beats"]) + 1
    secs = sum(b["duration"] for b in plan["beats"])
    rate = PRICE["veo_fast_per_s" if draft else "veo_per_s"]
    parts = {"soul": n_cast * PRICE["soul"], "nano_banana": n_keys * PRICE["nano_banana"], "veo": secs * rate}
    return {**{k: round(v, 2) for k, v in parts.items()}, "total": round(sum(parts.values()), 2)}


def soul_body(member: dict, aspect: str) -> dict:
    return {"prompt": f"photoreal full-body photo of {member['look']}, plain light studio background, "
                      "natural skin texture, soft light", "num_images": 1, "resolution": "2K",
            "aspect_ratio": aspect}


def insert_body(pose_url: str, cast_urls: list[str], scene: str, aspect: str) -> dict:
    who = "; ".join(f"mannequin {i + 1} becomes the person in reference image {i + 2}"
                    for i in range(len(cast_urls)))
    return {
        "prompt": ("Photoreal film still. Image 1 is a pose reference made of grey mannequins: keep every "
                   f"body pose, position and the camera framing exactly. {who}. Setting: {scene}. "
                   "No mannequins, no text."),
        "num_images": 1, "aspect_ratio": aspect, "output_format": "png",
        # The docs leave this item schema unresolved; this shape is a best guess, not verified.
        "input_images": [{"type": "image_url", "image_url": u} for u in [pose_url, *cast_urls]],
    }


def veo_body(first_url: str, last_url: str, prompt: str, duration: int, aspect: str) -> dict:
    return {"prompt": prompt, "first_frame_url": first_url, "last_frame_url": last_url, "duration": duration,
            "resolution": "720", "aspect_ratio": aspect, "generate_audio": False}


def urls(obj, skip=("status_url", "cancel_url")) -> list[str]:
    """Every media URL anywhere in a status response (its result shape isn't documented)."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                found += urls(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            found += urls(v, skip)
    elif isinstance(obj, str) and obj.startswith("https://"):
        if obj.split("?")[0].lower().endswith(MEDIA):
            found.append(obj)
    return list(dict.fromkeys(found))


class Client:
    def __init__(self, key: str | None = None, execute=one.execute, sleep=time.sleep,
                 poll_s=5, timeout_s=900):
        self.key = key or one.connection_key(PLATFORM, KEY_ENV)
        self.execute, self.sleep, self.poll_s, self.timeout_s = execute, sleep, poll_s, timeout_s

    def submit(self, model: str, body: dict) -> str:
        r = self.execute(PLATFORM, ACTIONS[model], self.key, body)
        if not r.get("request_id"):
            raise one.OneError(f"{model}: no request_id in {str(r)[:300]}")
        return r["request_id"]

    def wait(self, request_id: str, ignore=()) -> list[str]:
        """Poll until done; returns the result URLs, minus any in `ignore` (the inputs we sent)."""
        waited, misses = 0, 0
        while True:
            try:
                r = self.execute(PLATFORM, ACTIONS["status"], self.key, None, {"requestId": request_id})
                misses = 0
            except one.OneError:
                # The job is already paid for: ride out a flaky poll instead of abandoning it.
                misses += 1
                if misses > MAX_POLL_ERRORS:
                    raise
                r = {"status": "unknown"}
            status = r.get("status")
            if status == DONE:
                found = [u for u in urls(r) if u not in ignore]
                if not found:
                    raise one.OneError(f"{request_id} completed but no media URL in {str(r)[:300]}")
                return found
            if status in BAD:
                raise one.OneError(f"{request_id} ended as {status}")
            if waited >= self.timeout_s:
                raise one.OneError(f"{request_id} still {status} after {self.timeout_s}s")
            self.sleep(self.poll_s)
            waited += self.poll_s

    def run(self, model: str, body: dict, dest: Path, fetch=None) -> Path:
        url = self.wait(self.submit(model, body), ignore=set(urls(body)))[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        (fetch or _fetch)(url, dest)
        return dest


def _fetch(url: str, dest: Path) -> None:
    if not url.startswith("https://"):
        raise one.OneError(f"refusing non-https result URL: {url[:80]}")
    tmp = dest.with_name(dest.name + ".part")  # never leave a half-written file under the real name
    with _OPENER.open(url, timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, dest)


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise urllib.error.URLError(f"refusing redirect to non-https URL: {newurl[:80]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_HttpsOnly)
