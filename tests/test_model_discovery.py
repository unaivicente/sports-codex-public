from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.api.main import (
    ModelDiscoveryRefreshRequest,
    ModelDiscoverySampleClipRequest,
    refresh_model_discovery,
)
from packages.contracts import validate_evidence
from packages.model_registry import (
    FileModelRegistry,
    ModelCandidate,
    ModelDiscoveryEvaluationService,
    SmokeTestSampleClip,
    StaticCandidateSource,
)
from packages.ontology import get_ontology


class CountingSource:
    source_name = "counting-test-source"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def search_models(self, *, modality: str, task: str, limit: int) -> list[ModelCandidate]:
        self.calls.append((modality, task, limit))
        return []


class ModelDiscoveryTests(unittest.TestCase):
    def test_discovery_requires_setup_or_admin_trigger_before_source_search(self) -> None:
        source = CountingSource()
        service = ModelDiscoveryEvaluationService(
            source=source,
            registry=FileModelRegistry(Path(tempfile.gettempdir()) / "unused-registry.json"),
        )

        with self.assertRaisesRegex(ValueError, "discovery trigger"):
            service.discover_and_evaluate(
                trigger="background",
                ontology=get_ontology(),
                tasks_by_modality={"vision": ["zero-shot-image-classification"]},
            )

        self.assertEqual(source.calls, [])

    def test_discovers_scores_smoke_tests_recommends_and_persists_locally(self) -> None:
        ontology = get_ontology()
        ontology_label_ids = {label["label_id"] for label in ontology["labels"]}
        source = StaticCandidateSource(
            (
                ModelCandidate(
                    model_id="local/vision-foundation",
                    modality="vision",
                    task="zero-shot-image-classification",
                    source="test-fixture",
                    tags=("transformers", "safetensors", "license:mit"),
                    license="mit",
                    downloads=1000,
                    likes=50,
                    metadata={"local_runtime": "transformers", "remote_inference": False},
                ),
                ModelCandidate(
                    model_id="local/asr-foundation",
                    modality="asr",
                    task="automatic-speech-recognition",
                    source="test-fixture",
                    tags=("transformers", "safetensors", "license:apache-2.0"),
                    license="apache-2.0",
                    downloads=2000,
                    likes=70,
                    metadata={"local_runtime": "transformers", "remote_inference": False},
                ),
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry.json"
            service = ModelDiscoveryEvaluationService(
                source=source,
                registry=FileModelRegistry(registry_path),
            )
            result = service.discover_and_evaluate(
                trigger="setup",
                ontology=ontology,
                tasks_by_modality={
                    "vision": ["zero-shot-image-classification"],
                    "asr": ["automatic-speech-recognition"],
                },
                sample_clips=[
                    SmokeTestSampleClip(
                        sample_clip_id="sample-clip-1",
                        duration_seconds=2,
                        timestamps=(0, 1),
                        modalities=("vision", "asr"),
                    )
                ],
                limit_per_task=2,
                run_id="test-run-1",
            )

            self.assertTrue(registry_path.exists())
            registry = json.loads(registry_path.read_text(encoding="utf-8"))

        self.assertEqual(registry["runs"][0]["run_id"], "test-run-1")
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["remote_inference_used"])
        self.assertFalse(result["production_replacement_allowed"])
        self.assertFalse(result["auto_replace_production_models"])

        for candidate in result["candidates"]:
            self.assertGreater(candidate["score"]["total"], 0)
            self.assertIn("rubric", candidate["score"])
            self.assertEqual(len(candidate["smoke_tests"]), 2)
            for smoke_test in candidate["smoke_tests"]:
                self.assertTrue(
                    {
                        "timestamp",
                        "label",
                        "confidence",
                        "evidence",
                        "model_version",
                        "ontology_version",
                    }.issubset(smoke_test)
                )
                self.assertIn(smoke_test["label"], ontology_label_ids)
                self.assertEqual(smoke_test["ontology_version"], ontology["ontology_version"])
                self.assertGreaterEqual(len(smoke_test["evidence"]), 1)
                self.assertIs(validate_evidence(smoke_test["evidence"][0]), smoke_test["evidence"][0])
                self.assertFalse(smoke_test["checks"]["remote_inference_used"])

        recommendation = result["recommendation"]
        self.assertFalse(recommendation["production_replacement_allowed"])
        self.assertFalse(recommendation["auto_replace_production_models"])
        self.assertTrue(recommendation["requires_human_promotion"])
        self.assertEqual(
            {model["modality"] for model in recommendation["recommended_models"]},
            {"vision", "asr"},
        )

    def test_admin_refresh_endpoint_runs_explicit_local_registry_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "admin-registry.json"
            response = refresh_model_discovery(
                ModelDiscoveryRefreshRequest(
                    trigger="admin_refresh",
                    source_mode="static",
                    ontology_version="football-2026-05-11",
                    tasks_by_modality={"vision": ["zero-shot-image-classification"]},
                    sample_clips=[
                        ModelDiscoverySampleClipRequest(
                            sample_clip_id="admin-smoke-clip",
                            duration_seconds=1,
                            timestamps=[0],
                            modalities=["vision"],
                        )
                    ],
                    limit_per_task=1,
                    registry_path=str(registry_path),
                )
            )

            result = response["data"]["model_discovery"]
            self.assertTrue(registry_path.exists())

        self.assertEqual(result["trigger"], "admin_refresh")
        self.assertEqual(result["source"], "static-local-seed")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["registry"]["path"], str(registry_path))
        self.assertFalse(result["auto_replace_production_models"])
        self.assertEqual(
            result["recommendation"]["recommended_models"][0]["model_id"],
            "openai/clip-vit-base-patch32",
        )


if __name__ == "__main__":
    unittest.main()
