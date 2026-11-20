# Contributing to standin

Thanks for helping! Small, focused changes are the easiest to review.

## Setup

You need Python 3.11+. Blender, LM Studio, ffmpeg and the One CLI are only needed to run standin for real. The unit tests use fakes, so they need no keys, no network and no GPU. The Blender test runs only when Blender is installed.

```sh
git clone <your fork>
cd standin
python -m pip install -e ".[dev]"
python -m pytest      # unit tests
ruff check .          # lint
```

## How we work

- **Open an issue first** for anything bigger than a bug fix, so we can agree on the approach.
- Branch from `main` and keep PRs small (ideally under ~400 changed lines).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`, `docs: …`, `test: …`, `chore: …`.
- No runtime dependencies in the core package. Optional features (local voice, captions) stay in extras.
- Every call to a cloud app goes through the One CLI. Never add code that reads or stores an API key or token.
- Nothing paid may run without `--yes`. Tests must never make paid or network calls.
- Don't commit model weights, renders or third-party assets.

## PR checklist

- [ ] Tests added or updated, and `python -m pytest` passes
- [ ] `ruff check .` passes
- [ ] README updated if behaviour or options changed
- [ ] `CHANGELOG.md` entry under `## [Unreleased]`

## Reviews

A maintainer reviews every PR. CI (lint and tests) must be green before merge. Changes to the One wrapper, the upload command or anything that spends money get an extra look.

## Questions

Open an issue with the `question` label.

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).
