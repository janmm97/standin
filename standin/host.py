"""Give local keyframes a public URL so Higgsfield can read them, then remove them.

The One CLI sends JSON bodies only, so uploads go through a command you configure:
  STANDIN_UPLOAD_CMD  e.g. wrangler r2 object put my-bucket/{key} --file {path} --remote
  STANDIN_DELETE_CMD  e.g. wrangler r2 object delete my-bucket/{key} --remote
  STANDIN_PUBLIC_BASE e.g. https://pub-xxxx.r2.dev
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path


def split(template: str, nt: bool) -> list[str]:
    """shlex.split; on Windows (non-POSIX mode, so backslashes survive) it keeps the quotes, so drop them."""
    parts = shlex.split(template, posix=not nt)
    if nt:
        parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]
    return parts


class Host:
    def __init__(self, run=subprocess.run, env=os.environ):
        self.up, self.rm = env.get("STANDIN_UPLOAD_CMD"), env.get("STANDIN_DELETE_CMD")
        self.base = (env.get("STANDIN_PUBLIC_BASE") or "").rstrip("/")
        if not self.up or not self.base:
            raise RuntimeError("Set STANDIN_UPLOAD_CMD and STANDIN_PUBLIC_BASE (see .env.example)")
        self.run, self.prefix, self.keys = run, f"standin/{uuid.uuid4().hex[:12]}", []

    def _cmd(self, template: str, **kw) -> list[str]:
        # Split first, then fill in, so paths with spaces stay one argument.
        parts = []
        for t in split(template, nt=os.name == "nt"):
            for name, value in kw.items():  # not str.format: other braces (JSON, ${VAR}) stay as typed
                t = t.replace("{" + name + "}", value)
            parts.append(t)
        if parts and (exe := shutil.which(parts[0])):
            parts[0] = exe  # Windows needs the full path for .cmd shims like wrangler
        return parts

    def upload(self, path: Path) -> str:
        key = f"{self.prefix}/{path.name}"
        p = self.run(self._cmd(self.up, path=str(path), key=key), capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"upload failed for {path.name}: {(p.stdout + p.stderr)[-400:]}")
        self.keys.append(key)
        return f"{self.base}/{key}"

    def cleanup(self) -> list[str]:
        """Delete everything this run uploaded; returns keys that could not be deleted."""
        left = []
        for key in self.keys:
            if not self.rm:
                left.append(key)
                continue
            p = self.run(self._cmd(self.rm, key=key), capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                left.append(key)
        self.keys = []
        return left
