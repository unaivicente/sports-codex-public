# Architecture

## High-Level Modules

- Ingestion

- Extraction (Vision, Audio, OCR)

- Fusion

- Labelling

- Storage

- API

- UI

- Model Registry

- Training Pipeline

- Evaluation Engine

- Learning Policy Engine

## Data Flow

Video → Ingestion → Extractors → Evidence → Fusion → Labels → Storage → UI

                                                                  ↓

Correction → Learning Policy Engine → Training Dataset → Evaluation → Promotion

## Learning Loop (Closed Feedback System)

Predictions → Human Corrections → Structured Feedback → Training Dataset → Model Evaluation → Model Promotion → Updated Predictions



## Key Design Decisions

### 1. Ontology-driven labelling

Labels must come from ontology definitions, not model logic.

### 2. Per-second abstraction

All outputs normalized to 1-second intervals.

### 3. Evidence-first design

All predictions must include traceable evidence.

### 4. Loose coupling

Each module communicates via defined schemas.

### 5. Version Propagation

Every module must propagate:

- model_version

- ontology_version

These must remain attached to all downstream outputs.

### 6. Stateful vs Stateless Components

Stateless:

- Extractors

- Fusion

- Labelling

Stateful:

- Storage

- Model Registry

- Training Pipeline

- Ontology definitions

### 7. Failure Handling

- Missing modality → degrade gracefully with reduced confidence

- Conflicting evidence → mark as uncertain

- Invalid ontology transition → flag for review

### 8. Governed Learning

The system distinguishes between high-authority training feedback and lower-authority soft feedback.

Training Mode corrections can strongly influence model adaptation.

Soft Learning corrections are treated as weak signals unless aggregated, validated, or promoted through review.

Learning behaviour is controlled by policy, not by raw user edits.

### Open Questions

- How strict should ontology transitions be? 

- How to weight multimodal evidence?

- How to handle missing modalities?

- What reviewer roles are allowed to create training-mode corrections?

- Should soft learning update user-specific adapters before global adapters?

- What minimum trust_weight is required for training inclusion?

- How many soft corrections are required to equal one training correction?
