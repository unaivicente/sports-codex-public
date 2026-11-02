# Ontology Package

Local ontology definitions and evolution helpers.

Ontology evolution is additive and versioned:

- call `evolve_ontology(...)`, `add_label(...)`, or `deprecate_label(...)` to
  produce a new ontology payload with a new `ontology_version`
- added labels are appended from data definitions, not embedded in inference
  logic
- deprecated labels remain in `labels` and are recorded in `deprecated_labels`
  with a `replacement_label_id`
- the evolved payload keeps `previous_ontology_version` and an `evolution`
  block so older predictions can still be interpreted against their source
  ontology version

The helpers operate on local JSON-compatible dictionaries only. They do not use
cloud storage, remote inference, or external registries.

See the [implementation guide](../../docs/ML_WORKFLOWS.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
