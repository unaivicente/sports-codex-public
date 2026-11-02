"""Load local sport ontologies and expose stable metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from packages.contracts import ContractValidationError, CONTRACT_VERSION, load_schema, validate_ontology

DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parent / "definitions"


class OntologyLoaderError(ValueError):
    """Base error for local ontology loading failures."""


class OntologyNotFoundError(OntologyLoaderError):
    """Raised when a requested sport has no local ontology file."""


class OntologyValidationError(OntologyLoaderError):
    """Raised when a local ontology file does not satisfy the schema."""

    def __init__(self, path: Path, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        super().__init__(f"{path}: " + "; ".join(errors))


def list_available_sports(
    ontology_dir: Path | str = DEFAULT_ONTOLOGY_DIR,
) -> list[dict[str, Any]]:
    """Return metadata for every valid ontology file in the local directory."""

    entries: list[dict[str, Any]] = []
    for path in _ontology_files(Path(ontology_dir)):
        ontology = _load_ontology_file(path)
        entries.append(_metadata_for_ontology(ontology, sport=path.stem))
    return entries


def get_ontology_metadata(
    sport: str,
    ontology_dir: Path | str = DEFAULT_ONTOLOGY_DIR,
) -> dict[str, Any]:
    """Return metadata for a selected sport ontology."""

    path = _find_ontology_path(sport, Path(ontology_dir))
    ontology = _load_ontology_file(path)
    return _metadata_for_ontology(ontology, sport=path.stem)


def load_ontology(
    sport: str,
    ontology_dir: Path | str = DEFAULT_ONTOLOGY_DIR,
) -> Mapping[str, Any]:
    """Load and validate a selected sport ontology payload."""

    path = _find_ontology_path(sport, Path(ontology_dir))
    return _load_ontology_file(path)


def _ontology_files(ontology_dir: Path) -> list[Path]:
    if not ontology_dir.exists():
        return []
    return sorted(path for path in ontology_dir.iterdir() if path.is_file() and path.suffix == ".json")


def _find_ontology_path(sport: str, ontology_dir: Path) -> Path:
    requested = sport.strip().lower()
    for path in _ontology_files(ontology_dir):
        if path.stem.lower() == requested:
            return path
    raise OntologyNotFoundError(f"unknown sport ontology {sport!r}")


def _load_ontology_file(path: Path) -> Mapping[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise OntologyValidationError(path, [f"invalid JSON: {exc.msg}"]) from exc

    if not isinstance(payload, Mapping):
        raise OntologyValidationError(path, ["ontology file must contain a JSON object"])

    try:
        validate_ontology(payload)
    except ContractValidationError as exc:
        raise OntologyValidationError(path, exc.errors) from exc

    return payload


def _metadata_for_ontology(ontology: Mapping[str, Any], *, sport: str) -> dict[str, Any]:
    labels = ontology.get("labels", [])
    transition_rules = ontology.get("transition_rules", [])
    deprecated_labels = ontology.get("deprecated_labels", [])
    schema = load_schema("ontology")

    label_type_counts: dict[str, int] = {}
    if isinstance(labels, list):
        for label in labels:
            if isinstance(label, Mapping):
                label_type = label.get("label_type")
                if isinstance(label_type, str):
                    label_type_counts[label_type] = label_type_counts.get(label_type, 0) + 1

    metadata = ontology.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}

    return {
        "sport": sport,
        "ontology_id": ontology["ontology_id"],
        "ontology_version": ontology["ontology_version"],
        "contract_version": CONTRACT_VERSION,
        "schema_id": schema.get("$id"),
        "schema_title": schema.get("title"),
        "label_count": len(labels) if isinstance(labels, list) else 0,
        "label_type_counts": dict(sorted(label_type_counts.items())),
        "transition_rule_count": len(transition_rules) if isinstance(transition_rules, list) else 0,
        "deprecated_label_count": (
            len(deprecated_labels) if isinstance(deprecated_labels, list) else 0
        ),
        "previous_ontology_version": ontology.get("previous_ontology_version"),
        "metadata": dict(metadata),
    }
