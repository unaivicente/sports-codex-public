"""Backend import surface for shared contract validation."""

from __future__ import annotations

from typing import Any, Mapping

from packages.contracts import (
    CONTRACT_VERSION,
    contract_metadata,
    load_schema,
    validate_human_correction,
    validate_ontology,
    validate_prediction,
    validate_training_dataset_record,
)


def api_response(data: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """Build an API response that exposes the active contract version."""

    response: dict[str, Any] = dict(contract_metadata())
    if data is not None:
        response["data"] = dict(data)
    response.update(extra)
    return response


def health_response() -> dict[str, str]:
    """Return a minimal local API health payload."""

    return {"status": "ok", "contract_version": CONTRACT_VERSION}


__all__ = [
    "CONTRACT_VERSION",
    "api_response",
    "health_response",
    "load_schema",
    "validate_human_correction",
    "validate_ontology",
    "validate_prediction",
    "validate_training_dataset_record",
]
