"""Deterministic local mock extractors backed by ontology definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from packages.contracts import validate_evidence, validate_ontology
from packages.ontology import active_labels

from .interfaces import (
    SUPPORTED_MODALITIES,
    EvidencePayload,
    ExtractionRequest,
    ExtractorModality,
    require_supported_modality,
)

MOCK_EXTRACTOR_VERSION = "mock-extractor-local-0.1.0"


@dataclass(frozen=True)
class MockExtractor:
    """Ontology-driven mock implementation of the shared extractor interface."""

    modality: ExtractorModality
    model_version: str = MOCK_EXTRACTOR_VERSION
    evidence_type: str = "mock_ontology_signal"

    def __post_init__(self) -> None:
        object.__setattr__(self, "modality", require_supported_modality(self.modality))
        if not self.model_version:
            raise ValueError("model_version must be a non-empty string")
        if not self.evidence_type:
            raise ValueError("evidence_type must be a non-empty string")

    def extract(self, request: ExtractionRequest) -> list[EvidencePayload]:
        """Return one timestamped evidence item selected from the request ontology."""

        validate_ontology(request.ontology)
        labels = active_labels(request.ontology)
        if not labels:
            raise ValueError(f"ontology {request.ontology['ontology_version']} has no active labels")
        label = labels[int(request.timestamp) % len(labels)]
        ontology_version = request.ontology["ontology_version"]
        label_id = label["label_id"]
        confidence = _mock_confidence(self.modality)

        evidence: EvidencePayload = {
            "evidence_id": str(
                uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        (
                            request.video_id,
                            str(request.timestamp),
                            self.modality,
                            ontology_version,
                            label_id,
                            self.model_version,
                        )
                    ),
                )
            ),
            "modality": self.modality,
            "timestamp": request.timestamp,
            "type": self.evidence_type,
            "value": {
                "ontology_label_id": label_id,
                "label_type": label["label_type"],
                "ontology_version": ontology_version,
                "timebase": request.timebase,
            },
            "confidence": confidence,
            "source_model_version": self.model_version,
        }
        validate_evidence(evidence)
        return [evidence]


def build_mock_extractors(
    *,
    model_version: str = MOCK_EXTRACTOR_VERSION,
) -> tuple[MockExtractor, ...]:
    """Build one mock extractor for each MVP modality."""

    return tuple(
        MockExtractor(modality=modality, model_version=model_version)
        for modality in SUPPORTED_MODALITIES
    )


def _mock_confidence(modality: str) -> float:
    modality_index = SUPPORTED_MODALITIES.index(require_supported_modality(modality))
    return round(0.55 + (modality_index * 0.08), 2)
