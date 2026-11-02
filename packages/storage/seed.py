"""Seed a local development SQLite database with contract-shaped records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from packages.contracts import validate_ontology
from packages.storage.database import DEFAULT_DB_PATH, connect
from packages.storage.migrate import migrate

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = REPO_ROOT / "packages" / "ontology" / "definitions"


def load_local_ontologies(ontology_dir: Path | str = ONTOLOGY_DIR) -> list[Mapping[str, Any]]:
    """Load ontology definitions from disk for local seed data."""

    ontologies: list[Mapping[str, Any]] = []
    for path in sorted(Path(ontology_dir).glob("*.json")):
        ontology = json.loads(path.read_text(encoding="utf-8"))
        validate_ontology(ontology)
        ontologies.append(ontology)
    if not ontologies:
        raise RuntimeError(f"no ontology definitions found in {ontology_dir}")
    return ontologies


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def seed_dev_database(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create and seed a deterministic local development database."""

    migrate(db_path)
    ontologies = load_local_ontologies()
    ontology = ontologies[0]
    labels = ontology.get("labels", [])
    if not labels:
        raise RuntimeError(f"ontology {ontology['ontology_version']} has no labels")

    label = labels[0]["label_id"]
    ontology_version = ontology["ontology_version"]
    prediction_model_version = "mock-fusion-local-0.1.0"
    evidence_model_version = "mock-extractor-local-0.1.0"
    evidence = {
        "evidence_id": "dev-evidence-1",
        "modality": "vision",
        "timestamp": 0,
        "type": "dev_seed_signal",
        "value": {"label_id": label, "ontology_version": ontology_version},
        "confidence": 0.5,
        "source_model_version": evidence_model_version,
    }

    with connect(db_path) as connection:
        for local_ontology in ontologies:
            connection.execute(
                """
                INSERT OR REPLACE INTO ontology_versions (
                    ontology_version,
                    ontology_id,
                    sport_id,
                    sport_display_name,
                    definition_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    local_ontology["ontology_version"],
                    local_ontology["ontology_id"],
                    local_ontology.get("sport_id", "unknown"),
                    local_ontology.get("sport_display_name", "Unknown"),
                    _json(local_ontology),
                ),
            )

        connection.executemany(
            """
            INSERT OR REPLACE INTO model_versions (
                model_version,
                model_name,
                model_kind,
                source,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    evidence_model_version,
                    "Mock local extractor",
                    "extractor",
                    "local-dev-seed",
                    _json({"mode": "mock", "remote_inference": False}),
                ),
                (
                    prediction_model_version,
                    "Mock local fusion",
                    "fusion",
                    "local-dev-seed",
                    _json({"mode": "mock", "remote_inference": False}),
                ),
            ],
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO videos (
                video_id,
                original_filename,
                local_path,
                content_type,
                duration_seconds,
                timebase,
                byte_size,
                content_sha256,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dev-video-1",
                "sample-local-video.mp4",
                "data/videos/sample-local-video.mp4",
                "video/mp4",
                1,
                "seconds",
                0,
                None,
                _json({"seed_only": True, "binary_persisted_in_sqlite": False}),
            ),
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO evidence_records (
                evidence_id,
                video_id,
                modality,
                timestamp,
                evidence_type,
                value_json,
                confidence,
                source_model_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence["evidence_id"],
                "dev-video-1",
                evidence["modality"],
                evidence["timestamp"],
                evidence["type"],
                _json(evidence["value"]),
                evidence["confidence"],
                evidence_model_version,
            ),
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO predictions (
                prediction_id,
                video_id,
                timestamp,
                interval_start,
                interval_end,
                label,
                confidence,
                model_version,
                ontology_version,
                inference_config_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dev-prediction-1",
                "dev-video-1",
                0,
                0,
                1,
                label,
                0.5,
                prediction_model_version,
                ontology_version,
                _json({"mode": "dev_seed", "labels_from_ontology": True}),
            ),
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO prediction_evidence (prediction_id, evidence_id)
            VALUES (?, ?)
            """,
            ("dev-prediction-1", evidence["evidence_id"]),
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO corrections (
                correction_id,
                video_id,
                interval_start,
                interval_end,
                original_label,
                corrected_label,
                correction_type,
                edit_operation,
                learning_mode,
                reviewer_id,
                reviewer_role,
                reviewer_confidence,
                trust_weight,
                source_prediction_id,
                source_model_version,
                ontology_version,
                evidence_snapshot_json,
                post_correction_model_agreement,
                confidence_delta,
                review_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dev-correction-1",
                "dev-video-1",
                0,
                1,
                label,
                label,
                "confirm",
                "none",
                "training",
                "local-reviewer",
                "internal",
                0.9,
                0.8,
                "dev-prediction-1",
                prediction_model_version,
                ontology_version,
                _json([evidence]),
                1.0,
                0.0,
                "accepted",
                "Dev seed correction preserves source prediction and model provenance.",
            ),
        )

        connection.execute(
            """
            INSERT OR REPLACE INTO correction_trust_metadata (
                correction_id,
                policy_version,
                validity_status,
                assigned_trust_weight,
                reviewer_reliability,
                consensus_count,
                contradiction_count,
                assignment_reason,
                signals_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dev-correction-1",
                "learning-policy-local-0.1.0",
                "valid",
                0.8,
                1.0,
                1,
                0,
                "Internal training-mode confirmation in dev seed data.",
                _json({"learning_mode": "training", "reviewer_role": "internal"}),
            ),
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed a local development SQLite database.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    seed_dev_database(args.db_path)
    print(f"Seeded local development database at {args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
