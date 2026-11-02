# Fusion Package

Local-first helpers for multimodal metadata fusion.

Current scope:

- group timestamped evidence into one-second windows
- preserve all original evidence payloads and modalities in each window
- report missing expected modalities without failing or inventing placeholder
  evidence

No model inference or sport-specific labelling logic is implemented here.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
