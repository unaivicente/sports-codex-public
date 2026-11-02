"""Example local ontologies used by the MVP shell.

These definitions are data fixtures for local development. Mock prediction code
must select labels from these ontology payloads instead of embedding sport event
labels in inference logic.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

OntologyPayload = dict[str, Any]

_ONTOLOGIES: tuple[OntologyPayload, ...] = (
    {
        "ontology_id": "football-local-mvp",
        "sport_id": "football",
        "sport_display_name": "Football",
        "ontology_version": "football-local-2026-05-11",
        "display_name": "Football",
        "labels": [
            {
                "label_id": "football.phase.open_play",
                "label_type": "phase",
                "display_name": "Open play",
                "description": "General active play between stoppages.",
            },
            {
                "label_id": "football.event.pass",
                "label_type": "event",
                "display_name": "Pass",
                "description": "A player moves the ball to a teammate.",
            },
            {
                "label_id": "football.event.shot",
                "label_type": "event",
                "display_name": "Shot",
                "description": "A player attempts to score.",
            },
        ],
        "transition_rules": [
            {
                "from_label": "football.phase.open_play",
                "to_label": "football.event.pass",
                "rule_type": "allowed_during",
                "max_gap_seconds": 5,
            },
            {
                "from_label": "football.event.pass",
                "to_label": "football.event.shot",
                "rule_type": "allowed_after",
                "max_gap_seconds": 20,
            },
        ],
    },
    {
        "ontology_id": "basketball-local-mvp",
        "sport_id": "basketball",
        "sport_display_name": "Basketball",
        "ontology_version": "basketball-local-2026-05-11",
        "display_name": "Basketball",
        "labels": [
            {
                "label_id": "basketball.phase.half_court",
                "label_type": "phase",
                "display_name": "Half-court offense",
                "description": "Settled offensive possession in the front court.",
            },
            {
                "label_id": "basketball.event.pass",
                "label_type": "event",
                "display_name": "Pass",
                "description": "A player moves the ball to a teammate.",
            },
            {
                "label_id": "basketball.event.shot_attempt",
                "label_type": "event",
                "display_name": "Shot attempt",
                "description": "A player attempts a field goal.",
            },
        ],
        "transition_rules": [
            {
                "from_label": "basketball.phase.half_court",
                "to_label": "basketball.event.pass",
                "rule_type": "allowed_during",
                "max_gap_seconds": 5,
            },
            {
                "from_label": "basketball.event.pass",
                "to_label": "basketball.event.shot_attempt",
                "rule_type": "allowed_after",
                "max_gap_seconds": 24,
            },
        ],
    },
)


def list_ontologies() -> list[OntologyPayload]:
    """Return all bundled local ontologies as mutable response payloads."""

    return deepcopy(list(_ONTOLOGIES))


def get_ontology(ontology_id: str | None = None) -> OntologyPayload:
    """Return one bundled ontology by id, or the default ontology."""

    ontologies = list_ontologies()
    if ontology_id is None:
        return ontologies[0]

    for ontology in ontologies:
        if ontology["ontology_id"] == ontology_id:
            return ontology

    valid_ids = ", ".join(ontology["ontology_id"] for ontology in ontologies)
    raise KeyError(f"unknown ontology_id {ontology_id!r}; expected one of {valid_ids}")
