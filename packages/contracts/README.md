# Contracts Package

Shared local data contracts for the sports video metadata labeller.

Contract implementation version: `0.1.0`.

Portable JSON Schema files live in `schemas/`. Python backend validators are
exported from `packages.contracts`. Frontend applications should mirror the
types in `apps/web/src/contracts.ts` until a generation step is introduced.

These contracts are storage and transport definitions only. They do not add
cloud storage, remote inference, or sport-specific inference labels. Labels are
ontology identifiers and must be resolved against the referenced
`ontology_version`.

## Prediction Contract

Predictions are immutable model-authored records. They are the provenance source
for human corrections and training export lineage.

Required prediction fields:

- `prediction_id`: unique prediction identifier.
- `video_id`: local video identifier.
- `timestamp`: second-aligned prediction timestamp.
- `interval_start`: inclusive interval start, in the video timebase.
- `interval_end`: exclusive interval end, in the video timebase.
- `duration_seconds`: fixed to `1` for MVP one-second aggregation.
- `timebase`: timestamp scale used by the video.
- `label`: ontology label identifier.
- `confidence`: model confidence in the range `[0, 1]`.
- `evidence`: one or more evidence items supporting the label.
- `model_version`: model or mock-model version that produced the prediction.
- `ontology_version`: ontology version used when selecting the label.
- `inference_config`: optional thresholds, feature flags, or smoothing settings.
- `created_at`: prediction creation timestamp.

Evidence item fields:

- `evidence_id`: unique evidence identifier.
- `modality`: `vision`, `audio`, `ocr`, `asr`, or another ontology-supported
  local modality.
- `timestamp`: evidence timestamp in the same timebase as the prediction.
- `type`: evidence type.
- `value`: evidence payload or extracted value.
- `confidence`: evidence confidence in the range `[0, 1]`.
- `source_model_version`: model or extractor version that produced the evidence.

## Extractor Interface Contract

Visual, audio, OCR, and ASR extractors implement the same local interface:

- input: local video identifier, timestamp, timebase, and ontology payload;
- output: one or more Evidence Contract payloads;
- provenance: each evidence item includes `source_model_version`;
- ontology use: mock label-like signals may reference ontology label
  identifiers, but labels must be selected from the supplied ontology payload.

Extractors are stateless and local-first. They must not introduce cloud storage,
remote inference, or sport-specific label logic.

## Human Correction Contract

Human corrections are durable reviewer-authored records. A correction must not
mutate or overwrite the source prediction. It preserves the prediction snapshot
shown to the reviewer, the model provenance, the ontology provenance, and the
reviewer decision that may later be exported for training.

Required correction fields:

- `correction_id`: unique correction identifier.
- `video_id`: local video identifier.
- `target_interval`: interval being reviewed or edited.
- `corrected_intervals`: reviewer-approved intervals after the edit is applied.
- `correction_type`: `confirm`, `modify`, `delete`, `add`, or `ontology_gap`.
- `edit_operation`: `none`, `split`, `merge`, `relabel`, or
  `boundary_adjust`.
- `source_predictions`: immutable source prediction snapshots.
- `primary_source_prediction_id`: main source prediction for one-to-one edits,
  or `null` for source-free additions.
- `ontology_version`: ontology version available to the reviewer.
- `evidence_snapshot`: evidence visible to the reviewer at correction time.
- `learning_mode`: `training` or `soft`.
- `reviewer_id`: local reviewer identifier.
- `reviewer_role`: `internal`, `external`, `admin`, or `unknown`.
- `reviewer_confidence`: reviewer confidence in the range `[0, 1]`.
- `trust_weight`: training influence weight in the range `[0, 1]`.
- `review_status`: `pending`, `accepted`, `rejected`, or `needs_review`.
- `post_correction_model_agreement`: optional model re-evaluation result.
- `confidence_delta`: optional confidence change from model re-evaluation.
- `supersedes_correction_ids`: optional prior corrections superseded by this
  correction.
- `created_at`: correction creation timestamp.
- `notes`: optional reviewer or system notes.

`target_interval` fields:

- `interval_start`: inclusive target start.
- `interval_end`: exclusive target end.
- `timebase`: timestamp scale used by the video.
- `source_prediction_ids`: all source predictions affected by the correction.

`source_predictions` is required for every correction with source predictions.
It is empty only for source-free `add` corrections or source-free
`ontology_gap` reports. Each source prediction snapshot must use the Prediction
Contract fields and must preserve the exact values available when the correction
was made, including `label`, `confidence`, `evidence`, `model_version`, and
`ontology_version`.

