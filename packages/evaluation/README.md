# Evaluation Package

Local model evaluation and promotion-gating harness.

The harness compares a current model run with a candidate model run against the
same ontology-backed reference set. It computes:

- per-label precision, recall, and F1
- temporal boundary accuracy
- calibration expected calibration error
- false positives on rare ontology event labels
- inference cost deltas
- regressions across existing sport and ontology cohorts

The package is local-first and side-effect free. It does not call remote
inference, use cloud storage, mutate the local model registry, or automatically
promote models.

```sh
python -m packages.evaluation.model_evaluation evaluation_input.json \
  --output-path data/evaluation/model_evaluation_report.json
```

The input JSON contains `ontologies`, `references`, and `current`/`candidate`
prediction runs. Prediction payloads are validated against the shared prediction
contract and supplied ontology definitions before metrics are calculated.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
