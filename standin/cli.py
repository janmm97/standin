"""standin command line: models, doctor, plan, preview, make, batch."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import blender_run, direction, edit, higgsfield, images, models, one, voice
from .host import Host
from .plan import ASPECTS, make_plan, normalize, template_plan

DEFAULT_ASPECT = "9:16"


def say(msg: str) -> None:
    print(msg, flush=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "clip"


def get_plan(a) -> dict:
    if a.plan:
        raw = json.loads(Path(a.plan).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{a.plan} is not a plan (expected a JSON object)")
        # A saved plan keeps its own aspect unless --aspect is given.
        return normalize(raw, a.aspect or raw.get("aspect") or DEFAULT_ASPECT)
    aspect = a.aspect or DEFAULT_ASPECT
    if a.template:
        say("plan: template")
        return template_plan(a.brief, aspect)
    chosen, why = models.pick_chat(models.list_models())
    if chosen:
        say(f"plan model: {chosen.key} ({why}); loading...")
        models.ensure_loaded(chosen.key)
    plan, source = make_plan(a.brief, chosen.key if chosen else None, aspect)
    say(f"plan: {source}")
    return plan


def workdir(a, plan: dict) -> Path:
    d = Path(a.out) / slug(plan["title"] if a.plan else a.brief or plan["title"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return d


def sound(plan: dict, d: Path, want: bool) -> tuple[Path | None, Path]:
    """Voice-over (when an Orpheus model is installed) and captions; returns (wav or None, srt)."""
    wav, spoken = None, None
    vm = models.pick_voice(models.list_models()) if want else None
    if want and not vm:
        say("voice-over: skipped (no Orpheus model in LM Studio; see README)")
    if vm:
        try:
            models.ensure_loaded(vm.key)
            wav, spoken = voice.voice_over(plan, vm.key, d / "vo.wav")
            say(f"voice-over: {vm.key}, voice {plan['voice']}")
        except Exception as e:  # noqa: BLE001 (a silent video is still useful)
            say(f"voice-over: skipped ({e})")
    srt = d / "captions.srt"
    srt.write_text(edit.srt(edit.chunks(plan, spoken)), encoding="utf-8")
    return wav, srt


def cmd_models(a) -> int:
    found = models.list_models()
    for m in found:
        say(f"{m.type:10} {m.params_b:>5}B  {m.key}")
    chosen, why = models.pick_chat(found)
    vm = models.pick_voice(found)
    say(f"\nplan model:  {chosen.key if chosen else '-'} ({why})")
    say(f"voice model: {vm.key if vm else '- (install an Orpheus GGUF for voice-over)'}")
    return 0


def cmd_doctor(a) -> int:
    has_one = shutil.which("one")
    try:
        hf = bool(has_one and one.connection_key(higgsfield.PLATFORM, higgsfield.KEY_ENV))
    except one.OneError:
        hf = False
    try:
        Host()
        host = True
    except RuntimeError:
        host = False
    try:
        source = images.resolve(None)
    except ValueError as e:
        source = str(e)
    checks = [
        ("LM Studio CLI (lms)", shutil.which("lms"), "install LM Studio and run `lms bootstrap`"),
        ("Blender", blender_run.find_blender(), "install Blender 4.2+ or set STANDIN_BLENDER"),
        ("ffmpeg", blender_run.find_ffmpeg(), "install ffmpeg or set STANDIN_FFMPEG"),
        ("One CLI", has_one, "npm i -g @withone/cli, then `one init`"),
        ("Higgsfield in One", hf, "`one add higgsfield-ai` (paid steps only)"),
        (f"Images: {source}", True, ""),
        ("Keyframe hosting", host, "set STANDIN_UPLOAD_CMD and STANDIN_PUBLIC_BASE (paid steps only)"),
        ("voice extra", importlib.util.find_spec("snac"), "pip install 'standin[voice]'"),
    ]
    for name, ok, hint in checks:
        say(f"{'ok ' if ok else '-- '} {name}" + ("" if ok else f": {hint}"))
    return 0 if all(ok for _, ok, _ in checks[:3]) else 1


def cmd_plan(a) -> int:
    plan = get_plan(a)
    say(str(workdir(a, plan) / "plan.json"))
    return 0


def preview(a) -> Path:
    plan = get_plan(a)
    d = workdir(a, plan)
    say("blender: rendering preview...")
    blender_run.render(plan, d, "preview")
    mp4 = blender_run.frames_to_mp4(d / "preview", d / "preview.mp4")
    wav, srt = sound(plan, d, not a.no_vo)
    out = edit.finish(mp4, d / "preview_final.mp4", wav, srt)
    say(f"preview: {out}")
    return out


def reuse(dest: Path) -> bool:
    """A finished output from an earlier run is reused, so a rerun after a crash doesn't pay twice."""
    if dest.exists():
        say(f"reusing {dest.relative_to(dest.parent.parent)} (delete it to regenerate)")
    return dest.exists()


def paid(client, model: str, body: dict, dest: Path) -> Path:
    return dest if reuse(dest) else client.run(model, body, dest)


def picture(gen, prompt: str, refs: list[Path], aspect: str, dest: Path) -> Path:
    return dest if reuse(dest) else gen.image(prompt, refs, aspect, dest)


