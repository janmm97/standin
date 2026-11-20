# Security policy

## Supported versions

Only the latest release gets security fixes.

## Reporting a vulnerability

Please report privately via GitHub: Security tab → "Report a vulnerability". Don't open a public issue.
We aim to reply within 7 days and to fix confirmed issues in the next release.

## Scope

standin runs local tools (Blender, LM Studio, ffmpeg) and paid cloud generations through the One CLI. We especially want to hear about:

- ways a brief, a plan file or a model reply can run commands or write outside the work folder (for example shell or argument injection into the One CLI, Blender, ffmpeg or the upload command);
- ways standin can start paid generations without the user passing `--yes`;
- anything that writes connection keys, tokens or uploaded images somewhere the user didn't expect, or leaves uploaded frames public after a job.
