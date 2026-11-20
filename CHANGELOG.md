# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Project scaffold: MIT licence, contributing guide, code of conduct, security policy, templates and CI.
- Local model discovery: reads `lms ls --json`, picks the largest chat model LM Studio says will fit (`lms load --estimate-only`), skips embedding and voice (Orpheus) models, and starts the server and loads it.
- Shot plan: a local model writes a JSON plan (cast, beats, actions, camera, voice-over) using a strict schema with thinking turned off; any bad value is clamped, and a template plan is used when no model is available.
- Blender blocking: headless Blender builds one primitive mannequin per cast member, animates the plan's action presets (walk_in, wave, point, hand_off, turn_to_camera, sit, idle) and cameras (static, dolly, orbit, handheld), and renders a low-res Workbench preview MP4 plus full-res keyframes at every beat boundary.
- Higgsfield through the One CLI: Soul cast stills, Nano Banana actor insertion into keyframes, Veo 3.1 first/last-frame segments, status polling with timeouts, a tolerant result-URL reader and a cost estimate. Keyframes get a short-lived public URL through your own upload/delete command (for example wrangler + R2) and are deleted afterwards.
