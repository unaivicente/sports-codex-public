from __future__ import annotations

import unittest

from packages.contracts import ContractValidationError
from packages.evaluation import (
    MODEL_EVALUATION_HARNESS_VERSION,
    evaluate_model_candidate,
)


def sample_ontology() -> dict:
    return {
        "ontology_id": "neutral-evaluation",
        "ontology_version": "neutral-evaluation-2026-05-30",
        "labels": [
            {
                "label_id": "neutral.phase.active",
                "label_type": "phase",
                "display_name": "Active",
            },
            {
                "label_id": "neutral.event.attack",
                "label_type": "event",
                "display_name": "Attack",
            },
            {
                "label_id": "neutral.event.finish",
                "label_type": "event",
                "display_name": "Finish",
            },
        ],
        "thresholds": {"default_confidence": 0.55},
        "transition_rules": [],
    }


def reference(
    video_id: str,
    timestamp: int,
    label: str,
    *,
    sport: str = "neutral-sport",
    ontology: dict | None = None,
) -> dict:
    selected_ontology = ontology or sample_ontology()
    return {
        "reference_id": f"ref-{video_id}-{timestamp}",
        "video_id": video_id,
        "sport": sport,
        "timestamp": timestamp,
        "interval_start": timestamp,
        "interval_end": timestamp + 1,
        "label": label,
        "ontology_version": selected_ontology["ontology_version"],
    }


def prediction(
    video_id: str,
    timestamp: int,
    label: str,
    confidence: float,
    model_version: str,
    *,
    ontology: dict | None = None,
) -> dict:
    selected_ontology = ontology or sample_ontology()
    return {
        "prediction_id": f"{model_version}-{video_id}-{timestamp}",
        "video_id": video_id,
        "timestamp": timestamp,
        "interval_start": timestamp,
        "interval_end": timestamp + 1,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": label,
        "confidence": confidence,
        "evidence": [
            {
                "evidence_id": f"evidence-{model_version}-{video_id}-{timestamp}",
                "modality": "vision",
                "timestamp": timestamp,
                "type": "local_eval_fixture",
                "value": {
                    "ontology_label_id": label,
                    "ontology_version": selected_ontology["ontology_version"],
                },
                "confidence": max(round(confidence - 0.05, 2), 0),
                "source_model_version": f"{model_version}-vision",
            }
        ],
        "model_version": model_version,
        "ontology_version": selected_ontology["ontology_version"],
        "created_at": "2026-05-30T12:00:00Z",
    }


