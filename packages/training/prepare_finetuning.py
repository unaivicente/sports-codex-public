"""Prepare a local fine-tuning dataset manifest from accepted corrections.

This command is intentionally a preparation stub. It reads local SQLite
correction rows, validates derived training dataset records, and writes a
manifest. It does not train, evaluate, or promote any model.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from packages.contracts import ContractValidationError, validate_training_dataset_record
from packages.ontology import deprecated_label_map
from packages.storage.database import DEFAULT_DB_PATH, connect

MANIFEST_VERSION = "fine-tuning-prep-stub-0.1.0"
DEFAULT_PREP_DATASET_VERSION = "fine-tuning-prep-local-0.1.0"
DEFAULT_MANIFEST_PATH = Path("data/training/fine_tuning_dataset_manifest.json")

TRAINABLE_SOURCES = {
    "confirm": "confirmed",
    "modify": "corrected",
    "add": "human_added",
}


def prepare_fine_tuning_manifest(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    output_path: Path | str = DEFAULT_MANIFEST_PATH,
    dataset_version: str = DEFAULT_PREP_DATASET_VERSION,
    split: str = "train",
) -> dict[str, Any]:
    """Build and write a fine-tuning prep manifest from corrected intervals."""

    manifest_path = Path(output_path)
    dataset = collect_training_dataset_records(
        db_path=db_path,
        dataset_version=dataset_version,
        split=split,
    )
    records = dataset["records"]
    skipped = dataset["skipped"]
    correction_rows = dataset["candidate_corrections"]

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "dataset_version": dataset_version,
        "created_at": _utc_now(),
        "status": "prepared_stub",
        "training_started": False,
        "training_message": "Fine-tuning preparation only; no model training was run.",
        "source": {
            "type": "local_sqlite",
            "db_path": str(db_path),
            "corrected_interval_table": "corrections",
        },
        "filters": {
            "review_status": "accepted",
            "validity_status": "valid",
            "correction_types": sorted(TRAINABLE_SOURCES),
            "minimum_trust_weight": 0,
            "split": split,
        },
        "summary": {
            "candidate_corrections": correction_rows,
            "included_examples": len(records),
            "skipped_corrections": len(skipped),
        },
        "records": records,
        "skipped": skipped,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def collect_training_dataset_records(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    dataset_version: str = DEFAULT_PREP_DATASET_VERSION,
    split: str = "train",
) -> dict[str, Any]:
    """Collect accepted correction rows as validated training dataset records."""

    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    with connect(db_path) as connection:
        correction_rows = _fetch_accepted_corrections(connection)
        for row in correction_rows:
            record = _record_from_correction_row(
                row,
                dataset_version=dataset_version,
                split=split,
                skipped=skipped,
            )
            if record is not None:
                records.append(record)

    return {
        "dataset_version": dataset_version,
        "candidate_corrections": len(correction_rows),
        "records": records,
        "skipped": skipped,
    }


def _fetch_accepted_corrections(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT
                c.correction_id,
                c.video_id,
                c.interval_start,
                c.interval_end,
                c.original_label,
                c.corrected_label,
                c.correction_type,
                c.edit_operation,
                c.learning_mode,
                c.reviewer_id,
                c.reviewer_role,
                c.reviewer_confidence,
                c.trust_weight,
                c.source_prediction_id,
                c.source_model_version,
                c.ontology_version,
                c.evidence_snapshot_json,
                c.post_correction_model_agreement,
                c.confidence_delta,
                c.review_status,
                c.created_at,
                c.notes,
                v.timebase,
                tm.validity_status,
                tm.assigned_trust_weight,
                ov.ontology_id,
                ov.sport_id,
                ov.sport_display_name,
                ov.definition_json AS ontology_definition_json
            FROM corrections c
            JOIN videos v ON v.video_id = c.video_id
            LEFT JOIN correction_trust_metadata tm ON tm.correction_id = c.correction_id
            LEFT JOIN ontology_versions ov ON ov.ontology_version = c.ontology_version
            WHERE c.review_status = 'accepted'
            ORDER BY c.video_id, c.interval_start, c.interval_end, c.correction_id
            """
        )
    )


