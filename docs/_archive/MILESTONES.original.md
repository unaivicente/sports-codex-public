# Milestones

## Milestone 0 — Architecture Contracts (BLOCKING)

Goal: Freeze system interfaces before implementation.

Includes:

- MVP architecture definition

- Ontology schema

- Prediction schema

- Human correction schema

Exit criteria:

- All schemas defined and validated

- No ambiguity in data contracts

- Downstream modules unblocked

---

## Milestone 1 — Skeleton MVP

Goal: Establish repo structure and application shells.

Includes:

- Monorepo structure

- FastAPI backend shell

- React frontend shell

- SQLite storage

---

## Milestone 2 — Video Ingestion

Goal: Reliable ingestion and timestamp alignment.

Includes:

- MP4 ingestion

- Frame extraction

- Audio extraction

---

## Milestone 3 — Mock Multimodal Pipeline

Goal: Simulate model outputs with consistent interfaces.

Includes:

- Extractor contracts

- Mock visual/audio/OCR extractors

---

## Milestone 4 — Model Discovery and Local Model Registry

Goal: Establish a stable, reproducible foundation model stack and build a closed-loop learning system that improves over time through user corrections, ontology evolution, and structured evaluation.

This milestone intentionally separates:

- One-time model discovery and selection
- Continuous improvement via feedback and controlled training

The system must learn over time without sacrificing reproducibility, safety, or interpretability.

Includes:
- Model discovery happens once, not continuously
- All models are versioned and reproducible
- Learning is driven by structured human feedback
- Evaluation gates all model improvements
- Ontology evolution is first-class and versioned
- Training improves adapters, not the entire foundation stack


---

## Milestone 5 — Fusion and Labelling

Goal: Core intelligence layer.

Includes:

- Evidence aggregation

- Probabilistic labelling

- Temporal smoothing

- Decision trace output

---

## Milestone 6 — Human Review UI

Goal: Enable correction and inspection.

Includes:

- Timeline UI

- Editing tools

- Evidence inspector

- Correction persistence

---

## Milestone 7 — Export and Training Loop

Goal: Data extraction for analysis and training.

Includes:

- JSON/CSV exports

- Training dataset export

- Fine-tuning stub

---

## Milestone 8 — Testing, Security, Docs

Goal: Production readiness.

Includes:

- Schema tests

- Workflow tests

- Security review

- Documentation