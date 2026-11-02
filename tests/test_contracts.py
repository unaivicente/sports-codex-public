from __future__ import annotations

import unittest

from apps.api.contract_validation import api_response, health_response
from packages.contracts import (
    CONTRACT_VERSION,
    ContractValidationError,
    load_schema,
    validate_human_correction,
    validate_ontology,
    validate_prediction,
    validate_training_dataset_record,
)


def sample_ontology() -> dict:
    return {
        "ontology_id": "example-football",
        "ontology_version": "football-2026-05-06",
        "labels": [
            {
                "label_id": "football.event.pass",
                "label_type": "event",
                "display_name": "Pass",
            },
            {
                "label_id": "football.event.shot",
                "label_type": "event",
                "display_name": "Shot",
            },
        ],
        "transition_rules": [
            {
                "from_label": "football.event.pass",
                "to_label": "football.event.shot",
                "rule_type": "allowed_after",
                "max_gap_seconds": 30,
            }
        ],
    }


def sample_evidence() -> dict:
    return {
        "evidence_id": "evidence-1",
        "modality": "vision",
        "timestamp": 12,
        "type": "classifier_logit",
        "value": {"top_class": "football.event.pass"},
        "confidence": 0.77,
        "source_model_version": "vision-local-0.1.0",
    }


def sample_prediction() -> dict:
    return {
        "prediction_id": "prediction-1",
        "video_id": "video-1",
        "timestamp": 12,
        "interval_start": 12,
        "interval_end": 13,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": "football.event.pass",
        "confidence": 0.81,
        "evidence": [sample_evidence()],
        "model_version": "fusion-local-0.1.0",
        "ontology_version": "football-2026-05-06",
        "created_at": "2026-05-06T10:00:00Z",
    }


def sample_correction() -> dict:
    prediction = sample_prediction()
    return {
        "correction_id": "correction-1",
        "video_id": "video-1",
        "target_interval": {
            "interval_start": 12,
            "interval_end": 13,
            "timebase": "seconds",
            "source_prediction_ids": ["prediction-1"],
        },
        "corrected_intervals": [
            {
                "interval_start": 12,
                "interval_end": 13,
                "timebase": "seconds",
                "label": "football.event.shot",
                "ontology_version": "football-2026-05-06",
                "reviewer_confidence": 0.9,
                "evidence_refs": ["evidence-1"],
            }
        ],
        "correction_type": "modify",
        "edit_operation": "relabel",
        "source_predictions": [prediction],
        "primary_source_prediction_id": "prediction-1",
        "ontology_version": "football-2026-05-06",
        "evidence_snapshot": [sample_evidence()],
        "learning_mode": "training",
        "reviewer_id": "local-reviewer",
        "reviewer_role": "internal",
        "reviewer_confidence": 0.9,
        "trust_weight": 0.8,
        "review_status": "accepted",
        "created_at": "2026-05-06T10:05:00Z",
    }


