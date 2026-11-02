# Milestones

This roadmap describes intended outcomes. Status is based on source inspection
on 2 November 2026, not issue tracker completion. See [status](STATUS.md) for
specific integration gaps.

| Milestone | Evidence present | Remaining work |
| --- | --- | --- |
| 0. Architecture/contracts | Module boundaries, five schemas, validators, provenance/edit contracts | Complete temporal policy, schema/type parity automation and transport/storage mapping |
| 1. Application foundation | React UI, two Python API shells, SQLite migration and seed | Unified API integration and persistent application flow |
| 2. Video ingestion | MP4 frame extraction and exact timestamp planning | Audio extraction and upload-to-ingestion orchestration |
| 3. Mock multimodal pipeline | Vision/audio/OCR/ASR mock protocols and evidence | Connect media/evidence stages to application workflow |
| 4. Fusion and labelling | One-second evidence aggregation | Probabilistic labelling, temporal smoothing and full decision traces |
| 5. Human review | Timeline, confirm/relabel form, source provenance acknowledgement, fixture dashboard | Persistent corrections, full interval edits, evidence/queue review workflow |
| 6. Export and training loop | SQLite-backed manifest preparation and adapter JSON artifacts | Persistent reviewed-data integration, real exports through API, CSV/JSONL and actual training |
| 7. Testing and documentation | Unit/contract tests, build, implementation guides | CI, browser integration coverage, production service controls |
| 8. Model lifecycle | Metadata discovery, local registry, evaluation recommendations and ontology evolution helpers | Weight execution/benchmarking, real adapter training and reviewed promotion orchestration |

No complete production-readiness milestone is asserted. The next integration
work should first unify ontology/API boundaries and persist the review contract
before treating UI feedback as training data. Real model integration should
retain local execution and explicit evaluation gates.
