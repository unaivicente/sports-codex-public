"""Local extractor interfaces and mock implementations."""

from .interfaces import (
    ASRExtractor,
    AudioExtractor,
    EvidencePayload,
    ExtractionRequest,
    Extractor,
    ExtractorModality,
    OCRExtractor,
    SUPPORTED_MODALITIES,
    VisualExtractor,
    require_supported_modality,
)
from .mock import MOCK_EXTRACTOR_VERSION, MockExtractor, build_mock_extractors

__all__ = [
    "ASRExtractor",
    "AudioExtractor",
    "EvidencePayload",
    "ExtractionRequest",
    "Extractor",
    "ExtractorModality",
    "MOCK_EXTRACTOR_VERSION",
    "MockExtractor",
    "OCRExtractor",
    "SUPPORTED_MODALITIES",
    "VisualExtractor",
    "build_mock_extractors",
    "require_supported_modality",
]
