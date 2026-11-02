import { describe, expect, it } from "vitest";
import { CONTRACT_VERSION } from "./contracts";
import type {
  CorrectionSubmissionDataContract,
  FeedbackQualityDashboardDataContract,
  HumanCorrectionContract,
  MockPredictionsDataContract,
  OntologyContract,
  PredictionContract,
  SportsDataContract,
  VideoUploadDataContract,
} from "./contracts";

const ontologyFixture = {
  ontology_id: "fixture-local-mvp",
  ontology_version: "fixture-local-2026-05-28",
  display_name: "Fixture",
  labels: [
    {
      label_id: "fixture.phase.active",
      label_type: "phase",
      display_name: "Active",
    },
    {
      label_id: "fixture.event.detected",
      label_type: "event",
      display_name: "Detected",
    },
  ],
  transition_rules: [
    {
      from_label: "fixture.phase.active",
      to_label: "fixture.event.detected",
      rule_type: "allowed_during",
      max_gap_seconds: 1,
    },
  ],
} satisfies OntologyContract;

const predictionFixture = {
  prediction_id: "prediction-fixture-1",
  video_id: "local-video-fixture",
  timestamp: 4,
  interval_start: 4,
  interval_end: 5,
  duration_seconds: 1,
  timebase: "seconds",
  label: ontologyFixture.labels[1].label_id,
  confidence: 0.74,
  evidence: [
    {
      evidence_id: "evidence-fixture-1",
      modality: "vision",
      timestamp: 4,
      type: "local_mock_signal",
      value: { ontology_label_id: ontologyFixture.labels[1].label_id },
      confidence: 0.69,
      source_model_version: "mock-extractor-local-0.1.0",
    },
  ],
  model_version: "mock-fusion-local-0.1.0",
  ontology_version: ontologyFixture.ontology_version,
  post_correction_model_agreement: null,
  confidence_delta: null,
  created_at: "2026-05-28T12:00:00Z",
} satisfies PredictionContract;

