"""One-time foundation model discovery and local evaluation service.

The service is intentionally explicit: callers must invoke it with a setup or
admin refresh trigger. It can query Hugging Face metadata, but it never performs
remote inference and never mutates production model configuration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import log1p
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from packages.contracts import validate_evidence, validate_ontology
from packages.extraction import SUPPORTED_MODALITIES, require_supported_modality

DISCOVERY_SERVICE_VERSION = "model-discovery-local-0.1.0"
ALLOWED_DISCOVERY_TRIGGERS = ("setup", "admin_refresh")
DEFAULT_REGISTRY_PATH = Path("data/model_registry/model_discovery_registry.json")
REGISTRY_SCHEMA_VERSION = "local-model-discovery-registry-v1"

DEFAULT_TASKS_BY_MODALITY: dict[str, tuple[str, ...]] = {
    "vision": (
        "zero-shot-image-classification",
        "object-detection",
        "video-classification",
    ),
    "audio": ("audio-classification",),
    "ocr": ("image-to-text",),
    "asr": ("automatic-speech-recognition",),
}


class ModelCandidateSource(Protocol):
    """Metadata-only model search source."""

    source_name: str

    def search_models(
        self,
        *,
        modality: str,
        task: str,
        limit: int,
    ) -> list["ModelCandidate"]:
        """Return candidate models for a modality/task pair."""


@dataclass(frozen=True)
class ModelCandidate:
    """Candidate foundation model metadata discovered from a source."""

    model_id: str
    modality: str
    task: str
    source: str
    model_version: str | None = None
    pipeline_tag: str | None = None
    tags: tuple[str, ...] = ()
    license: str | None = None
    downloads: int | None = None
    likes: int | None = None
    last_modified: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "modality", require_supported_modality(self.modality))
        if not self.model_id:
            raise ValueError("model_id must be a non-empty string")
        if not self.task:
            raise ValueError("task must be a non-empty string")
        if not self.source:
            raise ValueError("source must be a non-empty string")
        if self.model_version is None:
            object.__setattr__(self, "model_version", self.model_id)
        object.__setattr__(self, "tags", tuple(str(tag) for tag in self.tags if str(tag)))

    def to_record(self) -> dict[str, Any]:
        """Return registry-ready candidate metadata."""

        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "modality": self.modality,
            "task": self.task,
            "source": self.source,
            "pipeline_tag": self.pipeline_tag,
            "tags": list(self.tags),
            "license": self.license,
            "downloads": self.downloads,
            "likes": self.likes,
            "last_modified": self.last_modified,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SmokeTestSampleClip:
    """Local sample clip descriptor used for metadata-only smoke tests."""

    sample_clip_id: str
    duration_seconds: float = 1
    timestamps: tuple[int | float, ...] = (0,)
    modalities: tuple[str, ...] = SUPPORTED_MODALITIES
    local_path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sample_clip_id:
            raise ValueError("sample_clip_id must be a non-empty string")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        timestamps = tuple(self.timestamps or (0,))
        for timestamp in timestamps:
            if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
                raise ValueError("sample clip timestamps must be numeric")
            if timestamp < 0:
                raise ValueError("sample clip timestamps must be >= 0")
            if timestamp >= self.duration_seconds:
                raise ValueError("sample clip timestamps must be inside duration_seconds")
        modalities = tuple(require_supported_modality(modality) for modality in self.modalities)
        if not modalities:
            raise ValueError("sample clip modalities must not be empty")
        object.__setattr__(self, "timestamps", timestamps)
        object.__setattr__(self, "modalities", modalities)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SmokeTestSampleClip":
        """Build a sample clip descriptor from API or test input."""

        return cls(
            sample_clip_id=str(payload.get("sample_clip_id", "")),
            duration_seconds=float(payload.get("duration_seconds", 1)),
            timestamps=tuple(payload.get("timestamps", (0,))),
            modalities=tuple(payload.get("modalities", SUPPORTED_MODALITIES)),
            local_path=payload.get("local_path"),
            metadata=payload.get("metadata", {}),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "sample_clip_id": self.sample_clip_id,
            "duration_seconds": self.duration_seconds,
            "timestamps": list(self.timestamps),
            "modalities": list(self.modalities),
            "local_path": self.local_path,
            "metadata": dict(self.metadata),
        }


class StaticCandidateSource:
    """Deterministic candidate source for local setup, tests, and demos."""

    source_name = "static-local-seed"

    def __init__(self, candidates: Iterable[ModelCandidate]) -> None:
        self._candidates = tuple(candidates)

    def search_models(self, *, modality: str, task: str, limit: int) -> list[ModelCandidate]:
        require_supported_modality(modality)
        matches = [
            candidate
            for candidate in self._candidates
            if candidate.modality == modality and candidate.task == task
        ]
        return matches[:limit]


class HuggingFaceModelSource:
    """Hugging Face metadata search source.

    This source only reads model metadata from the public API. It does not
    download model weights, upload media, or call any inference endpoint.
    """

    source_name = "huggingface-metadata"

    def __init__(
        self,
        *,
        endpoint: str = "https://huggingface.co/api/models",
        timeout_seconds: float = 10,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search_models(self, *, modality: str, task: str, limit: int) -> list[ModelCandidate]:
        require_supported_modality(modality)
        if limit < 1:
            raise ValueError("limit must be >= 1")

        query = urlencode(
            {
                "pipeline_tag": task,
                "sort": "downloads",
                "direction": "-1",
                "limit": str(limit),
                "full": "true",
            }
        )
        request = Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": f"{DISCOVERY_SERVICE_VERSION} metadata-discovery"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, list):
            raise ValueError("Hugging Face model search returned a non-list payload")

        return [
            _candidate_from_huggingface_payload(item, modality=modality, task=task)
            for item in payload[:limit]
            if isinstance(item, Mapping)
        ]


@dataclass
class FileModelRegistry:
    """Append-only local JSON registry for discovery runs."""

    path: Path | str = DEFAULT_REGISTRY_PATH

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "runs": [],
            }
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid registry payload in {self.path}")
        payload.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
        payload.setdefault("runs", [])
        return payload

    def save_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        registry = self.load()
        registry["schema_version"] = REGISTRY_SCHEMA_VERSION
        registry["updated_at"] = _utc_now()
        registry.setdefault("runs", []).append(dict(run))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f"{self.path.name}.tmp")
        temp_path.write_text(
            json.dumps(registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)
        return registry


class ModelDiscoveryEvaluationService:
    """Discover, score, smoke-test, recommend, and persist model candidates."""

    def __init__(
        self,
        *,
        source: ModelCandidateSource,
        registry: FileModelRegistry | None = None,
    ) -> None:
        self.source = source
        self.registry = registry or FileModelRegistry()

    def discover_and_evaluate(
        self,
        *,
        trigger: str,
        ontology: Mapping[str, Any],
        tasks_by_modality: Mapping[str, Sequence[str]] | None = None,
        sample_clips: Sequence[SmokeTestSampleClip | Mapping[str, Any]] | None = None,
        limit_per_task: int = 5,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Run one explicit discovery/evaluation pass and persist the result."""

        if trigger not in ALLOWED_DISCOVERY_TRIGGERS:
            allowed = ", ".join(ALLOWED_DISCOVERY_TRIGGERS)
            raise ValueError(f"discovery trigger must be one of {allowed}")
        if limit_per_task < 1:
            raise ValueError("limit_per_task must be >= 1")

        validate_ontology(ontology)
        task_plan = _normalise_tasks(tasks_by_modality or DEFAULT_TASKS_BY_MODALITY)
        clips = _normalise_sample_clips(sample_clips)
        created_at = _utc_now()
        selected_run_id = run_id or str(
            uuid5(
                NAMESPACE_URL,
                f"{created_at}:{trigger}:{ontology['ontology_version']}:{self.source.source_name}",
            )
        )

        candidates = self._discover_candidates(task_plan, limit_per_task)
        scored_candidates = [
            self._evaluate_candidate(
                candidate,
                ontology=ontology,
                sample_clips=clips,
                tasks_by_modality=task_plan,
            )
            for candidate in candidates
        ]
        scored_candidates.sort(
            key=lambda candidate: (
                candidate["score"]["total"],
                candidate["downloads"] or 0,
                candidate["model_id"],
            ),
            reverse=True,
        )
        recommendation = _recommend_stack(
            scored_candidates,
            tasks_by_modality=task_plan,
            run_id=selected_run_id,
        )
        run = {
            "run_id": selected_run_id,
            "trigger": trigger,
            "created_at": created_at,
            "service_version": DISCOVERY_SERVICE_VERSION,
            "source": self.source.source_name,
            "tasks_by_modality": {key: list(value) for key, value in task_plan.items()},
            "ontology_id": ontology["ontology_id"],
            "ontology_version": ontology["ontology_version"],
            "sample_clips": [clip.to_record() for clip in clips],
            "candidate_count": len(scored_candidates),
            "candidates": scored_candidates,
            "recommendation": recommendation,
            "registry": {"path": str(self.registry.path)},
            "remote_inference_used": False,
            "production_replacement_allowed": False,
            "auto_replace_production_models": False,
        }
        self.registry.save_run(run)
        return run

    def _discover_candidates(
        self,
        tasks_by_modality: Mapping[str, Sequence[str]],
        limit_per_task: int,
    ) -> list[ModelCandidate]:
        candidates: list[ModelCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for modality, tasks in tasks_by_modality.items():
            for task in tasks:
                for candidate in self.source.search_models(
                    modality=modality,
                    task=task,
                    limit=limit_per_task,
                ):
                    key = (candidate.model_id, candidate.modality, candidate.task)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
        return candidates

    def _evaluate_candidate(
        self,
        candidate: ModelCandidate,
        *,
        ontology: Mapping[str, Any],
        sample_clips: Sequence[SmokeTestSampleClip],
        tasks_by_modality: Mapping[str, Sequence[str]],
    ) -> dict[str, Any]:
        smoke_tests = [
            _run_smoke_test(candidate, clip=clip, timestamp=timestamp, ontology=ontology)
            for clip in sample_clips
            for timestamp in clip.timestamps
        ]
        score = _score_candidate(
            candidate,
            smoke_tests=smoke_tests,
            tasks_by_modality=tasks_by_modality,
        )
        record = candidate.to_record()
        record["score"] = score
        record["smoke_tests"] = smoke_tests
        return record


def default_seed_candidates() -> tuple[ModelCandidate, ...]:
    """Return deterministic HF-hosted metadata seeds for offline local runs."""

    return (
        ModelCandidate(
            model_id="openai/clip-vit-base-patch32",
            modality="vision",
            task="zero-shot-image-classification",
            source="static-local-seed",
            pipeline_tag="zero-shot-image-classification",
            tags=("transformers", "safetensors", "license:mit"),
            license="mit",
            downloads=5_000_000,
            likes=2_400,
            metadata={"local_runtime": "transformers", "remote_inference": False},
        ),
        ModelCandidate(
            model_id="facebook/detr-resnet-50",
            modality="vision",
            task="object-detection",
            source="static-local-seed",
            pipeline_tag="object-detection",
            tags=("transformers", "pytorch", "license:apache-2.0"),
            license="apache-2.0",
            downloads=1_200_000,
            likes=1_300,
            metadata={"local_runtime": "transformers", "remote_inference": False},
        ),
        ModelCandidate(
            model_id="MIT/ast-finetuned-audioset-10-10-0.4593",
            modality="audio",
            task="audio-classification",
            source="static-local-seed",
            pipeline_tag="audio-classification",
            tags=("transformers", "safetensors", "license:bsd-3-clause"),
            license="bsd-3-clause",
            downloads=550_000,
            likes=620,
            metadata={"local_runtime": "transformers", "remote_inference": False},
        ),
        ModelCandidate(
            model_id="microsoft/trocr-base-printed",
            modality="ocr",
            task="image-to-text",
            source="static-local-seed",
            pipeline_tag="image-to-text",
            tags=("transformers", "pytorch", "license:mit"),
            license="mit",
            downloads=900_000,
            likes=820,
            metadata={"local_runtime": "transformers", "remote_inference": False},
        ),
        ModelCandidate(
            model_id="openai/whisper-base",
            modality="asr",
            task="automatic-speech-recognition",
            source="static-local-seed",
            pipeline_tag="automatic-speech-recognition",
            tags=("transformers", "safetensors", "license:mit"),
            license="mit",
            downloads=8_000_000,
            likes=4_200,
            metadata={"local_runtime": "transformers", "remote_inference": False},
        ),
    )


def _candidate_from_huggingface_payload(
    payload: Mapping[str, Any],
    *,
    modality: str,
    task: str,
) -> ModelCandidate:
    model_id = str(payload.get("modelId") or payload.get("id") or "")
    tags = tuple(str(tag) for tag in payload.get("tags", []) if str(tag))
    sha = payload.get("sha")
    return ModelCandidate(
        model_id=model_id,
        modality=modality,
        task=task,
        source=HuggingFaceModelSource.source_name,
        model_version=f"{model_id}@{sha}" if sha else model_id,
        pipeline_tag=payload.get("pipeline_tag") or task,
        tags=tags,
        license=_license_from_huggingface_payload(payload, tags),
        downloads=_optional_int(payload.get("downloads")),
        likes=_optional_int(payload.get("likes")),
        last_modified=payload.get("lastModified"),
        metadata={
            "author": payload.get("author"),
            "library_name": payload.get("library_name"),
            "remote_inference": False,
        },
    )


def _license_from_huggingface_payload(payload: Mapping[str, Any], tags: Sequence[str]) -> str | None:
    card_data = payload.get("cardData")
    if isinstance(card_data, Mapping) and isinstance(card_data.get("license"), str):
        return card_data["license"]
    for tag in tags:
        if tag.startswith("license:"):
            return tag.partition(":")[2]
    return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_tasks(tasks_by_modality: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, ...]]:
    normalised: dict[str, tuple[str, ...]] = {}
    for modality, tasks in tasks_by_modality.items():
        normalised_modality = require_supported_modality(modality)
        deduped_tasks: list[str] = []
        seen: set[str] = set()
        for task in tasks:
            if not isinstance(task, str) or not task:
                raise ValueError("tasks must contain non-empty strings")
            if task in seen:
                continue
            seen.add(task)
            deduped_tasks.append(task)
        if not deduped_tasks:
            raise ValueError(f"{normalised_modality} must include at least one task")
        normalised[normalised_modality] = tuple(deduped_tasks)
    if not normalised:
        raise ValueError("tasks_by_modality must not be empty")
    return normalised


