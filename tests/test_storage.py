from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from packages.storage.migrate import migrate, pending_migrations
from packages.storage.seed import seed_dev_database


class StorageMigrationTests(unittest.TestCase):
    def test_initial_migration_creates_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite3"
            applied = migrate(db_path)

            self.assertEqual([migration.version for migration in applied], ["0001"])
            with sqlite3.connect(db_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            self.assertTrue(
                {
                    "schema_migrations",
                    "videos",
                    "ontology_versions",
                    "model_versions",
                    "evidence_records",
                    "predictions",
                    "prediction_evidence",
                    "learning_modes",
                    "reviewer_roles",
                    "corrections",
                    "correction_trust_metadata",
                }.issubset(tables)
            )

    def test_video_table_stores_metadata_not_binary_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite3"
            migrate(db_path)

            with sqlite3.connect(db_path) as connection:
                columns = connection.execute("PRAGMA table_info(videos)").fetchall()

            column_names = {column[1] for column in columns}
            column_types = {column[2].upper() for column in columns}
            self.assertIn("local_path", column_names)
            self.assertNotIn("BLOB", column_types)
            self.assertFalse({"bytes", "binary", "payload", "blob"} & column_names)

    def test_correction_schema_preserves_learning_and_provenance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite3"
            migrate(db_path)

            with sqlite3.connect(db_path) as connection:
                correction_columns = {
                    column[1] for column in connection.execute("PRAGMA table_info(corrections)")
                }
                trust_columns = {
                    column[1]
                    for column in connection.execute("PRAGMA table_info(correction_trust_metadata)")
                }

            self.assertTrue(
                {
                    "source_prediction_id",
                    "source_model_version",
                    "ontology_version",
                    "evidence_snapshot_json",
                    "learning_mode",
                    "reviewer_role",
                    "reviewer_confidence",
                    "trust_weight",
                    "post_correction_model_agreement",
                    "confidence_delta",
                }.issubset(correction_columns)
            )
            self.assertTrue(
                {
                    "policy_version",
                    "validity_status",
                    "assigned_trust_weight",
                    "reviewer_reliability",
                    "consensus_count",
                    "contradiction_count",
                    "signals_json",
                }.issubset(trust_columns)
            )

    def test_seed_dev_database_inserts_contract_shaped_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "dev.sqlite3"
            seed_dev_database(db_path)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self.assertEqual(pending_migrations(db_path), [])

                counts = {
                    table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()[
                        "count"
                    ]
                    for table in (
                        "videos",
                        "ontology_versions",
                        "model_versions",
                        "evidence_records",
                        "predictions",
                        "prediction_evidence",
                        "learning_modes",
                        "reviewer_roles",
                        "corrections",
                        "correction_trust_metadata",
                    )
                }
                correction = connection.execute(
                    """
                    SELECT
                        source_prediction_id,
                        source_model_version,
                        ontology_version,
                        evidence_snapshot_json,
                        learning_mode,
                        reviewer_role,
                        trust_weight
                    FROM corrections
                    WHERE correction_id = 'dev-correction-1'
                    """
                ).fetchone()

            self.assertGreaterEqual(counts["ontology_versions"], 1)
            self.assertGreaterEqual(counts["model_versions"], 2)
            self.assertEqual(counts["videos"], 1)
            self.assertEqual(counts["evidence_records"], 1)
            self.assertEqual(counts["predictions"], 1)
            self.assertEqual(counts["prediction_evidence"], 1)
            self.assertEqual(counts["learning_modes"], 2)
            self.assertEqual(counts["reviewer_roles"], 4)
            self.assertEqual(counts["corrections"], 1)
            self.assertEqual(counts["correction_trust_metadata"], 1)
            self.assertEqual(correction["source_prediction_id"], "dev-prediction-1")
            self.assertEqual(correction["source_model_version"], "mock-fusion-local-0.1.0")
            self.assertEqual(correction["learning_mode"], "training")
            self.assertEqual(correction["reviewer_role"], "internal")
            self.assertGreater(len(correction["evidence_snapshot_json"]), 2)
            self.assertGreater(correction["trust_weight"], 0)


if __name__ == "__main__":
    unittest.main()