class ModelEvaluationHarnessTests(unittest.TestCase):
    def test_candidate_with_required_improvement_is_eligible_for_promotion(self) -> None:
        ontology = sample_ontology()
        active = "neutral.phase.active"
        attack = "neutral.event.attack"
        finish = "neutral.event.finish"
        references = [
            reference("video-1", 0, active),
            reference("video-1", 1, attack),
            reference("video-1", 2, active),
            reference("video-1", 3, finish),
        ]
        current_predictions = [
            prediction("video-1", 0, active, 0.70, "current-local-0.1.0"),
            prediction("video-1", 1, active, 0.82, "current-local-0.1.0"),
            prediction("video-1", 2, active, 0.74, "current-local-0.1.0"),
            prediction("video-1", 3, active, 0.80, "current-local-0.1.0"),
        ]
        candidate_predictions = [
            prediction("video-1", 0, active, 0.91, "candidate-local-0.2.0"),
            prediction("video-1", 1, attack, 0.87, "candidate-local-0.2.0"),
            prediction("video-1", 2, active, 0.89, "candidate-local-0.2.0"),
            prediction("video-1", 3, finish, 0.86, "candidate-local-0.2.0"),
        ]

        result = evaluate_model_candidate(
            current_predictions=current_predictions,
            candidate_predictions=candidate_predictions,
            references=references,
            ontologies=[ontology],
            current_inference_cost={"total_inference_ms": 80},
            candidate_inference_cost={"total_inference_ms": 72},
            generated_at="2026-05-30T12:00:00Z",
        )

        self.assertEqual(result["harness_version"], MODEL_EVALUATION_HARNESS_VERSION)
        self.assertTrue(result["promotion_decision"]["promote"])
        self.assertEqual(result["promotion_decision"]["status"], "eligible_for_promotion")
        self.assertGreaterEqual(result["comparison"]["summary_deltas"]["macro_f1"], 0.01)
        self.assertEqual(result["candidate"]["per_label"][finish]["precision"], 1.0)
        self.assertEqual(result["candidate"]["temporal_boundary"]["boundary_accuracy"], 1.0)
        self.assertLessEqual(
            result["comparison"]["calibration"]["expected_calibration_error_delta"],
            0,
        )
        self.assertEqual(
            result["comparison"]["rare_event_false_positives"]["candidate"][
                "total_false_positives"
            ],
            0,
        )
        self.assertEqual(result["candidate"]["inference_cost"]["average_inference_ms"], 18.0)
        self.assertEqual(
            result["candidate"]["required_prediction_fields_validated"],
            [
                "timestamp",
                "label",
                "confidence",
                "evidence",
                "model_version",
                "ontology_version",
            ],
        )

    def test_candidate_is_blocked_when_rare_event_false_positives_increase(self) -> None:
        ontology = sample_ontology()
        active = "neutral.phase.active"
        finish = "neutral.event.finish"
        references = [
            reference("video-rare", 0, active),
            reference("video-rare", 1, active),
            reference("video-rare", 2, finish),
        ]
        current_predictions = [
            prediction("video-rare", 0, active, 0.82, "current-local-0.1.0"),
            prediction("video-rare", 1, active, 0.84, "current-local-0.1.0"),
            prediction("video-rare", 2, finish, 0.80, "current-local-0.1.0"),
        ]
        candidate_predictions = [
            prediction("video-rare", 0, finish, 0.93, "candidate-local-0.2.0"),
            prediction("video-rare", 1, finish, 0.91, "candidate-local-0.2.0"),
            prediction("video-rare", 2, finish, 0.90, "candidate-local-0.2.0"),
        ]

        result = evaluate_model_candidate(
            current_predictions=current_predictions,
            candidate_predictions=candidate_predictions,
            references=references,
            ontologies=[ontology],
            current_inference_cost={"total_inference_ms": 60},
            candidate_inference_cost={"total_inference_ms": 60},
            policy={"minimum_macro_f1_improvement": 0.0},
        )

        reason_codes = {
            reason["code"] for reason in result["promotion_decision"]["blocking_reasons"]
        }
        self.assertFalse(result["promotion_decision"]["promote"])
        self.assertIn("rare_event_false_positive_regression", reason_codes)
        self.assertEqual(
            result["comparison"]["rare_event_false_positives"]["total_false_positive_delta"],
            2,
        )

    def test_candidate_is_blocked_on_existing_sport_ontology_cohort_regression(self) -> None:
        ontology = sample_ontology()
        active = "neutral.phase.active"
        attack = "neutral.event.attack"
        references = [
            reference("old-video", 0, active, sport="legacy-sport"),
            reference("old-video", 1, attack, sport="legacy-sport"),
            reference("new-video", 0, active, sport="new-sport"),
            reference("new-video", 1, attack, sport="new-sport"),
            reference("new-video", 2, active, sport="new-sport"),
            reference("new-video", 3, attack, sport="new-sport"),
        ]
        current_predictions = [
            prediction("old-video", 0, active, 0.90, "current-local-0.1.0"),
            prediction("old-video", 1, attack, 0.89, "current-local-0.1.0"),
            prediction("new-video", 0, active, 0.75, "current-local-0.1.0"),
            prediction("new-video", 1, active, 0.76, "current-local-0.1.0"),
            prediction("new-video", 2, active, 0.74, "current-local-0.1.0"),
            prediction("new-video", 3, active, 0.73, "current-local-0.1.0"),
        ]
        candidate_predictions = [
            prediction("old-video", 0, active, 0.85, "candidate-local-0.2.0"),
            prediction("old-video", 1, active, 0.84, "candidate-local-0.2.0"),
            prediction("new-video", 0, active, 0.91, "candidate-local-0.2.0"),
            prediction("new-video", 1, attack, 0.90, "candidate-local-0.2.0"),
            prediction("new-video", 2, active, 0.89, "candidate-local-0.2.0"),
            prediction("new-video", 3, attack, 0.88, "candidate-local-0.2.0"),
        ]

        result = evaluate_model_candidate(
            current_predictions=current_predictions,
            candidate_predictions=candidate_predictions,
            references=references,
            ontologies=[ontology],
            current_inference_cost={"total_inference_ms": 120},
            candidate_inference_cost={"total_inference_ms": 120},
            policy={"minimum_macro_f1_improvement": 0.1},
        )

        reason_codes = {
            reason["code"] for reason in result["promotion_decision"]["blocking_reasons"]
        }
        legacy_cohort = next(
            cohort
            for cohort in result["comparison"]["cohorts"]
            if cohort["sport"] == "legacy-sport"
        )
        self.assertGreaterEqual(result["comparison"]["summary_deltas"]["macro_f1"], 0.1)
        self.assertLess(legacy_cohort["macro_f1_delta"], 0)
        self.assertFalse(result["promotion_decision"]["promote"])
        self.assertIn("protected_cohort_regression", reason_codes)

    def test_candidate_is_blocked_when_inference_cost_regresses(self) -> None:
        ontology = sample_ontology()
        active = "neutral.phase.active"
        references = [reference("video-cost", 0, active)]
        current_predictions = [prediction("video-cost", 0, active, 0.90, "current-local-0.1.0")]
        candidate_predictions = [
            prediction("video-cost", 0, active, 0.91, "candidate-local-0.2.0")
        ]

        result = evaluate_model_candidate(
            current_predictions=current_predictions,
            candidate_predictions=candidate_predictions,
            references=references,
            ontologies=[ontology],
            current_inference_cost={"total_inference_ms": 10},
            candidate_inference_cost={"total_inference_ms": 16},
            policy={
                "minimum_macro_f1_improvement": 0.0,
                "maximum_inference_cost_regression_ratio": 0.25,
            },
        )

        reason_codes = {
            reason["code"] for reason in result["promotion_decision"]["blocking_reasons"]
        }
        self.assertFalse(result["promotion_decision"]["promote"])
        self.assertIn("inference_cost_regression", reason_codes)
        self.assertEqual(
            result["comparison"]["inference_cost"]["average_inference_ms_regression_ratio"],
            0.6,
        )

    def test_prediction_labels_must_come_from_supplied_ontology(self) -> None:
        ontology = sample_ontology()
        active = "neutral.phase.active"
        references = [reference("video-invalid", 0, active)]
        current_predictions = [prediction("video-invalid", 0, active, 0.90, "current-local-0.1.0")]
        candidate = prediction("video-invalid", 0, active, 0.91, "candidate-local-0.2.0")
        candidate["label"] = "neutral.event.not-in-ontology"

        with self.assertRaises(ContractValidationError):
            evaluate_model_candidate(
                current_predictions=current_predictions,
                candidate_predictions=[candidate],
                references=references,
                ontologies=[ontology],
                current_inference_cost={"total_inference_ms": 10},
                candidate_inference_cost={"total_inference_ms": 10},
            )


if __name__ == "__main__":
    unittest.main()