def _normalise_sample_clips(
    sample_clips: Sequence[SmokeTestSampleClip | Mapping[str, Any]] | None,
) -> tuple[SmokeTestSampleClip, ...]:
    if not sample_clips:
        return (SmokeTestSampleClip(sample_clip_id="metadata-smoke-sample"),)
    clips: list[SmokeTestSampleClip] = []
    for clip in sample_clips:
        if isinstance(clip, SmokeTestSampleClip):
            clips.append(clip)
        else:
            clips.append(SmokeTestSampleClip.from_mapping(clip))
    return tuple(clips)


def _run_smoke_test(
    candidate: ModelCandidate,
    *,
    clip: SmokeTestSampleClip,
    timestamp: int | float,
    ontology: Mapping[str, Any],
) -> dict[str, Any]:
    labels = ontology["labels"]
    label = labels[int(timestamp) % len(labels)]
    label_id = label["label_id"]
    ontology_version = ontology["ontology_version"]
    local_path_exists = True if clip.local_path is None else Path(clip.local_path).exists()
    modality_available = candidate.modality in clip.modalities
    task_declared = bool(candidate.task)
    passed = local_path_exists and modality_available and task_declared
    confidence = 0.82 if passed else 0.0
    checks = {
        "sample_clip_available": local_path_exists,
        "modality_available": modality_available,
        "task_declared": task_declared,
        "remote_inference_used": False,
    }
    evidence = {
        "evidence_id": str(
            uuid5(
                NAMESPACE_URL,
                ":".join(
                    (
                        candidate.model_id,
                        candidate.model_version or candidate.model_id,
                        clip.sample_clip_id,
                        str(timestamp),
                        ontology_version,
                        label_id,
                    )
                ),
            )
        ),
        "modality": candidate.modality,
        "timestamp": timestamp,
        "type": "model_discovery_smoke_test",
        "value": {
            "candidate_model_id": candidate.model_id,
            "task": candidate.task,
            "sample_clip_id": clip.sample_clip_id,
            "ontology_label_id": label_id,
            "ontology_version": ontology_version,
            "checks": checks,
        },
        "confidence": confidence,
        "source_model_version": candidate.model_version or candidate.model_id,
    }
    validate_evidence(evidence)
    return {
        "sample_clip_id": clip.sample_clip_id,
        "timestamp": timestamp,
        "label": label_id,
        "confidence": confidence,
        "evidence": [evidence],
        "model_version": candidate.model_version,
        "ontology_version": ontology_version,
        "passed": passed,
        "checks": checks,
    }


