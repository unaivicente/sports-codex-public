"""Local model discovery, evaluation, and registry helpers."""

from .discovery import (
    ALLOWED_DISCOVERY_TRIGGERS,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_TASKS_BY_MODALITY,
    DISCOVERY_SERVICE_VERSION,
    FileModelRegistry,
    HuggingFaceModelSource,
    ModelCandidate,
    ModelDiscoveryEvaluationService,
    SmokeTestSampleClip,
    StaticCandidateSource,
    default_seed_candidates,
)

__all__ = [
    "ALLOWED_DISCOVERY_TRIGGERS",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_TASKS_BY_MODALITY",
    "DISCOVERY_SERVICE_VERSION",
    "FileModelRegistry",
    "HuggingFaceModelSource",
    "ModelCandidate",
    "ModelDiscoveryEvaluationService",
    "SmokeTestSampleClip",
    "StaticCandidateSource",
    "default_seed_candidates",
]
