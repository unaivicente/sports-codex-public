# Repository structure

```text
sports-codex/
  apps/
    api/                         Python demo server and FastAPI shell
    web/                         React, TypeScript, Vite and Vitest
  packages/
    contracts/schemas/           Portable JSON Schemas and Python validators
    ontology/definitions/        Versioned local sport definitions
    ingestion/                   Rational frame planning and FFmpeg extraction
    extraction/                  Extractor protocols and deterministic mocks
    fusion/                      One-second evidence aggregation
    labelling/                   Active-learning queue scorer
    storage/migrations/          SQLite schema and migration tooling
    training/                    Dataset manifests and adapter JSON artifacts
    evaluation/                  Model comparison and promotion gate
    model_registry/              Importable model discovery implementation
    model-registry/              Historical documentation directory
  tests/                         Python unittest suite
  docs/                          Current guides and archived planning
  Makefile                       Root development and data commands
  .env.example                   Illustrative local settings
  data/                          Generated local files; ignored by Git
```

## Source map

| Path | Responsibility |
| --- | --- |
| [`apps/api/server.py`](../apps/api/server.py) | HTTP handlers, CORS, unversioned frontend routes |
| [`apps/api/mock_payloads.py`](../apps/api/mock_payloads.py) | Demo predictions, correction acknowledgements, feedback fixtures |
| [`apps/api/main.py`](../apps/api/main.py) | FastAPI models and `/api/v1` endpoints |
| [`apps/api/ontologies.py`](../apps/api/ontologies.py) | API ontology loading, summaries and sport/version lookup |
| [`apps/api/contract_validation.py`](../apps/api/contract_validation.py) | API envelopes and schema availability checks |
| [`apps/web/src/App.tsx`](../apps/web/src/App.tsx) | Review workbench, timeline, correction form and dashboard |
| [`apps/web/src/api.ts`](../apps/web/src/api.ts) | Demo API fetch client and base URL |
| [`apps/web/src/contracts.ts`](../apps/web/src/contracts.ts) | Frontend contract types |
| [`packages/contracts/validation.py`](../packages/contracts/validation.py) | Runtime shape and semantic checks |
| [`packages/ontology/examples.py`](../packages/ontology/examples.py) | Embedded football/basketball ontology data used by the demo API |
| [`packages/ontology/loader.py`](../packages/ontology/loader.py) | File discovery, metadata and validation |
| [`packages/ontology/evolution.py`](../packages/ontology/evolution.py) | Additive changes and deprecated label mappings |
| [`packages/ingestion/frame_extraction.py`](../packages/ingestion/frame_extraction.py) | Exact timestamps, duration probe, extraction |
| [`packages/extraction/interfaces.py`](../packages/extraction/interfaces.py) / [`mock.py`](../packages/extraction/mock.py) | Extractor interface and modality mocks |
| [`packages/fusion/aggregation.py`](../packages/fusion/aggregation.py) | Grouping and missing-modality metadata |
| [`packages/labelling/active_learning.py`](../packages/labelling/active_learning.py) | Explainable review prioritisation |
| [`packages/storage/`](../packages/storage/) | Connection helper, migrations and fixtures |
| [`packages/training/prepare_finetuning.py`](../packages/training/prepare_finetuning.py) | SQLite correction filtering and manifest |
| [`packages/training/adapter_training.py`](../packages/training/adapter_training.py) | Label-head and adapter metadata artifacts |
| [`packages/model_registry/discovery.py`](../packages/model_registry/discovery.py) | Metadata discovery and local registry |
| [`packages/evaluation/model_evaluation.py`](../packages/evaluation/model_evaluation.py) | Metrics, comparison policy and promotion recommendation |

Run Python modules from the repository root. The importable registry module
uses an underscore: `packages.model_registry`. The hyphenated
`packages/model-registry` directory contains documentation only.
