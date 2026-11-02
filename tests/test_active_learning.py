from __future__ import annotations

import unittest

from packages.contracts import validate_human_correction, validate_prediction
from packages.labelling.active_learning import (
    FREQUENT_CORRECTION_FLAG,
    LOW_CONFIDENCE_FLAG,
    MULTIMODAL_DISAGREEMENT_FLAG,
    ONTOLOGY_TRANSITION_CONFLICT_FLAG,
    RARE_LABEL_FLAG,
    build_active_learning_demo_inputs,
    build_active_learning_queue,
)


def sample_queue_ontology() -> dict:
    return {
        "ontology_id": "neutral-active-learning",
        "ontology_version": "neutral-active-learning-2026-05-30",
        "labels": [
            {
                "label_id": "neutral.phase.active",
                "label_type": "phase",
                "display_name": "Active",
            },
            {
                "label_id": "neutral.event.progression",
                "label_type": "event",
                "display_name": "Progression",
            },
            {
                "label_id": "neutral.event.finish",
                "label_type": "event",
                "display_name": "Finish",
            },
        ],
        "transition_rules": [
            {
                "from_label": "neutral.phase.active",
                "to_label": "neutral.event.progression",
                "rule_type": "allowed_during",
                "max_gap_seconds": 2,
            },
            {
                "from_label": "neutral.event.progression",
                "to_label": "neutral.event.finish",
                "rule_type": "allowed_after",
                "max_gap_seconds": 2,
            },
        ],
        "thresholds": {"default_confidence": 0.55},
    }


class ActiveLearningQueueTests(unittest.TestCase):
    def test_queue_flags_segments_for_every_learning_signal(self) -> None:
        ontology = sample_queue_ontology()
        predictions, corrections = build_active_learning_demo_inputs(
            ontology,
            video_id="local-video-queue-test",
            created_at="2026-05-30T12:00:00Z",
        )
        queue = build_active_learning_queue(
            predictions=predictions,
            corrections=corrections,
            ontology=ontology,
            generated_at="2026-05-30T12:00:00Z",
        )
        entries = queue["queue"]
        flags = {flag for entry in entries for flag in entry["flags"]}
        scores = [entry["learning_value_score"] for entry in entries]
        ontology_labels = {label["label_id"] for label in ontology["labels"]}

        self.assertTrue(
            {
                LOW_CONFIDENCE_FLAG,
                MULTIMODAL_DISAGREEMENT_FLAG,
                ONTOLOGY_TRANSITION_CONFLICT_FLAG,
                RARE_LABEL_FLAG,
                FREQUENT_CORRECTION_FLAG,
            }.issubset(flags)
        )
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(entries[0]["rank"], 1)
        self.assertGreater(entries[0]["learning_value_score"], entries[-1]["learning_value_score"])

        for prediction in predictions:
            self.assertIs(validate_prediction(prediction, ontology=ontology), prediction)
        for correction in corrections:
            self.assertIs(validate_human_correction(correction, ontology=ontology), correction)
            self.assertEqual(
                correction["source_predictions"][0]["model_version"],
                predictions[2]["model_version"],
            )

        for entry in entries:
            self.assertIn(entry["label"], ontology_labels)
            self.assertEqual(entry["source_prediction"]["prediction_id"], entry["source_prediction_id"])
            self.assertEqual(entry["source_prediction"]["model_version"], entry["model_version"])
            self.assertEqual(entry["source_prediction"]["ontology_version"], entry["ontology_version"])
            self.assertGreaterEqual(len(entry["evidence"]), 1)

    def test_frequent_correction_reason_preserves_correction_provenance(self) -> None:
        ontology = sample_queue_ontology()
        predictions, corrections = build_active_learning_demo_inputs(
            ontology,
            video_id="local-video-corrections-test",
            created_at="2026-05-30T12:00:00Z",
        )
        queue = build_active_learning_queue(
            predictions=predictions,
            corrections=corrections,
            ontology=ontology,
            generated_at="2026-05-30T12:00:00Z",
        )
        frequent_entries = [
            entry for entry in queue["queue"] if FREQUENT_CORRECTION_FLAG in entry["flags"]
        ]

        self.assertEqual(len(frequent_entries), 1)
        reason = next(
            reason
            for reason in frequent_entries[0]["review_reasons"]
            if reason["flag"] == FREQUENT_CORRECTION_FLAG
        )

        self.assertEqual(reason["evidence"]["correction_count"], 2)
        self.assertEqual(
            reason["evidence"]["source_model_versions"],
            [predictions[2]["model_version"]],
        )
        self.assertEqual(
            reason["evidence"]["source_ontology_versions"],
            [ontology["ontology_version"]],
        )


if __name__ == "__main__":
    unittest.main()
