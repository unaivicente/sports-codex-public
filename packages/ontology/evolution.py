"""Local ontology evolution helpers.

These helpers produce a new ontology payload from an existing local definition.
They never mutate the source payload in place and never delete deprecated
labels; deprecations are recorded as mappings so old labels remain
interpretable.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Sequence

from packages.contracts import ContractValidationError, validate_ontology


class OntologyEvolutionError(ValueError):
    """Raised when an ontology evolution request is structurally unsafe."""


def evolve_ontology(
    ontology: Mapping[str, Any],
    *,
    ontology_version: str,
    labels_to_add: Sequence[Mapping[str, Any]] = (),
    deprecated_label_mappings: Sequence[Mapping[str, Any]] = (),
    created_at: str | None = None,
    change_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a new validated ontology version with additive changes.

    ``labels_to_add`` must contain full ontology label objects. Each
    ``deprecated_label_mappings`` entry must include ``label_id`` and
    ``replacement_label_id``. The deprecated label stays present in ``labels``
    and is marked with mapping metadata.
    """

    try:
        validate_ontology(ontology)
    except ContractValidationError as exc:
        raise OntologyEvolutionError(str(exc)) from exc

    if not ontology_version:
        raise OntologyEvolutionError("ontology_version must be a non-empty string")
    previous_version = str(ontology["ontology_version"])
    if ontology_version == previous_version:
        raise OntologyEvolutionError("ontology_version must change when evolving an ontology")

    evolved = deepcopy(dict(ontology))
    evolved["previous_ontology_version"] = previous_version
    evolved["ontology_version"] = ontology_version
    evolved["labels"] = deepcopy(list(ontology.get("labels", [])))
    evolved["deprecated_labels"] = deepcopy(list(ontology.get("deprecated_labels", [])))

    added_label_ids = _add_labels(evolved, labels_to_add)
    deprecated_label_ids = _deprecate_labels(
        evolved,
        deprecated_label_mappings,
        deprecated_in_version=ontology_version,
    )

    evolved["evolution"] = {
        "change_id": change_id or f"{previous_version}->{ontology_version}",
        "created_at": created_at or _utc_now(),
        "previous_ontology_version": previous_version,
        "ontology_version": ontology_version,
        "added_label_ids": added_label_ids,
        "deprecated_label_ids": deprecated_label_ids,
        "reason": reason or "local ontology evolution",
        "local_first": True,
    }

    try:
        validate_ontology(evolved)
    except ContractValidationError as exc:
        raise OntologyEvolutionError(str(exc)) from exc
    return evolved


