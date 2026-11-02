"""Local adapter training artifact pipeline.

The current project scope does not train a foundation model. This module turns
accepted corrections into deterministic, local JSON artifacts for sport-specific
adapters and ontology-specific label heads that a later trainer can consume.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from packages.ontology import deprecated_label_map
from packages.storage.database import DEFAULT_DB_PATH, connect
from packages.training.prepare_finetuning import (
    DEFAULT_PREP_DATASET_VERSION,
    collect_training_dataset_records,
)

ADAPTER_TRAINING_PIPELINE_VERSION = "adapter-training-local-0.1.0"
ADAPTER_ARTIFACT_SCHEMA_VERSION = "local-adapter-artifact-v1"
DEFAULT_ADAPTER_ARTIFACT_ROOT = Path("data/models/adapters")
DEFAULT_VALIDATION_RATIO = 0.2


def train_adapter_artifacts(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    artifact_root: Path | str = DEFAULT_ADAPTER_ARTIFACT_ROOT,
    dataset_version: str = DEFAULT_PREP_DATASET_VERSION,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    run_id: str | None = None,
    sport: str | None = None,
    ontology_version: str | None = None,
    foundation_model_version: str | None = None,
) -> dict[str, Any]:
    """Build append-only local adapter artifacts from accepted corrections.

    Artifacts are grouped by ``sport`` and ``ontology_version`` so a stable
    foundation model can keep separate lightweight adapters and label heads.
    """

    _validate_validation_ratio(validation_ratio)
    selected_run_id = run_id or _default_run_id()
    created_at = _utc_now()
    root = Path(artifact_root)

    dataset = collect_training_dataset_records(
        db_path=db_path,
        dataset_version=dataset_version,
        split="train",
    )
    records = [
        record
        for record in dataset["records"]
        if (sport is None or record["sport"] == sport)
        and (ontology_version is None or record["ontology_version"] == ontology_version)
    ]

    ontology_definitions = _fetch_ontology_definitions(db_path)
    grouped_records = _group_records(records)
    artifacts: list[dict[str, Any]] = []
    skipped_groups: list[dict[str, str]] = []

    for group_key, group_records in grouped_records.items():
        group_sport, group_ontology_version = group_key
        ontology = ontology_definitions.get(group_ontology_version)
        if ontology is None:
            skipped_groups.append(
                {
                    "sport": group_sport,
                    "ontology_version": group_ontology_version,
                    "reason": "ontology definition is missing",
                }
            )
            continue

        split_records = _assign_train_validation_splits(
            group_records,
            validation_ratio=validation_ratio,
            split_seed=f"{dataset_version}:{selected_run_id}:{group_sport}:{group_ontology_version}",
        )
        source_model_versions = sorted(
            {
                version
                for record in split_records
                for version in record.get("source_model_versions", [])
                if version
            }
        )
        selected_foundation_version = foundation_model_version or _foundation_model_version(
            source_model_versions
        )
        artifact = _build_artifact_payloads(
            records=split_records,
            ontology=ontology,
            sport=group_sport,
            dataset_version=dataset_version,
            run_id=selected_run_id,
            created_at=created_at,
            foundation_model_version=selected_foundation_version,
            source_model_versions=source_model_versions,
        )
        artifact_path = _artifact_path(
            root,
            sport=group_sport,
            ontology_version=group_ontology_version,
            artifact_version=artifact["manifest"]["artifact_version"],
        )
        _write_artifact_files(artifact_path, artifact)
        artifacts.append(
            {
                "sport": group_sport,
                "ontology_version": group_ontology_version,
                "artifact_version": artifact["manifest"]["artifact_version"],
                "model_version": artifact["manifest"]["model_version"],
                "artifact_path": str(artifact_path),
                "dataset": artifact["manifest"]["dataset"],
                "files": artifact["manifest"]["files"],
            }
        )

    result = {
        "pipeline_version": ADAPTER_TRAINING_PIPELINE_VERSION,
        "run_id": selected_run_id,
        "created_at": created_at,
        "dataset_version": dataset_version,
        "source": {
            "type": "local_sqlite",
            "db_path": str(db_path),
            "remote_inference_used": False,
            "cloud_storage_used": False,
        },
        "filters": {
            "sport": sport,
            "ontology_version": ontology_version,
            "validation_ratio": validation_ratio,
        },
        "summary": {
            "candidate_corrections": dataset["candidate_corrections"],
            "included_examples": len(records),
            "skipped_corrections": len(dataset["skipped"]),
            "artifact_count": len(artifacts),
            "skipped_groups": len(skipped_groups),
        },
        "artifacts": artifacts,
        "skipped_corrections": dataset["skipped"],
        "skipped_groups": skipped_groups,
    }
    return result


def _fetch_ontology_definitions(db_path: Path | str) -> dict[str, Mapping[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT ontology_version, definition_json
            FROM ontology_versions
            ORDER BY ontology_version
            """
        ).fetchall()

    ontologies: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        definition = json.loads(row["definition_json"])
        if isinstance(definition, Mapping):
            ontologies[row["ontology_version"]] = definition
    return ontologies


