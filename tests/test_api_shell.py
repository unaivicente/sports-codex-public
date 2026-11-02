from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from apps.api.mock_payloads import (
    MOCK_EVIDENCE_MODEL_VERSION,
    MOCK_MODEL_VERSION,
    build_active_learning_queue_payload,
    build_correction_submission_payload,
    build_feedback_quality_payload,
    build_health_payload,
    build_mock_predictions_payload,
    build_ontology_payload,
    build_sports_payload,
    build_video_upload_payload,
)
from apps.api.main import (
    MOCK_EVIDENCE_MODEL_VERSION,
    MOCK_MODEL_VERSION as API_MOCK_MODEL_VERSION,
    PredictionRequest,
    app,
    create_prediction,
)
from apps.api.ontologies import get_ontology as get_api_ontology
from packages.contracts import CONTRACT_VERSION, validate_ontology, validate_prediction


class ApiShellTests(unittest.TestCase):
    def test_health_payload_exposes_contract_version(self) -> None:
        self.assertEqual(build_health_payload(), {"status": "ok", "contract_version": CONTRACT_VERSION})

    def test_ontology_endpoint_payload_contains_valid_ontologies(self) -> None:
        payload = build_ontology_payload()

        self.assertEqual(payload["contract_version"], CONTRACT_VERSION)
        ontologies = payload["data"]["ontologies"]
        self.assertGreaterEqual(len(ontologies), 2)
        self.assertEqual(payload["data"]["default_ontology_id"], ontologies[0]["ontology_id"])

        for ontology in ontologies:
            self.assertIs(validate_ontology(ontology), ontology)

    def test_sports_payload_groups_ontology_backed_sports(self) -> None:
        payload = build_sports_payload()
        sports = payload["data"]["sports"]

        self.assertGreaterEqual(len(sports), 2)
        self.assertEqual(payload["data"]["default_sport_id"], sports[0]["sport_id"])
        self.assertEqual(payload["data"]["default_ontology_id"], sports[0]["ontologies"][0]["ontology_id"])

        for sport in sports:
            self.assertGreaterEqual(len(sport["ontologies"]), 1)
            for ontology in sport["ontologies"]:
                self.assertEqual(ontology["sport_id"], sport["sport_id"])
                self.assertIs(validate_ontology(ontology), ontology)

    def test_video_upload_payload_is_local_stub_only(self) -> None:
        payload = build_video_upload_payload(
            filename="clip.mp4",
            content_type="video/mp4",
            byte_count=128,
        )
        video = payload["data"]["video"]

        self.assertEqual(video["filename"], "clip.mp4")
        self.assertEqual(video["content_type"], "video/mp4")
        self.assertEqual(video["byte_count"], 128)
        self.assertEqual(video["status"], "accepted_stub")
        self.assertEqual(video["storage"], "not_persisted")
        self.assertEqual(video["processing"], "not_started")

    def test_mock_predictions_use_requested_ontology_labels_and_provenance(self) -> None:
        ontology_payload = build_ontology_payload()
        ontology = ontology_payload["data"]["ontologies"][1]
        prediction_payload = build_mock_predictions_payload(ontology["ontology_id"], video_id="video-123")
        predictions = prediction_payload["data"]["predictions"]
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}

        self.assertEqual(prediction_payload["data"]["video_id"], "video-123")
        self.assertEqual(prediction_payload["data"]["model_version"], MOCK_MODEL_VERSION)
        self.assertEqual(prediction_payload["data"]["ontology_version"], ontology["ontology_version"])
        self.assertGreaterEqual(len(predictions), 1)

        for prediction in predictions:
            self.assertIn(prediction["label"], ontology_label_ids)
            self.assertEqual(prediction["model_version"], MOCK_MODEL_VERSION)
            self.assertEqual(prediction["ontology_version"], ontology["ontology_version"])
            self.assertGreaterEqual(len(prediction["evidence"]), 1)
            self.assertEqual(
                prediction["evidence"][0]["source_model_version"],
                MOCK_EVIDENCE_MODEL_VERSION,
            )
            self.assertIs(validate_prediction(prediction, ontology=ontology), prediction)

    def test_correction_submission_preserves_source_prediction_provenance(self) -> None:
        ontology_payload = build_ontology_payload()
        ontology = ontology_payload["data"]["ontologies"][0]
        prediction = build_mock_predictions_payload(
            ontology["ontology_id"],
            video_id="video-456",
        )["data"]["predictions"][0]
        correction = {
            "correction_id": "correction-1",
            "video_id": prediction["video_id"],
            "target_interval": {
                "interval_start": prediction["interval_start"],
                "interval_end": prediction["interval_end"],
                "timebase": prediction["timebase"],
                "source_prediction_ids": [prediction["prediction_id"]],
            },
            "corrected_intervals": [
                {
                    "interval_start": prediction["interval_start"],
                    "interval_end": prediction["interval_end"],
                    "timebase": prediction["timebase"],
                    "label": prediction["label"],
                    "ontology_version": prediction["ontology_version"],
                    "reviewer_confidence": 0.75,
                    "evidence_refs": [
                        evidence["evidence_id"] for evidence in prediction["evidence"]
                    ],
                }
            ],
            "correction_type": "confirm",
            "edit_operation": "none",
            "source_predictions": [prediction],
            "primary_source_prediction_id": prediction["prediction_id"],
            "ontology_version": prediction["ontology_version"],
            "evidence_snapshot": prediction["evidence"],
            "learning_mode": "soft",
            "reviewer_id": "local-reviewer",
            "reviewer_role": "unknown",
            "reviewer_confidence": 0.75,
            "trust_weight": 0,
            "review_status": "pending",
            "created_at": "2026-05-28T12:00:00Z",
        }

        payload = build_correction_submission_payload(correction)

        self.assertTrue(payload["data"]["accepted"])
        self.assertEqual(
            payload["data"]["preserved_source_prediction_ids"],
            [prediction["prediction_id"]],
        )
        self.assertEqual(payload["data"]["source_model_versions"], [prediction["model_version"]])
        self.assertEqual(
            payload["data"]["source_ontology_versions"],
            [prediction["ontology_version"]],
        )

    def test_feedback_quality_payload_uses_ontology_labels(self) -> None:
        ontology_payload = build_ontology_payload()
        ontology = ontology_payload["data"]["ontologies"][0]
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}

        payload = build_feedback_quality_payload(ontology["ontology_id"])
        dashboard = payload["data"]["dashboard"]

        self.assertEqual(payload["contract_version"], CONTRACT_VERSION)
        self.assertEqual(dashboard["ontology_version"], ontology["ontology_version"])
        self.assertEqual(dashboard["model_version"], MOCK_MODEL_VERSION)
        self.assertEqual(
            {mode["learning_mode"] for mode in dashboard["correction_volume_by_mode"]},
            {"training", "soft"},
        )
        self.assertGreater(dashboard["correction_acceptance_rate"]["acceptance_rate"], 0)
        self.assertTrue(
            {
                "high_disagreement_labels",
                "reviewer_reliability_indicators",
                "soft_feedback_patterns",
            }.issubset(dashboard)
        )

        for label_metric in dashboard["high_disagreement_labels"]:
            self.assertIn(label_metric["label"], ontology_label_ids)
            self.assertEqual(label_metric["ontology_version"], ontology["ontology_version"])

        for pattern in dashboard["soft_feedback_patterns"]:
            self.assertIn(pattern["label"], ontology_label_ids)
            self.assertEqual(pattern["review_status"], "needs_review")

    def test_active_learning_queue_payload_ranks_review_segments(self) -> None:
        ontology_payload = build_ontology_payload()
        ontology = ontology_payload["data"]["ontologies"][0]
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}

        payload = build_active_learning_queue_payload(ontology["ontology_id"])
        active_learning = payload["data"]["active_learning"]
        queue = active_learning["queue"]
        flags = {flag for entry in queue for flag in entry["flags"]}

        self.assertEqual(payload["contract_version"], CONTRACT_VERSION)
        self.assertEqual(active_learning["ontology_version"], ontology["ontology_version"])
        self.assertGreaterEqual(active_learning["queued_count"], 1)
        self.assertEqual(
            [entry["learning_value_score"] for entry in queue],
            sorted((entry["learning_value_score"] for entry in queue), reverse=True),
        )
        self.assertTrue(
            {
                "low_confidence",
                "multimodal_disagreement",
                "ontology_transition_conflict",
                "rare_label",
                "frequent_correction",
            }.issubset(flags)
        )

        for entry in queue:
            self.assertIn(entry["label"], ontology_label_ids)
            self.assertEqual(entry["source_prediction"]["prediction_id"], entry["source_prediction_id"])
            self.assertEqual(entry["source_prediction"]["model_version"], entry["model_version"])
            self.assertEqual(entry["source_prediction"]["ontology_version"], entry["ontology_version"])
            self.assertGreaterEqual(len(entry["evidence"]), 1)

    def test_fastapi_active_learning_queue_endpoint_is_local_and_ranked(self) -> None:
        response = TestClient(app).get("/api/v1/active-learning/queue")
        payload = response.json()
        active_learning = payload["data"]["active_learning"]
        queue = active_learning["queue"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["contract_version"], CONTRACT_VERSION)
        self.assertGreaterEqual(active_learning["queued_count"], 1)
        self.assertEqual(
            [entry["rank"] for entry in queue],
            list(range(1, len(queue) + 1)),
        )
        self.assertTrue(all(entry["model_version"] for entry in queue))
        self.assertTrue(all(entry["ontology_version"] for entry in queue))

    def test_api_mock_prediction_payload_satisfies_schema_contract(self) -> None:
        response = create_prediction(
            PredictionRequest(video_id="local-video-1", timestamp=2, sport_id="football")
        )
        prediction = response["data"]["prediction"]
        ontology = get_api_ontology(ontology_version=prediction["ontology_version"])
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}

        self.assertEqual(response["contract_version"], CONTRACT_VERSION)
        self.assertEqual(response["data"]["validation"], {"schema": "prediction", "valid": True})
        self.assertIn(prediction["label"], ontology_label_ids)
        self.assertEqual(prediction["model_version"], API_MOCK_MODEL_VERSION)
        self.assertEqual(
            prediction["evidence"][0]["source_model_version"],
            MOCK_EVIDENCE_MODEL_VERSION,
        )
        self.assertTrue(
            {
                "timestamp",
                "label",
                "confidence",
                "evidence",
                "model_version",
                "ontology_version",
            }.issubset(prediction)
        )
        self.assertIs(validate_prediction(prediction, ontology=ontology), prediction)


if __name__ == "__main__":
    unittest.main()
