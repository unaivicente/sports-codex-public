# Training Package

Local training workflow preparation utilities.

Current scope: local training data preparation and adapter artifact generation.
The commands below read accepted, valid corrected intervals from the local
SQLite database and write local JSON artifacts. They do not retrain foundation
model weights, promote models, or call remote inference.

```sh
python -m packages.training.prepare_finetuning --db-path data/dev.sqlite3
python -m packages.training.adapter_training --db-path data/dev.sqlite3
```

The default manifest path is `data/training/fine_tuning_dataset_manifest.json`.
The default adapter artifact root is `data/models/adapters`.

Adapter artifacts are grouped by sport and ontology version. Each artifact
contains:

- `training_dataset.json` with deterministic train/validation splits
- `label_head.json` whose labels are copied from the ontology definition
- `adapter_config.json` with lightweight label-prior parameters
- `model_card.json` and `manifest.json` with version and provenance metadata

Artifact directories are append-only. Reusing the same artifact version path
raises an error instead of overwriting a previous local model artifact.

When an ontology version deprecates a label, training records map deprecated
corrected labels to their `replacement_label_id` while preserving the original
corrected label and mapping metadata. Label-head artifacts include active label
IDs, deprecated-label mappings, and ontology evolution metadata so model heads
can be rebuilt for the changed ontology without losing old-label provenance.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
