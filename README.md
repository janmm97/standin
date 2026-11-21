# standin

Block the motion in Blender, cast photoreal AI actors with Higgsfield through the One CLI, and voice it with local models.

Most AI video is "prompt and pray". standin works more like a film set:

1. **Plan:** the most capable chat model you have in [LM Studio](https://lmstudio.ai) writes a shot plan: cast, beats, actions, camera moves and the voice-over lines.
2. **Block:** headless [Blender](https://www.blender.org) turns the plan into a stand-in animation. Grey mannequins walk, sit, point and hand things over while the camera dollies or orbits. You get a free preview MP4 to check the timing before you spend anything.
3. **Cast:** through the [One CLI](https://withone.ai), Higgsfield creates your actors (Soul) and puts them into each Blender keyframe in the same pose and framing (Nano Banana). Veo 3.1 then animates from keyframe to keyframe, so the actors follow your blocking.
4. **Voice:** a local Orpheus model in LM Studio speaks the lines. ffmpeg adds captions and an "AI-generated" label.

It's for marketers, content creators and ops teams who want short ads and clips they can direct and repeat. Steps 1, 2 and 4 run on your own PC for free. Only step 3 is paid.

## Requirements

| | Needed for | Notes |
|---|---|---|
| Python 3.11+ | everything | |
| [Blender](https://www.blender.org/download/) 4.2+ | preview, make | found on PATH, in the standard install folders, or via `STANDIN_BLENDER` |
| [ffmpeg](https://ffmpeg.org/download.html) | preview, make | PATH or `STANDIN_FFMPEG` |
| [LM Studio](https://lmstudio.ai) + `lms` CLI | the plan, the voice | optional: without a chat model you get a template plan |
| [One CLI](https://withone.ai) + `one add higgsfield-ai` | make | paid Higgsfield credits |
| A public bucket (e.g. Cloudflare R2) | make | Higgsfield needs image URLs, see below |

A GPU helps but isn't required. Blender previews use the Workbench engine.

## Quick start

```bash
pip install git+https://github.com/janmm97/standin
standin doctor                   # what's installed, what's missing
standin models                   # your LM Studio models and the one standin picks
standin preview "launch of our oat-milk latte for cold mornings"
```

`preview` writes `out/<slug>/`, which contains `plan.json`, `preview.mp4` (the mannequins), `captions.srt`, `vo.wav` if you have a voice model, and `preview_final.mp4`.

When you like the timing, make the photoreal version:

```bash
standin make --plan out/launch-of-our-oat-milk-latte-for-cold-mornings/plan.json          # prints the cost estimate, spends nothing
standin make --plan out/launch-of-our-oat-milk-latte-for-cold-mornings/plan.json --yes    # generates (Veo 3.1 Fast)
standin make --plan ... --yes --no-draft                                                   # full Veo 3.1
```

You can edit `plan.json` by hand between steps. For many clips:

```bash
standin batch briefs.csv              # previews for every row (columns: brief, optional aspect)
standin batch briefs.csv --make --yes
```

Other options: `--aspect 16:9`, `--template` (skip the local model), `--no-vo`, `--out <folder>`.

## Directing the shot

Generic prompts give generic AI images. standin writes every prompt the way a director and a cinematographer would brief a crew:

- **One location and one look per film.** `plan.json` has a concrete `location` (for example "narrow corner cafe, worn oak counter, snow outside the window, 7am") and a `look` (light, palette, grain). Every keyframe and every video segment gets both, so the shots match.
- **Shot sizes, angles and lenses.** Each beat has a `shot` (`wide`, `medium`, `close`, `detail`) and an `angle` (`eye`, `low`, `high`). Blender frames the mannequins to match, using a 24, 35, 50 or 85 mm prime, so the image model gets a real composition to follow rather than a centred figure.
- **Real cuts.** Each beat gets its own first and last keyframe (2 per beat), so a wide shot cuts to a close-up instead of morphing into it.
- **Craft and what to avoid.** Each prompt asks for a cinema camera, shallow depth of field, real skin and materials, and motivated light. It rules out plastic skin, HDR colour, stock-photo grins, warped hands, text and watermarks.

The look is only as good as the plan. A capable local model writes a usable one. The `--template` plan is a fallback: its only line is your brief, and its location is generic. For a real ad, write `location`, `look`, `scene` and `vo` in `plan.json` yourself (or have any chat assistant write the plan against the schema in `standin/plan.py`), then run `preview` again before `make`.

## Picking the local model

`standin models` reads `lms ls --json`. It ignores embedding models and voice (Orpheus) models, sorts the chat models by parameter count, and asks LM Studio (`lms load <model> --estimate-only`) whether each one fits your machine. The biggest one that fits writes the plan. Set `STANDIN_CHAT_MODEL` to choose one yourself.

The plan uses a strict JSON schema with thinking turned off (`reasoning_effort: "none"`). A small model's mistakes are clamped to valid values, and if LM Studio isn't available the template plan is used.

## Voice-over (local)

1. In LM Studio, download an Orpheus 3B GGUF (search "orpheus-3b-0.1-ft"). standin finds any model with "orpheus" in its name, or the one you set in `STANDIN_VOICE_MODEL`.
2. `pip install "standin[voice] @ git+https://github.com/janmm97/standin"` adds SNAC, torch and numpy to decode the audio.

Voices: tara, leah, jess, leo, dan, mia, zac, zoe (the plan picks one). Orpheus is released under the Llama 3.2 community licence: you download it yourself, and standin doesn't ship any weights. Without a voice model the video gets captions only.

## Keyframe hosting (for `make`)

Higgsfield reads images from public URLs, and the One CLI sends JSON only, so standin uploads keyframes with a command you configure. It deletes them when the job ends, even if the job fails. Example with Cloudflare R2 and wrangler:

```bash
STANDIN_UPLOAD_CMD="npx wrangler r2 object put my-bucket/{key} --file {path} --remote"
STANDIN_DELETE_CMD="npx wrangler r2 object delete my-bucket/{key} --remote"
STANDIN_PUBLIC_BASE="https://pub-xxxxxxxx.r2.dev"
```

Any tool works: `{path}` is the local file and `{key}` is a random object name. See [.env.example](.env.example).

## Cost

`make` always prints an estimate first and needs `--yes` before it spends anything. With rough 2026-11 prices, the 3-beat template plan (1 actor, 14 s) comes to about $1.66 on Veo 3.1 Fast. A 4-beat, 2-actor, 22 s plan comes to about $9 on Veo 3.1. Check Higgsfield's current pricing.

## Measured on a laptop

RTX 3050 Laptop GPU (4 GB), Blender 5.3, LM Studio with qwen3.5-4b (Q4_K_M):

| Step | Time |
|---|---|
| Load the model (full GPU offload) | 28 s |
| Write a 4-beat plan (~1.7 tok/s) | 235 s |
| Blender preview, 529 frames at 180×320 | 40 s |
| 5 keyframes at 720×1280 | 9 s |
| Whole `preview` with an existing plan | 44 s |

On a 4 GB GPU the local plan is the slowest step. Use `--template` or edit a plan by hand if you're in a hurry.

## Honest limits

- The mannequins are crude on purpose (no elbows or knees). They're a pose and camera reference, not final art, and feet can slide in walk-ins.
- How closely the actors follow your blocking depends on Higgsfield's models. Keyframes pin the start and end of every beat; the motion in between is Veo's.
- The Higgsfield path hasn't been run against paid endpoints yet. The `input_images` item shape for Nano Banana is a best guess from incomplete docs (see `standin/higgsfield.py`). Please open an issue if a call fails.
- The voice path is tested with fixtures only so far: the Orpheus prompt format and the SNAC decode haven't been checked against a real model.
- The "will it fit" model check reads `lms load --estimate-only` output with a heuristic that hasn't been checked on many machines.
- Every output carries an "AI-generated" label. Don't use it to impersonate real people.

## Prior art

Text-to-video tools (Runway, Pika, Higgsfield's own apps) and pose-guided pipelines (ControlNet/AnimateDiff in ComfyUI) cover parts of this. standin's angle is the combination: a repeatable Blender blocking pass, a plan written by your own local model, paid generation only after a free preview, and everything scriptable from an agent through the One CLI.

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md). Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security
See [SECURITY.md](SECURITY.md). Don't open public issues for vulnerabilities.

## License
MIT, see [LICENSE](LICENSE).
