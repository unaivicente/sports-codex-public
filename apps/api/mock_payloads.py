"""Local API payload builders for the frontend shell."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from apps.api.contract_validation import api_response, health_response
from packages.contracts import (
    CONTRACT_VERSION,
    validate_human_correction,
    validate_ontology,
    validate_prediction,
)
from packages.labelling import build_active_learning_demo_inputs, build_active_learning_queue
from packages.ontology import active_labels, get_ontology, list_ontologies

MOCK_MODEL_VERSION = "mock-fusion-local-0.1.0"
MOCK_EVIDENCE_MODEL_VERSION = "mock-extractor-local-0.1.0"
MOCK_VIDEO_ID = "local-demo-video"


def build_health_payload() -> dict[str, str]:
    """Return API health metadata for local frontend status checks."""

    return health_response()


def build_ontology_payload() -> dict[str, Any]:
    """Return all local ontology definitions for frontend sport selection."""

    ontologies = list_ontologies()
    for ontology in ontologies:
        validate_ontology(ontology)

    return api_response(
        {
            "ontologies": ontologies,
            "default_ontology_id": ontologies[0]["ontology_id"],
        }
    )


def build_sports_payload() -> dict[str, Any]:
    """Return local sport options backed by ontology fixtures."""

    ontologies = list_ontologies()
    sports: dict[str, dict[str, Any]] = {}

    for ontology in ontologies:
        validate_ontology(ontology)
        sport_id = _sport_id_for_ontology(ontology)
        display_name = _sport_display_name_for_ontology(ontology)
        ontology["sport_id"] = sport_id
        ontology["sport_display_name"] = display_name

        sport = sports.setdefault(
            sport_id,
            {
                "sport_id": sport_id,
                "display_name": display_name,
                "ontologies": [],
            },
        )
        sport["ontologies"].append(ontology)

    sport_list = list(sports.values())
    default_sport = sport_list[0] if sport_list else None
    default_ontology = default_sport["ontologies"][0] if default_sport else None

    return api_response(
        {
            "sports": sport_list,
            "default_sport_id": default_sport["sport_id"] if default_sport else "",
            "default_ontology_id": default_ontology["ontology_id"] if default_ontology else "",
        }
    )


def build_feedback_quality_payload(ontology_id: str | None = None) -> dict[str, Any]:
    """Return deterministic local feedback quality aggregates for a dashboard."""

    ontology = get_ontology(ontology_id)
    validate_ontology(ontology)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    corrections = _build_feedback_quality_corrections(ontology)
    volume_by_mode = _correction_volume_by_mode(corrections)
    total_corrections = len(corrections)
    accepted_count = _count_where(corrections, "review_status", "accepted")
    rejected_count = _count_where(corrections, "review_status", "rejected")
    needs_review_count = _count_where(corrections, "review_status", "needs_review")

    return api_response(
        {
            "dashboard": {
                "generated_at": generated_at,
                "ontology_id": ontology["ontology_id"],
                "ontology_version": ontology["ontology_version"],
                "model_version": MOCK_MODEL_VERSION,
                "correction_volume_by_mode": volume_by_mode,
                "correction_acceptance_rate": {
                    "accepted_count": accepted_count,
                    "total_corrections": total_corrections,
                    "rejected_count": rejected_count,
                    "needs_review_count": needs_review_count,
                    "acceptance_rate": round(accepted_count / total_corrections, 2),
                },
                "high_disagreement_labels": _high_disagreement_labels(corrections, ontology),
                "reviewer_reliability_indicators": _reviewer_reliability_indicators(corrections),
                "soft_feedback_patterns": _soft_feedback_patterns(corrections, ontology),
            }
        }
    )


def build_active_learning_queue_payload(ontology_id: str | None = None) -> dict[str, Any]:
    """Return a ranked local active-learning review queue for an ontology."""

    ontology = get_ontology(ontology_id)
    validate_ontology(ontology)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    predictions, corrections = build_active_learning_demo_inputs(
        ontology,
        created_at=generated_at,
    )
    queue = build_active_learning_queue(
        predictions=predictions,
        corrections=corrections,
        ontology=ontology,
        generated_at=generated_at,
    )

    return api_response({"active_learning": queue})


def build_video_upload_payload(
    *,
    filename: str | None,
    content_type: str | None,
    byte_count: int,
) -> dict[str, Any]:
    """Accept local upload metadata without storing or processing video bytes."""

    safe_filename = filename or "selected-local-video"
    video_id = str(uuid5(NAMESPACE_URL, f"local-video:{safe_filename}:{byte_count}"))

    return api_response(
        {
            "video": {
                "video_id": video_id,
                "filename": safe_filename,
                "content_type": content_type or "application/octet-stream",
                "byte_count": byte_count,
                "status": "accepted_stub",
                "storage": "not_persisted",
                "processing": "not_started",
            }
        }
    )


def build_mock_predictions_payload(
    ontology_id: str | None = None,
    *,
    video_id: str | None = None,
) -> dict[str, Any]:
    """Return deterministic, contract-shaped mock predictions for an ontology."""

    ontology = get_ontology(ontology_id)
    validate_ontology(ontology)
    labels = active_labels(ontology)
    if not labels:
        raise ValueError(f"ontology {ontology['ontology_version']} has no active labels")
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    selected_video_id = video_id or MOCK_VIDEO_ID

    predictions = [
        _build_prediction(
            ontology=ontology,
            label=labels[index % len(labels)],
            timestamp=index * 8,
            confidence=round(0.72 + (index * 0.06), 2),
            created_at=created_at,
            video_id=selected_video_id,
        )
        for index in range(min(3, len(labels)))
    ]

    for prediction in predictions:
        validate_prediction(prediction, ontology=ontology)

    return api_response(
        {
            "video_id": selected_video_id,
            "ontology_id": ontology["ontology_id"],
            "ontology_version": ontology["ontology_version"],
            "model_version": MOCK_MODEL_VERSION,
            "predictions": predictions,
        }
    )


def build_correction_submission_payload(correction: dict[str, Any]) -> dict[str, Any]:
    """Validate and acknowledge a human correction without persistence."""

    ontology = _ontology_for_version(correction.get("ontology_version"))
    validate_human_correction(correction, ontology=ontology)
    source_predictions = correction.get("source_predictions", [])

    return api_response(
        {
            "accepted": True,
            "correction": correction,
            "preserved_source_prediction_ids": [
                prediction["prediction_id"] for prediction in source_predictions
            ],
            "source_model_versions": [
                prediction["model_version"] for prediction in source_predictions
            ],
            "source_ontology_versions": [
                prediction["ontology_version"] for prediction in source_predictions
            ],
        }
    )


def _build_prediction(
    *,
    ontology: dict[str, Any],
    label: dict[str, Any],
    timestamp: int,
    confidence: float,
    created_at: str,
    video_id: str,
) -> dict[str, Any]:
    label_id = label["label_id"]
    evidence_id = f"evidence-{ontology['ontology_id']}-{video_id}-{timestamp}"

    return {
        "prediction_id": f"prediction-{ontology['ontology_id']}-{video_id}-{timestamp}",
        "video_id": video_id,
        "timestamp": timestamp,
        "interval_start": timestamp,
        "interval_end": timestamp + 1,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": label_id,
        "confidence": confidence,
        "evidence": [
            {
                "evidence_id": evidence_id,
                "modality": "vision",
                "timestamp": timestamp,
                "type": "local_mock_signal",
                "value": {
                    "ontology_label_id": label_id,
                    "label_type": label["label_type"],
                },
                "confidence": max(round(confidence - 0.05, 2), 0),
                "source_model_version": MOCK_EVIDENCE_MODEL_VERSION,
            }
        ],
        "model_version": MOCK_MODEL_VERSION,
        "ontology_version": ontology["ontology_version"],
        "inference_config": {"source": "local_mock_api", "ontology_driven": True},
        "post_correction_model_agreement": None,
        "confidence_delta": None,
        "created_at": created_at,
    }


def _ontology_for_version(ontology_version: Any) -> dict[str, Any]:
    for ontology in list_ontologies():
        if ontology.get("ontology_version") == ontology_version:
            return ontology
    raise KeyError(f"unknown ontology_version {ontology_version!r}")


def _label_at(labels: list[dict[str, Any]], index: int) -> dict[str, Any]:
    return labels[index % len(labels)]


def _build_feedback_quality_corrections(ontology: dict[str, Any]) -> list[dict[str, Any]]:
    labels = active_labels(ontology)
    if not labels:
        raise ValueError(f"ontology {ontology['ontology_version']} has no active labels")
    primary_label = _label_at(labels, 0)
    secondary_label = _label_at(labels, 1)
    tertiary_label = _label_at(labels, 2)

    return [
        _feedback_correction("fq-1", primary_label, "training", "accepted", "internal-reviewer-1", "internal", 0.92, 0.90, 0.86, 0.03),
        _feedback_correction("fq-2", primary_label, "training", "accepted", "internal-reviewer-1", "internal", 0.88, 0.85, 0.78, 0.02),
        _feedback_correction("fq-3", secondary_label, "training", "accepted", "internal-reviewer-1", "internal", 0.90, 0.80, 0.70, -0.05),
        _feedback_correction("fq-4", secondary_label, "training", "accepted", "admin-reviewer-1", "admin", 0.94, 1.00, 0.82, 0.04),
        _feedback_correction("fq-5", tertiary_label, "training", "accepted", "internal-reviewer-1", "internal", 0.82, 0.75, 0.66, -0.10),
        _feedback_correction("fq-6", primary_label, "training", "needs_review", "internal-reviewer-1", "internal", 0.76, 0.00, 0.21, -0.34, contradiction_count=1),
        _feedback_correction("fq-7", secondary_label, "soft", "needs_review", "external-reviewer-2", "external", 0.60, 0.00, 0.18, -0.22, contradiction_count=1),
        _feedback_correction("fq-8", secondary_label, "soft", "needs_review", "external-reviewer-2", "external", 0.55, 0.00, 0.25, -0.25),
        _feedback_correction("fq-9", secondary_label, "soft", "needs_review", "external-reviewer-3", "external", 0.52, 0.00, 0.29, -0.20),
        _feedback_correction("fq-10", secondary_label, "soft", "accepted", "external-reviewer-2", "external", 0.65, 0.30, 0.64, -0.04),
        _feedback_correction("fq-11", primary_label, "soft", "accepted", "external-reviewer-2", "external", 0.62, 0.25, 0.58, -0.06),
        _feedback_correction("fq-12", tertiary_label, "soft", "accepted", "external-reviewer-3", "external", 0.72, 0.35, 0.60, -0.03),
        _feedback_correction("fq-13", tertiary_label, "soft", "needs_review", "external-reviewer-3", "external", 0.61, 0.00, 0.19, -0.31, correction_type="ontology_gap"),
        _feedback_correction("fq-14", primary_label, "soft", "rejected", "external-reviewer-2", "external", 0.40, 0.00, 0.14, -0.39, contradiction_count=1),
    ]


def _feedback_correction(
    correction_id: str,
    label: dict[str, Any],
    learning_mode: str,
    review_status: str,
    reviewer_id: str,
    reviewer_role: str,
    reviewer_confidence: float,
    trust_weight: float,
    model_agreement: float,
    confidence_delta: float,
    *,
    correction_type: str = "modify",
    contradiction_count: int = 0,
) -> dict[str, Any]:
    return {
        "correction_id": correction_id,
        "label": label["label_id"],
        "label_display_name": label.get("display_name", label["label_id"]),
        "label_type": label.get("label_type", "unknown"),
        "correction_type": correction_type,
        "learning_mode": learning_mode,
        "review_status": review_status,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "reviewer_confidence": reviewer_confidence,
        "trust_weight": trust_weight,
        "post_correction_model_agreement": model_agreement,
        "confidence_delta": confidence_delta,
        "source_model_version": MOCK_MODEL_VERSION,
        "contradiction_count": contradiction_count,
    }


def _correction_volume_by_mode(corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for learning_mode in ("training", "soft"):
        mode_corrections = [
            correction for correction in corrections if correction["learning_mode"] == learning_mode
        ]
        rows.append(
            {
                "learning_mode": learning_mode,
                "correction_count": len(mode_corrections),
                "accepted_count": _count_where(mode_corrections, "review_status", "accepted"),
                "rejected_count": _count_where(mode_corrections, "review_status", "rejected"),
                "needs_review_count": _count_where(
                    mode_corrections,
                    "review_status",
                    "needs_review",
                ),
                "average_trust_weight": _average(
                    correction["trust_weight"] for correction in mode_corrections
                ),
            }
        )
    return rows


def _high_disagreement_labels(
    corrections: list[dict[str, Any]],
    ontology: dict[str, Any],
) -> list[dict[str, Any]]:
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for correction in corrections:
        by_label[correction["label"]].append(correction)

    rows = []
    for label_id, label_corrections in by_label.items():
        disagreements = [
            correction
            for correction in label_corrections
            if correction["post_correction_model_agreement"] < 0.5
            or abs(correction["confidence_delta"]) >= 0.2
        ]
        if not disagreements:
            continue

        label = _ontology_label_by_id(ontology, label_id)
        rows.append(
            {
                **_label_summary(label, ontology),
                "correction_count": len(label_corrections),
                "disagreement_count": len(disagreements),
                "disagreement_rate": round(len(disagreements) / len(label_corrections), 2),
                "average_model_agreement": _average(
                    correction["post_correction_model_agreement"]
                    for correction in label_corrections
                ),
                "average_confidence_delta": _average(
                    correction["confidence_delta"] for correction in label_corrections
                ),
                "source_model_version": MOCK_MODEL_VERSION,
            }
        )

    return sorted(
        rows,
        key=lambda row: (row["disagreement_count"], row["disagreement_rate"]),
        reverse=True,
    )[:3]


def _reviewer_reliability_indicators(corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_reviewer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for correction in corrections:
        by_reviewer[correction["reviewer_id"]].append(correction)

    rows = []
    for reviewer_id, reviewer_corrections in by_reviewer.items():
        reviewed_count = len(reviewer_corrections)
        accepted_count = _count_where(reviewer_corrections, "review_status", "accepted")
        contradiction_count = sum(
            correction["contradiction_count"] for correction in reviewer_corrections
        )
        reliability_score = max(
            round(accepted_count / reviewed_count - contradiction_count / (reviewed_count * 2), 2),
            0,
        )
        rows.append(
            {
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_corrections[0]["reviewer_role"],
                "reviewed_count": reviewed_count,
                "accepted_count": accepted_count,
                "reliability_score": reliability_score,
                "average_reviewer_confidence": _average(
                    correction["reviewer_confidence"] for correction in reviewer_corrections
                ),
                "contradiction_count": contradiction_count,
            }
        )

    return sorted(rows, key=lambda row: row["reliability_score"], reverse=True)


def _soft_feedback_patterns(
    corrections: list[dict[str, Any]],
    ontology: dict[str, Any],
) -> list[dict[str, Any]]:
    needs_review = [
        correction
        for correction in corrections
        if correction["learning_mode"] == "soft" and correction["review_status"] == "needs_review"
    ]
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for correction in needs_review:
        by_label[correction["label"]].append(correction)

    rows = []
    for label_id, label_corrections in by_label.items():
        has_ontology_gap = any(
            correction["correction_type"] == "ontology_gap" for correction in label_corrections
        )
        if len(label_corrections) < 2 and not has_ontology_gap:
            continue

        label = _ontology_label_by_id(ontology, label_id)
        rows.append(
            {
                "pattern_id": f"soft-{label_id}",
                **_label_summary(label, ontology),
                "learning_mode": "soft",
                "occurrences": len(label_corrections),
                "reviewer_count": len(
                    {correction["reviewer_id"] for correction in label_corrections}
                ),
                "average_reviewer_confidence": _average(
                    correction["reviewer_confidence"] for correction in label_corrections
                ),
                "review_status": "needs_review",
                "review_reason": (
                    "Soft ontology-gap reports require internal ontology review."
                    if has_ontology_gap
                    else "Repeated soft corrections with low reviewer confidence."
                ),
            }
        )

    return sorted(rows, key=lambda row: row["occurrences"], reverse=True)


def _count_where(records: list[dict[str, Any]], key: str, value: Any) -> int:
    return sum(1 for record in records if record[key] == value)


def _average(values: Any) -> float:
    numbers = list(values)
    if not numbers:
        return 0
    return round(sum(numbers) / len(numbers), 2)


def _ontology_label_by_id(ontology: dict[str, Any], label_id: str) -> dict[str, Any]:
    for label in ontology["labels"]:
        if label["label_id"] == label_id:
            return label
    raise KeyError(f"unknown ontology label {label_id!r}")


def _label_summary(label: dict[str, Any], ontology: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label["label_id"],
        "label_display_name": label.get("display_name", label["label_id"]),
        "label_type": label.get("label_type", "unknown"),
        "ontology_version": ontology["ontology_version"],
    }


def _sport_id_for_ontology(ontology: dict[str, Any]) -> str:
    sport_id = ontology.get("sport_id")
    if isinstance(sport_id, str) and sport_id:
        return sport_id
    return ontology["ontology_id"].split("-local-", maxsplit=1)[0]


def _sport_display_name_for_ontology(ontology: dict[str, Any]) -> str:
    display_name = ontology.get("sport_display_name") or ontology.get("display_name")
    if isinstance(display_name, str) and display_name:
        return display_name
    return _sport_id_for_ontology(ontology).replace("-", " ").title()