class ContractSchemaTests(unittest.TestCase):
    def test_schema_files_are_loadable_and_version_is_exported(self) -> None:
        for name in (
            "ontology",
            "evidence",
            "prediction",
            "human_correction",
            "training_dataset_record",
        ):
            schema = load_schema(name)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("title", schema)

        self.assertEqual(CONTRACT_VERSION, "0.1.0")
        self.assertEqual(health_response(), {"status": "ok", "contract_version": "0.1.0"})
        self.assertEqual(
            api_response({"accepted": True}),
            {"contract_version": "0.1.0", "data": {"accepted": True}},
        )

    def test_prediction_schema_requires_project_contract_fields(self) -> None:
        schema = load_schema("prediction")

        self.assertTrue(
            {
                "timestamp",
                "label",
                "confidence",
                "evidence",
                "model_version",
                "ontology_version",
            }.issubset(schema["required"])
        )
        self.assertEqual(schema["properties"]["evidence"]["minItems"], 1)

    def test_valid_ontology_prediction_and_correction_are_accepted(self) -> None:
        ontology = sample_ontology()
        prediction = sample_prediction()
        correction = sample_correction()

        self.assertIs(validate_ontology(ontology), ontology)
        self.assertIs(validate_prediction(prediction, ontology=ontology), prediction)
        self.assertIs(validate_human_correction(correction, ontology=ontology), correction)

    def test_valid_ontology_with_transition_rules_is_accepted(self) -> None:
        ontology = {
            "ontology_id": "local-neutral",
            "ontology_version": "local-neutral-2026-05-29",
            "labels": [
                {
                    "label_id": "neutral.phase.active",
                    "label_type": "phase",
                    "display_name": "Active",
                },
                {
                    "label_id": "neutral.event.transition",
                    "label_type": "event",
                    "display_name": "Transition",
                },
                {
                    "label_id": "neutral.object.subject",
                    "label_type": "object",
                    "display_name": "Subject",
                },
            ],
            "transition_rules": [
                {
                    "from_label": "neutral.phase.active",
                    "to_label": "neutral.event.transition",
                    "rule_type": "allowed_during",
                    "min_gap_seconds": 0,
                    "max_gap_seconds": 3,
                }
            ],
            "thresholds": {"default_confidence": 0.5},
            "deprecated_labels": [],
        }

        self.assertIs(validate_ontology(ontology), ontology)

    def test_valid_ontology_with_deprecated_label_mapping_is_accepted(self) -> None:
        ontology = sample_ontology()
        ontology["ontology_version"] = "football-2026-05-30"
        ontology["previous_ontology_version"] = "football-2026-05-06"
        ontology["labels"][0]["deprecated"] = True
        ontology["labels"][0]["replacement_label_id"] = "football.event.shot"
        ontology["labels"][0]["deprecated_in_version"] = "football-2026-05-30"
        ontology["deprecated_labels"] = [
            {
                "label_id": "football.event.pass",
                "replacement_label_id": "football.event.shot",
                "deprecated_in_version": "football-2026-05-30",
                "reason": "merged into shot event for local test coverage",
            }
        ]

        self.assertIs(validate_ontology(ontology), ontology)

    def test_deprecated_label_mapping_must_reference_known_labels(self) -> None:
        ontology = sample_ontology()
        ontology["deprecated_labels"] = [
            {
                "label_id": "football.event.deleted",
                "replacement_label_id": "football.event.missing",
                "deprecated_in_version": "football-2026-05-30",
            }
        ]

        with self.assertRaises(ContractValidationError) as context:
            validate_ontology(ontology)

        self.assertIn(
            "ontology.deprecated_labels[0].label_id references unknown label 'football.event.deleted'",
            context.exception.errors,
        )
        self.assertIn(
            (
                "ontology.deprecated_labels[0].replacement_label_id references unknown label "
                "'football.event.missing'"
            ),
            context.exception.errors,
        )

    def test_deprecated_label_mapping_rejects_self_mapping(self) -> None:
        ontology = sample_ontology()
        ontology["deprecated_labels"] = [
            {
                "label_id": "football.event.pass",
                "replacement_label_id": "football.event.pass",
                "deprecated_in_version": "football-2026-05-30",
            }
        ]

        with self.assertRaises(ContractValidationError) as context:
            validate_ontology(ontology)

        self.assertIn("must not match label_id", str(context.exception))

    def test_invalid_ontology_reports_missing_label_fields_with_paths(self) -> None:
        ontology = sample_ontology()
        del ontology["labels"][0]["label_type"]
        del ontology["labels"][0]["display_name"]

        with self.assertRaises(ContractValidationError) as context:
            validate_ontology(ontology)

        self.assertIn(
            "ontology.labels[0].label_type must be a non-empty string",
            context.exception.errors,
        )
        self.assertIn(
            "ontology.labels[0].display_name must be a non-empty string",
            context.exception.errors,
        )

    def test_transition_rules_require_rule_type(self) -> None:
        ontology = sample_ontology()
        del ontology["transition_rules"][0]["rule_type"]

        with self.assertRaises(ContractValidationError) as context:
            validate_ontology(ontology)

        self.assertIn(
            "ontology.transition_rules[0].rule_type must be a non-empty string",
            context.exception.errors,
        )

    def test_transition_rules_reject_unknown_source_and_target_labels(self) -> None:
        ontology = sample_ontology()
        ontology["transition_rules"][0]["from_label"] = "football.event.kickoff"
        ontology["transition_rules"][0]["to_label"] = "football.event.goal"

        with self.assertRaises(ContractValidationError) as context:
            validate_ontology(ontology)

        self.assertIn(
            "ontology.transition_rules[0].from_label references unknown label 'football.event.kickoff'",
            context.exception.errors,
        )
        self.assertIn(
            "ontology.transition_rules[0].to_label references unknown label 'football.event.goal'",
            context.exception.errors,
        )

    def test_prediction_rejects_unknown_ontology_label(self) -> None:
        prediction = sample_prediction()
        prediction["label"] = "football.event.not-in-ontology"

        with self.assertRaises(ContractValidationError) as context:
            validate_prediction(prediction, ontology=sample_ontology())

        self.assertIn("unknown ontology label", str(context.exception))

    def test_prediction_requires_project_provenance_fields(self) -> None:
        prediction = sample_prediction()
        del prediction["model_version"]
        del prediction["ontology_version"]

        with self.assertRaises(ContractValidationError) as context:
            validate_prediction(prediction)

        self.assertIn("model_version", str(context.exception))
        self.assertIn("ontology_version", str(context.exception))

    def test_human_correction_preserves_source_prediction_provenance(self) -> None:
        correction = sample_correction()
        del correction["source_predictions"][0]["model_version"]

        with self.assertRaises(ContractValidationError) as context:
            validate_human_correction(correction, ontology=sample_ontology())

        self.assertIn("source_predictions[0].model_version", str(context.exception))

    def test_source_prediction_ids_must_match_snapshots(self) -> None:
        correction = sample_correction()
        correction["target_interval"]["source_prediction_ids"] = ["prediction-other"]

        with self.assertRaises(ContractValidationError) as context:
            validate_human_correction(correction, ontology=sample_ontology())

        self.assertIn("must match source_predictions", str(context.exception))

    def test_ontology_gap_cannot_create_training_weight(self) -> None:
        correction = sample_correction()
        correction["correction_type"] = "ontology_gap"
        correction["edit_operation"] = "none"
        correction["corrected_intervals"][0]["label"] = None
        correction["corrected_intervals"][0]["proposed_label"] = "New local label"

        with self.assertRaises(ContractValidationError) as context:
            validate_human_correction(correction, ontology=sample_ontology())

        self.assertIn("ontology_gap corrections must have trust_weight = 0", str(context.exception))

    def test_training_dataset_record_validation(self) -> None:
        record = {
            "training_example_id": "training-1",
            "dataset_version": "dataset-0.1.0",
            "correction_id": "correction-1",
            "video_id": "video-1",
            "sport": "football",
            "interval_start": 12,
            "interval_end": 13,
            "timebase": "seconds",
            "label": "football.event.shot",
            "source": "corrected",
            "correction_type": "modify",
            "edit_operation": "relabel",
            "learning_mode": "training",
            "trust_weight": 0.8,
            "ontology_version": "football-2026-05-06",
            "source_prediction_ids": ["prediction-1"],
            "source_model_versions": ["fusion-local-0.1.0"],
            "source_ontology_versions": ["football-2026-05-06"],
            "evidence_snapshot": [sample_evidence()],
            "split": "train",
        }

        self.assertIs(validate_training_dataset_record(record, ontology=sample_ontology()), record)

    def test_training_dataset_record_rejects_unknown_label(self) -> None:
        record = {
            "training_example_id": "training-1",
            "dataset_version": "dataset-0.1.0",
            "correction_id": "correction-1",
            "video_id": "video-1",
            "sport": "football",
            "interval_start": 12,
            "interval_end": 13,
            "timebase": "seconds",
            "label": "football.event.not-in-ontology",
            "source": "corrected",
            "correction_type": "modify",
            "edit_operation": "relabel",
            "learning_mode": "training",
            "trust_weight": 0.8,
            "ontology_version": "football-2026-05-06",
            "source_prediction_ids": ["prediction-1"],
            "source_model_versions": ["fusion-local-0.1.0"],
            "source_ontology_versions": ["football-2026-05-06"],
            "evidence_snapshot": [sample_evidence()],
            "split": "train",
        }

        with self.assertRaises(ContractValidationError) as context:
            validate_training_dataset_record(record, ontology=sample_ontology())

        self.assertIn("unknown ontology label", str(context.exception))

    def test_non_accepted_correction_has_zero_trust_weight(self) -> None:
        correction = sample_correction()
        correction["review_status"] = "pending"

        with self.assertRaises(ContractValidationError) as context:
            validate_human_correction(correction, ontology=sample_ontology())

        self.assertIn("trust_weight must be 0 unless review_status is accepted", str(context.exception))


if __name__ == "__main__":
    unittest.main()
