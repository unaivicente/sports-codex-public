"""One-second aggregation for local multimodal evidence payloads."""

from __future__ import annotations

from math import floor
from typing import Any, Iterable, Mapping

from packages.contracts import validate_evidence
from packages.extraction import SUPPORTED_MODALITIES

EvidenceWindowPayload = dict[str, Any]


def aggregate_evidence_by_second(
    evidence_items: Iterable[Mapping[str, Any]],
    *,
    expected_modalities: Iterable[str] | None = SUPPORTED_MODALITIES,
    timebase: str = "seconds",
) -> list[EvidenceWindowPayload]:
    """Group timestamped evidence into one-second windows.

    The original evidence payloads are retained in their input order within each
    window. Missing expected modalities are reported as metadata instead of
    producing an error or placeholder evidence.
    """

    if not timebase:
        raise ValueError("timebase must be a non-empty string")

    expected_modality_order = _normalise_expected_modalities(expected_modalities)
    grouped: dict[int, list[Mapping[str, Any]]] = {}

    for item in evidence_items:
        validate_evidence(item)
        timestamp = item["timestamp"]
        second = int(floor(timestamp))
        grouped.setdefault(second, []).append(item)

    windows: list[EvidenceWindowPayload] = []
    for second in sorted(grouped):
        evidence = list(grouped[second])
        modalities_present = _modalities_present(evidence, expected_modality_order)
        missing_modalities = [
            modality for modality in expected_modality_order if modality not in modalities_present
        ]

        windows.append(
            {
                "timestamp": second,
                "interval_start": second,
                "interval_end": second + 1,
                "duration_seconds": 1,
                "timebase": timebase,
                "evidence": evidence,
                "modalities_present": modalities_present,
                "missing_modalities": missing_modalities,
            }
        )

    return windows


def _normalise_expected_modalities(expected_modalities: Iterable[str] | None) -> tuple[str, ...]:
    if expected_modalities is None:
        return ()

    modalities: list[str] = []
    seen: set[str] = set()
    for modality in expected_modalities:
        if not isinstance(modality, str) or not modality:
            raise ValueError("expected_modalities must contain non-empty strings")
        if modality not in seen:
            seen.add(modality)
            modalities.append(modality)
    return tuple(modalities)


def _modalities_present(
    evidence_items: list[Mapping[str, Any]],
    expected_modalities: tuple[str, ...],
) -> list[str]:
    present = {str(item["modality"]) for item in evidence_items}
    ordered = [modality for modality in expected_modalities if modality in present]
    extra: list[str] = []
    seen_extra: set[str] = set()
    for item in evidence_items:
        modality = str(item["modality"])
        if modality in expected_modalities or modality in seen_extra:
            continue
        seen_extra.add(modality)
        extra.append(modality)
    return ordered + extra
