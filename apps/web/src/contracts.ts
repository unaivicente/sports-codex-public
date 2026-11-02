export const CONTRACT_VERSION = "0.1.0" as const;

export interface OntologyLabelContract {
  label_id: string;
  label_type: string;
  display_name: string;
  description?: string;
  parents?: string[];
  mutually_exclusive_with?: string[];
  metadata?: Record<string, unknown>;
}

export interface OntologyTransitionRuleContract {
  from_label: string;
  to_label: string;
  rule_type: string;
  min_gap_seconds?: number;
  max_gap_seconds?: number;
}

export interface OntologyContract {
  ontology_id: string;
  sport_id?: string;
  sport_display_name?: string;
  ontology_version: string;
  display_name?: string;
  labels: OntologyLabelContract[];
  transition_rules?: OntologyTransitionRuleContract[];
}

export interface EvidenceContract {
  evidence_id: string;
  modality: string;
  timestamp: number;
  type: string;
  value: unknown;
  confidence: number;
  source_model_version: string;
}

export interface PredictionContract {
  prediction_id: string;
  video_id: string;
  timestamp: number;
  interval_start: number;
  interval_end: number;
  duration_seconds: 1;
  timebase: string;
  label: string;
  confidence: number;
  evidence: EvidenceContract[];
  model_version: string;
  ontology_version: string;
  inference_config?: Record<string, unknown>;
  post_correction_model_agreement?: boolean | null;
  confidence_delta?: number | null;
  created_at: string;
}

export type CorrectionTypeContract = "confirm" | "modify" | "delete" | "add" | "ontology_gap";

export type EditOperationContract =
  | "none"
  | "split"
  | "merge"
  | "relabel"
  | "boundary_adjust";

export interface TargetIntervalContract {
  interval_start: number;
  interval_end: number;
  timebase: string;
  source_prediction_ids: string[];
}

export interface CorrectedIntervalContract {
  interval_start: number;
  interval_end: number;
  timebase: string;
  label: string | null;
  ontology_version: string;
  reviewer_confidence: number;
  evidence_refs: string[];
  proposed_label?: string;
  notes?: string;
}

export interface HumanCorrectionContract {
  correction_id: string;
  video_id: string;
  target_interval: TargetIntervalContract;
  corrected_intervals: CorrectedIntervalContract[];
  correction_type: CorrectionTypeContract;
  edit_operation: EditOperationContract;
  source_predictions: PredictionContract[];
  primary_source_prediction_id: string | null;
  ontology_version: string;
  evidence_snapshot: EvidenceContract[];
  learning_mode: "training" | "soft";
  reviewer_id: string;
  reviewer_role: "internal" | "external" | "admin" | "unknown";
  reviewer_confidence: number;
  trust_weight: number;
  review_status: "pending" | "accepted" | "rejected" | "needs_review";
  post_correction_model_agreement?: number | null;
  confidence_delta?: number | null;
  supersedes_correction_ids?: string[];
  created_at: string;
  notes?: string;
}

export interface TrainingDatasetRecordContract {
  training_example_id: string;
  dataset_version: string;
  correction_id: string;
  video_id: string;
  interval_start: number;
  interval_end: number;
  timebase: string;
  label: string;
  source: "confirmed" | "corrected" | "human_added";
  correction_type: "confirm" | "modify" | "add";
  edit_operation: EditOperationContract;
  learning_mode: "training" | "soft";
  trust_weight: number;
  ontology_version: string;
  source_prediction_ids: string[];
  source_model_versions: string[];
  source_ontology_versions: string[];
  evidence_snapshot: EvidenceContract[];
  split: "train" | "validation" | "test";
}

export interface ApiResponse<TData = unknown> {
  contract_version: typeof CONTRACT_VERSION;
  data?: TData;
  error?: string;
  errors?: string[];
}

export interface HealthContract {
  status: "ok";
  contract_version: typeof CONTRACT_VERSION;
}

export interface OntologyListDataContract {
  ontologies: OntologyContract[];
  default_ontology_id: string;
}

export interface SportContract {
  sport_id: string;
  display_name: string;
  ontologies: OntologyContract[];
}

export interface SportsDataContract {
  sports: SportContract[];
  default_sport_id: string;
  default_ontology_id: string;
}

export interface VideoRecordContract {
  video_id: string;
  filename: string;
  content_type: string;
  byte_count: number;
  status: "accepted_stub";
  storage: "not_persisted";
  processing: "not_started";
}

export interface VideoUploadDataContract {
  video: VideoRecordContract;
}

export interface MockPredictionsDataContract {
  video_id: string;
  ontology_id: string;
  ontology_version: string;
  model_version: string;
  predictions: PredictionContract[];
}

export interface CorrectionSubmissionDataContract {
  accepted: true;
  correction: HumanCorrectionContract;
  preserved_source_prediction_ids: string[];
  source_model_versions: string[];
  source_ontology_versions: string[];
}

export interface CorrectionVolumeByModeContract {
  learning_mode: "training" | "soft";
  correction_count: number;
  accepted_count: number;
  rejected_count: number;
  needs_review_count: number;
  average_trust_weight: number;
}

export interface CorrectionAcceptanceRateContract {
  accepted_count: number;
  total_corrections: number;
  rejected_count: number;
  needs_review_count: number;
  acceptance_rate: number;
}

export interface HighDisagreementLabelContract {
  label: string;
  label_display_name: string;
  label_type: string;
  ontology_version: string;
  correction_count: number;
  disagreement_count: number;
  disagreement_rate: number;
  average_model_agreement: number;
  average_confidence_delta: number;
  source_model_version: string;
}

export interface ReviewerReliabilityIndicatorContract {
  reviewer_id: string;
  reviewer_role: "internal" | "external" | "admin" | "unknown";
  reviewed_count: number;
  accepted_count: number;
  reliability_score: number;
  average_reviewer_confidence: number;
  contradiction_count: number;
}

export interface SoftFeedbackPatternContract {
  pattern_id: string;
  label: string;
  label_display_name: string;
  label_type: string;
  ontology_version: string;
  learning_mode: "soft";
  occurrences: number;
  reviewer_count: number;
  average_reviewer_confidence: number;
  review_status: "needs_review";
  review_reason: string;
}

export interface FeedbackQualityDashboardContract {
  generated_at: string;
  ontology_id: string;
  ontology_version: string;
  model_version: string;
  correction_volume_by_mode: CorrectionVolumeByModeContract[];
  correction_acceptance_rate: CorrectionAcceptanceRateContract;
  high_disagreement_labels: HighDisagreementLabelContract[];
  reviewer_reliability_indicators: ReviewerReliabilityIndicatorContract[];
  soft_feedback_patterns: SoftFeedbackPatternContract[];
}

export interface FeedbackQualityDashboardDataContract {
  dashboard: FeedbackQualityDashboardContract;
}
