# Local-first Multimodal Sports Video Metadata Labeller

> Planning document: the scope below describes the intended product, not a
> claim that every feature is implemented. See [implementation status](STATUS.md)
> and [architecture](ARCHITECTURE.md) for current behavior.

## Objective

Build a local-first system that ingests sports video and produces structured, explainable, per-second metadata using multimodal signals (vision, audio, OCR), with a human-in-the-loop correction workflow and a training data feedback loop.

## Core Principles

- Local-first: no mandatory cloud dependencies
- Modular: clear separation between ingestion, extraction, fusion, labelling
- Ontology-driven: no hard-coded sport logic
- Explainable: every prediction must include evidence
- Human-in-the-loop: corrections are first-class citizens
- Trainable: corrections feed future model improvement

## System Overview

Pipeline:

1. Video ingestion
2. Frame/audio extraction
3. Multimodal feature extraction
4. Evidence aggregation (per second)
5. Probabilistic labelling
6. Temporal smoothing
7. Prediction output
8. Human correction
9. Export → training loop

## MVP Scope

The MVP will:

- Work with local MP4 files only
- Use mock extractors (no real ML models yet)
- Produce per-second labels
- Support manual correction
- Export structured datasets

## Out of Scope (MVP)

- Real-time inference
- Cloud deployment
- Full model training pipelines
- Multi-user collaboration

## MVP Learning Scope

The MVP will:



- Capture structured corrections

- Support correction modes: training and soft learning

- Store correction authority and trust weight

- Export training-ready datasets

- Define training interfaces, without requiring full model training in MVP


## Model Lifecycle (Post-MVP)

1. Select foundation models

2. Generate predictions

3. Collect corrections

4. Build training datasets

5. Train adapters

6. Evaluate models

7. Promote or reject models


## Risks

- Poor schema design → rework across pipeline
- Temporal alignment errors → invalid labels
- Overcoupling ontology and inference logic
- UI complexity for annotation
- Ontology drift → inconsistent labels across time
- Poor correction quality → degraded model performance
- Lack of versioning → irreproducible results

## Success Criteria

- End-to-end pipeline works locally
- Predictions are explainable
- Corrections can be exported as training data
- Architecture supports future model integration

## Learning Readiness Criteria

- Corrections are structured and exportable
- Predictions are fully traceable (model + ontology)
- Data contracts support training pipeline integration

## Learning Modes

The system supports multiple learning modes to control how human feedback affects model improvement.

### Training Mode

Used by trusted internal reviewers.

Purpose:

- Generate high-confidence training data

- Correct model behaviour with strong weighting

- Support ontology refinement

- Produce promotion-ready datasets

Characteristics:

- Reviewer must be authenticated as internal/trusted

- Reviewer confidence is required

- Corrections receive high training weight

- Corrections can trigger model re-evaluation

- Corrections are eligible for model promotion workflows

### Soft Learning Mode

Used by external or general users.

Purpose:

- Capture weak learning signals

- Detect recurring model errors

- Improve active learning queues

- Inform future training without immediately dominating the model

Characteristics:

- Corrections receive lower training weight

- Corrections may require aggregation or consensus

- Corrections can flag likely issues but do not directly define model truth

- Corrections may improve user-specific or organisation-specific adapters before global models

### Learning Principle

Not all corrections are equal.

The system must distinguish between:

- authoritative corrections

- weak feedback

- confirmations

- uncertain edits

- ontology-gap reports