def _group_records(records: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["sport"]), str(record["ontology_version"]))].append(dict(record))
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _assign_train_validation_splits(
    records: Sequence[Mapping[str, Any]],
    *,
    validation_ratio: float,
    split_seed: str,
) -> list[dict[str, Any]]:
    if not records:
        return []

    ranked = sorted(
        (dict(record) for record in records),
        key=lambda record: _stable_split_key(record, split_seed),
    )
    validation_count = 0
    if validation_ratio > 0 and len(ranked) > 1:
        validation_count = max(1, round(len(ranked) * validation_ratio))
        validation_count = min(validation_count, len(ranked) - 1)

    validation_ids = {
        record["training_example_id"]
        for record in ranked[:validation_count]
    }
    split_records: list[dict[str, Any]] = []
    for record in sorted(ranked, key=lambda item: item["training_example_id"]):
        record["split"] = (
            "validation"
            if record["training_example_id"] in validation_ids
            else "train"
        )
        split_records.append(record)
    return split_records


def _stable_split_key(record: Mapping[str, Any], split_seed: str) -> str:
    key = ":".join(
        (
            split_seed,
            str(record.get("correction_id", "")),
            str(record.get("video_id", "")),
            str(record.get("interval_start", "")),
            str(record.get("interval_end", "")),
        )
    )
    return sha256(key.encode("utf-8")).hexdigest()


