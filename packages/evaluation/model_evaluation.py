"""Local model evaluation and promotion-gating harness.

The harness compares an incumbent model run with a candidate model run against
the same ontology-backed reference set. It is deliberately side-effect free:
it does not promote models, mutate registry state, call remote inference, or
write cloud artifacts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from packages.contracts import validate_ontology, validate_prediction

MODEL_EVALUATION_HARNESS_VERSION = "model-evaluation-local-0.1.0"
EVALUATION_SCHEMA_VERSION = "local-model-evaluation-v1"

DEFAULT_PROMOTION_POLICY: dict[str, int | float] = {
    "minimum_macro_f1_improvement": 0.01,
    "maximum_per_label_f1_regression": 0.05,
    "maximum_temporal_boundary_regression": 0.02,
    "maximum_calibration_ece_regression": 0.02,
    "maximum_rare_event_false_positive_regression": 0,
    "maximum_inference_cost_regression_ratio": 0.20,
    "maximum_protected_cohort_macro_f1_regression": 0.0,
    "boundary_tolerance_seconds": 0.5,
    "calibration_bins": 10,
    "rare_event_max_reference_count": 1,
    "rare_event_max_reference_frequency": 0.20,
}

PROMOTION_CONTRACT_FIELDS = (
    "timestamp",
    "label",
    "confidence",
    "evidence",
    "model_version",
    "ontology_version",
)

EvaluationKey = tuple[str, float]


def evaluate_model_candidate(
    *,
    current_predictions: Sequence[Mapping[str, Any]],
    candidate_predictions: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    ontologies: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    current_inference_cost: Mapping[str, Any] | None = None,
    candidate_inference_cost: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Compare current and candidate model runs and return a promotion gate.

    ``references`` are local ground-truth intervals or per-second labels. Every
    reference and prediction label is checked against the supplied ontology
    definitions, so the harness never embeds sport-specific label names.
    """

    selected_policy = _normalise_policy(policy)
    ontology_by_version = _normalise_ontologies(ontologies)
    reference_rows = _normalise_references(references, ontology_by_version)
    reference_samples = _reference_samples(reference_rows)

    current = _evaluate_run(
        run_name="current",
        predictions=current_predictions,
        references=reference_rows,
        reference_samples=reference_samples,
        ontologies=ontology_by_version,
        inference_cost=current_inference_cost,
        policy=selected_policy,
    )
    candidate = _evaluate_run(
        run_name="candidate",
        predictions=candidate_predictions,
        references=reference_rows,
        reference_samples=reference_samples,
        ontologies=ontology_by_version,
        inference_cost=candidate_inference_cost,
        policy=selected_policy,
    )
    comparison = _compare_runs(current, candidate)
    decision = _promotion_decision(comparison, selected_policy)

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "harness_version": MODEL_EVALUATION_HARNESS_VERSION,
        "generated_at": generated_at or _utc_now(),
        "local_first": {
            "cloud_storage_used": False,
            "remote_inference_used": False,
            "registry_mutated": False,
        },
        "prediction_contract_fields": list(PROMOTION_CONTRACT_FIELDS),
        "ontology_versions": sorted(ontology_by_version),
        "policy": selected_policy,
        "reference_summary": _reference_summary(reference_rows, reference_samples),
        "current": current,
        "candidate": candidate,
        "comparison": comparison,
        "promotion_decision": decision,
    }