describe("frontend contract fixtures", () => {
  it("exposes the shared local contract version", () => {
    expect(CONTRACT_VERSION).toBe("0.1.0");
  });

  it("models ontology-driven mock prediction payloads with required provenance", () => {
    const payload = {
      video_id: predictionFixture.video_id,
      ontology_id: ontologyFixture.ontology_id,
      ontology_version: ontologyFixture.ontology_version,
      model_version: predictionFixture.model_version,
      predictions: [predictionFixture],
    } satisfies MockPredictionsDataContract;
    const ontologyLabelIds = new Set(ontologyFixture.labels.map((label) => label.label_id));

    expect(payload.predictions).toHaveLength(1);
    expect(ontologyLabelIds.has(payload.predictions[0].label)).toBe(true);
    expect(payload.predictions[0]).toMatchObject({
      timestamp: 4,
      confidence: 0.74,
      model_version: payload.model_version,
      ontology_version: payload.ontology_version,
    });
    expect(payload.predictions[0].evidence[0]).toMatchObject({
      timestamp: 4,
      source_model_version: "mock-extractor-local-0.1.0",
    });
  });

  it("models backend sport discovery for ontology-backed labels", () => {
    const payload = {
      sports: [
        {
          sport_id: "fixture",
          display_name: "Fixture",
          ontologies: [ontologyFixture],
        },
      ],
      default_sport_id: "fixture",
      default_ontology_id: ontologyFixture.ontology_id,
    } satisfies SportsDataContract;

    expect(payload.sports[0].ontologies[0].labels[0].label_id).toBe("fixture.phase.active");
  });

  it("models local video upload stubs without storage or processing", () => {
    const payload = {
      video: {
        video_id: "video-fixture",
        filename: "clip.mp4",
        content_type: "video/mp4",
        byte_count: 128,
        status: "accepted_stub",
        storage: "not_persisted",
        processing: "not_started",
      },
    } satisfies VideoUploadDataContract;

    expect(payload.video.storage).toBe("not_persisted");
    expect(payload.video.processing).toBe("not_started");
  });

  it("models UNA-8 correction submissions with source provenance", () => {
    const correction = {
      correction_id: "correction-fixture-1",
      video_id: predictionFixture.video_id,
      target_interval: {
        interval_start: predictionFixture.interval_start,
        interval_end: predictionFixture.interval_end,
        timebase: predictionFixture.timebase,
        source_prediction_ids: [predictionFixture.prediction_id],
      },
      corrected_intervals: [
        {
          interval_start: predictionFixture.interval_start,
          interval_end: predictionFixture.interval_end,
          timebase: predictionFixture.timebase,
          label: ontologyFixture.labels[0].label_id,
          ontology_version: predictionFixture.ontology_version,
          reviewer_confidence: 0.75,
          evidence_refs: predictionFixture.evidence.map((evidence) => evidence.evidence_id),
        },
      ],
      correction_type: "modify",
      edit_operation: "relabel",
      source_predictions: [predictionFixture],
      primary_source_prediction_id: predictionFixture.prediction_id,
      ontology_version: predictionFixture.ontology_version,
      evidence_snapshot: predictionFixture.evidence,
      learning_mode: "soft",
      reviewer_id: "local-reviewer",
      reviewer_role: "unknown",
      reviewer_confidence: 0.75,
      trust_weight: 0,
      review_status: "pending",
      post_correction_model_agreement: null,
      confidence_delta: null,
      created_at: "2026-05-28T12:01:00Z",
    } satisfies HumanCorrectionContract;
    const payload = {
      accepted: true,
      correction,
      preserved_source_prediction_ids: [predictionFixture.prediction_id],
      source_model_versions: [predictionFixture.model_version],
      source_ontology_versions: [predictionFixture.ontology_version],
    } satisfies CorrectionSubmissionDataContract;

    expect(payload.correction.source_predictions[0].model_version).toBe(
      "mock-fusion-local-0.1.0",
    );
    expect(payload.preserved_source_prediction_ids).toEqual([predictionFixture.prediction_id]);
  });

  it("models UNA-59 feedback quality dashboard metrics from ontology labels", () => {
    const payload = {
      dashboard: {
        generated_at: "2026-05-30T12:00:00Z",
        ontology_id: ontologyFixture.ontology_id,
        ontology_version: ontologyFixture.ontology_version,
        model_version: predictionFixture.model_version,
        correction_volume_by_mode: [
          {
            learning_mode: "training",
            correction_count: 2,
            accepted_count: 2,
            rejected_count: 0,
            needs_review_count: 0,
            average_trust_weight: 0.9,
          },
          {
            learning_mode: "soft",
            correction_count: 3,
            accepted_count: 1,
            rejected_count: 0,
            needs_review_count: 2,
            average_trust_weight: 0.2,
          },
        ],
        correction_acceptance_rate: {
          accepted_count: 3,
          total_corrections: 5,
          rejected_count: 0,
          needs_review_count: 2,
          acceptance_rate: 0.6,
        },
        high_disagreement_labels: [
          {
            label: ontologyFixture.labels[1].label_id,
            label_display_name: ontologyFixture.labels[1].display_name,
            label_type: ontologyFixture.labels[1].label_type,
            ontology_version: ontologyFixture.ontology_version,
            correction_count: 3,
            disagreement_count: 2,
            disagreement_rate: 0.67,
            average_model_agreement: 0.25,
            average_confidence_delta: -0.18,
            source_model_version: predictionFixture.model_version,
          },
        ],
        reviewer_reliability_indicators: [
          {
            reviewer_id: "internal-reviewer-1",
            reviewer_role: "internal",
            reviewed_count: 2,
            accepted_count: 2,
            reliability_score: 0.95,
            average_reviewer_confidence: 0.9,
            contradiction_count: 0,
          },
        ],
        soft_feedback_patterns: [
          {
            pattern_id: "soft-repeat-fixture.event.detected",
            label: ontologyFixture.labels[1].label_id,
            label_display_name: ontologyFixture.labels[1].display_name,
            label_type: ontologyFixture.labels[1].label_type,
            ontology_version: ontologyFixture.ontology_version,
            learning_mode: "soft",
            occurrences: 2,
            reviewer_count: 2,
            average_reviewer_confidence: 0.58,
            review_status: "needs_review",
            review_reason: "Repeated soft corrections with low reviewer confidence.",
          },
        ],
      },
    } satisfies FeedbackQualityDashboardDataContract;
    const ontologyLabelIds = new Set(ontologyFixture.labels.map((label) => label.label_id));

    expect(payload.dashboard.correction_volume_by_mode.map((mode) => mode.learning_mode)).toEqual([
      "training",
      "soft",
    ]);
    expect(payload.dashboard.correction_acceptance_rate.acceptance_rate).toBe(0.6);
    expect(ontologyLabelIds.has(payload.dashboard.high_disagreement_labels[0].label)).toBe(true);
    expect(ontologyLabelIds.has(payload.dashboard.soft_feedback_patterns[0].label)).toBe(true);
    expect(payload.dashboard.soft_feedback_patterns[0].review_status).toBe("needs_review");
  });
});