def _build_artifact_payloads(
    *,
    records: Sequence[Mapping[str, Any]],
    ontology: Mapping[str, Any],
    sport: str,
    dataset_version: str,
    run_id: str,
    created_at: str,
    foundation_model_version: str,
    source_model_versions: Sequence[str],
) -> dict[str, Any]:
    ontology_version = str(ontology["ontology_version"])
    artifact_version = _artifact_version(
        sport=sport,
        ontology_version=ontology_version,
        dataset_version=dataset_version,
        run_id=run_id,
    )
    model_version = (
        f"{foundation_model_version}+adapter."
        f"{_normalise_identifier(sport)}."
        f"{_normalise_identifier(ontology_version)}."
        f"{_normalise_identifier(dataset_version)}."
        f"{_normalise_identifier(run_id)}"
    )
    split_counts = _split_counts(records)
    dataset_payload = {
        "schema_version": "local-adapter-training-dataset-v1",
        "dataset_version": dataset_version,
        "created_at": created_at,
        "sport": sport,
        "ontology_version": ontology_version,
        "pipeline_version": ADAPTER_TRAINING_PIPELINE_VERSION,
        "split_counts": split_counts,
        "records": list(records),
    }
    label_head = _build_label_head(
        ontology=ontology,
        records=records,
        dataset_version=dataset_version,
        created_at=created_at,
    )
    adapter_config = {
        "schema_version": ADAPTER_ARTIFACT_SCHEMA_VERSION,
        "adapter_type": "sport_specific_label_prior_adapter",
        "adapter_version": artifact_version,
        "model_version": model_version,
        "foundation_model_version": foundation_model_version,
        "foundation_model_stable": True,
        "source_model_versions": list(source_model_versions),
        "sport": sport,
        "ontology_version": ontology_version,
        "dataset_version": dataset_version,
        "created_at": created_at,
        "local_only": True,
        "remote_inference_used": False,
        "parameters": {
            "label_priors": label_head["label_priors"],
            "label_weights": label_head["label_weights"],
        },
    }
    model_card = {
        "model_version": model_version,
        "artifact_version": artifact_version,
        "model_kind": "sport_adapter_label_head",
        "pipeline_version": ADAPTER_TRAINING_PIPELINE_VERSION,
        "foundation_model_version": foundation_model_version,
        "sport": sport,
        "ontology_id": ontology.get("ontology_id"),
        "ontology_version": ontology_version,
        "previous_ontology_version": ontology.get("previous_ontology_version"),
        "dataset_version": dataset_version,
        "created_at": created_at,
        "intended_use": "Local sport-specific adapter and ontology label head artifact.",
        "limitations": [
            "Deterministic local artifact generation only; no foundation model weights were retrained.",
            "Label head classes are sourced from ontology definitions.",
        ],
        "provenance": {
            "source_prediction_ids": sorted(
                {
                    prediction_id
                    for record in records
                    for prediction_id in record.get("source_prediction_ids", [])
                }
            ),
            "source_model_versions": list(source_model_versions),
            "source_ontology_versions": sorted(
                {
                    ontology_version
                    for record in records
                    for ontology_version in record.get("source_ontology_versions", [])
                }
            ),
            "correction_ids": sorted({str(record["correction_id"]) for record in records}),
        },
        "ontology_evolution": {
            "previous_ontology_version": ontology.get("previous_ontology_version"),
            "deprecated_label_mappings": [
                mapping for mapping in ontology.get("deprecated_labels", [])
                if isinstance(mapping, Mapping)
            ],
            "change": dict(ontology.get("evolution", {})),
        },
        "local_first": {
            "cloud_storage_used": False,
            "remote_inference_used": False,
        },
    }
    manifest = {
        "schema_version": ADAPTER_ARTIFACT_SCHEMA_VERSION,
        "artifact_version": artifact_version,
        "model_version": model_version,
        "created_at": created_at,
        "pipeline_version": ADAPTER_TRAINING_PIPELINE_VERSION,
        "sport": sport,
        "ontology_version": ontology_version,
        "previous_ontology_version": ontology.get("previous_ontology_version"),
        "dataset": {
            "dataset_version": dataset_version,
            "train_examples": split_counts["train"],
            "validation_examples": split_counts["validation"],
            "total_examples": len(records),
        },
        "files": {
            "adapter_config": "adapter_config.json",
            "label_head": "label_head.json",
            "training_dataset": "training_dataset.json",
            "model_card": "model_card.json",
        },
        "local_first": {
            "cloud_storage_used": False,
            "remote_inference_used": False,
        },
    }
    return {
        "manifest": manifest,
        "adapter_config": adapter_config,
        "label_head": label_head,
        "training_dataset": dataset_payload,
        "model_card": model_card,
    }


def _build_label_head(
    *,
    ontology: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    dataset_version: str,
    created_at: str,
) -> dict[str, Any]:
    labels = ontology.get("labels", [])
    deprecated_mappings = deprecated_label_map(ontology)
    deprecated_label_ids = set(deprecated_mappings)
    active_label_ids = [
        str(label["label_id"])
        for label in labels
        if str(label["label_id"]) not in deprecated_label_ids
    ]
    label_weights: dict[str, float] = {str(label["label_id"]): 0.0 for label in labels}
    label_examples: dict[str, int] = {str(label["label_id"]): 0 for label in labels}

    for record in records:
        label = str(record["label"])
        if label not in label_weights:
            continue
        label_weights[label] = round(label_weights[label] + float(record["trust_weight"]), 6)
        label_examples[label] += 1

    total_weight = sum(label_weights.values())
    label_priors = {
        label_id: (
            round(weight / total_weight, 6)
            if total_weight > 0
            else 0.0
        )
        for label_id, weight in sorted(label_weights.items())
    }
    return {
        "schema_version": "local-ontology-label-head-v1",
        "head_type": "ontology_label_head",
        "dataset_version": dataset_version,
        "created_at": created_at,
        "ontology_id": ontology.get("ontology_id"),
        "ontology_version": ontology["ontology_version"],
        "previous_ontology_version": ontology.get("previous_ontology_version"),
        "labels_from_ontology": True,
        "active_label_ids": active_label_ids,
        "deprecated_label_mappings": [
            deprecated_mappings[label_id] for label_id in sorted(deprecated_mappings)
        ],
        "ontology_evolution": dict(ontology.get("evolution", {})),
        "labels": [
            {
                "label_id": label["label_id"],
                "label_type": label["label_type"],
                "display_name": label["display_name"],
                "deprecated": label["label_id"] in deprecated_label_ids,
                "replacement_label_id": (
                    deprecated_mappings[label["label_id"]]["replacement_label_id"]
                    if label["label_id"] in deprecated_mappings
                    else None
                ),
                "train_examples": label_examples[label["label_id"]],
                "train_weight": label_weights[label["label_id"]],
            }
            for label in labels
        ],
        "label_weights": dict(sorted(label_weights.items())),
        "label_priors": label_priors,
    }


