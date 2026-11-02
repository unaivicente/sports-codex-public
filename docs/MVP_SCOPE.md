# MVP Scope

> Planning document: the scope below describes the intended product, not a
> claim that every feature is implemented. See [implementation status](STATUS.md)
> and [architecture](ARCHITECTURE.md) for current behavior.

## Included

- Local MP4 ingestion

- Video metadata extraction

- Timestamp-aligned frame extraction

- Audio extraction where available

- Mock visual, audio, OCR, and ASR extractors

- One-second evidence aggregation

- Ontology-driven labelling

- Per-second prediction output

- Human correction workflow

- SQLite-backed local storage

- JSON, CSV, and JSONL exports

- Training dataset preparation stubs

## Excluded

- Real-time inference

- Cloud storage

- Remote model inference

- Full model training

- Multi-user collaboration

- Production authentication

- Distributed processing

- Mobile app support

## Non-negotiable Constraints

- Local-first by default

- No hard-coded sport labels in inference logic

- Every prediction must be traceable to evidence

- Every prediction must reference model and ontology versions

- Human corrections must preserve source prediction provenance