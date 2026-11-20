import pytest

from standin import cli
from standin.plan import normalize


def test_make_reuses_finished_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.blender_run, "render", lambda plan, d, mode: [d / "k.png"] * 4)
    done = tmp_path / "x" / "segments" / "seg_00.mp4"
    done.parent.mkdir(parents=True)
    done.write_bytes(b"paid earlier")
    runs = []
    client = type("C", (), {"run": lambda s, m, b, dest: runs.append((m, dest.name)) or dest})
    host = type("H", (), {"upload": lambda s, p: f"https://h/{p.name}", "cleanup": lambda s: []})
    monkeypatch.setattr(cli.higgsfield, "Client", client)
    monkeypatch.setattr(cli, "Host", host)
    monkeypatch.setattr(cli.edit, "concat", lambda segs, out: out)
    monkeypatch.setattr(cli.edit, "finish", lambda v, out, wav, srt: out)
    assert cli.main(["make", "x", "--template", "--yes", "--no-vo", "--out", str(tmp_path)]) == 0
    assert ("veo_fast", "seg_00.mp4") not in runs and ("veo_fast", "seg_01.mp4") in runs


def test_batch_rows_get_their_own_folder(tmp_path, monkeypatch):
    f = tmp_path / "b.csv"
    f.write_text("brief\nsame\nsame\n", encoding="utf-8")
    outs = []
    monkeypatch.setattr(cli, "preview", lambda a: outs.append(a.out))
    assert cli.main(["batch", str(f), "--template", "--out", str(tmp_path)]) == 0
    assert len(set(outs)) == 2


def test_normalize_survives_wrong_types():
    plan = normalize({"cast": {"name": "x"}, "beats": [{"action": "wave"}], "title": 5})
    assert plan["cast"][0]["name"] == "Host" and plan["beats"][0]["action"] == "wave"
    with pytest.raises(ValueError):
        normalize({"beats": "walk in"})
