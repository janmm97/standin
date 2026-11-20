import json
from pathlib import Path

import pytest

from standin import higgsfield, one
from standin.host import Host
from standin.plan import template_plan


class P:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_estimate_draft_and_final():
    plan = template_plan("x")  # 1 cast, 3 beats, 14 s
    assert higgsfield.estimate(plan, draft=True) == {
        "soul": 0.02, "nano_banana": 0.16, "veo": 1.4, "total": 1.58}
    assert higgsfield.estimate(plan, draft=False)["veo"] == 5.6


def test_bodies():
    b = higgsfield.insert_body("https://h/k0.png", ["https://h/a.png", "https://h/b.png"], "cafe", "9:16")
    assert [i["image_url"] for i in b["input_images"]] == ["https://h/k0.png", "https://h/a.png", "https://h/b.png"]
    assert "reference image 3" in b["prompt"] and b["aspect_ratio"] == "9:16"
    v = higgsfield.veo_body("https://a", "https://b", "walks", 6, "9:16")
    assert (v["first_frame_url"], v["last_frame_url"], v["duration"], v["generate_audio"]) == (
        "https://a", "https://b", 6, False)


def test_urls_finds_media_and_skips_status():
    r = {"status": "completed", "status_url": "https://x/s.png",
         "images": [{"url": "https://cdn/a.png?sig=1"}], "video": {"url": "https://cdn/v.mp4"},
         "note": "https://example.com/page"}
    assert higgsfield.urls(r) == ["https://cdn/a.png?sig=1", "https://cdn/v.mp4"]


def fake_execute(statuses):
    calls = []

    def ex(platform, action, key, data=None, path_vars=None):
        calls.append((action, data, path_vars))
        if action == higgsfield.ACTIONS["status"]:
            return statuses.pop(0)
        return {"status": "queued", "request_id": "req_1"}

    return ex, calls


def test_client_run_polls_then_downloads(tmp_path):
    ex, calls = fake_execute([{"status": "queued"}, {"status": "in_progress"},
                              {"status": "completed", "images": [{"url": "https://cdn/o.png"}]}])
    c = higgsfield.Client("live::higgsfield-ai::default::x", execute=ex, sleep=lambda s: None)
    got = {}
    out = c.run("soul", {"prompt": "p"}, tmp_path / "cast" / "a.png", fetch=lambda u, d: got.update(u=u, d=d))
    assert got == {"u": "https://cdn/o.png", "d": out}
    assert calls[1][2] == {"requestId": "req_1"} and len(calls) == 4


@pytest.mark.parametrize("bad", ["failed", "nsfw", "canceled"])
def test_client_raises_on_bad_status(bad):
    ex, _ = fake_execute([{"status": bad}])
    c = higgsfield.Client("k", execute=ex, sleep=lambda s: None)
    with pytest.raises(one.OneError, match=bad):
        c.wait("req_1")


def test_client_times_out():
    ex, _ = fake_execute([{"status": "queued"}] * 5)
    c = higgsfield.Client("k", execute=ex, sleep=lambda s: None, poll_s=5, timeout_s=10)
    with pytest.raises(one.OneError, match="still queued"):
        c.wait("req_1")


def test_one_execute_builds_command(monkeypatch):
    monkeypatch.setattr(one.shutil, "which", lambda n: "one")
    seen = {}

    def run(cmd, **k):
        seen["cmd"] = cmd
        return P(0, json.dumps({"response": {"request_id": "r"}}))

    got = one.execute("higgsfield-ai", "A", "K", {"a": 1}, {"requestId": "r"}, run=run)
    assert got == {"request_id": "r"}
    assert seen["cmd"][:7] == ["one", "--agent", "actions", "execute", "higgsfield-ai", "A", "K"]
    assert "--path-vars" in seen["cmd"] and seen["cmd"][-1] == "--confirm-write"


def test_one_execute_raises_on_error(monkeypatch):
    monkeypatch.setattr(one.shutil, "which", lambda n: "one")
    with pytest.raises(one.OneError, match="boom"):
        one.execute("p", "A", "K", {}, run=lambda c, **k: P(0, json.dumps({"error": "boom"})))


def test_connection_key_from_list(monkeypatch):
    monkeypatch.delenv("STANDIN_HIGGSFIELD_KEY", raising=False)
    monkeypatch.setattr(one.shutil, "which", lambda n: "one")
    listing = {"connections": [{"platform": "github", "key": "live::github::default::g"},
                               {"platform": "higgsfield-ai", "key": "live::higgsfield-ai::default::h"}]}
    run = lambda c, **k: P(0, json.dumps(listing))  # noqa: E731
    got = one.connection_key("higgsfield-ai", "STANDIN_HIGGSFIELD_KEY", run=run)
    assert got == "live::higgsfield-ai::default::h"
    with pytest.raises(one.OneError, match="one add slack"):
        one.connection_key("slack", "X", run=run)