def add_label(
    ontology: Mapping[str, Any],
    *,
    ontology_version: str,
    label: Mapping[str, Any],
    created_at: str | None = None,
    change_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a new ontology version with one added label."""

    return evolve_ontology(
        ontology,
        ontology_version=ontology_version,
        labels_to_add=(label,),
        created_at=created_at,
        change_id=change_id,
        reason=reason,
    )


def deprecate_label(
    ontology: Mapping[str, Any],
    *,
    ontology_version: str,
    label_id: str,
    replacement_label_id: str,
    reason: str | None = None,
    created_at: str | None = None,
    change_id: str | None = None,
) -> dict[str, Any]:
    """Return a new ontology version with one deprecated label mapping."""

    mapping: dict[str, Any] = {
        "label_id": label_id,
        "replacement_label_id": replacement_label_id,
    }
    if reason:
        mapping["reason"] = reason
    return evolve_ontology(
        ontology,
        ontology_version=ontology_version,
        deprecated_label_mappings=(mapping,),
        created_at=created_at,
        change_id=change_id,
        reason=reason,
    )


def deprecated_label_map(ontology: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return deprecated-label mappings keyed by deprecated label id."""

    mappings: dict[str, dict[str, Any]] = {}
    for mapping in ontology.get("deprecated_labels", []):
        if not isinstance(mapping, Mapping):
            continue
        label_id = mapping.get("label_id")
        if isinstance(label_id, str) and label_id:
            mappings[label_id] = dict(mapping)
    return mappings


def active_labels(ontology: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return ontology labels that are not deprecated in the current version."""

    deprecated_ids = set(deprecated_label_map(ontology))
    return [
        dict(label)
        for label in ontology.get("labels", [])
        if isinstance(label, Mapping)
        and isinstance(label.get("label_id"), str)
        and label["label_id"] not in deprecated_ids
    ]


def resolve_label_reference(
    ontology: Mapping[str, Any],
    label_id: str,
) -> dict[str, Any]:
    """Resolve a label against an ontology, including deprecation metadata."""

    labels = {
        label["label_id"]: dict(label)
        for label in ontology.get("labels", [])
        if isinstance(label, Mapping) and isinstance(label.get("label_id"), str)
    }
    try:
        label = labels[label_id]
    except KeyError as exc:
        raise OntologyEvolutionError(f"unknown ontology label {label_id!r}") from exc

    mapping = deprecated_label_map(ontology).get(label_id)
    if mapping is None:
        return {"label": label, "deprecated": False, "replacement_label": None}

    replacement_id = mapping["replacement_label_id"]
    replacement = labels.get(replacement_id)
    return {
        "label": label,
        "deprecated": True,
        "replacement_label": replacement,
        "deprecated_label_mapping": mapping,
    }


def _add_labels(evolved: dict[str, Any], labels_to_add: Sequence[Mapping[str, Any]]) -> list[str]:
    added_label_ids: list[str] = []
    label_ids = _label_ids(evolved["labels"])

    for index, label in enumerate(labels_to_add):
        if not isinstance(label, Mapping):
            raise OntologyEvolutionError(f"labels_to_add[{index}] must be an object")
        label_id = label.get("label_id")
        if not isinstance(label_id, str) or not label_id:
            raise OntologyEvolutionError(f"labels_to_add[{index}].label_id must be a non-empty string")
        if label_id in label_ids:
            raise OntologyEvolutionError(f"label {label_id!r} already exists")
        evolved["labels"].append(deepcopy(dict(label)))
        label_ids.add(label_id)
        added_label_ids.append(label_id)

    return added_label_ids


def _deprecate_labels(
    evolved: dict[str, Any],
    mappings_to_add: Sequence[Mapping[str, Any]],
    *,
    deprecated_in_version: str,
) -> list[str]:
    deprecated_label_ids: list[str] = []
    label_by_id = _label_by_id(evolved["labels"])
    existing_mappings = deprecated_label_map(evolved)

    for index, mapping in enumerate(mappings_to_add):
        if not isinstance(mapping, Mapping):
            raise OntologyEvolutionError(f"deprecated_label_mappings[{index}] must be an object")
        label_id = mapping.get("label_id")
        replacement_id = mapping.get("replacement_label_id")
        if not isinstance(label_id, str) or not label_id:
            raise OntologyEvolutionError(
                f"deprecated_label_mappings[{index}].label_id must be a non-empty string"
            )
        if not isinstance(replacement_id, str) or not replacement_id:
            raise OntologyEvolutionError(
                f"deprecated_label_mappings[{index}].replacement_label_id must be a non-empty string"
            )
        if label_id == replacement_id:
            raise OntologyEvolutionError(f"deprecated label {label_id!r} cannot map to itself")
        if label_id not in label_by_id:
            raise OntologyEvolutionError(f"deprecated label {label_id!r} must remain in labels")
        if replacement_id not in label_by_id:
            raise OntologyEvolutionError(f"replacement label {replacement_id!r} must exist in labels")
        if label_id in existing_mappings:
            raise OntologyEvolutionError(f"deprecated label {label_id!r} is already mapped")
        if replacement_id in existing_mappings:
            raise OntologyEvolutionError(
                f"replacement label {replacement_id!r} is itself deprecated"
            )

        stored_mapping = {
            "label_id": label_id,
            "replacement_label_id": replacement_id,
            "deprecated_in_version": deprecated_in_version,
        }
        for optional_field in ("reason", "migration_note"):
            value = mapping.get(optional_field)
            if isinstance(value, str) and value:
                stored_mapping[optional_field] = value
        evolved["deprecated_labels"].append(stored_mapping)
        label_by_id[label_id]["deprecated"] = True
        label_by_id[label_id]["replacement_label_id"] = replacement_id
        label_by_id[label_id]["deprecated_in_version"] = deprecated_in_version
        existing_mappings[label_id] = stored_mapping
        deprecated_label_ids.append(label_id)

    return deprecated_label_ids


def _label_by_id(labels: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for label in labels:
        if not isinstance(label, Mapping):
            continue
        label_id = label.get("label_id")
        if not isinstance(label_id, str):
            continue
        by_id[label_id] = label if isinstance(label, dict) else dict(label)
    return by_id


def _label_ids(labels: Iterable[Mapping[str, Any]]) -> set[str]:
    return set(_label_by_id(labels))


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
