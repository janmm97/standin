import os

import pytest

from standin import blender_run
from standin.plan import template_plan


class P:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_find_exe_prefers_env(monkeypatch):
    monkeypatch.setenv("STANDIN_BLENDER", "/opt/blender")
    assert blender_run.find_blender() == "/opt/blender"


def test_blender_cmd(tmp_path):
    cmd = blender_run.blender_cmd("blender", tmp_path / "plan.json", tmp_path, "keys", 10)
    assert cmd[:4] == ["blender", "-b", "--factory-startup", "-P"]
    assert cmd[4].endswith("scene.py")
    assert cmd[-4:] == [str(tmp_path / "plan.json"), str(tmp_path), "keys", "10"]


def test_render_writes_plan_and_checks_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("STANDIN_BLENDER", "blender")
    with pytest.raises(RuntimeError, match="keys render failed"):
        blender_run.render(template_plan("x"), tmp_path, "keys", run=lambda *a, **k: P(0, "no marker"))
    assert (tmp_path / "plan.json").exists()


def test_render_missing_blender(monkeypatch, tmp_path):
    monkeypatch.delenv("STANDIN_BLENDER", raising=False)
    monkeypatch.setattr(blender_run, "find_blender", lambda: None)
    with pytest.raises(RuntimeError, match="Blender not found"):
        blender_run.render(template_plan("x"), tmp_path, "keys")


@pytest.mark.skipif(not blender_run.find_blender() or not os.path.exists(blender_run.find_blender() or ""),
                    reason="Blender not installed")
def test_real_keyframes(tmp_path):
    plan = template_plan("smoke test")
    plan["beats"] = plan["beats"][:1]
    keys = blender_run.render(plan, tmp_path, "keys", scale=10)
    assert [k.name for k in keys] == ["k_00.png", "k_01.png"]
    assert all(k.stat().st_size > 0 for k in keys)


@pytest.mark.skipif(not blender_run.find_blender() or not os.path.exists(blender_run.find_blender() or ""),
                    reason="Blender not installed")
def test_beat_end_keyframe_keeps_the_end_pose(monkeypatch):
    """The image pinned at a beat boundary must show that beat's last pose, not the next beat's reset."""
    import subprocess
    from pathlib import Path

    monkeypatch.setenv("STANDIN_SCENE", str(blender_run.SCENE))
    probe = Path(__file__).with_name("blender_probe.py")
    p = subprocess.run([blender_run.find_blender(), "-b", "--factory-startup", "-P", str(probe)],
                       capture_output=True, text=True, timeout=120)
    rows = {int(r[1]): (float(r[2]), float(r[3])) for r in
            (ln.split() for ln in p.stdout.splitlines() if ln.startswith("PROBE "))}
    assert rows[97] == (-1.5, -3.2)  # end of the "point" beat: arm raised, dolly finished
    assert rows[193] == (0.0, -4.6)
