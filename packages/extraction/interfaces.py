"""Extractor interface contracts for local multimodal evidence producers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, cast, runtime_checkable

ExtractorModality = Literal["vision", "audio", "ocr", "asr"]
SUPPORTED_MODALITIES: tuple[ExtractorModality, ...] = ("vision", "audio", "ocr", "asr")
EvidencePayload = dict[str, Any]


@dataclass(frozen=True)
class ExtractionRequest:
    """Context shared by visual, audio, OCR, and ASR extractors."""

    video_id: str
    timestamp: int | float
    ontology: Mapping[str, Any]
    timebase: str = "seconds"

    def __post_init__(self) -> None:
        if not self.video_id:
            raise ValueError("video_id must be a non-empty string")
        if not isinstance(self.timestamp, (int, float)) or isinstance(self.timestamp, bool):
            raise ValueError("timestamp must be a number")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.timebase:
            raise ValueError("timebase must be a non-empty string")


@runtime_checkable
class Extractor(Protocol):
    """Common interface implemented by every local extractor."""

    modality: ExtractorModality
    model_version: str

    def extract(self, request: ExtractionRequest) -> list[EvidencePayload]:
        """Return timestamped evidence payloads for the requested interval."""


@runtime_checkable
class VisualExtractor(Extractor, Protocol):
    modality: Literal["vision"]


@runtime_checkable
class AudioExtractor(Extractor, Protocol):
    modality: Literal["audio"]


@runtime_checkable
class OCRExtractor(Extractor, Protocol):
    modality: Literal["ocr"]


@runtime_checkable
class ASRExtractor(Extractor, Protocol):
    modality: Literal["asr"]


def require_supported_modality(modality: str) -> ExtractorModality:
    """Return a typed modality or raise for unsupported extractor contracts."""

    if modality not in SUPPORTED_MODALITIES:
        expected = ", ".join(SUPPORTED_MODALITIES)
        raise ValueError(f"unsupported extractor modality {modality!r}; expected one of {expected}")
    return cast(ExtractorModality, modality)
