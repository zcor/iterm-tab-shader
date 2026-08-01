# Changelog

## 0.1.2

- Replaced per-tab SQLite subprocess polling with one incremental, read-only
  broker while preserving live `/model` and effort tint changes.
- Added private per-tab runtime state, stale runtime-file cleanup, and broker
  resource controls.

## 0.1.1

- Added a privacy-safe multi-agent iTerm panorama to the README.

## 0.1.0

- First public release with Codex tier and effort tints.
- Added Claude, Grok, Gemini, and Kimi companion wrappers.
- Added the local-only iTerm attention monitor and palette SVG.
