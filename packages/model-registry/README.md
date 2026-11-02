# Model Registry Package

Local-first model discovery and registry utilities live in the importable
`packages.model_registry` package.

Current scope:

- one-time setup/admin-triggered candidate discovery
- metadata-only Hugging Face search support
- local JSON registry persistence
- rubric-based candidate scoring
- ontology-backed local smoke-test evidence
- initial foundation stack recommendations

The registry does not load model weights, call remote inference, or auto-replace
production models.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