def test_host_upload_and_cleanup(tmp_path):
    env = {"STANDIN_UPLOAD_CMD": "up {path} b/{key}", "STANDIN_DELETE_CMD": "rm b/{key}",
           "STANDIN_PUBLIC_BASE": "https://pub.example/"}
    cmds = []
    h = Host(run=lambda c, **k: cmds.append(c) or P(), env=env)
    f = tmp_path / "my keys" / "k_00.png"
    url = h.upload(f)
    assert url.startswith("https://pub.example/standin/") and url.endswith("/k_00.png")
    assert cmds[0][1] == str(f)  # a path with a space stays one argument
    key = url.removeprefix("https://pub.example/")
    assert h.cleanup() == [] and cmds[1][-1] == f"b/{key}" and h.keys == []


def test_host_needs_config():
    with pytest.raises(RuntimeError, match="STANDIN_UPLOAD_CMD"):
        Host(env={})


def test_host_reports_undeleted_without_delete_cmd():
    h = Host(run=lambda c, **k: P(), env={"STANDIN_UPLOAD_CMD": "up {path}", "STANDIN_PUBLIC_BASE": "https://p"})
    h.upload(Path("a.png"))
    assert len(h.cleanup()) == 1


def test_fetch_refuses_non_https(tmp_path):
    with pytest.raises(higgsfield.one.OneError):
        higgsfield._fetch("file:///etc/passwd", tmp_path / "x")


def test_one_execute_bypasses_a_cmd_shim(monkeypatch, tmp_path):
    """cmd.exe re-parses a .cmd shim's args, so & | % in a prompt could run commands: call node directly."""
    js = tmp_path / "node_modules" / "@withone" / "cli" / "bin" / "cli.js"
    js.parent.mkdir(parents=True)
    js.write_text("")
    (tmp_path / "node.exe").write_text("")
    monkeypatch.setattr(one.shutil, "which", lambda n: str(tmp_path / "one.CMD"))
    seen = {}

    def run(cmd, **k):
        seen["cmd"] = cmd
        return P(0, "{}")

    body = {"prompt": 'say "hi" & del * | %PATH%', "n": 2}
    one.execute("p", "A", "K", body, run=run)
    assert seen["cmd"][:2] == [str(tmp_path / "node.exe"), str(js)]
    assert json.loads(seen["cmd"][seen["cmd"].index("-d") + 1]) == body  # text arrives unchanged
    js.unlink()  # unknown shim layout: refuse rather than go through cmd.exe
    with pytest.raises(one.OneError):
        one.execute("p", "A", "K", body, run=run)


def test_run_ignores_input_urls_echoed_in_the_result(tmp_path):
    ex, _ = fake_execute([{"status": "completed", "input": {"first_frame_url": "https://h/s_00.png"},
                           "video": {"url": "https://cdn/out.mp4"}}])
    c = higgsfield.Client("k", execute=ex, sleep=lambda s: None)
    got = {}
    c.run("veo", {"first_frame_url": "https://h/s_00.png"}, tmp_path / "a.mp4",
          fetch=lambda u, d: got.update(u=u))
    assert got["u"] == "https://cdn/out.mp4"


def test_wait_survives_a_flaky_poll_but_not_a_dead_one():
    calls = []

    def ex(platform, action, key, data=None, path_vars=None):
        calls.append(1)
        if len(calls) in (1, 2):
            raise one.OneError("503")
        return {"status": "completed", "url": "https://cdn/o.png"}

    c = higgsfield.Client("k", execute=ex, sleep=lambda s: None)
    assert c.wait("r") == ["https://cdn/o.png"]

    def dead(*a, **k):
        raise one.OneError("401")

    with pytest.raises(one.OneError, match="401"):
        higgsfield.Client("k", execute=dead, sleep=lambda s: None).wait("r")


def test_redirect_to_http_is_refused():
    h = higgsfield._HttpsOnly()
    req = higgsfield.urllib.request.Request("https://cdn/o.png")
    with pytest.raises(higgsfield.urllib.error.URLError, match="non-https"):
        h.redirect_request(req, None, 302, "Found", {}, "http://evil/o.png")


def test_host_split_drops_windows_quotes_and_keeps_other_braces():
    from standin import host as hostmod

    assert hostmod.split('up --file "{path}" -x \'a b\'', nt=True) == ["up", "--file", "{path}", "-x", "a b"]
    assert hostmod.split('up --file "{path}"', nt=False) == ["up", "--file", "{path}"]
    env = {"STANDIN_UPLOAD_CMD": 'up {path} \'{"k":"{key}"}\'', "STANDIN_PUBLIC_BASE": "https://p"}
    h = Host(run=lambda c, **k: P(), env=env)
    assert h._cmd(h.up, path="/a b/x.png", key="K")[1:] == ["/a b/x.png", '{"k":"K"}']
