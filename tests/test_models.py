import json

import pytest

from standin import models
from standin.models import Model, parse_ls, parse_params, pick_chat, pick_voice

LS = json.dumps([
    {"type": "llm", "modelKey": "qwen/qwen3.5-4b", "paramsString": "4B", "sizeBytes": 3_383_261_439},
    {"type": "llm", "modelKey": "big/llama-70b", "paramsString": "70B", "sizeBytes": 40_000_000_000},
    {"type": "llm", "modelKey": "tiny/gemma-270m", "sizeBytes": 200_000_000},
    {"type": "llm", "modelKey": "isaiahbjork/orpheus-3b-0.1-ft", "paramsString": "3B",
     "sizeBytes": 2_000_000_000},
    {"type": "embedding", "modelKey": "text-embedding-nomic-embed-text-v1.5", "sizeBytes": 84_106_624},
])


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv("STANDIN_CHAT_MODEL", raising=False)
    monkeypatch.delenv("STANDIN_VOICE_MODEL", raising=False)


@pytest.mark.parametrize("text,want", [
    ("4B", 4.0), ("8x7B", 56.0), ("270M", 0.27), ("qwen3.5-4b", 4.0), ("gemma-270m", 0.27), ("nomic", 0.0),
])
def test_parse_params(text, want):
    assert parse_params(text) == pytest.approx(want)


def test_parse_ls_reads_name_when_params_missing():
    ms = {m.key: m for m in parse_ls(LS)}
    assert ms["tiny/gemma-270m"].params_b == pytest.approx(0.27)
    assert ms["qwen/qwen3.5-4b"].type == "llm"


def test_pick_chat_takes_largest_that_fits_and_skips_voice_and_embeddings():
    ms = parse_ls(LS)
    m, why = pick_chat(ms, fits=lambda key: key != "big/llama-70b")
    assert m.key == "qwen/qwen3.5-4b"
    assert "1 bigger" in why


def test_pick_chat_largest_when_everything_fits():
    m, _ = pick_chat(parse_ls(LS), fits=lambda key: True)
    assert m.key == "big/llama-70b"


def test_pick_chat_falls_back_to_smallest_when_nothing_fits():
    m, why = pick_chat(parse_ls(LS), fits=lambda key: False)
    assert m.key == "tiny/gemma-270m" and "smallest" in why


def test_pick_chat_none_installed():
    m, why = pick_chat([Model("e", "embedding", 0, 1)], fits=lambda key: True)
    assert m is None and "no LM Studio chat model" in why


def test_env_override(monkeypatch):
    monkeypatch.setenv("STANDIN_CHAT_MODEL", "my/model-8b")
    m, why = pick_chat([], fits=lambda key: True)
    assert m.key == "my/model-8b" and "STANDIN_CHAT_MODEL" in why


def test_pick_voice():
    assert pick_voice(parse_ls(LS)).key.startswith("isaiahbjork/orpheus")
    assert pick_voice([]) is None


def test_ensure_loaded_starts_server_then_loads(monkeypatch):
    monkeypatch.setattr(models.shutil, "which", lambda name: "lms")
    calls = []

    class P:
        returncode = 0

    def run(cmd, **k):
        calls.append(cmd[1:])
        return P()

    assert models.ensure_loaded("qwen/qwen3.5-4b", run=run)
    assert calls == [["server", "start"], ["load", "qwen/qwen3.5-4b", "-y"]]


def test_fits_reads_estimate(monkeypatch):
    monkeypatch.setattr(models.shutil, "which", lambda name: "lms")

    class P:
        def __init__(self, out):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    ok = "Estimate: This model may be loaded based on your resource guardrails settings."
    bad = "Estimate: This model may not be loaded based on your resource guardrails settings."
    assert models.fits("a", run=lambda *a, **k: P(ok))
    assert not models.fits("a", run=lambda *a, **k: P(bad))
