"""FastAPI backend shell for the local metadata labeller."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Body, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from apps.api.contract_validation import api_response, health_response
from apps.api.ontologies import (
    OntologyNotFoundError as RegistryOntologyNotFoundError,
    get_ontology,
    ontology_summaries,
    sports_catalog,
)
from packages.ontology import (
    DEFAULT_ONTOLOGY_DIR,
    OntologyNotFoundError as SportOntologyNotFoundError,
    OntologyValidationError,
    active_labels,
    get_ontology_metadata,
    list_available_sports,
)
from packages.contracts import (
    CONTRACT_VERSION,
    ContractValidationError,
    validate_human_correction,
    validate_prediction,
)
from packages.extraction import SUPPORTED_MODALITIES
from packages.labelling import build_active_learning_demo_inputs, build_active_learning_queue
from packages.model_registry import (
    DEFAULT_REGISTRY_PATH,
    DEFAULT_TASKS_BY_MODALITY,
    FileModelRegistry,
    HuggingFaceModelSource,
    ModelDiscoveryEvaluationService,
    SmokeTestSampleClip,
    StaticCandidateSource,
    default_seed_candidates,
)

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
MOCK_MODEL_VERSION = "mock-fusion-local-0.1.0"
MOCK_EVIDENCE_MODEL_VERSION = "mock-extractor-local-0.1.0"


class PredictionRequest(BaseModel):
    """Request shape for mock prediction generation."""

    video_id: str = Field(..., min_length=1)
    timestamp: int = Field(0, ge=0)
    sport_id: str | None = Field(default=None, min_length=1)
    ontology_version: str | None = Field(default=None, min_length=1)


class ExportRequest(BaseModel):
    """Request shape for export stubs."""

    video_id: str | None = Field(default=None, min_length=1)
    ontology_version: str | None = Field(default=None, min_length=1)


class ActiveLearningQueueRequest(BaseModel):
    """Request shape for local active-learning queue scoring."""

    sport_id: str | None = Field(default=None, min_length=1)
    ontology_version: str | None = Field(default=None, min_length=1)
    predictions: list[dict[str, Any]] | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)


class ModelDiscoverySampleClipRequest(BaseModel):
    """Local sample descriptor for admin-triggered model smoke tests."""

    sample_clip_id: str = Field(..., min_length=1)
    duration_seconds: float = Field(1, gt=0)
    timestamps: list[float] = Field(default_factory=lambda: [0])
    modalities: list[str] = Field(default_factory=lambda: list(SUPPORTED_MODALITIES))
    local_path: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelDiscoveryRefreshRequest(BaseModel):
    """Request shape for one-time setup/admin model discovery."""

    trigger: str = Field("admin_refresh", min_length=1)
    source_mode: str = Field(
        "static",
        min_length=1,
        description="Use 'static' for local seeded metadata or 'huggingface' for HF metadata search.",
    )
    sport_id: str | None = Field(default=None, min_length=1)
    ontology_version: str | None = Field(default=None, min_length=1)
    tasks_by_modality: dict[str, list[str]] | None = None
    sample_clips: list[ModelDiscoverySampleClipRequest] = Field(
        default_factory=lambda: [
            ModelDiscoverySampleClipRequest(sample_clip_id="admin-refresh-smoke-sample")
        ]
    )
    limit_per_task: int = Field(5, ge=1, le=25)
    registry_path: str | None = Field(default=None, min_length=1)


class OntologyAPIError(Exception):
    """Raised by ontology helper exports before conversion to HTTP errors."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        errors: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.errors = errors or []
        super().__init__(detail)


SUPPORTED_EXPORTS = {
    "predictions_json": "Prediction JSON export",
    "corrections_json": "Human correction JSON export",
    "training_dataset": "Training dataset export",
}

