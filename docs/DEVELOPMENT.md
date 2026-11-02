# Development reference

Install dependencies using [getting started](GETTING_STARTED.md), then work from
the repository root. This repository has no CI workflow, root Python dependency
manager configuration, formatter/linter target or generated TypeScript contract
step at present.

## Make targets

| Target | Actual behavior |
| --- | --- |
| `make help` | Print available tasks |
| `make setup` | Ensure package/app directories exist; no dependency installation |
| `make check` | Check required paths and environment ignore rules, then run `make test` |
| `make test` | Backend unittest discovery and frontend Vitest |
| `make test-backend` | `python -m unittest discover -s tests` |
| `make test-frontend` | Install with npm ci only if node_modules is absent, then run Vitest |
| `make dev` | Print two launch commands; no processes started |
| `make db-migrate` | Apply local SQL migrations |
| `make db-seed` | Migrate and insert development fixture rows |
| `make db-dev` | Invoke seed path and report database location |
| `make fine-tuning-prepare` | Write a dataset manifest; no fine-tuning |
| `make adapter-train` | Write local adapter/label-head JSON artifacts |
| `make model-evaluate` | Read an existing comparison input and write a report |

## Make path overrides

| Variable | Default |
| --- | --- |
| `DB_PATH` | `data/dev.sqlite3` |
| `FT_MANIFEST_PATH` | `data/training/fine_tuning_dataset_manifest.json` |
| `ADAPTER_ARTIFACT_ROOT` | `data/models/adapters` |
| `MODEL_EVALUATION_INPUT` | `data/evaluation/model_evaluation_input.json` |
| `MODEL_EVALUATION_REPORT` | `data/evaluation/model_evaluation_report.json` |

```sh
make db-dev DB_PATH=/tmp/sports-review.sqlite3
make fine-tuning-prepare DB_PATH=/tmp/sports-review.sqlite3 FT_MANIFEST_PATH=/tmp/sports-manifest.json
```

Paths above contain no spaces. Use the module CLIs directly with quoted paths
when targeting directories containing spaces; Make target expansion may add
another shell/Make quoting boundary.

## CLI entry points

| Module | Options |
| --- | --- |
| `apps.api.server` | `--host`, `--port` |
| `packages.storage.migrate` | `--db-path`, `--migrations-dir`, `--status` |
| `packages.storage.seed` | `--db-path` |
| `packages.training.prepare_finetuning` | `--db-path`, `--output-path`, `--dataset-version`, `--split` |
| `packages.training.adapter_training` | `--db-path`, `--artifact-root`, `--dataset-version`, `--validation-ratio`, `--run-id`, `--sport`, `--ontology-version`, `--foundation-model-version` |
| `packages.evaluation.model_evaluation` | Positional input JSON, `--output-path` |

Use `python -m MODULE --help` to inspect argument help. Ontology evolution,
frame extraction, fusion and discovery also expose Python functions; they do
not have general-purpose standalone CLIs.

## Verification

```sh
make check
npm --prefix apps/web run build
```

The build runs TypeScript checking and Vite bundling into ignored
`apps/web/dist`. `npm --prefix apps/web run preview` serves that frontend build
locally; its configured API must still be running.

| Tests | Coverage |
| --- | --- |
| `test_contracts.py` | Schemas, prediction/correction/training shapes and provenance |
| `test_api_shell.py`, `test_ontology_api.py` | Shell helpers, optional FastAPI client routes, file ontologies |
| `test_ingestion.py` | Timestamp planning and fake-runner extraction commands |
| `test_extraction_contracts.py`, `test_fusion_aggregation.py` | Mock modality evidence and second grouping |
| `test_active_learning.py` | Queue flags, ranking and provenance |
| `test_storage.py` | SQLite migration, seed and constraints |
| `test_training_prepare.py` | Manifest filtering, adapter artifacts, splits and label evolution |
| `test_model_discovery.py` | Static metadata discovery, registry and recommendation constraints |
| `test_model_evaluation.py` | Metrics, regressions and promotion gate |
| `test_ontology_evolution.py` | Version changes, deprecations and preserved lineage |
| Frontend `contracts.test.ts` | Contract-shaped mock API payloads |
| Frontend `App.test.tsx` | Server-rendered feedback dashboard fixture sections |

The inspected environment passes 77 backend tests and 7 frontend tests. These
are unit/contract tests, not a real-model benchmark or full browser interaction
suite. FFmpeg extraction tests use a fake runner, so they do not prove the
availability of a local FFmpeg installation. Test availability may depend on
installed optional API dependencies.

## Generate an evaluation input

This builds a small valid comparison input using existing mock records. The
candidate is deliberately identical, so the improvement gate should block it.

```sh
python - <<'PYTHON'
import copy
import json
from pathlib import Path
from apps.api.mock_payloads import build_mock_predictions_payload
from packages.ontology import get_ontology

ontology = get_ontology("football-local-mvp")
current = build_mock_predictions_payload("football-local-mvp", video_id="demo")["data"]["predictions"]
candidate = copy.deepcopy(current)
for record in candidate:
    record["prediction_id"] += "-candidate"
    record["model_version"] = "candidate-local-0.1.0"
references = [
    {key: record[key] for key in (
        "video_id", "timestamp", "interval_start", "interval_end", "label", "ontology_version"
    )}
    for record in current
]
payload = {
    "ontologies": [ontology], "references": references,
    "current": {"predictions": current}, "candidate": {"predictions": candidate},
}
path = Path("data/evaluation/model_evaluation_input.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2) + "\n")
PYTHON
make model-evaluate
```

Expect status 1 and a saved report containing blocking reasons. This is an
example of evaluating supplied predictions, not executing candidate inference.

## Change conventions

Keep generic pipeline logic ontology driven. Change schemas, Python validation,
TypeScript mirrors and relevant tests together. Preserve source snapshots and
versions. Add new migrations rather than editing shared applied SQL. Keep
local media, datasets, generated artifacts and credentials untracked. Update
implementation documentation whenever an integration gap is completed.