`corrected_intervals` fields:

- `interval_start`: inclusive corrected start.
- `interval_end`: exclusive corrected end.
- `timebase`: timestamp scale used by the video.
- `label`: ontology label identifier, or `null` for `ontology_gap`.
- `ontology_version`: ontology version used for the corrected label.
- `reviewer_confidence`: reviewer confidence for this interval.
- `evidence_refs`: evidence IDs or correction-local references supporting the
  interval.
- `proposed_label`: optional free-text ontology-gap proposal. This is not a
  valid training label until a future ontology version defines it.
- `notes`: optional interval notes.

## Correction Type Semantics

- `confirm`: reviewer accepts the source prediction as-is. It uses
  `edit_operation = none`, preserves the source prediction snapshot, and emits a
  `confirmed` training record if accepted.
- `modify`: reviewer changes label, timing, or both. It preserves every affected
  source prediction snapshot and emits `corrected` training records if accepted.
- `delete`: reviewer marks one or more source predictions invalid. It preserves
  the source prediction snapshots and emits no positive label training record.
- `add`: reviewer creates one or more valid ontology-labelled intervals where no
  prediction existed. `source_predictions` and `source_prediction_ids` are empty,
  and accepted records emit `human_added` training records.
- `ontology_gap`: reviewer cannot choose a valid ontology label. The record may
  include `proposed_label`, but it is excluded from model training until a valid
  ontology label exists in a later accepted correction.

## Interval Edit Semantics

- `none`: no label or boundary change. Used for confirmations.
- `relabel`: one source prediction maps to one corrected interval with a
  different ontology label.
- `boundary_adjust`: one source prediction maps to one corrected interval with
  adjusted start or end time.
- `split`: one source prediction maps to multiple non-overlapping corrected
  intervals.
- `merge`: multiple source predictions map to one corrected interval.

Split and merge requirements:

- `target_interval.source_prediction_ids` includes every affected source
  prediction.
- `source_predictions` includes a full snapshot for every affected source
  prediction.
- `corrected_intervals` are sorted by `interval_start`.
- Corrected intervals do not overlap unless the referenced ontology version
  explicitly allows overlapping labels.

## Correction Validity

A correction is structurally valid only when:

- every target and corrected interval satisfies `interval_start < interval_end`;
- timestamps align to the video timebase;
- source prediction IDs and snapshots are present unless the correction is
  source-free;
- every source snapshot includes `model_version` and `ontology_version`;
- every corrected `label` exists in the referenced `ontology_version`, except
  for `ontology_gap` records;
- reviewer provenance and learning metadata are present; and
- `trust_weight` is zero for rejected, invalid, or ontology-gap records.

Model agreement after a correction can inform review queues and trust-weight
policy, but it must not override reviewer, ontology, provenance, or structural
validity.

## Training Export Contract

Training dataset rows are derived only from accepted, valid corrections.

Required training record fields:

- `training_example_id`: unique training example identifier.
- `dataset_version`: export dataset version.
- `correction_id`: source correction identifier.
- `video_id`: local video identifier.
- `sport`: sport identifier required by the portable training record schema.
- `interval_start`: inclusive training interval start.
- `interval_end`: exclusive training interval end.
- `timebase`: timestamp scale used by the video.
- `label`: ontology label identifier.
- `source`: `confirmed`, `corrected`, or `human_added`.
- `correction_type`: source correction type.
- `edit_operation`: source edit operation.
- `learning_mode`: source learning mode.
- `trust_weight`: correction trust weight.
- `ontology_version`: ontology version used for the training label.
- `source_prediction_ids`: source prediction IDs that contributed lineage.
- `source_model_versions`: model versions from the source prediction snapshots.
- `source_ontology_versions`: ontology versions from the source prediction
  snapshots.
- `evidence_snapshot`: evidence visible at correction time.
- `split`: `train`, `validation`, or `test`.

Training export rules:

- Accepted `confirm`, `modify`, and `add` corrections emit one training record
  per corrected interval.
- `split` corrections emit one training record per corrected interval.
- `merge` corrections emit one training record for the merged corrected
  interval and preserve every merged `source_prediction_id`.
- `delete` corrections emit no positive label records. They may be exported only
  to exclusion or error-analysis datasets.
- `ontology_gap` corrections are excluded from model training until the ontology
  is updated and a later accepted correction references a valid label.

See the [implementation guide](../../docs/DATA_CONTRACTS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