def make(a) -> Path | None:
    plan = get_plan(a)
    d = workdir(a, plan)
    source = images.resolve(a.images)
    cost = higgsfield.estimate(plan, a.draft, images=source == "higgsfield")
    say(f"images: {source} - {images.NOTE[source]}")
    say(f"Higgsfield estimate (USD, rough): {cost}  [{'Veo 3.1 Fast' if a.draft else 'Veo 3.1'}]")
    if not a.yes:
        say(f"no paid calls made. Check {d / 'plan.json'}, then add --yes to generate.")
        return None
    client, host = higgsfield.Client(), Host()  # fail on missing setup before the slow render
    gen = images.make(source, client, host)
    keys = blender_run.render(plan, d, "keys")
    if len(keys) != 2 * len(plan["beats"]):  # a first and last frame per beat; check before spending
        raise RuntimeError(f"Blender wrote {len(keys)} keyframes, expected {2 * len(plan['beats'])}")
    try:
        cast = []
        for i, member in enumerate(plan["cast"]):
            say(f"{source}: casting {member['name']}...")
            cast.append(picture(gen, direction.cast_prompt(plan, member), [], plan["aspect"],
                                d / "cast" / f"c_{i}.png"))
        stills = []
        for i, k in enumerate(keys):
            say(f"{source}: keyframe {i + 1}/{len(keys)}...")
            beat = plan["beats"][i // 2]  # keys come in (first, last) pairs per beat
            prompt = higgsfield.pose_prompt(len(cast), direction.still_prompt(plan, beat))
            dest = d / "shots" / f"s_{i:02}.png"
            stills.append(picture(gen, prompt, [Path(k), *cast], plan["aspect"], dest))
        if isinstance(gen, images.Agent) and gen.requests:
            req = d / "image_requests.json"
            req.write_text(json.dumps(gen.requests, indent=2), encoding="utf-8")
            say(f"{len(gen.requests)} image(s) to make, in order, as listed in {req}. Save each to its "
                "'output' path, then rerun this command to animate them.")
            return None
        shots = [host.upload(s) for s in stills]
        segs = []
        for i, b in enumerate(plan["beats"]):
            say(f"higgsfield: segment {i + 1}/{len(plan['beats'])}...")
            body = higgsfield.veo_body(shots[2 * i], shots[2 * i + 1], direction.motion_prompt(plan, b),
                                      b["duration"], plan["aspect"])
            model = "veo_fast" if a.draft else "veo"
            segs.append(paid(client, model, body, d / "segments" / f"seg_{i:02}.mp4"))
    finally:
        if left := host.cleanup():
            say(f"warning: could not delete {len(left)} hosted file(s): {', '.join(left)}")
    video = edit.concat(segs, d / "video.mp4")
    wav, srt = sound(plan, d, not a.no_vo)
    out = edit.finish(video, d / "final.mp4", wav, srt)
    say(f"final: {out}")
    return out


def cmd_batch(a) -> int:
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("brief") or "").strip()]
    failed = 0
    for n, row in enumerate(rows, 1):
        say(f"\n[{n}/{len(rows)}] {row['brief'][:60]}")
        sub = argparse.Namespace(**{**vars(a), "brief": row["brief"], "plan": None,
                                    "out": str(Path(a.out) / f"row-{n:02}"),  # briefs can share a slug
                                    "aspect": row.get("aspect") or a.aspect})
        try:
            (make if a.make else preview)(sub)
        except Exception as e:  # noqa: BLE001 (keep going; report at the end)
            failed += 1
            say(f"failed: {e}")
    say(f"\nbatch done: {len(rows) - failed} ok, {failed} failed")
    return 1 if failed else 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="standin", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="list LM Studio models and the ones standin would use")
    sub.add_parser("doctor", help="check Blender, ffmpeg, LM Studio, One and hosting")

    def common(sp, brief=True):
        if brief:
            sp.add_argument("brief", nargs="?", default="", help="what the clip is about")
            sp.add_argument("--plan", help="use this plan.json instead of writing one")
        sp.add_argument("--aspect", choices=ASPECTS, help="9:16 (default) or 16:9; a --plan keeps its own")
        sp.add_argument("--template", action="store_true", help="skip the local model; use the template plan")
        sp.add_argument("--out", default="out", help="output folder (default: out)")
        sp.add_argument("--no-vo", action="store_true", help="no voice-over")
        sp.add_argument("--draft", action=argparse.BooleanOptionalAction, default=True,
                        help="Veo 3.1 Fast (default) or --no-draft for Veo 3.1")
        sp.add_argument("--yes", action="store_true", help="allow paid Higgsfield calls")
        sp.add_argument("--images", choices=("auto", *images.PROVIDERS),
                        help="who makes the stills (default: STANDIN_IMAGES or auto: codex, gemini, openai, "
                             "then higgsfield)")

    for name, text in (("plan", "write a shot plan"), ("preview", "free local preview: plan, Blender, voice"),
                       ("make", "full photoreal video with Higgsfield (paid; needs --yes)")):
        common(sub.add_parser(name, help=text))
    b = sub.add_parser("batch", help="preview (or --make) every row of a CSV with a 'brief' column")
    b.add_argument("csv")
    b.add_argument("--make", action="store_true")
    common(b, brief=False)
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if a.cmd in ("plan", "preview", "make") and not (a.brief or a.plan):
        parser().error(f"{a.cmd} needs a brief or --plan")
    handlers = {"models": cmd_models, "doctor": cmd_doctor, "plan": cmd_plan, "batch": cmd_batch,
                "preview": preview, "make": make}
    try:
        rc = handlers[a.cmd](a)
        return rc if isinstance(rc, int) else 0
    except (RuntimeError, one.OneError, OSError, ValueError, subprocess.SubprocessError) as e:
        say(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
