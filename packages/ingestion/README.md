# Ingestion Package

Local-first media ingestion helpers.

Current scope:

- timestamp-aligned frame planning at configurable FPS;
- local MP4 frame extraction through a caller-provided/local `ffmpeg` binary;
- exact timestamp metadata preserved as rational seconds for every extracted
  frame.

The package does not upload media, call remote inference, or define any
sport-specific labels.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