def _evaluate_run(
    *,
    run_name: str,
    predictions: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    ontologies: Mapping[str, Mapping[str, Any]],
    inference_cost: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    prediction_rows, predictions_by_key = _normalise_predictions(
        predictions,
        ontologies,
        run_name=run_name,
    )
    labels = _ontology_label_ids(ontologies.values())
    label_metrics = _per_label_metrics(
        labels=labels,
        reference_samples=reference_samples,
        predictions_by_key=predictions_by_key,
    )
    summary = _label_metric_summary(label_metrics, reference_samples, predictions_by_key)
    temporal = _temporal_boundary_metrics(
        references=references,
        predictions=prediction_rows,
        tolerance_seconds=float(policy["boundary_tolerance_seconds"]),
    )
    calibration = _calibration_metrics(
        reference_samples=reference_samples,
        predictions_by_key=predictions_by_key,
        bin_count=int(policy["calibration_bins"]),
    )
    rare_events = _rare_event_false_positives(
        reference_samples=reference_samples,
        predictions_by_key=predictions_by_key,
        ontologies=ontologies,
        rare_event_max_reference_count=int(policy["rare_event_max_reference_count"]),
        rare_event_max_reference_frequency=float(policy["rare_event_max_reference_frequency"]),
    )
    cost = _inference_cost_metrics(prediction_rows, inference_cost)
    cohorts = _cohort_metrics(
        labels=labels,
        reference_samples=reference_samples,
        predictions_by_key=predictions_by_key,
    )

    return {
        "run_name": run_name,
        "prediction_count": len(prediction_rows),
        "model_versions": sorted({str(prediction["model_version"]) for prediction in prediction_rows}),
        "ontology_versions": sorted(
            {str(prediction["ontology_version"]) for prediction in prediction_rows}
        ),
        "required_prediction_fields_validated": list(PROMOTION_CONTRACT_FIELDS),
        "summary": summary,
        "per_label": label_metrics,
        "temporal_boundary": temporal,
        "calibration": calibration,
        "rare_event_false_positives": rare_events,
        "inference_cost": cost,
        "cohorts": cohorts,
    }


def _normalise_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    selected: dict[str, Any] = dict(DEFAULT_PROMOTION_POLICY)
    if policy:
        selected.update(dict(policy))

    for key in DEFAULT_PROMOTION_POLICY:
        value = selected[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"promotion policy {key!r} must be numeric")
        if value < 0:
            raise ValueError(f"promotion policy {key!r} must be >= 0")

    if int(selected["calibration_bins"]) < 1:
        raise ValueError("promotion policy 'calibration_bins' must be >= 1")
    return selected


def _normalise_ontologies(
    ontologies: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if isinstance(ontologies, Mapping) and "ontology_version" in ontologies:
        candidates: Sequence[Mapping[str, Any]] = (ontologies,)
    elif isinstance(ontologies, Mapping):
        candidates = tuple(
            ontology for ontology in ontologies.values() if isinstance(ontology, Mapping)
        )
    else:
        candidates = tuple(ontologies)

    by_version: dict[str, Mapping[str, Any]] = {}
    for ontology in candidates:
        validate_ontology(ontology)
        version = str(ontology["ontology_version"])
        if version in by_version:
            raise ValueError(f"duplicate ontology_version {version!r}")
        by_version[version] = ontology

    if not by_version:
        raise ValueError("at least one ontology definition is required")
    return by_version


def _normalise_references(
    references: Sequence[Mapping[str, Any]],
    ontologies: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, reference in enumerate(references):
        if not isinstance(reference, Mapping):
            raise ValueError(f"references[{index}] must be an object")

        video_id = _required_string(reference, "video_id", f"references[{index}]")
        ontology_version = _required_string(reference, "ontology_version", f"references[{index}]")
        label = _required_string(reference, "label", f"references[{index}]")
        ontology = _ontology_for_version(ontologies, ontology_version, f"references[{index}]")
        label_ids = _ontology_label_ids((ontology,))
        if label not in label_ids:
            raise ValueError(
                f"references[{index}].label references unknown ontology label {label!r}"
            )

        interval_start, interval_end = _interval_bounds(reference, f"references[{index}]")
        sport = str(
            reference.get("sport")
            or reference.get("sport_id")
            or ontology.get("sport")
            or ontology.get("ontology_id")
            or "unknown"
        )
        rows.append(
            {
                "reference_id": str(reference.get("reference_id") or f"reference-{index + 1}"),
                "video_id": video_id,
                "sport": sport,
                "timestamp": _number(reference.get("timestamp"), default=interval_start),
                "interval_start": interval_start,
                "interval_end": interval_end,
                "label": label,
                "ontology_version": ontology_version,
            }
        )

    if not rows:
        raise ValueError("at least one reference record is required")
    return rows


def _normalise_predictions(
    predictions: Sequence[Mapping[str, Any]],
    ontologies: Mapping[str, Mapping[str, Any]],
    *,
    run_name: str,
) -> tuple[list[dict[str, Any]], dict[EvaluationKey, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_key: dict[EvaluationKey, dict[str, Any]] = {}
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, Mapping):
            raise ValueError(f"{run_name}_predictions[{index}] must be an object")

        ontology_version = _required_string(
            prediction,
            "ontology_version",
            f"{run_name}_predictions[{index}]",
        )
        ontology = _ontology_for_version(
            ontologies,
            ontology_version,
            f"{run_name}_predictions[{index}]",
        )
        validate_prediction(prediction, ontology=ontology)
        row = dict(prediction)
        key = _prediction_key(row)
        if key in by_key:
            raise ValueError(
                f"{run_name}_predictions has duplicate prediction for "
                f"video_id={key[0]!r}, timestamp={key[1]!r}"
            )
        rows.append(row)
        by_key[key] = row
    return rows, by_key


def _reference_samples(
    references: Sequence[Mapping[str, Any]],
) -> dict[EvaluationKey, dict[str, Any]]:
    samples: dict[EvaluationKey, dict[str, Any]] = {}
    for reference in references:
        for timestamp in _per_second_timestamps(
            float(reference["interval_start"]),
            float(reference["interval_end"]),
        ):
            key = (str(reference["video_id"]), timestamp)
            if key in samples:
                raise ValueError(
                    "reference records must not overlap for "
                    f"video_id={key[0]!r}, timestamp={timestamp!r}"
                )
            sample = dict(reference)
            sample["timestamp"] = timestamp
            samples[key] = sample
    return samples


def _per_label_metrics(
    *,
    labels: Sequence[str],
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    predictions_by_key: Mapping[EvaluationKey, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    true_positive: Counter[str] = Counter()
    false_positive: Counter[str] = Counter()
    false_negative: Counter[str] = Counter()

    for key, reference in reference_samples.items():
        reference_label = str(reference["label"])
        prediction = predictions_by_key.get(key)
        if prediction is None:
            false_negative[reference_label] += 1
            continue

        predicted_label = str(prediction["label"])
        if predicted_label == reference_label:
            true_positive[reference_label] += 1
        else:
            false_negative[reference_label] += 1
            false_positive[predicted_label] += 1

    for key, prediction in predictions_by_key.items():
        if key not in reference_samples:
            false_positive[str(prediction["label"])] += 1

    all_labels = sorted(
        set(labels)
        | set(true_positive)
        | set(false_positive)
        | set(false_negative)
    )
    metrics: dict[str, dict[str, Any]] = {}
    for label in all_labels:
        tp = true_positive[label]
        fp = false_positive[label]
        fn = false_negative[label]
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        metrics[label] = {
            "label": label,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "support": tp + fn,
            "predicted_count": tp + fp,
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }
    return metrics


def _label_metric_summary(
    label_metrics: Mapping[str, Mapping[str, Any]],
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    predictions_by_key: Mapping[EvaluationKey, Mapping[str, Any]],
) -> dict[str, Any]:
    supported = [metric for metric in label_metrics.values() if metric["support"] > 0]
    correct = sum(
        1
        for key, reference in reference_samples.items()
        if key in predictions_by_key
        and predictions_by_key[key]["label"] == reference["label"]
    )
    total_support = len(reference_samples)
    weighted_f1 = _safe_divide(
        sum(metric["f1"] * metric["support"] for metric in supported),
        sum(metric["support"] for metric in supported),
    )
    return {
        "reference_count": total_support,
        "prediction_count": len(predictions_by_key),
        "matched_reference_count": correct,
        "missing_prediction_count": sum(1 for key in reference_samples if key not in predictions_by_key),
        "accuracy": _safe_divide(correct, total_support),
        "macro_f1": _safe_divide(sum(metric["f1"] for metric in supported), len(supported)),
        "weighted_f1": weighted_f1,
    }


def _temporal_boundary_metrics(
    *,
    references: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
    tolerance_seconds: float,
) -> dict[str, Any]:
    reference_segments = _segments_from_rows(references)
    prediction_segments = _segments_from_rows(predictions)
    matched_boundaries = 0
    boundary_count = 2 * len(reference_segments)
    matched_segments = 0
    boundary_errors: list[float] = []

    for reference in reference_segments:
        match = _best_overlapping_segment(reference, prediction_segments)
        if match is None:
            continue

        matched_segments += 1
        start_error = abs(match["interval_start"] - reference["interval_start"])
        end_error = abs(match["interval_end"] - reference["interval_end"])
        boundary_errors.extend((start_error, end_error))
        if start_error <= tolerance_seconds:
            matched_boundaries += 1
        if end_error <= tolerance_seconds:
            matched_boundaries += 1

    return {
        "boundary_tolerance_seconds": tolerance_seconds,
        "reference_segment_count": len(reference_segments),
        "prediction_segment_count": len(prediction_segments),
        "matched_label_segment_count": matched_segments,
        "matched_boundary_count": matched_boundaries,
        "total_boundary_count": boundary_count,
        "boundary_accuracy": _safe_divide(matched_boundaries, boundary_count),
        "mean_boundary_error_seconds": (
            round(sum(boundary_errors) / len(boundary_errors), 6)
            if boundary_errors
            else None
        ),
    }


def _calibration_metrics(
    *,
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    predictions_by_key: Mapping[EvaluationKey, Mapping[str, Any]],
    bin_count: int,
) -> dict[str, Any]:
    bins = [
        {
            "lower": round(index / bin_count, 6),
            "upper": round((index + 1) / bin_count, 6),
            "count": 0,
            "accuracy": 0.0,
            "average_confidence": 0.0,
            "gap": 0.0,
        }
        for index in range(bin_count)
    ]
    confidence_sums = [0.0 for _ in range(bin_count)]
    correctness_sums = [0 for _ in range(bin_count)]

    for key, reference in reference_samples.items():
        prediction = predictions_by_key.get(key)
        if prediction is None:
            continue
        confidence = _clamp(_number(prediction.get("confidence"), default=0.0), 0.0, 1.0)
        bin_index = min(int(confidence * bin_count), bin_count - 1)
        bins[bin_index]["count"] += 1
        confidence_sums[bin_index] += confidence
        correctness_sums[bin_index] += int(prediction["label"] == reference["label"])

    evaluated_count = sum(bin_data["count"] for bin_data in bins)
    expected_calibration_error = 0.0
    for index, bin_data in enumerate(bins):
        count = int(bin_data["count"])
        if count == 0:
            continue
        accuracy = correctness_sums[index] / count
        average_confidence = confidence_sums[index] / count
        gap = abs(accuracy - average_confidence)
        bin_data["accuracy"] = round(accuracy, 6)
        bin_data["average_confidence"] = round(average_confidence, 6)
        bin_data["gap"] = round(gap, 6)
        expected_calibration_error += (count / evaluated_count) * gap

    return {
        "bin_count": bin_count,
        "evaluated_prediction_count": evaluated_count,
        "expected_calibration_error": round(expected_calibration_error, 6),
        "bins": bins,
    }


def _rare_event_false_positives(
    *,
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    predictions_by_key: Mapping[EvaluationKey, Mapping[str, Any]],
    ontologies: Mapping[str, Mapping[str, Any]],
    rare_event_max_reference_count: int,
    rare_event_max_reference_frequency: float,
) -> dict[str, Any]:
    label_types = _ontology_label_types(ontologies.values())
    reference_counts = Counter(str(reference["label"]) for reference in reference_samples.values())
    total_references = len(reference_samples)
    rare_event_labels = sorted(
        label
        for label, label_type in label_types.items()
        if label_type == "event"
        and (
            reference_counts[label] <= rare_event_max_reference_count
            or _safe_divide(reference_counts[label], total_references)
            <= rare_event_max_reference_frequency
        )
    )
    rare_event_label_set = set(rare_event_labels)
    false_positive_counts: Counter[str] = Counter()

    for key, prediction in predictions_by_key.items():
        predicted_label = str(prediction["label"])
        if predicted_label not in rare_event_label_set:
            continue
        reference = reference_samples.get(key)
        if reference is None or reference["label"] != predicted_label:
            false_positive_counts[predicted_label] += 1

    total_false_positives = sum(false_positive_counts.values())
    return {
        "rare_event_labels": rare_event_labels,
        "rare_event_policy": {
            "max_reference_count": rare_event_max_reference_count,
            "max_reference_frequency": rare_event_max_reference_frequency,
        },
        "total_false_positives": total_false_positives,
        "per_label_false_positives": dict(sorted(false_positive_counts.items())),
    }


def _inference_cost_metrics(
    predictions: Sequence[Mapping[str, Any]],
    explicit_cost: Mapping[str, Any] | None,
) -> dict[str, Any]:
    prediction_count = len(predictions)
    if explicit_cost is not None:
        total_ms = _cost_total_ms(explicit_cost)
        average_ms = _optional_number(explicit_cost.get("average_inference_ms"))
        if average_ms is None and total_ms is not None and prediction_count:
            average_ms = total_ms / prediction_count
        return {
            "source": "explicit",
            "available": total_ms is not None or average_ms is not None,
            "prediction_count": prediction_count,
            "total_inference_ms": _round_or_none(total_ms),
            "average_inference_ms": _round_or_none(average_ms),
            "estimated_cost_usd": _round_or_none(
                _optional_number(explicit_cost.get("estimated_cost_usd")),
                digits=8,
            ),
        }

    per_prediction_ms = [
        value
        for prediction in predictions
        for value in (_prediction_inference_ms(prediction),)
        if value is not None
    ]
    if not per_prediction_ms:
        return {
            "source": "not_provided",
            "available": False,
            "prediction_count": prediction_count,
            "total_inference_ms": None,
            "average_inference_ms": None,
            "estimated_cost_usd": None,
        }

    total_ms = sum(per_prediction_ms)
    return {
        "source": "prediction_metadata",
        "available": True,
        "prediction_count": prediction_count,
        "total_inference_ms": round(total_ms, 6),
        "average_inference_ms": round(total_ms / len(per_prediction_ms), 6),
        "estimated_cost_usd": None,
    }


def _cohort_metrics(
    *,
    labels: Sequence[str],
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
    predictions_by_key: Mapping[EvaluationKey, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped_reference_samples: dict[tuple[str, str], dict[EvaluationKey, Mapping[str, Any]]] = defaultdict(dict)
    for key, reference in reference_samples.items():
        grouped_reference_samples[(str(reference["sport"]), str(reference["ontology_version"]))][key] = reference

    cohorts: list[dict[str, Any]] = []
    for (sport, ontology_version), cohort_samples in sorted(grouped_reference_samples.items()):
        cohort_predictions = {
            key: predictions_by_key[key]
            for key in cohort_samples
            if key in predictions_by_key
        }
        label_metrics = _per_label_metrics(
            labels=labels,
            reference_samples=cohort_samples,
            predictions_by_key=cohort_predictions,
        )
        cohorts.append(
            {
                "sport": sport,
                "ontology_version": ontology_version,
                "summary": _label_metric_summary(
                    label_metrics,
                    cohort_samples,
                    cohort_predictions,
                ),
            }
        )
    return cohorts


def _compare_runs(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    current_summary = current["summary"]
    candidate_summary = candidate["summary"]
    per_label: dict[str, dict[str, Any]] = {}
    for label in sorted(set(current["per_label"]) | set(candidate["per_label"])):
        current_metric = current["per_label"].get(label, _empty_label_metric(label))
        candidate_metric = candidate["per_label"].get(label, _empty_label_metric(label))
        per_label[label] = {
            "label": label,
            "current": current_metric,
            "candidate": candidate_metric,
            "precision_delta": round(candidate_metric["precision"] - current_metric["precision"], 6),
            "recall_delta": round(candidate_metric["recall"] - current_metric["recall"], 6),
            "f1_delta": round(candidate_metric["f1"] - current_metric["f1"], 6),
        }

    current_rare = current["rare_event_false_positives"]
    candidate_rare = candidate["rare_event_false_positives"]
    current_cost = current["inference_cost"]
    candidate_cost = candidate["inference_cost"]

    return {
        "summary_deltas": {
            "accuracy": round(candidate_summary["accuracy"] - current_summary["accuracy"], 6),
            "macro_f1": round(candidate_summary["macro_f1"] - current_summary["macro_f1"], 6),
            "weighted_f1": round(
                candidate_summary["weighted_f1"] - current_summary["weighted_f1"],
                6,
            ),
        },
        "per_label": per_label,
        "temporal_boundary": {
            "boundary_accuracy_delta": round(
                candidate["temporal_boundary"]["boundary_accuracy"]
                - current["temporal_boundary"]["boundary_accuracy"],
                6,
            ),
            "current": current["temporal_boundary"],
            "candidate": candidate["temporal_boundary"],
        },
        "calibration": {
            "expected_calibration_error_delta": round(
                candidate["calibration"]["expected_calibration_error"]
                - current["calibration"]["expected_calibration_error"],
                6,
            ),
            "current": current["calibration"],
            "candidate": candidate["calibration"],
        },
        "rare_event_false_positives": {
            "total_false_positive_delta": (
                candidate_rare["total_false_positives"]
                - current_rare["total_false_positives"]
            ),
            "current": current_rare,
            "candidate": candidate_rare,
        },
        "inference_cost": _compare_cost(current_cost, candidate_cost),
        "cohorts": _compare_cohorts(current["cohorts"], candidate["cohorts"]),
    }


def _promotion_decision(
    comparison: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    blocking_reasons: list[dict[str, Any]] = []
    macro_f1_delta = comparison["summary_deltas"]["macro_f1"]
    if macro_f1_delta + 1e-12 < policy["minimum_macro_f1_improvement"]:
        blocking_reasons.append(
            _blocking_reason(
                "minimum_improvement_not_met",
                "performance",
                "Candidate macro F1 did not meet the required minimum improvement.",
                {
                    "macro_f1_delta": macro_f1_delta,
                    "required_delta": policy["minimum_macro_f1_improvement"],
                },
            )
        )

    for label, metrics in comparison["per_label"].items():
        if metrics["f1_delta"] < -float(policy["maximum_per_label_f1_regression"]):
            blocking_reasons.append(
                _blocking_reason(
                    "per_label_f1_regression",
                    "performance",
                    f"Candidate regressed F1 for ontology label {label!r}.",
                    {
                        "label": label,
                        "f1_delta": metrics["f1_delta"],
                        "allowed_regression": policy["maximum_per_label_f1_regression"],
                    },
                )
            )

    temporal_delta = comparison["temporal_boundary"]["boundary_accuracy_delta"]
    if temporal_delta < -float(policy["maximum_temporal_boundary_regression"]):
        blocking_reasons.append(
            _blocking_reason(
                "temporal_boundary_regression",
                "performance",
                "Candidate temporal boundary accuracy regressed.",
                {
                    "boundary_accuracy_delta": temporal_delta,
                    "allowed_regression": policy["maximum_temporal_boundary_regression"],
                },
            )
        )

    calibration_delta = comparison["calibration"]["expected_calibration_error_delta"]
    if calibration_delta > float(policy["maximum_calibration_ece_regression"]):
        blocking_reasons.append(
            _blocking_reason(
                "calibration_regression",
                "safety",
                "Candidate calibration error regressed.",
                {
                    "expected_calibration_error_delta": calibration_delta,
                    "allowed_regression": policy["maximum_calibration_ece_regression"],
                },
            )
        )

    rare_delta = comparison["rare_event_false_positives"]["total_false_positive_delta"]
    if rare_delta > int(policy["maximum_rare_event_false_positive_regression"]):
        blocking_reasons.append(
            _blocking_reason(
                "rare_event_false_positive_regression",
                "safety",
                "Candidate increased false positives on rare ontology event labels.",
                {
                    "false_positive_delta": rare_delta,
                    "allowed_regression": policy[
                        "maximum_rare_event_false_positive_regression"
                    ],
                },
            )
        )

    cost = comparison["inference_cost"]
    if not cost["available"]:
        blocking_reasons.append(
            _blocking_reason(
                "inference_cost_missing",
                "performance",
                "Both current and candidate inference costs are required for promotion gating.",
                cost,
            )
        )
    elif cost["average_inference_ms_regression_ratio"] > float(
        policy["maximum_inference_cost_regression_ratio"]
    ):
        blocking_reasons.append(
            _blocking_reason(
                "inference_cost_regression",
                "performance",
                "Candidate inference cost regressed beyond policy.",
                {
                    "average_inference_ms_regression_ratio": cost[
                        "average_inference_ms_regression_ratio"
                    ],
                    "allowed_regression_ratio": policy[
                        "maximum_inference_cost_regression_ratio"
                    ],
                },
            )
        )

    for cohort in comparison["cohorts"]:
        if cohort["macro_f1_delta"] < -float(
            policy["maximum_protected_cohort_macro_f1_regression"]
        ):
            blocking_reasons.append(
                _blocking_reason(
                    "protected_cohort_regression",
                    "performance",
                    "Candidate regressed on an existing sport/ontology cohort.",
                    {
                        "sport": cohort["sport"],
                        "ontology_version": cohort["ontology_version"],
                        "macro_f1_delta": cohort["macro_f1_delta"],
                        "allowed_regression": policy[
                            "maximum_protected_cohort_macro_f1_regression"
                        ],
                    },
                )
            )

    return {
        "promote": not blocking_reasons,
        "status": "eligible_for_promotion" if not blocking_reasons else "blocked",
        "minimum_improvement_met": macro_f1_delta + 1e-12
        >= policy["minimum_macro_f1_improvement"],
        "blocking_reasons": blocking_reasons,
        "requires_human_promotion": True,
        "auto_promote": False,
    }


def _compare_cost(
    current_cost: Mapping[str, Any],
    candidate_cost: Mapping[str, Any],
) -> dict[str, Any]:
    current_average = current_cost.get("average_inference_ms")
    candidate_average = candidate_cost.get("average_inference_ms")
    available = isinstance(current_average, (int, float)) and isinstance(
        candidate_average,
        (int, float),
    )
    if not available:
        return {
            "available": False,
            "current": current_cost,
            "candidate": candidate_cost,
            "average_inference_ms_delta": None,
            "average_inference_ms_regression_ratio": None,
        }

    delta = candidate_average - current_average
    if current_average == 0:
        regression_ratio = float("inf") if candidate_average > 0 else 0.0
    else:
        regression_ratio = delta / current_average
    return {
        "available": True,
        "current": current_cost,
        "candidate": candidate_cost,
        "average_inference_ms_delta": round(delta, 6),
        "average_inference_ms_regression_ratio": round(regression_ratio, 6),
    }


def _compare_cohorts(
    current_cohorts: Sequence[Mapping[str, Any]],
    candidate_cohorts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    current_by_key = {
        (cohort["sport"], cohort["ontology_version"]): cohort for cohort in current_cohorts
    }
    candidate_by_key = {
        (cohort["sport"], cohort["ontology_version"]): cohort for cohort in candidate_cohorts
    }
    comparisons: list[dict[str, Any]] = []
    for key in sorted(set(current_by_key) | set(candidate_by_key)):
        current = current_by_key.get(key)
        candidate = candidate_by_key.get(key)
        if current is None or candidate is None:
            continue
        comparisons.append(
            {
                "sport": key[0],
                "ontology_version": key[1],
                "current": current["summary"],
                "candidate": candidate["summary"],
                "macro_f1_delta": round(
                    candidate["summary"]["macro_f1"] - current["summary"]["macro_f1"],
                    6,
                ),
                "accuracy_delta": round(
                    candidate["summary"]["accuracy"] - current["summary"]["accuracy"],
                    6,
                ),
            }
        )
    return comparisons


def _reference_summary(
    references: Sequence[Mapping[str, Any]],
    reference_samples: Mapping[EvaluationKey, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "reference_interval_count": len(references),
        "reference_sample_count": len(reference_samples),
        "sports": sorted({str(reference["sport"]) for reference in references}),
        "ontology_versions": sorted({str(reference["ontology_version"]) for reference in references}),
        "labels": sorted({str(reference["label"]) for reference in references}),
    }


def _segments_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("video_id", "")),
            str(row.get("ontology_version", "")),
            _number(row.get("interval_start"), default=_number(row.get("timestamp"), default=0.0)),
            _number(row.get("interval_end"), default=_number(row.get("timestamp"), default=0.0) + 1),
            str(row.get("label", "")),
        ),
    )
    segments: list[dict[str, Any]] = []
    for row in sorted_rows:
        start, end = _interval_bounds(row, "segment")
        label = str(row["label"])
        video_id = str(row["video_id"])
        ontology_version = str(row["ontology_version"])
        if (
            segments
            and segments[-1]["video_id"] == video_id
            and segments[-1]["ontology_version"] == ontology_version
            and segments[-1]["label"] == label
            and abs(segments[-1]["interval_end"] - start) <= 1e-9
        ):
            segments[-1]["interval_end"] = end
            continue

        segments.append(
            {
                "video_id": video_id,
                "ontology_version": ontology_version,
                "label": label,
                "interval_start": start,
                "interval_end": end,
            }
        )
    return segments


def _best_overlapping_segment(
    reference: Mapping[str, Any],
    prediction_segments: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    matches = [
        prediction
        for prediction in prediction_segments
        if prediction["video_id"] == reference["video_id"]
        and prediction["ontology_version"] == reference["ontology_version"]
        and prediction["label"] == reference["label"]
        and _overlap_seconds(prediction, reference) > 0
    ]
    if not matches:
        return None
    return max(matches, key=lambda prediction: _overlap_seconds(prediction, reference))


def _overlap_seconds(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    return max(
        min(float(first["interval_end"]), float(second["interval_end"]))
        - max(float(first["interval_start"]), float(second["interval_start"])),
        0.0,
    )


def _ontology_for_version(
    ontologies: Mapping[str, Mapping[str, Any]],
    ontology_version: str,
    path: str,
) -> Mapping[str, Any]:
    try:
        return ontologies[ontology_version]
    except KeyError as exc:
        raise ValueError(f"{path}.ontology_version {ontology_version!r} has no ontology") from exc


def _ontology_label_ids(ontologies: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(label["label_id"])
            for ontology in ontologies
            for label in ontology.get("labels", [])
            if isinstance(label, Mapping) and label.get("label_id")
        }
    )


def _ontology_label_types(ontologies: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    label_types: dict[str, str] = {}
    for ontology in ontologies:
        for label in ontology.get("labels", []):
            if isinstance(label, Mapping) and label.get("label_id"):
                label_types[str(label["label_id"])] = str(label.get("label_type", ""))
    return label_types


def _prediction_key(prediction: Mapping[str, Any]) -> EvaluationKey:
    return (
        str(prediction["video_id"]),
        _number(prediction.get("timestamp"), default=_number(prediction["interval_start"], default=0.0)),
    )


def _interval_bounds(payload: Mapping[str, Any], path: str) -> tuple[float, float]:
    if "interval_start" in payload and "interval_end" in payload:
        start = _number(payload.get("interval_start"), default=float("nan"))
        end = _number(payload.get("interval_end"), default=float("nan"))
    elif "timestamp" in payload:
        start = _number(payload.get("timestamp"), default=float("nan"))
        end = start + 1
    else:
        raise ValueError(f"{path} requires timestamp or interval_start/interval_end")

    if start != start or end != end:
        raise ValueError(f"{path} interval bounds must be numeric")
    if start < 0 or end <= start:
        raise ValueError(f"{path}.interval_start must be >= 0 and less than interval_end")
    return start, end


def _per_second_timestamps(start: float, end: float) -> list[float]:
    if _is_whole_second(start) and _is_whole_second(end):
        return [float(timestamp) for timestamp in range(int(start), int(end))]
    return [start]


def _is_whole_second(value: float) -> bool:
    return abs(value - round(value)) <= 1e-9


def _cost_total_ms(cost: Mapping[str, Any]) -> float | None:
    total_ms = _optional_number(cost.get("total_inference_ms"))
    if total_ms is not None:
        return total_ms
    total_seconds = _optional_number(cost.get("total_inference_seconds"))
    if total_seconds is not None:
        return total_seconds * 1000
    local_compute_seconds = _optional_number(cost.get("local_compute_seconds"))
    if local_compute_seconds is not None:
        return local_compute_seconds * 1000
    return None


def _prediction_inference_ms(prediction: Mapping[str, Any]) -> float | None:
    for field in ("inference_cost_ms", "inference_ms", "duration_ms"):
        value = _optional_number(prediction.get(field))
        if value is not None:
            return value

    inference_cost = prediction.get("inference_cost")
    if isinstance(inference_cost, Mapping):
        for field in ("inference_ms", "duration_ms", "wall_time_ms"):
            value = _optional_number(inference_cost.get(field))
            if value is not None:
                return value
    return None


def _required_string(payload: Mapping[str, Any], field: str, path: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path}.{field} must be a non-empty string")
    return value


def _number(value: Any, *, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _optional_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _round_or_none(value: float | None, *, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 6)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _empty_label_metric(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "support": 0,
        "predicted_count": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


def _blocking_reason(
    code: str,
    category: str,
    message: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "message": message,
        "evidence": dict(evidence),
    }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_evaluation_input(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("evaluation input JSON must be an object")

    current = payload.get("current", {})
    candidate = payload.get("candidate", {})
    if not isinstance(current, Mapping) or not isinstance(candidate, Mapping):
        raise ValueError("evaluation input requires object fields 'current' and 'candidate'")

    return evaluate_model_candidate(
        current_predictions=current.get("predictions", payload.get("current_predictions", [])),
        candidate_predictions=candidate.get(
            "predictions",
            payload.get("candidate_predictions", []),
        ),
        current_inference_cost=current.get("inference_cost"),
        candidate_inference_cost=candidate.get("inference_cost"),
        references=payload.get("references", []),
        ontologies=payload.get("ontologies", {}),
        policy=payload.get("policy"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a local current model run against a candidate model run."
    )
    parser.add_argument("input_path", help="JSON file containing ontologies, references, and model runs.")
    parser.add_argument("--output-path", help="Optional path for the evaluation report JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = _load_evaluation_input(Path(args.input_path))
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = result["promotion_decision"]
    print(f"Promotion gate: {decision['status']}")
    if decision["blocking_reasons"]:
        for reason in decision["blocking_reasons"]:
            print(f"- {reason['code']}: {reason['message']}")
    else:
        print("Candidate met the configured evaluation gate.")
    return 0 if decision["promote"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