def _score_candidate(
    candidate: ModelCandidate,
    *,
    smoke_tests: Sequence[Mapping[str, Any]],
    tasks_by_modality: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    task_modality_match = float(
        candidate.modality in tasks_by_modality
        and candidate.task in tasks_by_modality[candidate.modality]
    )
    smoke_pass_rate = (
        sum(1 for result in smoke_tests if result.get("passed")) / len(smoke_tests)
        if smoke_tests
        else 0.0
    )
    rubric = {
        "task_modality_match": {"weight": 0.25, "score": task_modality_match},
        "local_runtime_fit": {"weight": 0.20, "score": _local_runtime_score(candidate)},
        "license_fit": {"weight": 0.15, "score": _license_score(candidate.license)},
        "community_signal": {"weight": 0.15, "score": _community_signal(candidate)},
        "maintenance_signal": {"weight": 0.10, "score": _maintenance_signal(candidate.last_modified)},
        "smoke_test_pass_rate": {"weight": 0.15, "score": round(smoke_pass_rate, 4)},
    }
    total = round(
        sum(item["weight"] * item["score"] for item in rubric.values()),
        4,
    )
    return {
        "total": total,
        "rubric": rubric,
        "service_version": DISCOVERY_SERVICE_VERSION,
    }


def _local_runtime_score(candidate: ModelCandidate) -> float:
    tags = {tag.lower() for tag in candidate.tags}
    metadata = {str(key): value for key, value in candidate.metadata.items()}
    if metadata.get("remote_inference") is True:
        return 0.0
    if metadata.get("local_runtime"):
        return 1.0
    if tags & {"safetensors", "onnx", "gguf", "coreml", "transformers"}:
        return 1.0
    if tags & {"pytorch", "tensorflow", "keras"}:
        return 0.75
    return 0.4


def _license_score(license_name: str | None) -> float:
    if not license_name:
        return 0.5
    lowered = license_name.lower()
    if any(marker in lowered for marker in ("non-commercial", "cc-by-nc", "research")):
        return 0.2
    if any(marker in lowered for marker in ("mit", "apache", "bsd", "openrail", "cc-by")):
        return 1.0
    return 0.7


def _community_signal(candidate: ModelCandidate) -> float:
    downloads = max(candidate.downloads or 0, 0)
    likes = max(candidate.likes or 0, 0)
    download_score = min(log1p(downloads) / log1p(5_000_000), 1.0)
    like_score = min(log1p(likes) / log1p(5_000), 1.0)
    return round((download_score * 0.75) + (like_score * 0.25), 4)


def _maintenance_signal(last_modified: str | None) -> float:
    if not last_modified:
        return 0.5
    try:
        modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
    except ValueError:
        return 0.5
    age_days = max((datetime.now(UTC) - modified.astimezone(UTC)).days, 0)
    if age_days <= 365:
        return 1.0
    if age_days <= 365 * 3:
        return 0.75
    if age_days <= 365 * 5:
        return 0.55
    return 0.35


def _recommend_stack(
    scored_candidates: Sequence[Mapping[str, Any]],
    *,
    tasks_by_modality: Mapping[str, Sequence[str]],
    run_id: str,
) -> dict[str, Any]:
    recommended_models: list[dict[str, Any]] = []
    missing_modalities: list[str] = []
    for modality in tasks_by_modality:
        candidates = [
            candidate
            for candidate in scored_candidates
            if candidate["modality"] == modality
            and any(result.get("passed") for result in candidate["smoke_tests"])
        ]
        if not candidates:
            missing_modalities.append(modality)
            continue
        best = max(candidates, key=lambda candidate: candidate["score"]["total"])
        recommended_models.append(
            {
                "modality": modality,
                "task": best["task"],
                "model_id": best["model_id"],
                "model_version": best["model_version"],
                "score": best["score"]["total"],
                "rationale": (
                    "highest local rubric score with passing smoke tests for "
                    f"{modality}"
                ),
            }
        )

    return {
        "stack_id": str(uuid5(NAMESPACE_URL, f"{run_id}:initial-foundation-stack")),
        "strategy": "top_scoring_candidate_per_modality",
        "recommended_models": recommended_models,
        "missing_modalities": missing_modalities,
        "requires_human_promotion": True,
        "production_replacement_allowed": False,
        "auto_replace_production_models": False,
        "service_version": DISCOVERY_SERVICE_VERSION,
    }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
