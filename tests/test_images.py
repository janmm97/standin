import base64
import json
from pathlib import Path

import pytest

from standin import cli, images, one


class P:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def no_codex(monkeypatch):
    def gone():
        raise one.OneError("codex not found")

    monkeypatch.setattr(images, "codex_cmd", gone)


def test_auto_prefers_a_signed_in_codex(monkeypatch):
    monkeypatch.setattr(images, "codex_cmd", lambda: ["codex"])
    assert images.resolve("auto", env={"OPENAI_API_KEY": "k"}, run=lambda c, **k: P(0)) == "codex"
    # signed out: fall through to the API keys, then Higgsfield
    assert images.resolve("auto", env={"OPENAI_API_KEY": "k"}, run=lambda c, **k: P(1)) == "openai"


def test_auto_order_without_codex(monkeypatch):
    no_codex(monkeypatch)
    assert images.resolve(None, env={"GOOGLE_API_KEY": "g", "OPENAI_API_KEY": "o"}) == "gemini"
    assert images.resolve(None, env={"OPENAI_API_KEY": "o"}) == "openai"
    assert images.resolve(None, env={}) == "higgsfield"
    assert images.resolve(None, env={"STANDIN_IMAGES": "agent"}) == "agent"
    with pytest.raises(ValueError, match="unknown image provider"):
        images.resolve("dalle", env={})


def test_codex_runs_read_only_and_copies_the_session_image(monkeypatch, tmp_path):
    monkeypatch.setattr(images, "codex_cmd", lambda: ["node", "codex.js"])
    sid = "01a1fbf5-3db0-7e50-971d-52e01336a282"
    seen = {}

    def run(cmd, **k):
        seen.update(cmd=cmd, input=k["input"])
        out = tmp_path / "home" / "generated_images" / sid
        out.mkdir(parents=True)
        (out / "exec-1.png").write_bytes(b"PNG")
        return P(0, f"session id: {sid}\n", "")

    c = images.Codex(env={"CODEX_HOME": str(tmp_path / "home")}, run=run)
    pose, actor = tmp_path / "k & 1.png", tmp_path / "c_0.png"
    got = c.image('a "cafe" & 100%', [pose, actor], "9:16", tmp_path / "shots" / "s_00.png")
    assert got.read_bytes() == b"PNG"
    assert seen["cmd"][:6] == ["node", "codex.js", "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    assert seen["cmd"][6:] == ["-i", str(pose), "-i", str(actor), "-"]  # prompt goes in on stdin
    assert 'a "cafe" & 100%' in seen["input"] and "portrait 9:16" in seen["input"]


def test_codex_without_an_image_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(images, "codex_cmd", lambda: ["codex"])
    c = images.Codex(env={"CODEX_HOME": str(tmp_path)}, run=lambda c, **k: P(1, "", "usage limit"))
    with pytest.raises(RuntimeError, match="usage limit"):
        c.image("x", [], "9:16", tmp_path / "o.png")


def test_gemini_body_and_reply(tmp_path):
    ref = tmp_path / "k.png"
    ref.write_bytes(b"POSE")
    seen = {}

    def post(url, data, headers):
        seen.update(url=url, body=json.loads(data), headers=headers)
        img = {"inlineData": {"data": base64.b64encode(b"IMG").decode()}}
        return {"candidates": [{"content": {"parts": [{"text": "ok"}, img]}}]}

    g = images.Gemini(env={"GEMINI_API_KEY": "g"}, post=post)
    assert g.image("shot", [ref], "16:9", tmp_path / "o.png").read_bytes() == b"IMG"
    assert seen["url"].endswith("/gemini-2.5-flash-image:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "g"
    parts = seen["body"]["contents"][0]["parts"]
    assert base64.b64decode(parts[0]["inline_data"]["data"]) == b"POSE" and parts[1] == {"text": "shot"}
    assert seen["body"]["generationConfig"]["imageConfig"] == {"aspectRatio": "16:9"}


def test_openai_edits_with_refs_and_generates_without(tmp_path):
    ref = tmp_path / "k.png"
    ref.write_bytes(b"POSE")
    calls = []
    ok = {"data": [{"b64_json": base64.b64encode(b"IMG").decode()}]}
    o = images.OpenAI(env={"OPENAI_API_KEY": "o"}, post=lambda u, d, h: calls.append((u, d, h)) or ok)
    o.image("shot", [ref], "9:16", tmp_path / "a.png")
    o.image("cast", [], "9:16", tmp_path / "b.png")
    (u1, d1, h1), (u2, d2, _) = calls
    assert u1.endswith("/images/edits") and b'name="image[]"; filename="k.png"' in d1 and b"POSE" in d1
    assert b"1024x1536" in d1 and h1["Content-Type"].startswith("multipart/form-data; boundary=")
    assert u2.endswith("/images/generations") and json.loads(d2)["prompt"] == "cast"
    assert (tmp_path / "a.png").read_bytes() == b"IMG"


def test_higgsfield_provider_uploads_each_reference_once(tmp_path):
    runs, ups = [], []

    class C:
        def run(self, model, body, dest):
            runs.append((model, body))
            return dest

    class H:
        def upload(self, p):
            ups.append(p)
            return f"https://h/{Path(p).name}"

    h = images.make("higgsfield", C(), H())
    actor = Path("c_0.png")
    h.image("cast", [], "9:16", Path("c.png"))
    h.image("k1", [Path("k_00.png"), actor], "9:16", Path("s0.png"))
    h.image("k2", [Path("k_01.png"), actor], "9:16", Path("s1.png"))
    assert [m for m, _ in runs] == ["soul", "nano_banana", "nano_banana"]
    assert ups.count(actor) == 1
    assert [i["image_url"] for i in runs[2][1]["input_images"]] == ["https://h/k_01.png", "https://h/c_0.png"]


def test_make_with_agent_writes_requests_and_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.blender_run, "render",
                        lambda plan, d, mode: [d / "keys" / f"k_{i:02}.png" for i in range(6)])

    class Boom:
        def run(self, *a):
            raise AssertionError("no Higgsfield call expected")

        def upload(self, p):
            raise AssertionError("no upload expected")

        def cleanup(self):
            return []

    monkeypatch.setattr(cli.higgsfield, "Client", Boom)
    monkeypatch.setattr(cli, "Host", Boom)
    assert cli.main(["make", "x", "--template", "--yes", "--images", "agent", "--out", str(tmp_path)]) == 0
    req = json.loads((tmp_path / "x" / "image_requests.json").read_text(encoding="utf-8"))
    assert len(req) == 7 and req[0]["references"] == [] and req[0]["output"].endswith("c_0.png")
    assert req[1]["references"][1] == req[0]["output"]  # each keyframe uses the cast still made first
    assert "mannequin 1 becomes the person in reference image 2" in req[1]["prompt"]


@pytest.mark.parametrize("cls", [images.Gemini, images.OpenAI])
def test_api_providers_fail_early_without_a_key(cls):
    with pytest.raises(RuntimeError, match="_API_KEY"):
        cls(env={})


def test_post_reports_the_api_error_body(monkeypatch):
    import io
    import urllib.error

    def boom(req, timeout):
        body = io.BytesIO(b'{"error":"bad size"}')
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, body)

    monkeypatch.setattr(images.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match=r"HTTP 400.*bad size"):
        images._post("https://example.test/x", b"{}", {})
