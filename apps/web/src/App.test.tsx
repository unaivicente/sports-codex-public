import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FeedbackQualityDashboard } from "./App";
import type { FeedbackQualityDashboardContract } from "./contracts";

const dashboardFixture = {
  generated_at: "2026-05-30T12:00:00Z",
  ontology_id: "fixture-local-mvp",
  ontology_version: "fixture-local-2026-05-30",
  model_version: "mock-fusion-local-0.1.0",
  correction_volume_by_mode: [
    {
      learning_mode: "training",
      correction_count: 6,
      accepted_count: 5,
      rejected_count: 0,
      needs_review_count: 1,
      average_trust_weight: 0.72,
    },
    {
      learning_mode: "soft",
      correction_count: 8,
      accepted_count: 3,
      rejected_count: 1,
      needs_review_count: 4,
      average_trust_weight: 0.11,
    },
  ],
  correction_acceptance_rate: {
    accepted_count: 8,
    total_corrections: 14,
    rejected_count: 1,
    needs_review_count: 5,
    acceptance_rate: 0.57,
  },
  high_disagreement_labels: [
    {
      label: "fixture.event.pass",
      label_display_name: "Pass",
      label_type: "event",
      ontology_version: "fixture-local-2026-05-30",
      correction_count: 6,
      disagreement_count: 3,
      disagreement_rate: 0.5,
      average_model_agreement: 0.48,
      average_confidence_delta: -0.12,
      source_model_version: "mock-fusion-local-0.1.0",
    },
  ],
  reviewer_reliability_indicators: [
    {
      reviewer_id: "internal-reviewer-1",
      reviewer_role: "internal",
      reviewed_count: 5,
      accepted_count: 4,
      reliability_score: 0.7,
      average_reviewer_confidence: 0.86,
      contradiction_count: 1,
    },
  ],
  soft_feedback_patterns: [
    {
      pattern_id: "soft-fixture.event.pass",
      label: "fixture.event.pass",
      label_display_name: "Pass",
      label_type: "event",
      ontology_version: "fixture-local-2026-05-30",
      learning_mode: "soft",
      occurrences: 3,
      reviewer_count: 2,
      average_reviewer_confidence: 0.56,
      review_status: "needs_review",
      review_reason: "Repeated soft corrections with low reviewer confidence.",
    },
  ],
} satisfies FeedbackQualityDashboardContract;

describe("FeedbackQualityDashboard", () => {
  it("renders all feedback quality sections from ontology-backed dashboard data", () => {
    const html = renderToStaticMarkup(
      <FeedbackQualityDashboard
        dashboard={dashboardFixture}
        isLoading={false}
        onRefresh={() => undefined}
        status="Updated"
      />,
    );

    expect(html).toContain("Correction Volume");
    expect(html).toContain("Training");
    expect(html).toContain("Soft");
    expect(html).toContain("Acceptance Rate");
    expect(html).toContain("High-Disagreement Labels");
    expect(html).toContain("Reviewer Reliability");
    expect(html).toContain("Soft Feedback Review");
    expect(html).toContain("Pass");
    expect(html).toContain("fixture.event.pass");
    expect(html).toContain("Repeated soft corrections with low reviewer confidence.");
  });
});
