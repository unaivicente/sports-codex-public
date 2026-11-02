# Model and learning workflows

These tools operate on supplied Python data or local SQLite/JSON files. They
are usable independently of the UI. Current mock evidence and adapter artifacts
must not be interpreted as trained model performance.

## Ontology sources and evolution

There are two ontology sources:

| Source | Consumers | Definitions |
| --- | --- | --- |
| `packages.ontology.get_ontology` / `list_ontologies` | Demo API, React selectors | Embedded `football-local-mvp` and `basketball-local-mvp` fixtures in `examples.py` |
| `packages.ontology.load_ontology` and API file registry | File metadata discovery, FastAPI, SQLite seed | `definitions/example-football.json` and `definitions/football.json` |

These catalogs have different IDs and versions. Do not mix demo corrections
with a file-backed ontology simply because both describe football.

Evolution helpers return new dictionaries without mutating the source:

```python
from packages.ontology import add_label, deprecate_label, load_ontology

original = load_ontology("football")
evolved = add_label(
    original,
    ontology_version="football-local-v2",
    label={"label_id": "football.event.custom", "label_type": "event", "display_name": "Custom event"},
    reason="Local annotation vocabulary extension",
)
previous_label = original["labels"][0]["label_id"]
evolved = deprecate_label(
    evolved,
    ontology_version="football-local-v3",
    label_id=previous_label,
    replacement_label_id="football.event.custom",
)
```

Old labels remain interpretable through deprecation mappings and
`previous_ontology_version`. Saving the new definition and registering it in
storage is an explicit caller responsibility. Use a separate versioned JSON
file rather than replacing historical definitions needed by predictions.

## Frame planning and extraction

```python
from packages.ingestion import plan_frame_timestamps, extract_frames_at_fps

assert len(plan_frame_timestamps(duration_seconds=1, fps=3)) == 3
# Exact rational timestamps: 0, 1/3, 2/3.
frames = extract_frames_at_fps("sample.mp4", "data/frames/sample", fps=2)
metadata = [frame.as_metadata() for frame in frames]
```

The real extraction call requires a local MP4 and FFmpeg. When duration is not
supplied, FFprobe reads it. Each frame gets an index, local path, decimal seconds
and exact numerator/denominator metadata. Sampling begins at zero and excludes
the end boundary. The implementation launches FFmpeg per planned frame and
passes `-y`, so an existing output filename may be overwritten. Use a dedicated
output directory per run. Audio track extraction is not implemented.

## Mock extraction and fusion

```python
from packages.ontology import load_ontology
from packages.extraction import ExtractionRequest, build_mock_extractors
from packages.fusion import aggregate_evidence_by_second

ontology = load_ontology("football")
request = ExtractionRequest(video_id="demo", timestamp=0, ontology=ontology)
evidence = [item for extractor in build_mock_extractors() for item in extractor.extract(request)]
windows = aggregate_evidence_by_second(evidence)
assert windows[0]["missing_modalities"] == []
```

All four modality extractors share a protocol and generate ontology-backed
synthetic evidence. Fusion validates evidence, groups by the floor of each
timestamp, preserves original payloads, and reports present/missing modalities.
It emits populated seconds only, not predictions, probabilities or smoothed
labels. `expected_modalities=None` disables missing-modality expectations.

## Active-learning review scoring

```python
from packages.labelling import build_active_learning_demo_inputs, build_active_learning_queue
from packages.ontology import load_ontology

ontology = load_ontology("football")
predictions, corrections = build_active_learning_demo_inputs(ontology)
queue = build_active_learning_queue(
    predictions=predictions, corrections=corrections, ontology=ontology,
)
assert queue["queued_count"] == len(queue["queue"])
```

| Flag | Contribution |
| --- | --- |
| Low confidence | 0.24 |
| Multimodal disagreement | 0.26 |
| Ontology transition conflict | 0.22 |
| Rare label | 0.12 |
| Frequent corrections | 0.20 |

The score is the sum of applicable contributions and can exceed 1. It is a
priority score rather than a probability. Entries with no flags are omitted.
Ranking uses descending score, flag count, then earlier timestamp. Every entry
retains source prediction, evidence, model and ontology versions and detailed
reasons. Thresholds and rarity/correction parameters can be supplied by callers;
see `build_active_learning_queue` for defaults. Confirmation/rejected feedback
does not count toward frequent-correction flags. This scorer does not approve
corrections, train models or persist review decisions.