app = FastAPI(
    title="Local-first Sports Video Metadata Labeller API",
    version=CONTRACT_VERSION,
    description="Local FastAPI shell for ontology-driven mock metadata labelling.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
router = APIRouter(prefix=API_PREFIX)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _not_found_from_ontology_error(exc: RegistryOntologyNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _validation_error_response(exc: ContractValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.errors)


def _ontology_api_error(exc: OntologyValidationError) -> OntologyAPIError:
    return OntologyAPIError(status_code=422, detail="invalid ontology file", errors=exc.errors)


def list_ontology_sports(
    ontology_dir: Path | str = DEFAULT_ONTOLOGY_DIR,
) -> dict[str, Any]:
    """Return file-discovered sport ontology metadata as an API response."""

    try:
        sports = list_available_sports(ontology_dir)
    except OntologyValidationError as exc:
        raise _ontology_api_error(exc) from exc

    return api_response({"sports": sports}, api_version=API_VERSION)


def get_sport_ontology_metadata(
    sport: str,
    ontology_dir: Path | str = DEFAULT_ONTOLOGY_DIR,
) -> dict[str, Any]:
    """Return file-discovered ontology metadata for one sport."""

    try:
        ontology = get_ontology_metadata(sport, ontology_dir)
    except SportOntologyNotFoundError as exc:
        raise OntologyAPIError(status_code=404, detail=str(exc)) from exc
    except OntologyValidationError as exc:
        raise _ontology_api_error(exc) from exc

    return api_response({"ontology": ontology}, api_version=API_VERSION)


def _build_mock_prediction(request: PredictionRequest) -> dict[str, Any]:
    try:
        ontology = get_ontology(
            ontology_version=request.ontology_version,
            sport_id=request.sport_id,
        )
    except RegistryOntologyNotFoundError as exc:
        raise _not_found_from_ontology_error(exc) from exc

    labels = active_labels(ontology)
    if not labels:
        raise HTTPException(status_code=422, detail="ontology has no active labels")
    label = labels[request.timestamp % len(labels)]
    label_id = label["label_id"]
    ontology_version = ontology["ontology_version"]
    interval_start = request.timestamp
    interval_end = interval_start + 1

    evidence = {
        "evidence_id": str(
            uuid5(
                NAMESPACE_URL,
                f"{request.video_id}:{request.timestamp}:{label_id}:mock-evidence",
            )
        ),
        "modality": "vision",
        "timestamp": interval_start,
        "type": "mock_ontology_signal",
        "value": {
            "label_id": label_id,
            "label_type": label["label_type"],
            "ontology_version": ontology_version,
        },
        "confidence": 0.5,
        "source_model_version": MOCK_EVIDENCE_MODEL_VERSION,
    }
    prediction = {
        "prediction_id": str(
            uuid5(
                NAMESPACE_URL,
                f"{request.video_id}:{request.timestamp}:{ontology_version}:mock-prediction",
            )
        ),
        "video_id": request.video_id,
        "timestamp": interval_start,
        "interval_start": interval_start,
        "interval_end": interval_end,
        "duration_seconds": 1,
        "timebase": "seconds",
        "label": label_id,
        "confidence": 0.5,
        "evidence": [evidence],
        "model_version": MOCK_MODEL_VERSION,
        "ontology_version": ontology_version,
        "inference_config": {
            "mode": "mock",
            "label_selection": "timestamp_modulo_ontology_labels",
        },
        "post_correction_model_agreement": None,
        "confidence_delta": None,
        "created_at": _utc_now(),
    }

    try:
        validate_prediction(prediction, ontology=ontology)
    except ContractValidationError as exc:
        raise _validation_error_response(exc) from exc

    return prediction


def _build_active_learning_queue_response(
    *,
    sport_id: str | None = None,
    ontology_version: str | None = None,
    predictions: list[dict[str, Any]] | None = None,
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        ontology = get_ontology(
            ontology_version=ontology_version,
            sport_id=sport_id,
        )
    except RegistryOntologyNotFoundError as exc:
        raise _not_found_from_ontology_error(exc) from exc

    generated_at = _utc_now()
    queue_predictions = predictions
    queue_corrections = corrections or []
    if queue_predictions is None:
        queue_predictions, queue_corrections = build_active_learning_demo_inputs(
            ontology,
            created_at=generated_at,
        )

    try:
        queue = build_active_learning_queue(
            predictions=queue_predictions,
            corrections=queue_corrections,
            ontology=ontology,
            generated_at=generated_at,
        )
    except ContractValidationError as exc:
        raise _validation_error_response(exc) from exc

    return api_response({"active_learning": queue}, api_version=API_VERSION)


@app.get("/", tags=["local"])
def root() -> dict[str, Any]:
    return {
        "name": "Local-first Sports Video Metadata Labeller API",
        "api_prefix": API_PREFIX,
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    response = health_response()
    response["api_version"] = API_VERSION
    return response


@router.post("/videos", tags=["videos"])
async def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
    video_id = str(uuid5(NAMESPACE_URL, f"local-video:{file.filename or 'unnamed'}"))
    content_type = file.content_type or "application/octet-stream"
    await file.close()
    return api_response(
        {
            "video_id": video_id,
            "filename": file.filename,
            "content_type": content_type,
            "status": "accepted_stub",
            "storage": "not_persisted",
            "message": "Upload endpoint shell only; no bytes are stored or processed yet.",
        },
        api_version=API_VERSION,
    )


@router.post("/predictions", tags=["predictions"])
def create_prediction(request: PredictionRequest) -> dict[str, Any]:
    prediction = _build_mock_prediction(request)
    return api_response(
        {
            "prediction": prediction,
            "validation": {"schema": "prediction", "valid": True},
        },
        api_version=API_VERSION,
    )


@router.post("/predictions/mock", tags=["predictions"])
def create_mock_prediction(request: PredictionRequest) -> dict[str, Any]:
    return create_prediction(request)


@router.post("/corrections", tags=["corrections"])
def submit_correction(correction: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        ontology = get_ontology(ontology_version=correction.get("ontology_version"))
        validate_human_correction(correction, ontology=ontology)
    except RegistryOntologyNotFoundError as exc:
        raise _not_found_from_ontology_error(exc) from exc
    except ContractValidationError as exc:
        raise _validation_error_response(exc) from exc

    source_predictions = correction.get("source_predictions", [])
    return api_response(
        {
            "accepted": True,
            "correction": correction,
            "preserved_source_prediction_ids": [
                prediction["prediction_id"] for prediction in source_predictions
            ],
            "source_model_versions": [
                prediction["model_version"] for prediction in source_predictions
            ],
            "source_ontology_versions": [
                prediction["ontology_version"] for prediction in source_predictions
            ],
        },
        api_version=API_VERSION,
    )


@router.get("/exports", tags=["exports"])
def list_export_stubs() -> dict[str, Any]:
    return api_response(
        {
            "exports": [
                {"export_type": export_type, "description": description, "status": "stub"}
                for export_type, description in SUPPORTED_EXPORTS.items()
            ]
        },
        api_version=API_VERSION,
    )


@router.post("/exports/{export_type}", tags=["exports"])
def create_export_stub(export_type: str, request: ExportRequest | None = None) -> dict[str, Any]:
    if export_type not in SUPPORTED_EXPORTS:
        raise HTTPException(status_code=404, detail=f"unknown export_type {export_type!r}")

    return api_response(
        {
            "export_type": export_type,
            "description": SUPPORTED_EXPORTS[export_type],
            "status": "stub",
            "file_written": False,
            "request": request.dict() if request is not None else {},
        },
        api_version=API_VERSION,
    )


@router.get("/active-learning/queue", tags=["active-learning"])
def read_active_learning_queue(
    sport_id: str | None = None,
    ontology_version: str | None = None,
) -> dict[str, Any]:
    return _build_active_learning_queue_response(
        sport_id=sport_id,
        ontology_version=ontology_version,
    )


@router.post("/active-learning/queue", tags=["active-learning"])
def create_active_learning_queue(request: ActiveLearningQueueRequest) -> dict[str, Any]:
    return _build_active_learning_queue_response(
        sport_id=request.sport_id,
        ontology_version=request.ontology_version,
        predictions=request.predictions,
        corrections=request.corrections,
    )


@router.post("/admin/model-discovery/refresh", tags=["admin"])
def refresh_model_discovery(request: ModelDiscoveryRefreshRequest) -> dict[str, Any]:
    """Run explicit setup/admin discovery without changing production models."""

    try:
        ontology = get_ontology(
            ontology_version=request.ontology_version,
            sport_id=request.sport_id,
        )
    except RegistryOntologyNotFoundError as exc:
        raise _not_found_from_ontology_error(exc) from exc

    if request.source_mode == "static":
        source = StaticCandidateSource(default_seed_candidates())
    elif request.source_mode == "huggingface":
        source = HuggingFaceModelSource()
    else:
        raise HTTPException(
            status_code=400,
            detail="source_mode must be either 'static' or 'huggingface'",
        )

    registry = FileModelRegistry(request.registry_path or DEFAULT_REGISTRY_PATH)
    service = ModelDiscoveryEvaluationService(source=source, registry=registry)
    sample_clips = [
        SmokeTestSampleClip.from_mapping(sample_clip.dict())
        for sample_clip in request.sample_clips
    ]

    try:
        result = service.discover_and_evaluate(
            trigger=request.trigger,
            ontology=ontology,
            tasks_by_modality=request.tasks_by_modality or DEFAULT_TASKS_BY_MODALITY,
            sample_clips=sample_clips,
            limit_per_task=request.limit_per_task,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return api_response({"model_discovery": result}, api_version=API_VERSION)


@router.get("/sports", tags=["ontologies"])
def list_sports() -> dict[str, Any]:
    return api_response({"sports": sports_catalog()}, api_version=API_VERSION)


@router.get("/ontologies", tags=["ontologies"])
def list_ontologies(include_labels: bool = False) -> dict[str, Any]:
    return api_response(
        {"ontologies": ontology_summaries(include_labels=include_labels)},
        api_version=API_VERSION,
    )


@router.get("/ontologies/{ontology_version}", tags=["ontologies"])
def read_ontology(ontology_version: str) -> dict[str, Any]:
    try:
        ontology = get_ontology(ontology_version=ontology_version)
    except RegistryOntologyNotFoundError as exc:
        raise _not_found_from_ontology_error(exc) from exc
    return api_response({"ontology": ontology}, api_version=API_VERSION)


app.include_router(router)
