# Extraction Package

Local extractor interface contracts for MVP multimodal evidence generation.

The shared contract is `Extractor.extract(request) -> list[EvidencePayload]`.
Each evidence payload must satisfy `packages.contracts.validate_evidence` and
therefore includes:

- `evidence_id`
- `modality`
- `timestamp`
- `type`
- `value`
- `confidence`
- `source_model_version`

Supported MVP modalities are `vision`, `audio`, `ocr`, and `asr`. Extractors
are stateless and local-first; this package does not introduce cloud storage or
remote inference.

`MockExtractor` is deterministic and ontology-driven. It selects label
identifiers from the supplied ontology payload and records the selected
`ontology_label_id` inside evidence `value`; it does not embed sport-specific
labels in inference logic.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
