import json
from pathlib import Path

import pytest

from standin import cli


def test_slug():
    assert cli.slug("Cozy Oat-Milk Launch!") == "cozy-oat-milk-launch"
    assert cli.slug("!!!") == "clip"


def test_plan_template_writes_plan(tmp_path, capsys):
    assert cli.main(["plan", "oat milk launch", "--template", "--out", str(tmp_path)]) == 0
    plan = json.loads((tmp_path / "oat-milk-launch" / "plan.json").read_text(encoding="utf-8"))
    assert len(plan["beats"]) == 3 and "plan: template" in capsys.readouterr().out


def test_plan_needs_brief():
    with pytest.raises(SystemExit):
        cli.main(["plan"])


def test_make_without_yes_spends_nothing(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("no paid or render call expected")

    monkeypatch.setattr(cli.higgsfield, "Client", boom)
    monkeypatch.setattr(cli.blender_run, "render", boom)
    assert cli.main(["make", "x", "--template", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "'total': 1.58" in out and "no paid calls made" in out


def test_make_with_yes_runs_pipeline_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.blender_run, "render",
                        lambda plan, d, mode: [d / "keys" / f"k_{i:02}.png" for i in range(4)])
    runs = []

    class FakeClient:
        def run(self, model, body, dest):
            runs.append((model, body))
            return dest

    class FakeHost:
        cleaned = False

        def upload(self, path):
            return f"https://h/{Path(path).name}"

        def cleanup(self):
            FakeHost.cleaned = True
            return []

    monkeypatch.setattr(cli.higgsfield, "Client", FakeClient)
    monkeypatch.setattr(cli, "Host", FakeHost)
    monkeypatch.setattr(cli.edit, "concat", lambda segs, out: out)
    monkeypatch.setattr(cli.edit, "finish", lambda v, out, wav, srt: out)
    assert cli.main(["make", "x", "--template", "--yes", "--no-vo", "--out", str(tmp_path)]) == 0
    assert [m for m, _ in runs] == ["soul"] + ["nano_banana"] * 4 + ["veo_fast"] * 3
    first_veo = runs[5][1]
    assert (first_veo["first_frame_url"], first_veo["last_frame_url"]) == ("https://h/s_00.png", "https://h/s_01.png")
    assert FakeHost.cleaned and (tmp_path / "x" / "captions.srt").exists()


def test_make_cleans_up_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.blender_run, "render", lambda plan, d, mode: [d / "k.png"] * 4)

    class FailClient:
        def run(self, *a):
            raise cli.one.OneError("nsfw")

    cleaned = []
    host = type("H", (), {"upload": lambda s, p: "https://h/x", "cleanup": lambda s: cleaned.append(1) or []})
    monkeypatch.setattr(cli.higgsfield, "Client", FailClient)
    monkeypatch.setattr(cli, "Host", host)
    assert cli.main(["make", "x", "--template", "--yes", "--out", str(tmp_path)]) == 1
    assert cleaned == [1]


def test_batch_runs_each_row_and_counts_failures(tmp_path, monkeypatch, capsys):
    f = tmp_path / "briefs.csv"
    f.write_text("brief,aspect\nfirst clip,16:9\n,\nsecond clip,\n", encoding="utf-8")
    seen = []

    def fake_preview(a):
        seen.append((a.brief, a.aspect))
        if a.brief == "second clip":
            raise RuntimeError("blender missing")

    monkeypatch.setattr(cli, "preview", fake_preview)
    assert cli.main(["batch", str(f), "--template"]) == 1
    assert seen == [("first clip", "16:9"), ("second clip", None)]  # None: get_plan applies 9:16
    assert "1 ok, 1 failed" in capsys.readouterr().out


def test_saved_plan_keeps_its_aspect_unless_overridden(tmp_path):
    f = tmp_path / "plan.json"
    plan = {"aspect": "16:9", "beats": [{"action": "wave", "duration": 4}]}
    f.write_text(json.dumps(plan), encoding="utf-8")
    base = ["plan", "--plan", str(f), "--out", str(tmp_path)]
    assert cli.get_plan(cli.parser().parse_args(base))["aspect"] == "16:9"
    assert cli.get_plan(cli.parser().parse_args([*base, "--aspect", "9:16"]))["aspect"] == "9:16"


def test_plan_file_that_is_not_an_object_is_an_error(tmp_path, capsys):
    f = tmp_path / "plan.json"
    f.write_text("[1, 2]", encoding="utf-8")
    assert cli.main(["plan", "--plan", str(f), "--out", str(tmp_path)]) == 1
    assert "not a plan" in capsys.readouterr().out


def test_make_refuses_to_spend_when_keyframe_count_is_wrong(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.blender_run, "render", lambda plan, d, mode: [d / "k.png"])
    ran = []

    class FakeClient:
        def run(self, *a):
            ran.append(a)

    monkeypatch.setattr(cli.higgsfield, "Client", FakeClient)
    monkeypatch.setattr(cli, "Host", lambda: object())
    assert cli.main(["make", "x", "--template", "--yes", "--out", str(tmp_path)]) == 1
    assert not ran and "expected 4" in capsys.readouterr().out


def test_timeouts_are_reported_not_a_traceback(monkeypatch, capsys):
    import subprocess

    def slow(a):
        raise subprocess.TimeoutExpired("blender", 1)

    monkeypatch.setattr(cli, "preview", slow)
    assert cli.main(["preview", "x", "--template"]) == 1
    assert "error:" in capsys.readouterr().out
