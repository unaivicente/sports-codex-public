from __future__ import annotations

import unittest

from packages.contracts import validate_ontology, validate_prediction
from packages.ontology import (
    OntologyEvolutionError,
    active_labels,
    deprecated_label_map,
    evolve_ontology,
    resolve_label_reference,
)


def sample_ontology() -> dict:
    return {
        "ontology_id": "neutral-local",
        "sport_id": "neutral",
        "ontology_version": "neutral-2026-05-30-a",
        "labels": [
            {
                "label_id": "neutral.phase.active",
                "label_type": "phase",
                "display_name": "Active",
            },
            {
                "label_id": "neutral.event.old",
                "label_type": "event",
                "display_name": "Old event",
            },
        ],
        "transition_rules": [
            {
                "from_label": "neutral.phase.active",
                "to_label": "neutral.event.old",
                "rule_type": "allowed_after",
            }
        ],
        "deprecated_labels": [],
    }


def sample_prediction(ontology: dict) -> dict:
    return {
        "prediction_id": "prediction-old-label",
        "video_id": "video-1",
        "timestamp": 0,
        "interval_start": 0,
        "interval_end": 1,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": "neutral.event.old",
        "confidence": 0.7,
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "modality": "vision",
                "timestamp": 0,
                "type": "mock_ontology_signal",
                "value": {"ontology_label_id": "neutral.event.old"},
                "confidence": 0.65,
                "source_model_version": "mock-extractor-local-0.1.0",
            }
        ],
        "model_version": "mock-fusion-local-0.1.0",
        "ontology_version": ontology["ontology_version"],
        "created_at": "2026-05-30T00:00:00Z",
    }


class OntologyEvolutionWorkflowTests(unittest.TestCase):
    def test_evolve_ontology_adds_labels_and_maps_deprecations_without_deleting_old_label(self) -> None:
        ontology = sample_ontology()

        evolved = evolve_ontology(
            ontology,
            ontology_version="neutral-2026-05-30-b",
            labels_to_add=(
                {
                    "label_id": "neutral.event.new",
                    "label_type": "event",
                    "display_name": "New event",
                },
            ),
            deprecated_label_mappings=(
                {
                    "label_id": "neutral.event.old",
                    "replacement_label_id": "neutral.event.new",
                    "reason": "split into clearer event class",
                },
            ),
            created_at="2026-05-30T00:01:00Z",
            change_id="ontology-change-1",
        )

        self.assertIs(validate_ontology(evolved), evolved)
        self.assertEqual(evolved["previous_ontology_version"], ontology["ontology_version"])
        self.assertEqual(evolved["ontology_version"], "neutral-2026-05-30-b")
        self.assertIn("neutral.event.old", {label["label_id"] for label in evolved["labels"]})
        self.assertIn("neutral.event.new", {label["label_id"] for label in evolved["labels"]})
        self.assertEqual(
            deprecated_label_map(evolved)["neutral.event.old"]["replacement_label_id"],
            "neutral.event.new",
        )
        self.assertEqual(
            [label["label_id"] for label in active_labels(evolved)],
            ["neutral.phase.active", "neutral.event.new"],
        )

    def test_old_predictions_remain_interpretable_through_source_version_and_mapping(self) -> None:
        original = sample_ontology()
        old_prediction = sample_prediction(original)
        self.assertIs(validate_prediction(old_prediction, ontology=original), old_prediction)

        evolved = evolve_ontology(
            original,
            ontology_version="neutral-2026-05-30-b",
            labels_to_add=(
                {
                    "label_id": "neutral.event.new",
                    "label_type": "event",
                    "display_name": "New event",
                },
            ),
            deprecated_label_mappings=(
                {
                    "label_id": "neutral.event.old",
                    "replacement_label_id": "neutral.event.new",
                },
            ),
            created_at="2026-05-30T00:01:00Z",
        )
        resolved = resolve_label_reference(evolved, old_prediction["label"])

        self.assertTrue(resolved["deprecated"])
        self.assertEqual(resolved["label"]["label_id"], "neutral.event.old")
        self.assertEqual(resolved["replacement_label"]["label_id"], "neutral.event.new")

    def test_evolution_rejects_missing_replacement_label(self) -> None:
        with self.assertRaisesRegex(OntologyEvolutionError, "replacement label"):
            evolve_ontology(
                sample_ontology(),
                ontology_version="neutral-2026-05-30-b",
                deprecated_label_mappings=(
                    {
                        "label_id": "neutral.event.old",
                        "replacement_label_id": "neutral.event.missing",
                    },
                ),
            )


if __name__ == "__main__":
    unittest.main()
