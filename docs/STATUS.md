# Implementation status

Snapshot: 2 November 2026, implementation baseline `95aed22`.
This describes source behavior, not acceptance of an entire roadmap milestone.

| Area | Implemented | Remaining / limitation |
| --- | --- | --- |
| Frontend | Local preview, selectors, mock timeline, confirm/relabel, fixture feedback dashboard | Full edit operations, persistent review state, active-learning queue screen |
| Demo API | Health, embedded ontology catalogs, mock predictions, queue/dashboard fixtures, upload/correction acknowledgements | Storage and real processing |
| FastAPI | Versioned routes, OpenAPI, file ontology catalog, mock predictions, supplied queue scoring, metadata discovery | Compatibility with frontend, authentication, persistence; exports are stubs |
| Ontologies | Demo football/basketball fixtures; two football JSON files; validation and additive evolution | Unified catalogs, persistence workflow for evolved versions |
| Ingestion | Rational frame planning, FFprobe duration and local MP4 frame extraction | Audio track extraction and API orchestration |
| Extraction | Shared protocols and four deterministic mocks | Real vision/audio/OCR/ASR models |
| Fusion | One-second evidence grouping with missing-modality metadata | Probabilistic label scoring and temporal smoothing |
| Active learning | Explainable prioritisation with source snapshots | Full reviewer/trust policy service and queue persistence |
| Contracts | Five portable schemas, Python validators, TypeScript mirrors | Generation/parity automation and complete cross-record temporal policy |
| SQLite | Migration, relational constraints and deterministic seed | Full transport-to-SQLite mapping and persistent HTTP workflows |
| Training preparation | Filtered manifests, deprecation-aware labels and adapter/label-head JSON | Actual model weight training and integrated reviewed-data pipeline |
| Discovery | Static or opt-in remote metadata, rubric scores, synthetic smoke tests, local JSON registry | Real inference benchmarking and production stack management |
| Evaluation | Metrics and configurable promotion recommendation | Automated promotion execution and independent production validation |
| Operations | Local Make commands, tests and frontend build | CI, hosted runtime and production service controls |

## Known integration gaps

1. The React client expects unversioned demo paths and list-shaped predictions;
   FastAPI exposes `/api/v1` and different request/response shapes.
2. Demo ontologies are embedded fixtures. FastAPI and SQLite seed use different
   file-backed definitions and version identifiers.
3. HTTP correction acknowledgements are not persisted. Training tools read only
   separate SQLite rows, not browser submissions.
4. Nested multi-source interval edit contracts exceed the current flat SQLite
   correction representation. A persistence adapter/schema extension is needed.
5. Fusion emits populated evidence windows and no learned labels. The UI's
   sparse mock intervals do not satisfy a future full-video contiguous pipeline.
6. Adapter artifacts encode preparation data and label priors. Discovery smoke
   tests are synthetic. Neither proves trained-model quality.
7. There is no production authentication; `admin` in a route name is descriptive.

## Verification record

- Backend unittest discovery: 77 tests passed.
- Frontend Vitest: 7 tests passed across two test files.
- TypeScript check and Vite production build passed.
- Documentation examples and local API smoke checks are verified as part of
  documentation publication.

The unit suite does not establish full browser behavior, real FFmpeg execution,
real-model accuracy or production readiness. Refer to
[development](DEVELOPMENT.md) for test boundaries and commands.
