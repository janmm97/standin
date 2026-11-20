"""Thin wrapper around the One CLI (https://withone.ai): `one --agent actions execute ...`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class OneError(RuntimeError):
    pass


def _one() -> list[str]:
    exe = shutil.which("one")
    if not exe:
        raise OneError("One CLI not found: install it (npm i -g @withone/cli), "
                       "then `one init` and `one add higgsfield-ai`")
    if not exe.lower().endswith((".cmd", ".bat")):
        return [exe]
    # npm installs `one` as a .cmd shim on Windows. cmd.exe re-parses its command line, and the JSON body's
    # own quotes leave prompt text unquoted, so & | > % in a prompt would run commands or expand variables.
    # Run the CLI's node script directly so cmd.exe never sees the arguments.
    d = Path(exe).parent
    js = d / "node_modules" / "@withone" / "cli" / "bin" / "cli.js"
    node = str(d / "node.exe") if (d / "node.exe").is_file() else shutil.which("node")
    if not (js.is_file() and node):
        raise OneError(f"refusing to run One through the {exe} shim (unsafe for prompt text); "
                       f"expected {js} and node on PATH")
    return [node, str(js)]


def execute(platform: str, action_id: str, key: str, data: dict | None = None,
            path_vars: dict | None = None, run=subprocess.run) -> dict:
    cmd = [*_one(), "--agent", "actions", "execute", platform, action_id, key]
    if path_vars:
        cmd += ["--path-vars", json.dumps(path_vars)]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    cmd.append("--confirm-write")
    p = run(cmd, capture_output=True, text=True, timeout=300)
    try:
        out = json.loads(p.stdout or "{}")
    except json.JSONDecodeError as e:
        raise OneError(f"One returned non-JSON (exit {p.returncode}): {(p.stdout + p.stderr)[-500:]}") from e
    if p.returncode != 0 or (isinstance(out, dict) and out.get("error")):
        err = out.get("error") if isinstance(out, dict) else out
        raise OneError(f"One {action_id} failed: {str(err)[:500]}")
    return out.get("response", out) if isinstance(out, dict) else out


def _keys(obj, platform: str):
    if isinstance(obj, str) and obj.startswith(f"live::{platform}::"):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _keys(v, platform)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v, platform)


def connection_key(platform: str, env: str, run=subprocess.run) -> str:
    """The connection key from `env`, else the first matching one in `one --agent list`."""
    if k := os.environ.get(env):
        return k
    p = run([*_one(), "--agent", "list"], capture_output=True, text=True, timeout=60)
    try:
        k = next(_keys(json.loads(p.stdout or "{}"), platform), None)
    except json.JSONDecodeError:
        k = None
    if not k:
        raise OneError(f"No {platform} connection in One: run `one add {platform}` or set {env}")
    return k
