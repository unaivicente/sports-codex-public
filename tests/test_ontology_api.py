from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.api.main import OntologyAPIError, get_sport_ontology_metadata, list_ontology_sports
from packages.ontology import (
    DEFAULT_ONTOLOGY_DIR,
    OntologyNotFoundError,
    OntologyValidationError,
    get_ontology_metadata,
    list_available_sports,
    load_ontology,
)


def write_ontology(path: Path, *, ontology_id: str = "tennis") -> None:
    payload = {
        "ontology_id": ontology_id,
        "ontology_version": f"{ontology_id}-2026-05-11",
        "metadata": {"display_name": ontology_id.title()},
        "labels": [
            {
                "label_id": f"{ontology_id}.event.serve",
                "label_type": "event",
                "display_name": "Serve",
            },
            {
                "label_id": f"{ontology_id}.phase.rally",
                "label_type": "phase",
                "display_name": "Rally",
            },
        ],
        "transition_rules": [
            {
                "from_label": f"{ontology_id}.event.serve",
                "to_label": f"{ontology_id}.phase.rally",
                "rule_type": "allowed_after",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class OntologyLoaderTests(unittest.TestCase):
    def test_local_ontology_fixtures_validate_against_contract(self) -> None:
        ontology_paths = sorted(DEFAULT_ONTOLOGY_DIR.glob("*.json"))

        self.assertGreaterEqual(len(ontology_paths), 1)
        for ontology_path in ontology_paths:
            ontology = load_ontology(ontology_path.stem, DEFAULT_ONTOLOGY_DIR)
            label_ids = {label["label_id"] for label in ontology["labels"]}

            self.assertEqual(ontology_path.stem, ontology["ontology_id"])
            self.assertGreaterEqual(len(label_ids), 1)
            for rule in ontology.get("transition_rules", []):
                self.assertIn(rule["from_label"], label_ids)
                self.assertIn(rule["to_label"], label_ids)

    def test_default_sports_include_local_football_ontology(self) -> None:
        sports = list_available_sports()
        sports_by_name = {sport["sport"]: sport for sport in sports}

        self.assertIn("football", sports_by_name)
        self.assertEqual(sports_by_name["football"]["ontology_id"], "football")
        self.assertEqual(sports_by_name["football"]["ontology_version"], "football-2026-05-11")
        self.assertEqual(sports_by_name["football"]["schema_title"], "OntologyContract")
        self.assertEqual(
            sports_by_name["football"]["label_type_counts"],
            {"event": 2, "object": 1, "phase": 2},
        )

    def test_selected_ontology_metadata_is_returned_without_full_label_payload(self) -> None:
        metadata = get_ontology_metadata("football")

        self.assertEqual(metadata["sport"], "football")
        self.assertEqual(metadata["label_count"], 5)
        self.assertEqual(metadata["transition_rule_count"], 3)
        self.assertNotIn("labels", metadata)

    def test_loader_rejects_invalid_ontology_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ontology_dir = Path(tmp)
            (ontology_dir / "invalid.json").write_text(
                json.dumps(
                    {
                        "ontology_id": "invalid",
                        "ontology_version": "invalid-1",
                        "labels": [{"label_id": "invalid.event"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(OntologyValidationError) as context:
                list_available_sports(ontology_dir)

        self.assertIn("display_name", str(context.exception))

    def test_loader_rejects_transition_to_unknown_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ontology_dir = Path(tmp)
            write_ontology(ontology_dir / "tennis.json")
            payload = json.loads((ontology_dir / "tennis.json").read_text(encoding="utf-8"))
            payload["transition_rules"][0]["to_label"] = "tennis.event.missing"
            (ontology_dir / "tennis.json").write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(OntologyValidationError) as context:
                load_ontology("tennis", ontology_dir)

        self.assertIn("references unknown label", str(context.exception))

    def test_missing_sport_is_not_found(self) -> None:
        with self.assertRaises(OntologyNotFoundError):
            load_ontology("basketball", DEFAULT_ONTOLOGY_DIR)


class OntologyEndpointTests(unittest.TestCase):
    def test_list_sports_endpoint_response(self) -> None:
        response = list_ontology_sports()
        sports_by_name = {sport["sport"]: sport for sport in response["data"]["sports"]}

        self.assertEqual(response["contract_version"], "0.1.0")
        self.assertIn("football", sports_by_name)

    def test_get_selected_sport_endpoint_response(self) -> None:
        response = get_sport_ontology_metadata("football")

        self.assertEqual(response["data"]["ontology"]["ontology_id"], "football")
        self.assertEqual(response["data"]["ontology"]["metadata"]["display_name"], "Football")

    def test_endpoint_rejects_invalid_ontology_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ontology_dir = Path(tmp)
            (ontology_dir / "broken.json").write_text("{", encoding="utf-8")

            with self.assertRaises(OntologyAPIError) as context:
                list_ontology_sports(ontology_dir)

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.detail, "invalid ontology file")
        self.assertIn("invalid JSON", context.exception.errors[0])

    def test_endpoint_reports_unknown_sport_as_404(self) -> None:
        with self.assertRaises(OntologyAPIError) as context:
            get_sport_ontology_metadata("basketball")

        self.assertEqual(context.exception.status_code, 404)

    def test_temp_directory_sports_are_discovered_from_files_not_code_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ontology_dir = Path(tmp)
            write_ontology(ontology_dir / "tennis.json", ontology_id="tennis")

            response = list_ontology_sports(ontology_dir)

        self.assertEqual(response["data"]["sports"][0]["sport"], "tennis")
        self.assertEqual(response["data"]["sports"][0]["ontology_id"], "tennis")


if __name__ == "__main__":
    unittest.main()
