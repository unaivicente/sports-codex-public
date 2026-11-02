# Labelling package

Explainable active-learning queue scoring is implemented in
[`active_learning.py`](active_learning.py).

`build_active_learning_queue(predictions=..., ontology=..., corrections=...)`
validates ontology-backed predictions and ranks records with low confidence,
multimodal disagreement, ontology transition conflicts, rare labels or frequent
corrections. Entries preserve source predictions, evidence, model and ontology
versions and each flag's scoring contribution. `build_active_learning_demo_inputs`
produces local fixtures that exercise the scoring rules.

This package does not implement general probabilistic label generation,
temporal smoothing, correction persistence or a complete reviewer trust-policy
service. The React UI only provides confirmation and relabelling; interval edit
semantics are defined separately by the contracts package.

See [learning workflows](../../docs/ML_WORKFLOWS.md),
[data contracts](../../docs/DATA_CONTRACTS.md) and
[implementation status](../../docs/STATUS.md).
