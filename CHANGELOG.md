# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Project scaffold: MIT licence, contributing guide, code of conduct, security policy, templates and CI.
- Local model discovery: reads `lms ls --json`, picks the largest chat model LM Studio says will fit (`lms load --estimate-only`), skips embedding and voice (Orpheus) models, and starts the server and loads it.
- Shot plan: a local model writes a JSON plan (cast, beats, actions, camera, voice-over) using a strict schema with thinking turned off; any bad value is clamped, and a template plan is used when no model is available.
- Blender blocking: headless Blender builds one primitive mannequin per cast member, animates the plan's action presets (walk_in, wave, point, hand_off, turn_to_camera, sit, idle) and cameras (static, dolly, orbit, handheld), and renders a low-res Workbench preview MP4 plus full-res keyframes at every beat boundary.
- Higgsfield through the One CLI: Soul cast stills, Nano Banana actor insertion into keyframes, Veo 3.1 first/last-frame segments, status polling with timeouts, a tolerant result-URL reader and a cost estimate. Keyframes get a short-lived public URL through your own upload/delete command (for example wrangler + R2) and are deleted afterwards.
- Local voice-over: Orpheus TTS through LM Studio, decoded with SNAC to 24 kHz WAV (optional `voice` extra), one line per beat fitted to the beat's length.
- Final edit with ffmpeg: joins the segments, adds the voice-over, burns ~3-word captions timed to each beat's spoken line, and stamps an "AI-generated" label.
- `standin` CLI: `models`, `doctor`, `plan`, `preview` (free, local), `make` (paid; prints a cost estimate and needs `--yes`), `batch` (CSV of briefs).

### Known limits
- Not yet run with paid Higgsfield calls: the result-URL and `input_images` shapes are unverified.
- The Orpheus prompt, the SNAC decode and the model-fit heuristic are tested with fixtures only.

### Fixed
- Blender output paths are made absolute, so a relative `--out` no longer writes to the drive root.