def _record_from_correction_row(
    row: sqlite3.Row,
    *,
    dataset_version: str,
    split: str,
    skipped: list[dict[str, str]],
) -> dict[str, Any] | None:
    correction_id = row["correction_id"]
    correction_type = row["correction_type"]

    if row["validity_status"] != "valid":
        skipped.append(
            {
                "correction_id": correction_id,
                "reason": "correction validity_status is not valid",
            }
        )
        return None

    if correction_type not in TRAINABLE_SOURCES:
        skipped.append(
            {
                "correction_id": correction_id,
                "reason": f"correction_type {correction_type!r} is not trainable",
            }
        )
        return None

    if not row["corrected_label"]:
        skipped.append(
            {
                "correction_id": correction_id,
                "reason": "corrected_label is required for training records",
            }
        )
        return None

    if row["trust_weight"] <= 0:
        skipped.append(
            {
                "correction_id": correction_id,
                "reason": "trust_weight must be greater than zero",
            }
        )
        return None

    try:
        evidence_snapshot = _load_json_list(row["evidence_snapshot_json"])
        ontology = _load_json_object(row["ontology_definition_json"])
    except ValueError as exc:
        skipped.append({"correction_id": correction_id, "reason": str(exc)})
        return None

    sport_id = _sport_id_from_row(row, ontology)
    source_prediction_ids = [row["source_prediction_id"]] if row["source_prediction_id"] else []
    source_model_versions = [row["source_model_version"]] if row["source_model_version"] else []
    source_ontology_versions = [row["ontology_version"]]
    label, deprecated_mapping = _training_label(row["corrected_label"], ontology)

    record = {
        "training_example_id": (
            f"{dataset_version}:{correction_id}:"
            f"{_format_interval(row['interval_start'])}-{_format_interval(row['interval_end'])}"
        ),
        "dataset_version": dataset_version,
        "correction_id": correction_id,
        "video_id": row["video_id"],
        "sport": sport_id,
        "sport_display_name": _sport_display_name_from_row(row, ontology, sport_id),
        "ontology_id": row["ontology_id"] or ontology.get("ontology_id"),
        "interval_start": row["interval_start"],
        "interval_end": row["interval_end"],
        "timebase": row["timebase"],
        "label": label,
        "source": TRAINABLE_SOURCES[correction_type],
        "correction_type": correction_type,
        "edit_operation": row["edit_operation"],
        "learning_mode": row["learning_mode"],
        "trust_weight": row["trust_weight"],
        "ontology_version": row["ontology_version"],
        "source_prediction_ids": source_prediction_ids,
        "source_model_versions": source_model_versions,
        "source_ontology_versions": source_ontology_versions,
        "evidence_snapshot": evidence_snapshot,
        "split": split,
        "original_label": row["original_label"],
        "reviewer_id": row["reviewer_id"],
        "reviewer_role": row["reviewer_role"],
        "reviewer_confidence": row["reviewer_confidence"],
        "validity_status": row["validity_status"],
        "assigned_trust_weight": row["assigned_trust_weight"],
        "source_model_version": row["source_model_version"],
        "post_correction_model_agreement": row["post_correction_model_agreement"],
        "confidence_delta": row["confidence_delta"],
        "correction_created_at": row["created_at"],
    }
    if deprecated_mapping is not None:
        record["source_corrected_label"] = row["corrected_label"]
        record["deprecated_label_mapping"] = deprecated_mapping

    try:
        validate_training_dataset_record(record, ontology=ontology)
    except ContractValidationError as exc:
        skipped.append({"correction_id": correction_id, "reason": str(exc)})
        return None

    return record


def _training_label(
    corrected_label: str,
    ontology: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    mapping = deprecated_label_map(ontology).get(corrected_label)
    if mapping is None:
        return corrected_label, None
    return str(mapping["replacement_label_id"]), dict(mapping)


def _sport_id_from_row(row: sqlite3.Row, ontology: Mapping[str, Any]) -> str:
    row_sport = row["sport_id"]
    if isinstance(row_sport, str) and row_sport:
        return row_sport

    ontology_sport = ontology.get("sport_id")
    if isinstance(ontology_sport, str) and ontology_sport:
        return ontology_sport

    ontology_id = ontology.get("ontology_id")
    if isinstance(ontology_id, str) and ontology_id:
        return ontology_id

    return "unknown"


def _sport_display_name_from_row(
    row: sqlite3.Row,
    ontology: Mapping[str, Any],
    sport_id: str,
) -> str:
    row_display = row["sport_display_name"]
    if isinstance(row_display, str) and row_display and row_display != "Unknown":
        return row_display

    ontology_display = ontology.get("sport_display_name")
    if isinstance(ontology_display, str) and ontology_display:
        return ontology_display

    metadata = ontology.get("metadata")
    if isinstance(metadata, Mapping):
        metadata_display = metadata.get("display_name")
        if isinstance(metadata_display, str) and metadata_display:
            return metadata_display

    return sport_id.replace("-", " ").replace("_", " ").title()


def _load_json_list(raw_value: str | None) -> list[Any]:
    if raw_value is None:
        raise ValueError("evidence_snapshot_json is missing")
    value = json.loads(raw_value)
    if not isinstance(value, list):
        raise ValueError("evidence_snapshot_json must decode to a list")
    return value


def _load_json_object(raw_value: str | None) -> Mapping[str, Any]:
    if raw_value is None:
        raise ValueError("ontology definition is missing")
    value = json.loads(raw_value)
    if not isinstance(value, Mapping):
        raise ValueError("ontology definition must decode to an object")
    return value


def _format_interval(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace(".", "_")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a local fine-tuning dataset manifest from accepted corrected "
            "intervals without training a model."
        )
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--output-path",
        default=str(DEFAULT_MANIFEST_PATH),
        help=f"Manifest JSON output path (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--dataset-version",
        default=DEFAULT_PREP_DATASET_VERSION,
        help=f"Dataset version to stamp into records (default: {DEFAULT_PREP_DATASET_VERSION})",
    )
    parser.add_argument(
        "--split",
        choices=("train", "validation", "test"),
        default="train",
        help="Dataset split assigned to generated records (default: train)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = prepare_fine_tuning_manifest(
        db_path=args.db_path,
        output_path=args.output_path,
        dataset_version=args.dataset_version,
        split=args.split,
    )
    print(f"Wrote fine-tuning preparation manifest to {args.output_path}")
    print(f"Included examples: {manifest['summary']['included_examples']}")
    print(f"Skipped corrections: {manifest['summary']['skipped_corrections']}")
    print("No model training was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
