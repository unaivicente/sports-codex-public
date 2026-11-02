"""Validation helpers for shared local data contracts.

The JSON Schema files are the portable contract surface. These helpers provide
the backend with dependency-free runtime validation for the same payload shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .version import CONTRACT_VERSION

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

SCHEMA_FILES = {
    "ontology": "ontology.schema.json",
    "evidence": "evidence.schema.json",
    "prediction": "prediction.schema.json",
    "human_correction": "human_correction.schema.json",
    "training_dataset_record": "training_dataset_record.schema.json",
}


class ContractValidationError(ValueError):
    """Raised when a payload does not satisfy the shared contracts."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def contract_metadata() -> dict[str, str]:
    """Return metadata that API responses should expose."""

    return {"contract_version": CONTRACT_VERSION}


def load_schema(name: str) -> dict[str, Any]:
    """Load one of the bundled JSON Schema definitions by logical name."""

    try:
        schema_file = SCHEMA_FILES[name]
    except KeyError as exc:
        valid_names = ", ".join(sorted(SCHEMA_FILES))
        raise KeyError(f"unknown contract schema {name!r}; expected one of {valid_names}") from exc

    with (SCHEMA_DIR / schema_file).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_evidence(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    errors: list[str] = []
    _validate_evidence_shape(payload, "evidence", errors)
    _raise_if_errors(errors)
    return payload


def validate_ontology(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    errors: list[str] = []
    _require_mapping(payload, "ontology", errors)

    _require_nonempty_string(payload, "ontology_id", "ontology", errors)
    _require_nonempty_string(payload, "ontology_version", "ontology", errors)
    labels = _require_list(payload, "labels", "ontology", errors, min_items=1)

    label_ids: set[str] = set()
    for index, label in enumerate(labels):
        path = f"ontology.labels[{index}]"
        _require_mapping(label, path, errors)
        _require_nonempty_string(label, "label_id", path, errors)
        _require_nonempty_string(label, "label_type", path, errors)
        _require_nonempty_string(label, "display_name", path, errors)
        if isinstance(label, Mapping):
            label_id = label.get("label_id")
            if isinstance(label_id, str):
                if label_id in label_ids:
                    errors.append(f"{path}.label_id duplicates {label_id!r}")
                label_ids.add(label_id)
            deprecated = label.get("deprecated")
            if deprecated is not None and not isinstance(deprecated, bool):
                errors.append(f"{path}.deprecated must be a boolean when present")

    for index, rule in enumerate(payload.get("transition_rules", [])):
        path = f"ontology.transition_rules[{index}]"
        _require_mapping(rule, path, errors)
        _require_nonempty_string(rule, "from_label", path, errors)
        _require_nonempty_string(rule, "to_label", path, errors)
        _require_nonempty_string(rule, "rule_type", path, errors)
        if isinstance(rule, Mapping):
            for field in ("from_label", "to_label"):
                value = rule.get(field)
                if isinstance(value, str) and value not in label_ids:
                    errors.append(f"{path}.{field} references unknown label {value!r}")

    deprecated_labels_payload = payload.get("deprecated_labels", [])
    if deprecated_labels_payload is None:
        deprecated_labels_payload = []
    if not isinstance(deprecated_labels_payload, list):
        errors.append("ontology.deprecated_labels must be a list")
        deprecated_labels_payload = []

    deprecated_label_ids: set[str] = set()
    for index, mapping in enumerate(deprecated_labels_payload):
        path = f"ontology.deprecated_labels[{index}]"
        _require_mapping(mapping, path, errors)
        label_id = _require_nonempty_string(mapping, "label_id", path, errors)
        replacement_label_id = _require_nonempty_string(
            mapping,
            "replacement_label_id",
            path,
            errors,
        )
        _require_nonempty_string(mapping, "deprecated_in_version", path, errors)
        if not isinstance(mapping, Mapping):
            continue
        if isinstance(label_id, str):
            if label_id in deprecated_label_ids:
                errors.append(f"{path}.label_id duplicates deprecated mapping for {label_id!r}")
            deprecated_label_ids.add(label_id)
            if label_id not in label_ids:
                errors.append(f"{path}.label_id references unknown label {label_id!r}")
        if isinstance(replacement_label_id, str):
            if replacement_label_id not in label_ids:
                errors.append(
                    f"{path}.replacement_label_id references unknown label {replacement_label_id!r}"
                )
            if replacement_label_id == label_id:
                errors.append(f"{path}.replacement_label_id must not match label_id")

    for index, label in enumerate(labels):
        if not isinstance(label, Mapping):
            continue
        path = f"ontology.labels[{index}]"
        replacement_label_id = label.get("replacement_label_id")
        if isinstance(replacement_label_id, str) and replacement_label_id not in label_ids:
            errors.append(
                f"{path}.replacement_label_id references unknown label {replacement_label_id!r}"
            )

    _raise_if_errors(errors)
    return payload


def validate_prediction(
    payload: Mapping[str, Any],
    *,
    ontology: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    errors: list[str] = []
    _validate_prediction_shape(payload, "prediction", errors)

    if ontology is not None and isinstance(payload, Mapping):
        label_ids, ontology_version = _ontology_index(ontology, errors)
        label = payload.get("label")
        if isinstance(label, str) and label not in label_ids:
            errors.append(f"prediction.label references unknown ontology label {label!r}")
        _validate_ontology_version(payload, "prediction", ontology_version, errors)

    _raise_if_errors(errors)
    return payload


def validate_human_correction(
    payload: Mapping[str, Any],
    *,
    ontology: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    errors: list[str] = []
    _require_mapping(payload, "human_correction", errors)

    for field in (
        "correction_id",
        "video_id",
        "ontology_version",
        "learning_mode",
        "reviewer_id",
        "reviewer_role",
        "review_status",
        "created_at",
    ):
        _require_nonempty_string(payload, field, "human_correction", errors)

    correction_type = _require_enum(
        payload,
        "correction_type",
        "human_correction",
        {"confirm", "modify", "delete", "add", "ontology_gap"},
        errors,
    )
    edit_operation = _require_enum(
        payload,
        "edit_operation",
        "human_correction",
        {"none", "split", "merge", "relabel", "boundary_adjust"},
        errors,
    )
    _require_enum(payload, "learning_mode", "human_correction", {"training", "soft"}, errors)
    _require_enum(
        payload,
        "reviewer_role",
        "human_correction",
        {"internal", "external", "admin", "unknown"},
        errors,
    )
    review_status = _require_enum(
        payload,
        "review_status",
        "human_correction",
        {"pending", "accepted", "rejected", "needs_review"},
        errors,
    )
    _require_number(payload, "reviewer_confidence", "human_correction", errors, minimum=0, maximum=1)
    trust_weight = _require_number(payload, "trust_weight", "human_correction", errors, minimum=0, maximum=1)

    target_interval = payload.get("target_interval")
    source_ids = _validate_interval(
        target_interval,
        "human_correction.target_interval",
        errors,
        require_source_ids=True,
    )

    source_predictions = _require_list(payload, "source_predictions", "human_correction", errors)
    source_prediction_ids: set[str] = set()
    for index, prediction in enumerate(source_predictions):
        path = f"human_correction.source_predictions[{index}]"
        _validate_prediction_shape(prediction, path, errors)
        if isinstance(prediction, Mapping):
            prediction_id = prediction.get("prediction_id")
            if isinstance(prediction_id, str):
                source_prediction_ids.add(prediction_id)

    primary_id = payload.get("primary_source_prediction_id")
    if primary_id is not None and not isinstance(primary_id, str):
        errors.append("human_correction.primary_source_prediction_id must be a string or null")

    source_free = correction_type == "add" or (correction_type == "ontology_gap" and not source_predictions)
    if source_free:
        if source_ids:
            errors.append("source-free corrections must not include target source_prediction_ids")
        if source_predictions:
            errors.append("source-free corrections must not include source_predictions")
        if primary_id is not None:
            errors.append("source-free corrections must have primary_source_prediction_id = null")
    else:
        if not source_ids:
            errors.append("source-based corrections must include target source_prediction_ids")
        if not source_predictions:
            errors.append("source-based corrections must include source_predictions")
        if source_ids and source_prediction_ids and source_ids != source_prediction_ids:
            errors.append("target source_prediction_ids must match source_predictions snapshots")
        if isinstance(primary_id, str) and source_prediction_ids and primary_id not in source_prediction_ids:
            errors.append("primary_source_prediction_id must reference a source prediction snapshot")

    corrected_intervals = _require_list(payload, "corrected_intervals", "human_correction", errors)
    _validate_corrected_intervals(
        corrected_intervals,
        correction_type,
        errors,
        ontology=ontology,
    )

    evidence_snapshot = _require_list(payload, "evidence_snapshot", "human_correction", errors)
    for index, item in enumerate(evidence_snapshot):
        _validate_evidence_shape(item, f"human_correction.evidence_snapshot[{index}]", errors)

    _validate_correction_semantics(
        correction_type,
        edit_operation,
        corrected_intervals,
        source_predictions,
        errors,
    )

    if isinstance(review_status, str) and review_status != "accepted" and trust_weight not in (None, 0):
        errors.append("human_correction.trust_weight must be 0 unless review_status is accepted")
    if correction_type == "ontology_gap" and trust_weight not in (None, 0):
        errors.append("ontology_gap corrections must have trust_weight = 0")

    if ontology is not None and isinstance(payload, Mapping):
        _, ontology_version = _ontology_index(ontology, errors)
        _validate_ontology_version(payload, "human_correction", ontology_version, errors)

    _raise_if_errors(errors)
    return payload


def validate_training_dataset_record(
    payload: Mapping[str, Any],
    *,
    ontology: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    errors: list[str] = []
    _require_mapping(payload, "training_dataset_record", errors)

    for field in (
        "training_example_id",
        "dataset_version",
        "correction_id",
        "video_id",
        "sport",
        "label",
        "correction_type",
        "edit_operation",
        "learning_mode",
        "ontology_version",
    ):
        _require_nonempty_string(payload, field, "training_dataset_record", errors)

    _require_enum(
        payload,
        "source",
        "training_dataset_record",
        {"confirmed", "corrected", "human_added"},
        errors,
    )
    _require_enum(
        payload,
        "correction_type",
        "training_dataset_record",
        {"confirm", "modify", "add"},
        errors,
    )
    _require_enum(
        payload,
        "edit_operation",
        "training_dataset_record",
        {"none", "split", "merge", "relabel", "boundary_adjust"},
        errors,
    )
    _require_enum(
        payload,
        "learning_mode",
        "training_dataset_record",
        {"training", "soft"},
        errors,
    )
    _require_enum(
        payload,
        "split",
        "training_dataset_record",
        {"train", "validation", "test"},
        errors,
    )
    _require_number(payload, "interval_start", "training_dataset_record", errors, minimum=0)
    _require_number(payload, "interval_end", "training_dataset_record", errors, minimum=0)
    _require_nonempty_string(payload, "timebase", "training_dataset_record", errors)
    if (
        isinstance(payload, Mapping)
        and isinstance(payload.get("interval_start"), (int, float))
        and isinstance(payload.get("interval_end"), (int, float))
        and payload["interval_start"] >= payload["interval_end"]
    ):
        errors.append("training_dataset_record.interval_start must be less than interval_end")
    _require_number(payload, "trust_weight", "training_dataset_record", errors, minimum=0, maximum=1)

    for field in ("source_prediction_ids", "source_model_versions", "source_ontology_versions"):
        values = _require_list(payload, field, "training_dataset_record", errors)
        for index, value in enumerate(values):
            if not isinstance(value, str) or not value:
                errors.append(f"training_dataset_record.{field}[{index}] must be a non-empty string")

    evidence_snapshot = _require_list(payload, "evidence_snapshot", "training_dataset_record", errors)
    for index, item in enumerate(evidence_snapshot):
        _validate_evidence_shape(item, f"training_dataset_record.evidence_snapshot[{index}]", errors)

    if ontology is not None and isinstance(payload, Mapping):
        label_ids, ontology_version = _ontology_index(ontology, errors)
        label = payload.get("label")
        if isinstance(label, str) and label not in label_ids:
            errors.append(f"training_dataset_record.label references unknown ontology label {label!r}")
        _validate_ontology_version(payload, "training_dataset_record", ontology_version, errors)

    _raise_if_errors(errors)
    return payload


def _validate_prediction_shape(payload: Any, path: str, errors: list[str]) -> None:
    _require_mapping(payload, path, errors)
    if not isinstance(payload, Mapping):
        return

    for field in (
        "prediction_id",
        "video_id",
        "timebase",
        "label",
        "model_version",
        "ontology_version",
        "created_at",
    ):
        _require_nonempty_string(payload, field, path, errors)
    _require_number(payload, "timestamp", path, errors, minimum=0)
    _require_number(payload, "interval_start", path, errors, minimum=0)
    _require_number(payload, "interval_end", path, errors, minimum=0)
    _require_number(payload, "duration_seconds", path, errors, minimum=1, maximum=1)
    _require_number(payload, "confidence", path, errors, minimum=0, maximum=1)

    if (
        isinstance(payload.get("interval_start"), (int, float))
        and isinstance(payload.get("interval_end"), (int, float))
        and payload["interval_start"] >= payload["interval_end"]
    ):
        errors.append(f"{path}.interval_start must be less than interval_end")
    if (
        isinstance(payload.get("interval_start"), (int, float))
        and isinstance(payload.get("interval_end"), (int, float))
        and isinstance(payload.get("duration_seconds"), (int, float))
        and abs(
            (payload["interval_end"] - payload["interval_start"]) - payload["duration_seconds"]
        )
        > 1e-9
    ):
        errors.append(f"{path}.duration_seconds must match interval_end - interval_start")

    evidence = _require_list(payload, "evidence", path, errors, min_items=1)
    for index, item in enumerate(evidence):
        _validate_evidence_shape(item, f"{path}.evidence[{index}]", errors)


def _validate_evidence_shape(payload: Any, path: str, errors: list[str]) -> None:
    _require_mapping(payload, path, errors)
    if not isinstance(payload, Mapping):
        return

    for field in ("evidence_id", "modality", "type", "source_model_version"):
        _require_nonempty_string(payload, field, path, errors)
    if "value" not in payload:
        errors.append(f"{path}.value is required")
    _require_number(payload, "timestamp", path, errors, minimum=0)
    _require_number(payload, "confidence", path, errors, minimum=0, maximum=1)


def _validate_interval(
    payload: Any,
    path: str,
    errors: list[str],
    *,
    require_source_ids: bool = False,
) -> set[str]:
    _require_mapping(payload, path, errors)
    if not isinstance(payload, Mapping):
        return set()

    _require_number(payload, "interval_start", path, errors, minimum=0)
    _require_number(payload, "interval_end", path, errors, minimum=0)
    _require_nonempty_string(payload, "timebase", path, errors)
    if (
        isinstance(payload.get("interval_start"), (int, float))
        and isinstance(payload.get("interval_end"), (int, float))
        and payload["interval_start"] >= payload["interval_end"]
    ):
        errors.append(f"{path}.interval_start must be less than interval_end")

    source_ids: set[str] = set()
    if require_source_ids:
        values = _require_list(payload, "source_prediction_ids", path, errors)
        for index, value in enumerate(values):
            if not isinstance(value, str) or not value:
                errors.append(f"{path}.source_prediction_ids[{index}] must be a non-empty string")
            else:
                source_ids.add(value)
    return source_ids


def _validate_corrected_intervals(
    intervals: list[Any],
    correction_type: str | None,
    errors: list[str],
    *,
    ontology: Mapping[str, Any] | None,
) -> None:
    label_ids: set[str] | None = None
    ontology_version: str | None = None
    if ontology is not None:
        label_ids, ontology_version = _ontology_index(ontology, errors)

    previous_end: int | float | None = None
    for index, interval in enumerate(intervals):
        path = f"human_correction.corrected_intervals[{index}]"
        _validate_interval(interval, path, errors)
        if not isinstance(interval, Mapping):
            continue

        _require_number(interval, "reviewer_confidence", path, errors, minimum=0, maximum=1)
        _require_nonempty_string(interval, "ontology_version", path, errors)
        evidence_refs = _require_list(interval, "evidence_refs", path, errors)
        for ref_index, ref in enumerate(evidence_refs):
            if not isinstance(ref, str) or not ref:
                errors.append(f"{path}.evidence_refs[{ref_index}] must be a non-empty string")

        label = interval.get("label")
        if correction_type == "ontology_gap":
            if label is not None:
                errors.append(f"{path}.label must be null for ontology_gap corrections")
        elif not isinstance(label, str) or not label:
            errors.append(f"{path}.label must be a non-empty ontology label")
        elif label_ids is not None and label not in label_ids:
            errors.append(f"{path}.label references unknown ontology label {label!r}")

        if ontology_version is not None:
            _validate_ontology_version(interval, path, ontology_version, errors)

        start = interval.get("interval_start")
        end = interval.get("interval_end")
        if isinstance(start, (int, float)) and previous_end is not None and start < previous_end:
            errors.append("human_correction.corrected_intervals must be sorted and non-overlapping")
        if isinstance(end, (int, float)):
            previous_end = end


def _validate_correction_semantics(
    correction_type: str | None,
    edit_operation: str | None,
    corrected_intervals: list[Any],
    source_predictions: list[Any],
    errors: list[str],
) -> None:
    if correction_type == "confirm" and edit_operation != "none":
        errors.append("confirm corrections must use edit_operation = none")
    if correction_type == "add" and source_predictions:
        errors.append("add corrections must not include source prediction snapshots")
    if correction_type in {"confirm", "modify", "add"} and not corrected_intervals:
        errors.append(f"{correction_type} corrections must include corrected_intervals")
    if correction_type == "delete" and corrected_intervals:
        errors.append("delete corrections must not include positive corrected_intervals")
    if edit_operation == "split" and len(corrected_intervals) < 2:
        errors.append("split edit_operation requires at least two corrected_intervals")
    if edit_operation == "merge" and len(source_predictions) < 2:
        errors.append("merge edit_operation requires at least two source_predictions")
    if edit_operation == "merge" and len(corrected_intervals) != 1:
        errors.append("merge edit_operation requires exactly one corrected_interval")


def _ontology_index(ontology: Mapping[str, Any], errors: list[str]) -> tuple[set[str], str | None]:
    try:
        validate_ontology(ontology)
    except ContractValidationError as exc:
        errors.extend(f"ontology reference: {error}" for error in exc.errors)
        return set(), None

    labels = ontology.get("labels", [])
    label_ids = {
        label.get("label_id")
        for label in labels
        if isinstance(label, Mapping) and isinstance(label.get("label_id"), str)
    }
    version = ontology.get("ontology_version")
    return label_ids, version if isinstance(version, str) else None


def _validate_ontology_version(
    payload: Mapping[str, Any],
    path: str,
    ontology_version: str | None,
    errors: list[str],
) -> None:
    if ontology_version is None:
        return
    value = payload.get("ontology_version")
    if isinstance(value, str) and value != ontology_version:
        errors.append(f"{path}.ontology_version {value!r} does not match ontology {ontology_version!r}")


def _require_mapping(payload: Any, path: str, errors: list[str]) -> None:
    if not isinstance(payload, Mapping):
        errors.append(f"{path} must be an object")


def _require_nonempty_string(
    payload: Mapping[str, Any],
    field: str,
    path: str,
    errors: list[str],
) -> str | None:
    value = payload.get(field) if isinstance(payload, Mapping) else None
    if not isinstance(value, str) or not value:
        errors.append(f"{path}.{field} must be a non-empty string")
        return None
    return value


def _require_number(
    payload: Mapping[str, Any],
    field: str,
    path: str,
    errors: list[str],
    *,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
) -> int | float | None:
    value = payload.get(field) if isinstance(payload, Mapping) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path}.{field} must be a number")
        return None
    if minimum is not None and value < minimum:
        errors.append(f"{path}.{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{path}.{field} must be <= {maximum}")
    return value


def _require_list(
    payload: Mapping[str, Any],
    field: str,
    path: str,
    errors: list[str],
    *,
    min_items: int = 0,
) -> list[Any]:
    value = payload.get(field) if isinstance(payload, Mapping) else None
    if not isinstance(value, list):
        errors.append(f"{path}.{field} must be a list")
        return []
    if len(value) < min_items:
        errors.append(f"{path}.{field} must contain at least {min_items} item(s)")
    return value


def _require_enum(
    payload: Mapping[str, Any],
    field: str,
    path: str,
    values: set[str],
    errors: list[str],
) -> str | None:
    value = payload.get(field) if isinstance(payload, Mapping) else None
    if value not in values:
        expected = ", ".join(sorted(values))
        errors.append(f"{path}.{field} must be one of: {expected}")
        return None
    return value if isinstance(value, str) else None


def _raise_if_errors(errors: list[str]) -> None:
    if errors:
        raise ContractValidationError(errors)
