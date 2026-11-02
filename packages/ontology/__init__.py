"""Local ontology definitions and helpers."""

from .evolution import (
    OntologyEvolutionError,
    add_label,
    active_labels,
    deprecate_label,
    deprecated_label_map,
    evolve_ontology,
    resolve_label_reference,
)
from .examples import get_ontology, list_ontologies
from .loader import (
    DEFAULT_ONTOLOGY_DIR,
    OntologyLoaderError,
    OntologyNotFoundError,
    OntologyValidationError,
    get_ontology_metadata,
    list_available_sports,
    load_ontology,
)

__all__ = [
    "DEFAULT_ONTOLOGY_DIR",
    "OntologyEvolutionError",
    "OntologyLoaderError",
    "OntologyNotFoundError",
    "OntologyValidationError",
    "add_label",
    "active_labels",
    "deprecate_label",
    "deprecated_label_map",
    "evolve_ontology",
    "get_ontology",
    "get_ontology_metadata",
    "list_available_sports",
    "list_ontologies",
    "load_ontology",
    "resolve_label_reference",
]
