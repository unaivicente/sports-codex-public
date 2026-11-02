"""Active-learning review queue scoring.

The scorer is intentionally local and data-driven. It reads ontology labels and
transition rules from the supplied ontology payload, then ranks existing
prediction records for human review without embedding sport-specific labels.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from packages.contracts import validate_ontology, validate_prediction
from packages.ontology import active_labels

LOW_CONFIDENCE_FLAG = "low_confidence"
MULTIMODAL_DISAGREEMENT_FLAG = "multimodal_disagreement"
ONTOLOGY_TRANSITION_CONFLICT_FLAG = "ontology_transition_conflict"
RARE_LABEL_FLAG = "rare_label"
FREQUENT_CORRECTION_FLAG = "frequent_correction"

FLAG_WEIGHTS = {
    LOW_CONFIDENCE_FLAG: 0.24,
    MULTIMODAL_DISAGREEMENT_FLAG: 0.26,
    ONTOLOGY_TRANSITION_CONFLICT_FLAG: 0.22,
    RARE_LABEL_FLAG: 0.12,
    FREQUENT_CORRECTION_FLAG: 0.20,
}

DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55
DEFAULT_RARE_LABEL_MAX_COUNT = 1
DEFAULT_RARE_LABEL_MAX_FREQUENCY = 0.20
DEFAULT_FREQUENT_CORRECTION_MIN_COUNT = 2


def build_active_learning_queue(
    *,
    predictions: Iterable[Mapping[str, Any]],
    ontology: Mapping[str, Any],
    corrections: Iterable[Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
    low_confidence_threshold: float | None = None,
    rare_label_max_count: int = DEFAULT_RARE_LABEL_MAX_COUNT,
    rare_label_max_frequency: float = DEFAULT_RARE_LABEL_MAX_FREQUENCY,
    frequent_correction_min_count: int = DEFAULT_FREQUENT_CORRECTION_MIN_COUNT,
) -> dict[str, Any]:
    """Rank prediction segments by expected learning value.

    Queue entries preserve the source prediction snapshot and expose each
    contributing review flag with its scoring evidence.
    """

    validate_ontology(ontology)
    ontology_labels = {
        label["label_id"]: label for label in ontology.get("labels", []) if isinstance(label, Mapping)
    }
    threshold = _confidence_threshold(ontology, low_confidence_threshold)
    prediction_rows = [
        deepcopy(dict(prediction))
        for prediction in sorted(
            predictions,
            key=lambda item: (
                str(item.get("video_id", "")),
                _number(item.get("timestamp"), default=0),
                str(item.get("prediction_id", "")),
            ),
        )
    ]

    for prediction in prediction_rows:
        validate_prediction(prediction, ontology=ontology)

    label_counts = Counter(str(prediction["label"]) for prediction in prediction_rows)
    corrections_by_prediction = _corrections_by_source_prediction(corrections or [])
    previous_by_video: dict[str, Mapping[str, Any]] = {}
    queue_entries: list[dict[str, Any]] = []
    flag_counts: Counter[str] = Counter()

    for prediction in prediction_rows:
        prediction_id = str(prediction["prediction_id"])
        video_id = str(prediction["video_id"])
        reasons: list[dict[str, Any]] = []

        low_confidence_reason = _low_confidence_reason(prediction, threshold)
        if low_confidence_reason is not None:
            reasons.append(low_confidence_reason)

        disagreement_reason = _multimodal_disagreement_reason(prediction, ontology_labels)
        if disagreement_reason is not None:
            reasons.append(disagreement_reason)

        previous_prediction = previous_by_video.get(video_id)
        if previous_prediction is not None:
            transition_reason = _ontology_transition_reason(previous_prediction, prediction, ontology)
            if transition_reason is not None:
                reasons.append(transition_reason)
        previous_by_video[video_id] = prediction

        rare_label_reason = _rare_label_reason(
            prediction,
            label_counts=label_counts,
            total_predictions=len(prediction_rows),
            rare_label_max_count=rare_label_max_count,
            rare_label_max_frequency=rare_label_max_frequency,
        )
        if rare_label_reason is not None:
            reasons.append(rare_label_reason)

        frequent_correction_reason = _frequent_correction_reason(
            prediction,
            correction_refs=corrections_by_prediction.get(prediction_id, []),
            frequent_correction_min_count=frequent_correction_min_count,
        )
        if frequent_correction_reason is not None:
            reasons.append(frequent_correction_reason)

        if not reasons:
            continue

        reasons.sort(key=lambda reason: reason["learning_value_contribution"], reverse=True)
        for reason in reasons:
            flag_counts[reason["flag"]] += 1

        queue_entries.append(
            {
                "queue_entry_id": f"active-learning:{prediction_id}",
                "video_id": video_id,
                "timestamp": prediction["timestamp"],
                "interval_start": prediction.get("interval_start", prediction["timestamp"]),
                "interval_end": prediction.get("interval_end", prediction["timestamp"] + 1),
                "label": prediction["label"],
                "confidence": prediction["confidence"],
                "learning_value_score": round(
                    sum(reason["learning_value_contribution"] for reason in reasons),
                    4,
                ),
                "flags": [reason["flag"] for reason in reasons],
                "review_reasons": reasons,
                "source_prediction_id": prediction_id,
                "model_version": prediction["model_version"],
                "ontology_version": prediction["ontology_version"],
                "source_model_version": prediction["model_version"],
                "source_ontology_version": prediction["ontology_version"],
                "evidence": deepcopy(prediction["evidence"]),
                "source_prediction": deepcopy(prediction),
            }
        )

    queue_entries.sort(
        key=lambda entry: (
            entry["learning_value_score"],
            len(entry["flags"]),
            -_number(entry["timestamp"], default=0),
        ),
        reverse=True,
    )
    for index, entry in enumerate(queue_entries, start=1):
        entry["rank"] = index

    return {
        "generated_at": generated_at or _utc_now(),
        "ontology_id": ontology["ontology_id"],
        "ontology_version": ontology["ontology_version"],
        "model_versions": sorted({str(prediction["model_version"]) for prediction in prediction_rows}),
        "candidate_count": len(prediction_rows),
        "queued_count": len(queue_entries),
        "scoring": {
            "low_confidence_threshold": threshold,
            "rare_label_max_count": rare_label_max_count,
            "rare_label_max_frequency": rare_label_max_frequency,
            "frequent_correction_min_count": frequent_correction_min_count,
            "flag_weights": dict(FLAG_WEIGHTS),
        },
        "flag_counts": dict(sorted(flag_counts.items())),
        "queue": queue_entries,
    }


def build_active_learning_demo_inputs(
    ontology: Mapping[str, Any],
    *,
    video_id: str = "local-active-learning-demo",
    model_version: str = "mock-fusion-local-0.1.0",
    evidence_model_version: str = "mock-extractor-local-0.1.0",
    created_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build deterministic local inputs that exercise every queue flag."""

    validate_ontology(ontology)
    labels = active_labels(ontology)
    if not labels:
        raise ValueError(f"ontology {ontology['ontology_version']} has no active labels")
    primary = labels[0]
    secondary = labels[1] if len(labels) > 1 else labels[0]
    tertiary = labels[2] if len(labels) > 2 else labels[-1]
    timestamp = created_at or _utc_now()
    threshold = _confidence_threshold(ontology, None)

    predictions = [
        _demo_prediction(
            ontology=ontology,
            label=primary,
            timestamp=0,
            confidence=max(round(threshold - 0.18, 2), 0.05),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": primary},
        ),
        _demo_prediction(
            ontology=ontology,
            label=secondary,
            timestamp=1,
            confidence=min(round(threshold + 0.18, 2), 0.99),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": secondary, "audio": primary, "ocr": secondary},
        ),
        _demo_prediction(
            ontology=ontology,
            label=primary,
            timestamp=2,
            confidence=min(round(threshold + 0.20, 2), 0.99),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": primary},
        ),
        _demo_prediction(
            ontology=ontology,
            label=secondary,
            timestamp=3,
            confidence=min(round(threshold + 0.24, 2), 0.99),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": secondary},
        ),
        _demo_prediction(
            ontology=ontology,
            label=tertiary,
            timestamp=4,
            confidence=min(round(threshold + 0.28, 2), 0.99),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": tertiary},
        ),
        _demo_prediction(
            ontology=ontology,
            label=primary,
            timestamp=5,
            confidence=min(round(threshold + 0.22, 2), 0.99),
            video_id=video_id,
            model_version=model_version,
            evidence_model_version=evidence_model_version,
            created_at=timestamp,
            evidence_labels={"vision": primary},
        ),
    ]

    corrections = [
        _demo_correction(
            correction_id="active-learning-correction-1",
            source_prediction=predictions[2],
            corrected_label=secondary,
            reviewer_id="internal-reviewer-1",
            reviewer_role="internal",
            learning_mode="training",
            reviewer_confidence=0.88,
            trust_weight=0.85,
            created_at=timestamp,
        ),
        _demo_correction(
            correction_id="active-learning-correction-2",
            source_prediction=predictions[2],
            corrected_label=secondary,
            reviewer_id="external-reviewer-2",
            reviewer_role="external",
            learning_mode="soft",
            reviewer_confidence=0.64,
            trust_weight=0.30,
            created_at=timestamp,
        ),
    ]

    return predictions, corrections


