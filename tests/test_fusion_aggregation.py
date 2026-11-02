from __future__ import annotations

import unittest

from packages.contracts import ContractValidationError
from packages.fusion import aggregate_evidence_by_second


def evidence(
    evidence_id: str,
    modality: str,
    timestamp: int | float,
    confidence: float = 0.7,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "modality": modality,
        "timestamp": timestamp,
        "type": "mock_ontology_signal",
        "value": {
            "ontology_label_id": "custom.event.alpha",
            "ontology_version": "custom-local-2026-05-28",
        },
        "confidence": confidence,
        "source_model_version": f"{modality}-local-0.1.0",
    }


class FusionAggregationTests(unittest.TestCase):
    def test_groups_evidence_into_one_second_windows(self) -> None:
        windows = aggregate_evidence_by_second(
            [
                evidence("vision-0", "vision", 0.1),
                evidence("audio-0", "audio", 0.9),
                evidence("ocr-1", "ocr", 1.0),
                evidence("asr-1", "asr", 1.75),
            ]
        )

        self.assertEqual([window["timestamp"] for window in windows], [0, 1])
        self.assertEqual(windows[0]["interval_start"], 0)
        self.assertEqual(windows[0]["interval_end"], 1)
        self.assertEqual(windows[1]["interval_start"], 1)
        self.assertEqual(windows[1]["interval_end"], 2)
        self.assertEqual(
            [item["evidence_id"] for item in windows[0]["evidence"]],
            ["vision-0", "audio-0"],
        )
        self.assertEqual(
            [item["evidence_id"] for item in windows[1]["evidence"]],
            ["ocr-1", "asr-1"],
        )

    def test_preserves_multiple_modalities_in_each_window(self) -> None:
        items = [
            evidence("audio-2", "audio", 2.2),
            evidence("vision-2", "vision", 2.3),
            evidence("tracking-2", "tracking", 2.4),
        ]

        windows = aggregate_evidence_by_second(items, expected_modalities=("vision", "audio"))

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["evidence"], items)
        self.assertEqual(windows[0]["modalities_present"], ["vision", "audio", "tracking"])
        self.assertEqual(windows[0]["missing_modalities"], [])

    def test_missing_modalities_are_reported_without_placeholder_evidence(self) -> None:
        windows = aggregate_evidence_by_second(
            [evidence("vision-4", "vision", 4)],
            expected_modalities=("vision", "audio", "ocr"),
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["modalities_present"], ["vision"])
        self.assertEqual(windows[0]["missing_modalities"], ["audio", "ocr"])
        self.assertEqual(len(windows[0]["evidence"]), 1)

    def test_empty_evidence_input_returns_no_windows(self) -> None:
        self.assertEqual(aggregate_evidence_by_second([]), [])

    def test_invalid_evidence_is_rejected_by_contract_validator(self) -> None:
        invalid = evidence("bad", "vision", 0)
        del invalid["source_model_version"]

        with self.assertRaises(ContractValidationError) as context:
            aggregate_evidence_by_second([invalid])

        self.assertIn("source_model_version", str(context.exception))


if __name__ == "__main__":
    unittest.main()
