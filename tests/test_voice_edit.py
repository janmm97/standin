import subprocess
import wave

import pytest

from standin import edit, voice
from standin.blender_run import find_ffmpeg
from standin.plan import template_plan


def tok(ids):
    """Encode SNAC ids the way Orpheus prints them."""
    return "".join(f"<custom_token_{i + 10 + (k % 7) * 4096}>" for k, i in enumerate(ids))


def test_parse_tokens_skips_markers_and_partial_frames():
    ids = list(range(1, 15)) + [99, 100]  # two full frames + 2 stray tokens
    assert voice.parse_tokens("<custom_token_4>" + tok(ids)) == list(range(1, 15))


def test_to_layers_order():
    l0, l1, l2 = voice.to_layers([0, 1, 2, 3, 4, 5, 6])
    assert (l0, l1, l2) == ([0], [1, 4], [2, 3, 5, 6])


def test_speak_and_voice_over(tmp_path):
    seen = []

    def post(url, body):
        seen.append((url, body))
        return {"choices": [{"text": tok(list(range(7)) * 2)}]}

    pcm_per_line = b"\x01\x00" * voice.RATE  # 1 s of audio
    plan = template_plan("oat milk")
    wav, spoken = voice.voice_over(plan, "orpheus", tmp_path / "vo.wav", post=post,
                                   decoder=lambda layers: pcm_per_line)
    assert seen[0][0].endswith("/completions") and seen[0][1]["prompt"].startswith("<|audio|>tara: ")
    assert spoken == [1.0, 1.0, 1.0]
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 14 * 24000


def test_speak_without_audio_tokens():
    with pytest.raises(RuntimeError, match="no audio tokens"):
        voice.speak("hi", "tara", "qwen", post=lambda u, b: {"choices": [{"text": "hello"}]})


def test_fit_pads_and_cuts():
    assert len(voice.fit(b"\x01\x00" * 10, 1)) == 48000
    assert len(voice.fit(b"\x01\x00" * 30000, 1)) == 48000


def test_chunks_and_srt():
    plan = {"beats": [{"duration": 4, "vo": "one two three four"}, {"duration": 6, "vo": ""},
                      {"duration": 4, "vo": "five six"}]}
    cues = edit.chunks(plan, spoken=[2.0, 0, 0])
    assert cues == [(0.0, 1.0, "one two three"), (1.0, 2.0, "four"), (10.0, 13.6, "five six")]
    assert edit.srt(cues[:1]) == "1\n00:00:00,000 --> 00:00:01,000\none two three\n\n"
    assert edit._ts(3725.5) == "01:02:05,500"


def test_finish_command(tmp_path, monkeypatch):
    monkeypatch.setattr(edit, "find_ffmpeg", lambda: "ffmpeg")
    seen = {}

    def run(cmd, cwd=None, **k):
        seen.update(cmd=cmd, cwd=cwd)
        return type("P", (), {"returncode": 0, "stderr": ""})()

    edit.finish(tmp_path / "v.mp4", tmp_path / "final.mp4", tmp_path / "vo.wav", tmp_path / "c.srt", run=run)
    vf = seen["cmd"][seen["cmd"].index("-vf") + 1]
    assert seen["cwd"] == tmp_path and vf.startswith("subtitles=c.srt") and "AI-generated" in vf
    assert seen["cmd"][-1] == "final.mp4" and "-shortest" in seen["cmd"]


@pytest.mark.skipif(not find_ffmpeg(), reason="ffmpeg not installed")
def test_real_edit(tmp_path):
    ffmpeg = find_ffmpeg()
    for i, color in enumerate(("red", "blue")):
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", f"color={color}:s=180x320:d=1", "-pix_fmt", "yuv420p",
                        str(tmp_path / f"s{i}.mp4")], check=True)
    joined = edit.concat([tmp_path / "s0.mp4", tmp_path / "s1.mp4"], tmp_path / "joined.mp4")
    voice.write_wav(tmp_path / "vo.wav", b"\0\0" * voice.RATE * 2)
    (tmp_path / "c.srt").write_text(edit.srt([(0, 1, "hello there")]), encoding="utf-8")
    out = edit.finish(joined, tmp_path / "final.mp4", tmp_path / "vo.wav", tmp_path / "c.srt")
    assert out.stat().st_size > 1000


def test_concat_list_escapes_single_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr(edit, "find_ffmpeg", lambda: "ffmpeg")
    class R:
        returncode, stderr = 0, ""

    edit.concat([tmp_path / "it's.mp4"], tmp_path / "v.mp4", run=lambda *a, **k: R())
    line = (tmp_path / "v.txt").read_text(encoding="utf-8").strip()
    assert line.endswith("it'\\''s.mp4'") and line.startswith("file '")