## Dataset preparation

```sh
make db-dev
make fine-tuning-prepare
```

The manifest defaults to `data/training/fine_tuning_dataset_manifest.json`.
It contains records, provenance, source information, filters, included/skipped
counts and per-correction skip reasons. Inclusion requires an accepted
correction, valid trust metadata, positive weight, a corrected label and a
trainable type (`confirm`, `modify`, `add`). Derived records are validated.
Both training and soft feedback can qualify if they meet those filters.

```sh
python -m packages.training.prepare_finetuning \
  --db-path data/dev.sqlite3 \
  --output-path data/training/reviewed-manifest.json \
  --dataset-version reviewed-v1 --split train
```

The command does not run fine-tuning. It reads the flat SQLite correction
representation, not API correction submission history. Mapping deprecated labels
retains source corrected labels and mapping metadata.

## Adapter and label-head artifacts

```sh
make adapter-train
python -m packages.training.adapter_training \
  --db-path data/dev.sqlite3 --artifact-root data/models/adapters \
  --dataset-version reviewed-v1 --validation-ratio 0.2 --run-id local-review-v1
```

Records are grouped by sport and ontology version. For each group, artifacts
contain `training_dataset.json`, `label_head.json`, `adapter_config.json`,
`model_card.json`, and `manifest.json`. Label heads use active ontology labels;
adapter parameters are lightweight weighted label priors, not optimized neural
model weights. Provenance and deprecation mappings are included.

The train/validation assignment is deterministic for the same dataset, run ID,
sport and ontology version. A new run ID can change the split. Splitting is by
training example, not by video or reviewer, so independent evaluation datasets
need their own leakage controls. Existing artifact-version directories are
rejected rather than overwritten. No model promotion or registry update occurs.

Optional filters: `--sport`, `--ontology-version`, `--foundation-model-version`.
These artifacts prepare a future trainer; no foundation model is loaded.

## Model discovery and registry

`packages.model_registry` provides `StaticCandidateSource`,
`HuggingFaceModelSource`, `FileModelRegistry`, `SmokeTestSampleClip` and
`ModelDiscoveryEvaluationService`. Discovery must be triggered explicitly with
`setup` or `admin_refresh`. Static mode works without network requests;
Hugging Face mode reads model metadata only.

Candidates are scored using metadata and synthetic ontology-backed smoke-test
evidence, then a recommended foundation stack is recorded. This is not a
benchmark of actual model inference. No weights are downloaded, no media is
uploaded and no production model is replaced.

The registry defaults to
`data/model_registry/model_discovery_registry.json`. It appends run records
and replaces its JSON file through a temporary file. There is no multi-process
write coordination. `MODEL_REGISTRY_DIR` in `.env.example` is illustrative and
does not override this path. Use the service constructor or FastAPI request's
`registry_path`. See [API reference](API_REFERENCE.md) for a static refresh.

## Model evaluation

```sh
python -m packages.evaluation.model_evaluation evaluation_input.json \
  --output-path data/evaluation/model_evaluation_report.json
```

Input shape:

```json
{
  "ontologies": [],
  "references": [],
  "current": {"predictions": [], "inference_cost": {}},
  "candidate": {"predictions": [], "inference_cost": {}},
  "policy": {}
}
```

Populate ontologies with valid definitions, references with video/interval/label/
ontology-version records, and both runs with valid prediction contracts. This
shape illustrates the keys; empty input is not a meaningful evaluation dataset.
The executable example in [development](DEVELOPMENT.md) builds valid data.

Metrics include per-label precision/recall/F1, temporal boundary accuracy,
calibration error, rare-event false positives, inference cost and sport/ontology
cohort regressions. Default policy requires at least 0.01 macro-F1 improvement
and checks maximum regressions: label F1 0.05, boundaries 0.02, calibration 0.02,
rare-event false positives 0, inference-cost ratio 0.20, protected cohort F1 0.
Policy settings are explicit in `DEFAULT_PROMOTION_POLICY`.

Reports include the selected policy, per-run metrics, comparison and
`promotion_decision` with blocking reasons. Exit status is **0 when promotion
is recommended, 1 when blocked**. Neither the function nor CLI promotes models
or changes registry state. The input file must already exist;
`make model-evaluate` does not generate it.
