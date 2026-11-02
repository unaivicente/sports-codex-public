# Model discovery and registry

This is the importable Python implementation: `packages.model_registry`.
The historical [`model-registry`](../model-registry/README.md) directory is a
documentation entry point only.

`StaticCandidateSource` uses local metadata. `HuggingFaceModelSource` optionally
reads public model metadata. `ModelDiscoveryEvaluationService` requires an
explicit setup/admin refresh trigger, scores candidates and emits synthetic
ontology-backed smoke-test evidence. `FileModelRegistry` records runs in local
JSON, defaulting to `data/model_registry/model_discovery_registry.json`.

Discovery does not download weights, run actual model benchmarks, upload media
or replace production models. See [learning workflows](../../docs/ML_WORKFLOWS.md)
and the [FastAPI discovery route](../../docs/API_REFERENCE.md).
