"""Local ontology registry used by the API shell."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from packages.contracts import validate_ontology

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_DEFINITIONS_DIR = REPO_ROOT / "packages" / "ontology" / "definitions"


class OntologyNotFoundError(LookupError):
    """Raised when an ontology lookup cannot be satisfied locally."""


def load_ontologies() -> list[dict[str, Any]]:
    """Load and validate all local ontology definitions."""

    ontologies: list[dict[str, Any]] = []
    for path in sorted(ONTOLOGY_DEFINITIONS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            ontology = json.load(handle)
        validate_ontology(ontology)
        ontologies.append(ontology)
    return ontologies


def available_ontologies() -> list[dict[str, Any]]:
    """Return defensive copies of all available local ontologies."""

    return copy.deepcopy(load_ontologies())


def ontology_summaries(*, include_labels: bool = False) -> list[dict[str, Any]]:
    """Return compact metadata suitable for API discovery endpoints."""

    summaries: list[dict[str, Any]] = []
    for ontology in load_ontologies():
        summary: dict[str, Any] = {
            "ontology_id": ontology["ontology_id"],
            "ontology_version": ontology["ontology_version"],
            "sport_id": ontology.get("sport_id", "unknown"),
            "sport_display_name": ontology.get("sport_display_name", "Unknown"),
            "label_count": len(ontology.get("labels", [])),
            "deprecated_label_count": len(ontology.get("deprecated_labels", [])),
            "previous_ontology_version": ontology.get("previous_ontology_version"),
        }
        if include_labels:
            summary["labels"] = copy.deepcopy(ontology.get("labels", []))
        summaries.append(summary)
    return summaries


def sports_catalog() -> list[dict[str, Any]]:
    """Group ontology metadata by sport for local discovery."""

    sports: dict[str, dict[str, Any]] = {}
    for summary in ontology_summaries():
        sport_id = summary["sport_id"]
        sport = sports.setdefault(
            sport_id,
            {
                "sport_id": sport_id,
                "display_name": summary["sport_display_name"],
                "ontologies": [],
            },
        )
        sport["ontologies"].append(
            {
                "ontology_id": summary["ontology_id"],
                "ontology_version": summary["ontology_version"],
                "label_count": summary["label_count"],
            }
        )
    return list(sports.values())


def get_ontology(
    *,
    ontology_version: str | None = None,
    sport_id: str | None = None,
) -> dict[str, Any]:
    """Resolve a local ontology by version or sport."""

    ontologies = load_ontologies()
    if not ontologies:
        raise OntologyNotFoundError("no local ontology definitions are available")

    if ontology_version is not None:
        for ontology in ontologies:
            if ontology.get("ontology_version") == ontology_version:
                return copy.deepcopy(ontology)
        raise OntologyNotFoundError(f"unknown ontology_version {ontology_version!r}")

    if sport_id is not None:
        for ontology in ontologies:
            if ontology.get("sport_id") == sport_id:
                return copy.deepcopy(ontology)
        raise OntologyNotFoundError(f"unknown sport_id {sport_id!r}")

    return copy.deepcopy(ontologies[0])