def _artifact_path(
    artifact_root: Path,
    *,
    sport: str,
    ontology_version: str,
    artifact_version: str,
) -> Path:
    return (
        artifact_root
        / _normalise_identifier(sport)
        / _normalise_identifier(ontology_version)
        / _normalise_identifier(artifact_version)
    )


def _write_artifact_files(artifact_path: Path, artifact: Mapping[str, Any]) -> None:
    try:
        artifact_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"adapter artifact path already exists and will not be overwritten: {artifact_path}"
        ) from exc

    files = {
        "manifest.json": artifact["manifest"],
        "adapter_config.json": artifact["adapter_config"],
        "label_head.json": artifact["label_head"],
        "training_dataset.json": artifact["training_dataset"],
        "model_card.json": artifact["model_card"],
    }
    for filename, payload in files.items():
        (artifact_path / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _artifact_version(
    *,
    sport: str,
    ontology_version: str,
    dataset_version: str,
    run_id: str,
) -> str:
    return ".".join(
        (
            _normalise_identifier(sport),
            _normalise_identifier(ontology_version),
            _normalise_identifier(dataset_version),
            _normalise_identifier(run_id),
        )
    )


def _normalise_identifier(value: str) -> str:
    cleaned = [character if character.isalnum() or character in "._-" else "-" for character in value]
    identifier = "".join(cleaned).strip(".-_")
    return identifier or "unknown"


def _foundation_model_version(source_model_versions: Sequence[str]) -> str:
    if len(source_model_versions) == 1:
        return source_model_versions[0]
    if source_model_versions:
        digest = sha256(",".join(source_model_versions).encode("utf-8")).hexdigest()[:12]
        return f"mixed-foundation-local-{digest}"
    return "unknown-foundation-local"


def _split_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"train": 0, "validation": 0}
    for record in records:
        split = record.get("split")
        if split in counts:
            counts[split] += 1
    return counts


def _validate_validation_ratio(value: float) -> None:
    if value < 0 or value >= 1:
        raise ValueError("validation_ratio must be >= 0 and < 1")


def _default_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build local sport adapter and ontology label-head artifacts from corrections."
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ADAPTER_ARTIFACT_ROOT),
        help=f"Artifact root directory (default: {DEFAULT_ADAPTER_ARTIFACT_ROOT})",
    )
    parser.add_argument(
        "--dataset-version",
        default=DEFAULT_PREP_DATASET_VERSION,
        help=f"Dataset version to stamp into records (default: {DEFAULT_PREP_DATASET_VERSION})",
    )
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=DEFAULT_VALIDATION_RATIO,
        help=f"Validation split ratio, >= 0 and < 1 (default: {DEFAULT_VALIDATION_RATIO})",
    )
    parser.add_argument("--run-id", help="Optional artifact run identifier.")
    parser.add_argument("--sport", help="Optional sport filter.")
    parser.add_argument("--ontology-version", help="Optional ontology version filter.")
    parser.add_argument("--foundation-model-version", help="Optional stable foundation model version.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = train_adapter_artifacts(
        db_path=args.db_path,
        artifact_root=args.artifact_root,
        dataset_version=args.dataset_version,
        validation_ratio=args.validation_ratio,
        run_id=args.run_id,
        sport=args.sport,
        ontology_version=args.ontology_version,
        foundation_model_version=args.foundation_model_version,
    )
    print(f"Adapter artifacts written: {result['summary']['artifact_count']}")
    for artifact in result["artifacts"]:
        print(f"- {artifact['model_version']} -> {artifact['artifact_path']}")
    print("No foundation model retraining or remote inference was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
