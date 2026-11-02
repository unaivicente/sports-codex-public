# Data Contracts

## Prediction Schema

Per-second output:

- timestamp

- label

- confidence

- evidence

- model_version

- ontology_version

- post_correction_model_agreement (true/false)

- confidence_delta

## Prediction Metadata 

Each prediction must include:

- prediction_id (unique identifier)

- video_id

- timestamp

- label

- confidence

- evidence

- model_version

- ontology_version

- inference_config (optional: thresholds, parameters)


## Evidence Format

Each evidence item:

- evidence_id

- modality (vision/audio/ocr/asr)

- timestamp

- type

- value

- confidence

- source_model_version

## Correction Schema


- correction_id

- video_id

- interval_start

- interval_end

- original_label

- corrected_label

- correction_type (confirm / modify / delete / add / ontology_gap)

- learning_mode (training / soft)

- reviewer_id

- reviewer_role (internal / external / admin / unknown)

- reviewer_confidence

- trust_weight

- source_prediction_id

- source_model_version

- ontology_version

- evidence_snapshot

- post_correction_model_agreement

- confidence_delta

- review_status (pending / accepted / rejected / needs_review)

- created_at

- notes 

## Correction Trust Score

Each correction receives a trust_weight between 0 and 1.

Suggested default weighting:

- Internal training-mode correction: 0.8–1.0

- Admin correction: 1.0

- External soft correction: 0.1–0.4

- Confirmed by multiple users: increases weight

- Contradicted by later reviewers: decreases weight

- Ontology-invalid correction: 0.0

The trust_weight determines how strongly a correction contributes to training.

## Correction Validity

A correction is valid for training only if:

- interval_start < interval_end

- timestamps align to the video timebase

- corrected_label exists in the referenced ontology_version, unless correction_type = ontology_gap

- source_prediction_id exists, unless correction_type = add

- reviewer_confidence meets the threshold for the learning_mode

- temporal constraints are not violated, unless explicitly marked as boundary correction

Model agreement is not required for validity.

Model re-evaluation is used as a weighting and review signal, not as the source of truth.

## Correction Validity — Structural

A correction is valid only if:

- interval_start < interval_end

- timestamps align with video timebase

- corrected_label exists in ontology_version

- source_prediction_id exists OR correction_type = "new"

## Ontology Schema

Must support:

- ontology_version

- events

- phases

- objects

- allowed transitions

- thresholds

- deprecated_labels (with mapping)


## Invariants

- No prediction without evidence

- No label outside ontology

- All timestamps must align to video timebase

- Every prediction must reference at least one evidence_id

- Every correction must reference a valid prediction_id OR explicitly mark "new label"

- Corrections must align with ontology_version

## Temporal Constraints

- Predictions must be contiguous per-second intervals with no gaps

- Overlapping labels must be explicitly allowed by ontology

- Temporal smoothing must not introduce invalid transitions

## Training Data Contract

Derived from corrections:

- video_id

- interval_start

- interval_end

- label

- source (corrected / confirmed)

- model_version_at_time

- ontology_version

## Correction Validity — Ontology

- corrected_label must exist in ontology_version

- transition into corrected_label must be allowed

- overlapping labels must be permitted by ontology rules

## Correction Validity — Reviewer Signal

A correction contributes to training if:

- reviewer_confidence ≥ threshold

OR

- correction is confirmed by ≥ N reviewers

OR

- reviewer has high historical reliability score

## Correction Validity — Consistency

- Correction does not contradict adjacent intervals unless explicitly marked as boundary change

- Correction does not introduce impossible temporal transitions

- Correction is not frequently reversed by later corrections

## Correction Validity

A correction is considered valid for training if:

1. It satisfies structural and ontology constraints

2. It meets reviewer signal criteria:

   - sufficient confidence OR

   - reviewer consensus OR

   - trusted reviewer source

3. It passes temporal consistency checks

4. It is not flagged as conflicting or unstable

Model re-evaluation is used to:

- assess correction reliability

- prioritise review

- weight training examples

Model agreement alone does NOT determine validity.


## Model Re-evaluation After Correction

When a correction is applied:

1. Recompute prediction for the corrected interval

2. Compare:

   - original_prediction

   - corrected_label

   - updated_prediction

3. Record:

   - model_agreement (did model converge to correction?)

   - confidence_shift


## Learning Mode

Each correction must specify a learning_mode:

- training

- soft

### training

Used for high-confidence internal review.

Expected behaviour:

- High trust weight

- Eligible for training datasets by default

- Eligible for model re-evaluation

- Eligible for promotion workflows

### soft

Used for general user feedback.

Expected behaviour:

- Lower trust weight

- May require aggregation before training use

- Useful for active learning prioritisation

- May contribute to user-specific or organisation-specific adapters

## Training Dataset Record

Derived from accepted corrections:

- training_example_id

- correction_id

- video_id

- sport

- interval_start

- interval_end

- label

- learning_mode

- trust_weight

- ontology_version

- source_model_version

- dataset_version

- split (train / validation / test)