def _low_confidence_reason(
    prediction: Mapping[str, Any],
    threshold: float,
) -> dict[str, Any] | None:
    confidence = _number(prediction.get("confidence"), default=0)
    if confidence >= threshold:
        return None

    severity = min((threshold - confidence) / max(threshold, 0.01), 1)
    return {
        "flag": LOW_CONFIDENCE_FLAG,
        "learning_value_contribution": round(FLAG_WEIGHTS[LOW_CONFIDENCE_FLAG] * severity, 4),
        "evidence": {
            "confidence": confidence,
            "threshold": threshold,
        },
    }


def _multimodal_disagreement_reason(
    prediction: Mapping[str, Any],
    ontology_labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    label_by_modality: dict[str, set[str]] = defaultdict(set)
    ontology_label_ids = set(ontology_labels)

    for evidence in prediction.get("evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        modality = evidence.get("modality")
        if not isinstance(modality, str) or not modality:
            continue
        evidence_label = _evidence_label(evidence, ontology_label_ids)
        if evidence_label is not None:
            label_by_modality[modality].add(evidence_label)

    modality_labels = {
        modality: sorted(labels) for modality, labels in label_by_modality.items() if labels
    }
    unique_labels = sorted({label for labels in modality_labels.values() for label in labels})
    if len(modality_labels) < 2 or len(unique_labels) < 2:
        return None

    return {
        "flag": MULTIMODAL_DISAGREEMENT_FLAG,
        "learning_value_contribution": FLAG_WEIGHTS[MULTIMODAL_DISAGREEMENT_FLAG],
        "evidence": {
            "modality_labels": modality_labels,
            "unique_ontology_labels": unique_labels,
        },
    }


def _ontology_transition_reason(
    previous_prediction: Mapping[str, Any],
    prediction: Mapping[str, Any],
    ontology: Mapping[str, Any],
) -> dict[str, Any] | None:
    from_label = str(previous_prediction["label"])
    to_label = str(prediction["label"])
    if from_label == to_label:
        return None

    rules = [rule for rule in ontology.get("transition_rules", []) if isinstance(rule, Mapping)]
    if not rules:
        return None

    gap_seconds = max(
        _number(prediction.get("interval_start", prediction.get("timestamp")), default=0)
        - _number(
            previous_prediction.get("interval_end", previous_prediction.get("timestamp")),
            default=0,
        ),
        0,
    )
    matching_rules = [
        rule
        for rule in rules
        if rule.get("from_label") == from_label and rule.get("to_label") == to_label
    ]

    if not matching_rules:
        return {
            "flag": ONTOLOGY_TRANSITION_CONFLICT_FLAG,
            "learning_value_contribution": FLAG_WEIGHTS[ONTOLOGY_TRANSITION_CONFLICT_FLAG],
            "evidence": {
                "from_prediction_id": previous_prediction["prediction_id"],
                "from_label": from_label,
                "to_prediction_id": prediction["prediction_id"],
                "to_label": to_label,
                "gap_seconds": gap_seconds,
                "conflict": "transition is not allowed by ontology",
                "ontology_version": ontology["ontology_version"],
            },
        }

    valid_rule = next(
        (rule for rule in matching_rules if _transition_timing_allows(rule, gap_seconds)),
        None,
    )
    if valid_rule is not None:
        return None

    return {
        "flag": ONTOLOGY_TRANSITION_CONFLICT_FLAG,
        "learning_value_contribution": FLAG_WEIGHTS[ONTOLOGY_TRANSITION_CONFLICT_FLAG],
        "evidence": {
            "from_prediction_id": previous_prediction["prediction_id"],
            "from_label": from_label,
            "to_prediction_id": prediction["prediction_id"],
            "to_label": to_label,
            "gap_seconds": gap_seconds,
            "conflict": "transition violates ontology timing constraints",
            "matching_rules": [dict(rule) for rule in matching_rules],
            "ontology_version": ontology["ontology_version"],
        },
    }


def _rare_label_reason(
    prediction: Mapping[str, Any],
    *,
    label_counts: Counter[str],
    total_predictions: int,
    rare_label_max_count: int,
    rare_label_max_frequency: float,
) -> dict[str, Any] | None:
    label = str(prediction["label"])
    count = label_counts[label]
    frequency = count / total_predictions if total_predictions else 0
    if count > rare_label_max_count and frequency > rare_label_max_frequency:
        return None

    return {
        "flag": RARE_LABEL_FLAG,
        "learning_value_contribution": FLAG_WEIGHTS[RARE_LABEL_FLAG],
        "evidence": {
            "label": label,
            "label_count": count,
            "candidate_count": total_predictions,
            "label_frequency": round(frequency, 4),
        },
    }


def _frequent_correction_reason(
    prediction: Mapping[str, Any],
    *,
    correction_refs: list[dict[str, Any]],
    frequent_correction_min_count: int,
) -> dict[str, Any] | None:
    if len(correction_refs) < frequent_correction_min_count:
        return None

    return {
        "flag": FREQUENT_CORRECTION_FLAG,
        "learning_value_contribution": FLAG_WEIGHTS[FREQUENT_CORRECTION_FLAG],
        "evidence": {
            "source_prediction_id": prediction["prediction_id"],
            "correction_count": len(correction_refs),
            "correction_ids": [correction["correction_id"] for correction in correction_refs],
            "learning_modes": sorted({correction["learning_mode"] for correction in correction_refs}),
            "review_statuses": sorted({correction["review_status"] for correction in correction_refs}),
            "source_model_versions": sorted(
                {
                    version
                    for correction in correction_refs
                    for version in correction["source_model_versions"]
                }
            ),
            "source_ontology_versions": sorted(
                {
                    version
                    for correction in correction_refs
                    for version in correction["source_ontology_versions"]
                }
            ),
        },
    }


def _corrections_by_source_prediction(
    corrections: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_prediction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for correction in corrections:
        if correction.get("correction_type") == "confirm":
            continue
        if correction.get("review_status") == "rejected":
            continue

        source_ids = _source_prediction_ids(correction)
        if not source_ids:
            continue

        source_predictions = [
            prediction
            for prediction in correction.get("source_predictions", [])
            if isinstance(prediction, Mapping)
        ]
        source_model_versions = sorted(
            {
                str(prediction.get("model_version"))
                for prediction in source_predictions
                if prediction.get("model_version")
            }
        )
        source_ontology_versions = sorted(
            {
                str(prediction.get("ontology_version"))
                for prediction in source_predictions
                if prediction.get("ontology_version")
            }
        )
        correction_ref = {
            "correction_id": str(correction.get("correction_id", "unknown-correction")),
            "correction_type": str(correction.get("correction_type", "unknown")),
            "learning_mode": str(correction.get("learning_mode", "unknown")),
            "review_status": str(correction.get("review_status", "unknown")),
            "reviewer_confidence": correction.get("reviewer_confidence"),
            "trust_weight": correction.get("trust_weight"),
            "source_model_versions": source_model_versions,
            "source_ontology_versions": source_ontology_versions,
        }
        for source_id in sorted(source_ids):
            by_prediction[source_id].append(correction_ref)
    return by_prediction


def _source_prediction_ids(correction: Mapping[str, Any]) -> set[str]:
    source_ids: set[str] = set()
    for field in ("source_prediction_id", "primary_source_prediction_id"):
        value = correction.get(field)
        if isinstance(value, str) and value:
            source_ids.add(value)

    target_interval = correction.get("target_interval")
    if isinstance(target_interval, Mapping):
        for value in target_interval.get("source_prediction_ids", []):
            if isinstance(value, str) and value:
                source_ids.add(value)

    for prediction in correction.get("source_predictions", []):
        if isinstance(prediction, Mapping):
            prediction_id = prediction.get("prediction_id")
            if isinstance(prediction_id, str) and prediction_id:
                source_ids.add(prediction_id)

    return source_ids


def _evidence_label(evidence: Mapping[str, Any], ontology_label_ids: set[str]) -> str | None:
    value = evidence.get("value")
    if isinstance(value, Mapping):
        for key in (
            "ontology_label_id",
            "label_id",
            "label",
            "top_label",
            "top_class",
            "predicted_label",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate in ontology_label_ids:
                return candidate

    for key in ("ontology_label_id", "label_id", "label"):
        candidate = evidence.get(key)
        if isinstance(candidate, str) and candidate in ontology_label_ids:
            return candidate

    return None


def _transition_timing_allows(rule: Mapping[str, Any], gap_seconds: float) -> bool:
    min_gap = rule.get("min_gap_seconds")
    max_gap = rule.get("max_gap_seconds")

    if isinstance(min_gap, (int, float)) and gap_seconds < min_gap:
        return False
    if isinstance(max_gap, (int, float)) and gap_seconds > max_gap:
        return False
    return True


def _confidence_threshold(
    ontology: Mapping[str, Any],
    explicit_threshold: float | None,
) -> float:
    if explicit_threshold is not None:
        return explicit_threshold

    thresholds = ontology.get("thresholds")
    if isinstance(thresholds, Mapping):
        default = thresholds.get("default_confidence")
        if isinstance(default, (int, float)):
            return float(default)

    return DEFAULT_LOW_CONFIDENCE_THRESHOLD


def _demo_prediction(
    *,
    ontology: Mapping[str, Any],
    label: Mapping[str, Any],
    timestamp: int,
    confidence: float,
    video_id: str,
    model_version: str,
    evidence_model_version: str,
    created_at: str,
    evidence_labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    label_id = str(label["label_id"])
    prediction_id = f"active-learning-prediction-{ontology['ontology_id']}-{video_id}-{timestamp}"
    evidence = [
        {
            "evidence_id": f"active-learning-evidence-{ontology['ontology_id']}-{timestamp}-{modality}",
            "modality": modality,
            "timestamp": timestamp,
            "type": "local_mock_signal",
            "value": {
                "ontology_label_id": evidence_label["label_id"],
                "label_type": evidence_label["label_type"],
                "ontology_version": ontology["ontology_version"],
            },
            "confidence": max(round(confidence - 0.05, 2), 0),
            "source_model_version": evidence_model_version,
        }
        for modality, evidence_label in evidence_labels.items()
    ]

    return {
        "prediction_id": prediction_id,
        "video_id": video_id,
        "timestamp": timestamp,
        "interval_start": timestamp,
        "interval_end": timestamp + 1,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": label_id,
        "confidence": confidence,
        "evidence": evidence,
        "model_version": model_version,
        "ontology_version": ontology["ontology_version"],
        "inference_config": {"source": "local_active_learning_demo", "ontology_driven": True},
        "post_correction_model_agreement": None,
        "confidence_delta": None,
        "created_at": created_at,
    }


def _demo_correction(
    *,
    correction_id: str,
    source_prediction: Mapping[str, Any],
    corrected_label: Mapping[str, Any],
    reviewer_id: str,
    reviewer_role: str,
    learning_mode: str,
    reviewer_confidence: float,
    trust_weight: float,
    created_at: str,
) -> dict[str, Any]:
    evidence_refs = [evidence["evidence_id"] for evidence in source_prediction["evidence"]]
    return {
        "correction_id": correction_id,
        "video_id": source_prediction["video_id"],
        "target_interval": {
            "interval_start": source_prediction["interval_start"],
            "interval_end": source_prediction["interval_end"],
            "timebase": source_prediction["timebase"],
            "source_prediction_ids": [source_prediction["prediction_id"]],
        },
        "corrected_intervals": [
            {
                "interval_start": source_prediction["interval_start"],
                "interval_end": source_prediction["interval_end"],
                "timebase": source_prediction["timebase"],
                "label": corrected_label["label_id"],
                "ontology_version": source_prediction["ontology_version"],
                "reviewer_confidence": reviewer_confidence,
                "evidence_refs": evidence_refs,
            }
        ],
        "correction_type": "modify",
        "edit_operation": "relabel",
        "source_predictions": [deepcopy(dict(source_prediction))],
        "primary_source_prediction_id": source_prediction["prediction_id"],
        "ontology_version": source_prediction["ontology_version"],
        "evidence_snapshot": deepcopy(source_prediction["evidence"]),
        "learning_mode": learning_mode,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "reviewer_confidence": reviewer_confidence,
        "trust_weight": trust_weight,
        "review_status": "accepted",
        "post_correction_model_agreement": 0.22,
        "confidence_delta": -0.28,
        "created_at": created_at,
    }


def _number(value: Any, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
