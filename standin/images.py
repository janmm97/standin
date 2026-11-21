"""Image generation for the cast stills and keyframes, from the cheapest backend you already have.

auto picks, in order: the Codex CLI signed in with ChatGPT (included in your plan), a Gemini API key, an
OpenAI API key, then Higgsfield. `agent` writes the requests to a file so any assistant that can make images
(ChatGPT, Gemini, Claude with an image tool...) fills them in. Video (Veo) stays on Higgsfield.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import higgsfield, one

PROVIDERS = ("codex", "gemini", "openai", "agent", "higgsfield")
NOTE = {
    "codex": "Codex CLI with your ChatGPT plan (no Higgsfield image cost)",
    "gemini": "Gemini API (billed to your Google key; not in this estimate)",
    "openai": "OpenAI Images API (billed to your OpenAI key; not in this estimate)",
    "agent": "your own assistant: standin writes image_requests.json and stops",
    "higgsfield": "Higgsfield Soul + Nano Banana",
}
SHAPE = {"9:16": "portrait 9:16", "16:9": "landscape 16:9"}


def codex_cmd() -> list[str]:
    return one.npm_cmd("codex", "@openai/codex/bin/codex.js", "install it (npm i -g @openai/codex), "
                       "then `codex login`")


def detect(env=os.environ, run=subprocess.run) -> str:
    try:
        if run(codex_cmd() + ["login", "status"], capture_output=True, timeout=30).returncode == 0:
            return "codex"
    except (one.OneError, OSError, subprocess.SubprocessError):
        pass
    if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        return "gemini"
    if env.get("OPENAI_API_KEY"):
        return "openai"
    return "higgsfield"


def resolve(choice: str | None, env=os.environ, run=subprocess.run) -> str:
    choice = (choice or env.get("STANDIN_IMAGES") or "auto").lower()
    if choice == "auto":
        return detect(env, run)
    if choice not in PROVIDERS:
        raise ValueError(f"unknown image provider {choice!r}; use auto or one of {', '.join(PROVIDERS)}")
    return choice


class Codex:
    """`codex exec` with its built-in image tool. Codex runs read-only and saves under CODEX_HOME, so the
    newest image in that session's folder is copied to dest. Measured: ~45 s per image."""

    def __init__(self, env=os.environ, run=subprocess.run):
        self.env, self.run = env, run
        self.home = Path(env.get("CODEX_HOME") or Path.home() / ".codex")

    def image(self, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
        cmd = codex_cmd() + ["exec", "--skip-git-repo-check", "--sandbox", "read-only"]
        for r in refs:
            cmd += ["-i", str(r)]
        ask = (f"Use your image generation tool to make exactly one {SHAPE.get(aspect, aspect)} image. "
               f"Do not write files or run commands. {prompt}")
        p = self.run(cmd + ["-"], input=ask, capture_output=True, text=True, encoding="utf-8",
                     errors="replace", timeout=900)
        log = (p.stdout or "") + (p.stderr or "")
        m = re.search(r"session id:\s*([0-9a-fA-F-]{36})", log)
        folder = self.home / "generated_images" / (m.group(1) if m else "-")
        pngs = sorted(folder.glob("*.png"), key=lambda f: f.stat().st_mtime) if m else []
        if not pngs:
            raise RuntimeError(f"codex made no image (exit {p.returncode}): {log.strip()[-300:]}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pngs[-1], dest)
        return dest


def _post(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data, headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 (fixed https API URLs)
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # the body says why (bad key, quota, unsupported size)
        raise RuntimeError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: "
                           f"{e.read().decode('utf-8', 'replace')[:300]}") from None


def _save(b64: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(b64))
    return dest


class Gemini:
    """Gemini image model over REST. Not yet run against the live API."""

    def __init__(self, env=os.environ, post=_post):
        self.key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
        if not self.key:
            raise RuntimeError("--images gemini needs GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment")
        self.model = env.get("STANDIN_GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        self.post = post

    def image(self, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
        parts = [{"inline_data": {"mime_type": "image/png",
                                  "data": base64.b64encode(r.read_bytes()).decode()}} for r in refs]
        parts.append({"text": prompt})
        body = {"contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        r = self.post(url, json.dumps(body).encode(), {"Content-Type": "application/json",
                                                        "x-goog-api-key": self.key})
        for part in (r.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return _save(data, dest)
        raise RuntimeError(f"Gemini returned no image: {json.dumps(r)[:300]}")


class OpenAI:
    """OpenAI Images API: edits with references, generations without. Not yet run against the live API."""

    SIZE = {"9:16": "1024x1536", "16:9": "1536x1024"}

    def __init__(self, env=os.environ, post=_post):
        self.key = env.get("OPENAI_API_KEY")
        if not self.key:
            raise RuntimeError("--images openai needs OPENAI_API_KEY in the environment")
        self.model = env.get("STANDIN_OPENAI_IMAGE_MODEL", "gpt-image-1")
        self.post = post

    def image(self, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
        fields = {"model": self.model, "prompt": prompt, "size": self.SIZE.get(aspect, "auto"), "n": "1"}
        auth = {"Authorization": f"Bearer {self.key}"}
        if refs:
            data, ctype = multipart(fields, [("image[]", r) for r in refs])
            r = self.post("https://api.openai.com/v1/images/edits", data, {**auth, "Content-Type": ctype})
        else:
            fields["n"] = 1
            r = self.post("https://api.openai.com/v1/images/generations", json.dumps(fields).encode(),
                          {**auth, "Content-Type": "application/json"})
        b64 = ((r.get("data") or [{}])[0]).get("b64_json")
        if not b64:
            raise RuntimeError(f"OpenAI returned no image: {json.dumps(r)[:300]}")
        return _save(b64, dest)


def multipart(fields: dict, files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, p in files:
        head = (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{p.name}"\r\n'
                "Content-Type: image/png\r\n\r\n")
        out.append(head.encode() + p.read_bytes() + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


class Agent:
    """Writes what to make instead of making it; a rerun picks up the files the assistant saved."""

    def __init__(self):
        self.requests: list[dict] = []

    def image(self, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
        self.requests.append({"output": str(dest), "aspect": aspect, "references": [str(r) for r in refs],
                              "prompt": prompt})
        return dest


class Higgsfield:
    """Soul for a still with no references, Nano Banana with them. Uploads each reference once."""

    def __init__(self, client, host):
        self.client, self.host, self.urls = client, host, {}

    def _url(self, p: Path) -> str:
        if p not in self.urls:
            self.urls[p] = self.host.upload(p)
        return self.urls[p]

    def image(self, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
        if not refs:
            return self.client.run("soul", higgsfield.soul_body(prompt, aspect), dest)
        body = higgsfield.insert_body(self._url(refs[0]), [self._url(r) for r in refs[1:]], prompt, aspect)
        return self.client.run("nano_banana", body, dest)


def make(name: str, client=None, host=None):
    if name == "higgsfield":
        return Higgsfield(client, host)
    return {"codex": Codex, "gemini": Gemini, "openai": OpenAI, "agent": Agent}[name]()
