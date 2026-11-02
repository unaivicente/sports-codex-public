# Data contracts

Contract version: `0.1.0`, defined in
[`packages/contracts/version.py`](../packages/contracts/version.py).
The portable definitions are the five
[JSON Schemas](../packages/contracts/schemas/). Python runtime validation is
implemented explicitly in
[`validation.py`](../packages/contracts/validation.py); it is not a generic
JSON Schema execution engine. TypeScript types in
[`apps/web/src/contracts.ts`](../apps/web/src/contracts.ts) are maintained
manually. Update all three surfaces when changing a shared contract.

The detailed [contracts package reference](../packages/contracts/README.md)
describes correction and edit semantics. This guide records the runtime shape
and the current integration boundaries.

## Schemas and validators

| Schema name | Portable file | Python validator |
| --- | --- | --- |
| `ontology` | [ontology.schema.json](../packages/contracts/schemas/ontology.schema.json) | `validate_ontology` |
| `evidence` | [evidence.schema.json](../packages/contracts/schemas/evidence.schema.json) | `validate_evidence` |
| `prediction` | [prediction.schema.json](../packages/contracts/schemas/prediction.schema.json) | `validate_prediction` |
| `human_correction` | [human_correction.schema.json](../packages/contracts/schemas/human_correction.schema.json) | `validate_human_correction` |
| `training_dataset_record` | [training_dataset_record.schema.json](../packages/contracts/schemas/training_dataset_record.schema.json) | `validate_training_dataset_record` |

Import validators from `packages.contracts`. `load_schema(name)` returns a schema
as a dictionary. `ContractValidationError.errors` contains validation messages.
Pass an ontology to prediction/correction/training validators to check labels.

## Ontology

Required fields: `ontology_id`, `ontology_version`, and non-empty `labels`.
Each label has `label_id`, `label_type`, and `display_name`. Optional metadata
includes sport identity, thresholds, transition rules, and evolution history.
Transition rules refer to known labels. Versions are explicit identifiers; API
default lookup selects the first matching sorted definition, not the newest
semantic version.

Evolution produces a new payload with `previous_ontology_version` and an
`evolution` block. Deprecated labels remain present with mappings containing
`label_id`, `replacement_label_id` and `deprecated_in_version`. Active label
selection excludes them. See [learning workflows](ML_WORKFLOWS.md).

## Evidence

Required fields: `evidence_id`, `modality`, non-negative `timestamp`, `type`,
`value`, `confidence` in `[0, 1]`, and `source_model_version`. The shared
extractor interface supports `vision`, `audio`, `ocr`, and `asr`.
`value` carries modality-specific data and may contain an ontology label
identifier; evidence does not itself imply real inference has run.

## Prediction

Required fields:

| Group | Fields |
| --- | --- |
| Identity | `prediction_id`, `video_id` |
| Time | `timestamp`, `interval_start`, `interval_end`, `duration_seconds`, `timebase` |
| Output | `label`, `confidence`, non-empty `evidence` |
| Provenance | `model_version`, `ontology_version`, `created_at` |

Intervals use inclusive start and exclusive end. MVP records have
`duration_seconds: 1`; timestamps and interval bounds must satisfy the runtime
validator. `inference_config`, `post_correction_model_agreement` and
`confidence_delta` are optional metadata. Prediction agreement is boolean or
null; correction agreement is a numeric `[0, 1]` score or null.

A reproducible example can be obtained from the demo payload builder:

```python
from apps.api.mock_payloads import build_mock_predictions_payload
from packages.contracts import validate_prediction
from packages.ontology import get_ontology

ontology = get_ontology("football-local-mvp")
prediction = build_mock_predictions_payload("football-local-mvp", video_id="demo")["data"]["predictions"][0]
validate_prediction(prediction, ontology=ontology)
```

Predictions are treated as immutable provenance sources. The APIs generate
records but do not persist them. Neither record validation nor fusion currently
guarantees contiguous full-video coverage across a series of records.

## Human correction

The transport contract is an interval edit with source snapshots, not a flat
`original_label` / `corrected_label` pair.

| Group | Required fields |
| --- | --- |
| Identity | `correction_id`, `video_id`, `created_at` |
| Edit | `target_interval`, `corrected_intervals`, `correction_type`, `edit_operation` |
| Provenance | `source_predictions`, `primary_source_prediction_id`, `ontology_version`, `evidence_snapshot` |
| Reviewer/policy | `learning_mode`, `reviewer_id`, `reviewer_role`, `reviewer_confidence`, `trust_weight`, `review_status` |

`target_interval` carries start/end, timebase, and affected source prediction
IDs. Each corrected interval carries start/end, timebase, label, ontology
version, reviewer confidence and evidence references. Optional gap proposals
use `proposed_label` rather than becoming valid labels automatically.

| Correction type | Meaning | Positive training rows when eligible |
| --- | --- | --- |
| `confirm` | Keep a source label | `confirmed` |
| `modify` | Change label and/or timing | `corrected` |
| `add` | Add a source-free interval | `human_added` |
| `delete` | Invalidate source output | None |
| `ontology_gap` | No suitable defined label | None |

Edit operations are `none`, `split`, `merge`, `relabel`, and `boundary_adjust`.
Source snapshots retain their original model/ontology/evidence fields. Source-free
`add` and `ontology_gap` records are supported by transport validation. Refer
to the schema and package reference for operation-specific interval rules.

Reviewer roles are `internal`, `external`, `admin`, and `unknown`; review status
is `pending`, `accepted`, `rejected`, or `needs_review`; learning mode is
`training` or `soft`. Rejected, pending, needs-review and ontology-gap records
must have zero trust weight under current validation. Accepted feedback still
needs validity and positive trust to enter database-backed preparation.

The runtime validates structure, provenance and applicable ontology semantics;
reviewer authentication, consensus history and a complete correction policy
engine are not implemented. Model agreement must not determine human truth.

## Training dataset record

Required fields include `training_example_id`, `dataset_version`,
`correction_id`, `video_id`, **`sport`**, interval start/end and `timebase`,
`label`, `source`, `correction_type`, `edit_operation`, `learning_mode`,
`trust_weight`, `ontology_version`, `source_prediction_ids`,
`source_model_versions`, `source_ontology_versions`, `evidence_snapshot`,
and `split` (`train`, `validation`, `test`).

The database exporter requires accepted corrections, `validity_status: "valid"`,
positive trust, a trainable correction type and a corrected label. It validates
each derived row and records skip reasons. Deprecated corrected labels can map
to active replacement IDs while retaining source label/mapping metadata.

The transport schema can represent split/merge lineage. The current SQLite
schema stores flat correction rows with one source prediction reference; there
is no API-to-SQLite adapter implementing the full edit contract yet. See
[storage](STORAGE.md) before designing persistence or export integrations.

## Invariants and remaining policy work

Evidence, model version, ontology version and correction lineage must survive
all downstream transformations. Label identities must be checked against the
referenced ontology. Intervals must use the video timebase and valid boundaries.

Contiguous full-video predictions, complete overlap/transition enforcement,
reviewer reliability, consensus-based trust, post-correction model execution
and promotion orchestration remain design goals. They must not be inferred from
a successful shape validation or API acknowledgement.
