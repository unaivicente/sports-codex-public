from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from packages.storage.database import connect
from packages.storage.seed import seed_dev_database
from packages.ontology import evolve_ontology
from packages.training.adapter_training import (
    ADAPTER_TRAINING_PIPELINE_VERSION,
    train_adapter_artifacts,
)
from packages.training.prepare_finetuning import (
    DEFAULT_PREP_DATASET_VERSION,
    MANIFEST_VERSION,
    collect_training_dataset_records,
    main,
    prepare_fine_tuning_manifest,
)


class FineTuningPreparationTests(unittest.TestCase):
    def test_manifest_is_prepared_from_seeded_corrected_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "dev.sqlite3"
            output_path = temp_path / "manifest.json"
            seed_dev_database(db_path)

            manifest = prepare_fine_tuning_manifest(
                db_path=db_path,
                output_path=output_path,
                dataset_version="dataset-test-0.1.0",
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), manifest)
            self.assertEqual(manifest["manifest_version"], MANIFEST_VERSION)
            self.assertEqual(manifest["dataset_version"], "dataset-test-0.1.0")
            self.assertFalse(manifest["training_started"])
            self.assertEqual(manifest["status"], "prepared_stub")
            self.assertEqual(manifest["summary"]["candidate_corrections"], 1)
            self.assertEqual(manifest["summary"]["included_examples"], 1)
            self.assertEqual(manifest["summary"]["skipped_corrections"], 0)

            record = manifest["records"][0]
            self.assertEqual(record["correction_id"], "dev-correction-1")
            self.assertEqual(record["video_id"], "dev-video-1")
            self.assertEqual(record["sport"], "football")
            self.assertEqual(record["interval_start"], 0)
            self.assertEqual(record["interval_end"], 1)
            self.assertEqual(record["source"], "confirmed")
            self.assertEqual(record["source_prediction_ids"], ["dev-prediction-1"])
            self.assertEqual(record["source_model_versions"], ["mock-fusion-local-0.1.0"])
            self.assertEqual(record["source_ontology_versions"], [record["ontology_version"]])
            self.assertGreater(record["trust_weight"], 0)
            self.assertGreaterEqual(len(record["evidence_snapshot"]), 1)

    def test_cli_writes_manifest_without_training_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "dev.sqlite3"
            output_path = temp_path / "cli-manifest.json"
            seed_dev_database(db_path)

            exit_code = main(
                [
                    "--db-path",
                    str(db_path),
                    "--output-path",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_version"], DEFAULT_PREP_DATASET_VERSION)
            self.assertFalse(manifest["training_started"])
            self.assertEqual(manifest["summary"]["included_examples"], 1)

    def test_adapter_training_writes_versioned_sport_artifacts_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "dev.sqlite3"
            artifact_root = temp_path / "models"
            seed_dev_database(db_path)
            _add_second_training_correction(db_path)

            result = train_adapter_artifacts(
                db_path=db_path,
                artifact_root=artifact_root,
                dataset_version="adapter-dataset-test-0.1.0",
                validation_ratio=0.5,
                run_id="adapter-run-1",
            )

            self.assertEqual(result["pipeline_version"], ADAPTER_TRAINING_PIPELINE_VERSION)
            self.assertEqual(result["summary"]["artifact_count"], 1)
            self.assertEqual(result["summary"]["included_examples"], 2)
            artifact = result["artifacts"][0]
            artifact_path = Path(artifact["artifact_path"])
            self.assertTrue(artifact_path.exists())

            manifest = _read_json(artifact_path / "manifest.json")
            dataset = _read_json(artifact_path / "training_dataset.json")
            label_head = _read_json(artifact_path / "label_head.json")
            adapter_config = _read_json(artifact_path / "adapter_config.json")
            model_card = _read_json(artifact_path / "model_card.json")

            self.assertEqual(manifest["sport"], "football")
            self.assertEqual(manifest["ontology_version"], dataset["ontology_version"])
            self.assertEqual(manifest["dataset"]["train_examples"], 1)
            self.assertEqual(manifest["dataset"]["validation_examples"], 1)
            self.assertEqual({record["split"] for record in dataset["records"]}, {"train", "validation"})
            self.assertTrue(all(record["source_prediction_ids"] for record in dataset["records"]))
            self.assertTrue(all(record["source_model_versions"] for record in dataset["records"]))
            self.assertTrue(all(record["source_ontology_versions"] for record in dataset["records"]))

            dataset_labels = {record["label"] for record in dataset["records"]}
            label_head_ids = [label["label_id"] for label in label_head["labels"]]
            self.assertTrue(dataset_labels.issubset(label_head_ids))
            self.assertTrue(label_head["labels_from_ontology"])
            self.assertEqual(adapter_config["adapter_type"], "sport_specific_label_prior_adapter")
            self.assertTrue(adapter_config["foundation_model_stable"])
            self.assertFalse(adapter_config["remote_inference_used"])
            self.assertFalse(model_card["local_first"]["cloud_storage_used"])
            self.assertFalse(model_card["local_first"]["remote_inference_used"])
            self.assertEqual(
                set(model_card["provenance"]["correction_ids"]),
                {"dev-correction-1", "dev-correction-2"},
            )

            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                train_adapter_artifacts(
                    db_path=db_path,
                    artifact_root=artifact_root,
                    dataset_version="adapter-dataset-test-0.1.0",
                    validation_ratio=0.5,
                    run_id="adapter-run-1",
                )

            second_result = train_adapter_artifacts(
                db_path=db_path,
                artifact_root=artifact_root,
                dataset_version="adapter-dataset-test-0.1.0",
                validation_ratio=0.5,
                run_id="adapter-run-2",
            )
            self.assertNotEqual(
                second_result["artifacts"][0]["artifact_path"],
                artifact["artifact_path"],
            )

    def test_evolved_ontology_maps_deprecated_training_label_and_rebuilds_head(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "dev.sqlite3"
            artifact_root = temp_path / "models"
            seed_dev_database(db_path)
            evolved = _add_evolved_ontology_training_correction(db_path)

            dataset = collect_training_dataset_records(
                db_path=db_path,
                dataset_version="evolved-dataset-test-0.1.0",
            )
            evolved_records = [
                record
                for record in dataset["records"]
                if record["correction_id"] == "dev-correction-evolved"
            ]
            self.assertEqual(len(evolved_records), 1)
            self.assertEqual(evolved_records[0]["ontology_version"], evolved["ontology_version"])
            self.assertEqual(evolved_records[0]["source_ontology_versions"], [evolved["ontology_version"]])
            self.assertEqual(evolved_records[0]["source_corrected_label"], "football.event.pass")
            self.assertEqual(evolved_records[0]["label"], "football.event.cross")
            self.assertEqual(
                evolved_records[0]["deprecated_label_mapping"]["replacement_label_id"],
                "football.event.cross",
            )

            result = train_adapter_artifacts(
                db_path=db_path,
                artifact_root=artifact_root,
                dataset_version="evolved-dataset-test-0.1.0",
                validation_ratio=0,
                run_id="evolved-run",
                ontology_version=evolved["ontology_version"],
            )

            self.assertEqual(result["summary"]["artifact_count"], 1)
            artifact_path = Path(result["artifacts"][0]["artifact_path"])
            label_head = _read_json(artifact_path / "label_head.json")
            model_card = _read_json(artifact_path / "model_card.json")

            self.assertEqual(
                label_head["previous_ontology_version"],
                evolved["previous_ontology_version"],
            )
            self.assertIn("football.event.cross", label_head["active_label_ids"])
            self.assertNotIn("football.event.pass", label_head["active_label_ids"])
            self.assertEqual(
                label_head["deprecated_label_mappings"][0]["replacement_label_id"],
                "football.event.cross",
            )
            label_by_id = {label["label_id"]: label for label in label_head["labels"]}
            self.assertTrue(label_by_id["football.event.pass"]["deprecated"])
            self.assertEqual(label_by_id["football.event.cross"]["train_examples"], 1)
            self.assertEqual(
                model_card["ontology_evolution"]["deprecated_label_mappings"][0]["label_id"],
                "football.event.pass",
            )


def _add_second_training_correction(db_path: Path) -> None:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                c.video_id,
                c.original_label,
                c.source_model_version,
                c.ontology_version,
                c.evidence_snapshot_json,
                v.timebase,
                ov.definition_json
            FROM corrections c
            JOIN videos v ON v.video_id = c.video_id
            JOIN ontology_versions ov ON ov.ontology_version = c.ontology_version
            WHERE c.correction_id = 'dev-correction-1'
            """
        ).fetchone()
        ontology = json.loads(row["definition_json"])
        labels = ontology["labels"]
        corrected_label = labels[1]["label_id"] if len(labels) > 1 else labels[0]["label_id"]

        connection.execute(
            """
            INSERT INTO predictions (
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
                "dev-prediction-2",
                row["video_id"],
                0,
                0,
                1,
                row["original_label"],
                0.45,
                row["source_model_version"],
                row["ontology_version"],
                json.dumps({"mode": "adapter_test_seed"}, sort_keys=True),
            ),
        )
        connection.execute(
            """
            INSERT INTO corrections (
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
                "dev-correction-2",
                row["video_id"],
                0,
                1,
                row["original_label"],
                corrected_label,
                "modify",
                "relabel",
                "training",
                "local-reviewer",
                "internal",
                0.95,
                0.9,
                "dev-prediction-2",
                row["source_model_version"],
                row["ontology_version"],
                row["evidence_snapshot_json"],
                0.2,
                -0.25,
                "accepted",
                "Second correction for adapter split coverage.",
            ),
        )
        connection.execute(
            """
            INSERT INTO correction_trust_metadata (
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
                "dev-correction-2",
                "learning-policy-local-0.1.0",
                "valid",
                0.9,
                1.0,
                1,
                0,
                "Internal training-mode modification in adapter test data.",
                json.dumps({"learning_mode": "training", "reviewer_role": "internal"}),
            ),
        )


def _add_evolved_ontology_training_correction(db_path: Path) -> dict:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                c.video_id,
                c.original_label,
                c.source_model_version,
                c.ontology_version,
                c.evidence_snapshot_json,
                ov.definition_json
            FROM corrections c
            JOIN ontology_versions ov ON ov.ontology_version = c.ontology_version
            WHERE c.correction_id = 'dev-correction-1'
            """
        ).fetchone()
        base_ontology = json.loads(row["definition_json"])
        evolved = evolve_ontology(
            base_ontology,
            ontology_version="football-2026-05-30",
            labels_to_add=(
                {
                    "label_id": "football.event.cross",
                    "label_type": "event",
                    "display_name": "Cross",
                },
            ),
            deprecated_label_mappings=(
                {
                    "label_id": "football.event.pass",
                    "replacement_label_id": "football.event.cross",
                    "reason": "local test deprecation mapping",
                },
            ),
            created_at="2026-05-30T00:00:00Z",
            change_id="football-evolution-test",
        )

        connection.execute(
            """
            INSERT INTO ontology_versions (
                ontology_version,
                ontology_id,
                sport_id,
                sport_display_name,
                definition_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                evolved["ontology_version"],
                evolved["ontology_id"],
                evolved.get("sport_id", "football"),
                evolved.get("sport_display_name", "Football"),
                json.dumps(evolved, sort_keys=True),
            ),
        )
        connection.execute(
            """
            INSERT INTO predictions (
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
                "dev-prediction-evolved",
                row["video_id"],
                0,
                0,
                1,
                "football.event.pass",
                0.45,
                row["source_model_version"],
                evolved["ontology_version"],
                json.dumps({"mode": "evolved_ontology_test"}, sort_keys=True),
            ),
        )
        connection.execute(
            """
            INSERT INTO corrections (
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
                "dev-correction-evolved",
                row["video_id"],
                0,
                1,
                row["original_label"],
                "football.event.pass",
                "modify",
                "relabel",
                "training",
                "local-reviewer",
                "internal",
                0.95,
                0.9,
                "dev-prediction-evolved",
                row["source_model_version"],
                evolved["ontology_version"],
                row["evidence_snapshot_json"],
                0.2,
                -0.25,
                "accepted",
                "Evolved ontology correction using deprecated source label.",
            ),
        )
        connection.execute(
            """
            INSERT INTO correction_trust_metadata (
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
                "dev-correction-evolved",
                "learning-policy-local-0.1.0",
                "valid",
                0.9,
                1.0,
                1,
                0,
                "Internal training-mode correction against evolved ontology.",
                json.dumps({"learning_mode": "training", "reviewer_role": "internal"}),
            ),
        )
        return evolved


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
