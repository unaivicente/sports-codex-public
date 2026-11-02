from __future__ import annotations

import unittest

from packages.contracts import ContractValidationError, validate_evidence
from packages.extraction import (
    SUPPORTED_MODALITIES,
    ExtractionRequest,
    Extractor,
    MockExtractor,
    build_mock_extractors,
)
from packages.ontology import get_ontology


def custom_ontology() -> dict:
    return {
        "ontology_id": "custom-local-mvp",
        "ontology_version": "custom-local-2026-05-28",
        "labels": [
            {
                "label_id": "custom.phase.alpha",
                "label_type": "phase",
                "display_name": "Alpha",
            },
            {
                "label_id": "custom.event.beta",
                "label_type": "event",
                "display_name": "Beta",
            },
        ],
    }


class ExtractionContractTests(unittest.TestCase):
    def test_common_interface_covers_mvp_modalities(self) -> None:
        extractors = build_mock_extractors()

        self.assertEqual(tuple(extractor.modality for extractor in extractors), SUPPORTED_MODALITIES)
        for extractor in extractors:
            self.assertIsInstance(extractor, Extractor)
            self.assertTrue(callable(extractor.extract))
            self.assertTrue(extractor.model_version)

    def test_mock_extractors_return_timestamped_evidence_for_each_modality(self) -> None:
        ontology = get_ontology("football-local-mvp")
        request = ExtractionRequest(video_id="video-1", timestamp=8, ontology=ontology)
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}

        for extractor in build_mock_extractors():
            evidence_items = extractor.extract(request)

            self.assertEqual(len(evidence_items), 1)
            evidence = evidence_items[0]
            self.assertEqual(evidence["timestamp"], request.timestamp)
            self.assertEqual(evidence["modality"], extractor.modality)
            self.assertEqual(evidence["source_model_version"], extractor.model_version)
            self.assertIn(evidence["value"]["ontology_label_id"], ontology_label_ids)
            self.assertEqual(evidence["value"]["ontology_version"], ontology["ontology_version"])
            self.assertIs(validate_evidence(evidence), evidence)

    def test_mock_extractor_selects_labels_from_supplied_ontology(self) -> None:
        ontology = custom_ontology()
        request = ExtractionRequest(video_id="video-2", timestamp=1, ontology=ontology)

        evidence = MockExtractor("ocr").extract(request)[0]

        self.assertEqual(evidence["value"]["ontology_label_id"], "custom.event.beta")
        self.assertEqual(evidence["value"]["label_type"], "event")
        self.assertEqual(evidence["value"]["ontology_version"], "custom-local-2026-05-28")

    def test_unsupported_modality_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as context:
            MockExtractor("radar")  # type: ignore[arg-type]

        self.assertIn("unsupported extractor modality", str(context.exception))

    def test_evidence_validator_requires_timestamp(self) -> None:
        evidence = MockExtractor("vision").extract(
            ExtractionRequest(video_id="video-3", timestamp=0, ontology=custom_ontology())
        )[0]
        del evidence["timestamp"]

        with self.assertRaises(ContractValidationError) as context:
            validate_evidence(evidence)

        self.assertIn("evidence.timestamp", str(context.exception))


if __name__ == "__main__":
    unittest.main()
