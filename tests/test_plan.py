import json

import pytest

from standin.plan import keyframe_frames, make_plan, normalize, template_plan, total_seconds


def test_normalize_clamps_bad_values():
    p = normalize({
        "cast": [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        "beats": [{"action": "Backflip", "camera": "drone", "duration": 5, "vo": "  hi \n there "},
                  {"action": "WAVE", "camera": "orbit", "duration": "9"}, "junk"],
        "voice": "nobody",
    }, aspect="4:3")
    assert len(p["cast"]) == 3
    b0, b1 = p["beats"]
    assert (b0["action"], b0["camera"], b0["duration"], b0["vo"]) == ("idle", "static", 4, "hi there")
    assert (b1["action"], b1["camera"], b1["duration"]) == ("wave", "orbit", 8)
    assert p["aspect"] == "9:16" and p["voice"] == "tara"


def test_normalize_needs_beats():
    with pytest.raises(ValueError):
        normalize({"beats": []})


def test_normalize_default_cast():
    assert normalize({"beats": [{}]})["cast"][0]["name"] == "Host"


def test_template_plan_is_valid():
    p = template_plan("New  running shoe", "16:9")
    assert p["aspect"] == "16:9" and len(p["beats"]) == 3
    assert "New running shoe" in p["beats"][1]["scene"]
    assert [b["shot"] for b in p["beats"]] == ["wide", "detail", "close"]
    assert p["location"] and p["look"]


def test_keyframes_and_length():
    p = template_plan("x")
    assert total_seconds(p) == 14
    assert keyframe_frames(p) == [1, 97, 98, 241, 242, 337]  # a cut between beats: 2 per beat


def test_make_plan_uses_model():
    raw = {"title": "T", "cast": [{"name": "Mia", "look": "runner"}],
           "beats": [{"action": "wave", "camera": "dolly", "duration": 6, "scene": "park", "vo": "Hello"}]}
    seen = {}

    def post(url, body):
        seen.update(url=url, body=body)
        return {"choices": [{"message": {"content": "<think>ok</think>" + json.dumps(raw)}}]}

    p, src = make_plan("shoes", "qwen/qwen3.5-4b", post=post)
    assert src == "LM Studio (qwen/qwen3.5-4b)"
    assert p["beats"][0]["action"] == "wave"
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["body"]["response_format"]["type"] == "json_schema"


def test_make_plan_falls_back_on_error():
    def post(url, body):
        raise OSError("connection refused")

    p, src = make_plan("shoes", "m", post=post)
    assert src.startswith("template (LM Studio failed: OSError")
    assert len(p["beats"]) == 3


def test_make_plan_without_model():
    _, src = make_plan("shoes", None)
    assert src == "template (no chat model)"
