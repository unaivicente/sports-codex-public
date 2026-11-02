import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Database,
  FileVideo,
  ListChecks,
  Play,
  RefreshCw,
  Send,
  Upload,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  API_BASE_URL,
  fetchFeedbackQualityDashboard,
  fetchHealth,
  fetchMockPredictions,
  fetchSports,
  submitCorrection,
  uploadVideo,
} from "./api";
import type {
  CorrectionSubmissionDataContract,
  FeedbackQualityDashboardContract,
  HumanCorrectionContract,
  OntologyContract,
  PredictionContract,
  SportContract,
  VideoRecordContract,
} from "./contracts";

type BackendState = "checking" | "connected" | "disconnected";

interface BackendStatus {
  state: BackendState;
  message: string;
  contractVersion?: string;
}

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({
    state: "checking",
    message: "Checking backend",
  });
  const [sports, setSports] = useState<SportContract[]>([]);
  const [selectedSportId, setSelectedSportId] = useState("");
  const [selectedOntologyId, setSelectedOntologyId] = useState("");
  const [predictions, setPredictions] = useState<PredictionContract[]>([]);
  const [predictionStatus, setPredictionStatus] = useState("Select a video");
  const [isRequestingPredictions, setIsRequestingPredictions] = useState(false);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoRecord, setVideoRecord] = useState<VideoRecordContract | null>(null);
  const [videoStatus, setVideoStatus] = useState("No local video selected");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [selectedPredictionId, setSelectedPredictionId] = useState("");
  const [correctedLabel, setCorrectedLabel] = useState("");
  const [correctionNotes, setCorrectionNotes] = useState("");
  const [correctionStatus, setCorrectionStatus] = useState("No correction submitted");
  const [correctionSummary, setCorrectionSummary] =
    useState<CorrectionSubmissionDataContract | null>(null);
  const [isSubmittingCorrection, setIsSubmittingCorrection] = useState(false);
  const [feedbackDashboard, setFeedbackDashboard] =
    useState<FeedbackQualityDashboardContract | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState("Dashboard not loaded");
  const [isLoadingFeedback, setIsLoadingFeedback] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void loadBackendData();
  }, []);

  useEffect(() => {
    if (!videoFile) {
      setVideoUrl(null);
      return;
    }

    const objectUrl = URL.createObjectURL(videoFile);
    setVideoUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [videoFile]);

  const selectedSport = useMemo(
    () => sports.find((sport) => sport.sport_id === selectedSportId) ?? null,
    [sports, selectedSportId],
  );

  const selectedOntology = useMemo(() => {
    return selectedSport?.ontologies.find((ontology) => ontology.ontology_id === selectedOntologyId) ?? null;
  }, [selectedOntologyId, selectedSport]);

  const labelsById = useMemo(() => {
    return new Map(selectedOntology?.labels.map((label) => [label.label_id, label]) ?? []);
  }, [selectedOntology]);

  const selectedPrediction = useMemo(() => {
    return predictions.find((prediction) => prediction.prediction_id === selectedPredictionId) ?? null;
  }, [predictions, selectedPredictionId]);

  useEffect(() => {
    setCorrectedLabel(selectedPrediction?.label ?? "");
  }, [selectedPrediction?.label, selectedPrediction?.prediction_id]);

  useEffect(() => {
    if (backendStatus.state !== "connected") {
      return;
    }

    if (!selectedOntologyId) {
      setFeedbackDashboard(null);
      setFeedbackStatus("No ontology selected");
      return;
    }

    void loadFeedbackDashboard(selectedOntologyId);
  }, [backendStatus.state, selectedOntologyId]);

  async function loadBackendData() {
    const controller = new AbortController();
    setBackendStatus({ state: "checking", message: "Checking backend" });

    try {
      const [health, sportsData] = await Promise.all([
        fetchHealth(controller.signal),
        fetchSports(controller.signal),
      ]);
      const defaultSport =
        sportsData.sports.find((sport) => sport.sport_id === sportsData.default_sport_id) ??
        sportsData.sports[0] ??
        null;
      const defaultOntology =
        defaultSport?.ontologies.find(
          (ontology) => ontology.ontology_id === sportsData.default_ontology_id,
        ) ??
        defaultSport?.ontologies[0] ??
        null;

      setSports(sportsData.sports);
      setSelectedSportId((current) => {
        const sportIds = new Set(sportsData.sports.map((sport) => sport.sport_id));
        return sportIds.has(current) ? current : defaultSport?.sport_id ?? "";
      });
      setSelectedOntologyId((current) => {
        const ontologyIds = new Set(
          sportsData.sports.flatMap((sport) =>
            sport.ontologies.map((ontology) => ontology.ontology_id),
          ),
        );
        return ontologyIds.has(current) ? current : defaultOntology?.ontology_id ?? "";
      });
      setBackendStatus({
        state: "connected",
        message: "Backend connected",
        contractVersion: health.contract_version,
      });
      setPredictionStatus(videoRecord ? "Ready for mock predictions" : "Select a video");
    } catch (error: unknown) {
      setSports([]);
      setSelectedSportId("");
      setSelectedOntologyId("");
      setPredictions([]);
      setSelectedPredictionId("");
      setFeedbackDashboard(null);
      setFeedbackStatus("Backend unavailable");
      setBackendStatus({
        state: "disconnected",
        message: error instanceof Error ? error.message : "Backend unavailable",
      });
      setPredictionStatus("Backend unavailable");
    }
  }

  async function loadFeedbackDashboard(ontologyId: string) {
    setIsLoadingFeedback(true);
    setFeedbackStatus("Loading local feedback metrics");

    try {
      const payload = await fetchFeedbackQualityDashboard(ontologyId);
      setFeedbackDashboard(payload.dashboard);
      setFeedbackStatus(`Updated ${formatDateTime(payload.dashboard.generated_at)}`);
    } catch (error: unknown) {
      setFeedbackDashboard(null);
      setFeedbackStatus(error instanceof Error ? error.message : "Feedback dashboard unavailable");
    } finally {
      setIsLoadingFeedback(false);
    }
  }

  function handleVideoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    void acceptVideoFile(file);
  }

  function handleDemoVideo() {
    const file = new File(["local mock video fixture"], "demo-local-fixture.mp4", {
      type: "video/mp4",
    });
    void acceptVideoFile(file);
  }

  async function acceptVideoFile(file: File | null) {
    setVideoFile(file);
    setVideoRecord(null);
    setPredictions([]);
    setSelectedPredictionId("");
    setCorrectionSummary(null);
    setCorrectionStatus("No correction submitted");

    if (!file) {
      setVideoStatus("No local video selected");
      setPredictionStatus("Select a video");
      return;
    }

    setVideoStatus("Uploading to local stub");
    setPredictionStatus("Waiting for upload stub");

    try {
      const payload = await uploadVideo(file);
      setVideoRecord(payload.video);
      setVideoStatus("Upload stub accepted");
      setPredictionStatus("Ready for mock predictions");
    } catch (error: unknown) {
      setVideoStatus(error instanceof Error ? error.message : "Upload failed");
      setPredictionStatus("Video upload required");
    }
  }

  function handleSportChange(sportId: string) {
    const sport = sports.find((item) => item.sport_id === sportId) ?? null;
    setSelectedSportId(sportId);
    setSelectedOntologyId(sport?.ontologies[0]?.ontology_id ?? "");
    clearPredictionState();
  }

  function handleOntologyChange(ontologyId: string) {
    setSelectedOntologyId(ontologyId);
    clearPredictionState();
  }

  async function handleRequestPredictions() {
    if (!selectedOntology || !videoRecord) {
      return;
    }

    setIsRequestingPredictions(true);
    setPredictionStatus("Requesting mock predictions");
    setCorrectionSummary(null);
    setCorrectionStatus("No correction submitted");

    try {
      const payload = await fetchMockPredictions(selectedOntology.ontology_id, videoRecord.video_id);
      setPredictions(payload.predictions);
      setSelectedPredictionId(payload.predictions[0]?.prediction_id ?? "");
      setPredictionStatus(`${payload.predictions.length} mock predictions loaded`);
    } catch (error: unknown) {
      setPredictions([]);
      setSelectedPredictionId("");
      setPredictionStatus(error instanceof Error ? error.message : "Prediction request failed");
    } finally {
      setIsRequestingPredictions(false);
    }
  }

  async function handleSubmitCorrection() {
    if (!selectedPrediction || !correctedLabel) {
      return;
    }

    const sameLabel = correctedLabel === selectedPrediction.label;
    const correction: HumanCorrectionContract = {
      correction_id: makeLocalId("correction"),
      video_id: selectedPrediction.video_id,
      target_interval: {
        interval_start: selectedPrediction.interval_start,
        interval_end: selectedPrediction.interval_end,
        timebase: selectedPrediction.timebase,
        source_prediction_ids: [selectedPrediction.prediction_id],
      },
      corrected_intervals: [
        {
          interval_start: selectedPrediction.interval_start,
          interval_end: selectedPrediction.interval_end,
          timebase: selectedPrediction.timebase,
          label: correctedLabel,
          ontology_version: selectedPrediction.ontology_version,
          reviewer_confidence: 0.75,
          evidence_refs: selectedPrediction.evidence.map((evidence) => evidence.evidence_id),
          notes: correctionNotes || undefined,
        },
      ],
      correction_type: sameLabel ? "confirm" : "modify",
      edit_operation: sameLabel ? "none" : "relabel",
      source_predictions: [selectedPrediction],
      primary_source_prediction_id: selectedPrediction.prediction_id,
      ontology_version: selectedPrediction.ontology_version,
      evidence_snapshot: selectedPrediction.evidence,
      learning_mode: "soft",
      reviewer_id: "local-reviewer",
      reviewer_role: "unknown",
      reviewer_confidence: 0.75,
      trust_weight: 0,
      review_status: "pending",
      post_correction_model_agreement: null,
      confidence_delta: null,
      created_at: new Date().toISOString(),
      notes: correctionNotes || undefined,
    };

    setIsSubmittingCorrection(true);
    setCorrectionStatus("Submitting correction");

    try {
      const response = await submitCorrection(correction);
      setCorrectionSummary(response);
      setCorrectionStatus("Correction accepted by local stub");
    } catch (error: unknown) {
      setCorrectionSummary(null);
      setCorrectionStatus(error instanceof Error ? error.message : "Correction submission failed");
    } finally {
      setIsSubmittingCorrection(false);
    }
  }

  function clearPredictionState() {
    setPredictions([]);
    setSelectedPredictionId("");
    setCorrectionSummary(null);
    setCorrectionStatus("No correction submitted");
    setPredictionStatus(videoRecord ? "Ready for mock predictions" : "Select a video");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local-first MVP</p>
          <h1>Sports Metadata Labeller</h1>
        </div>
        <div className="topbar-actions">
          <StatusPill status={backendStatus} />
          <button className="icon-button" type="button" onClick={() => void loadBackendData()}>
            <RefreshCw size={16} aria-hidden="true" />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <section className="workspace-grid" aria-label="Labelling workspace">
        <aside className="panel controls-panel">
          <PanelHeader icon={<FileVideo size={18} />} title="Video Source" />
          <input
            ref={fileInputRef}
            className="file-input"
            type="file"
            accept="video/mp4,video/*"
            onChange={handleVideoChange}
          />
          <button className="upload-target" type="button" onClick={() => fileInputRef.current?.click()}>
            <Upload size={22} aria-hidden="true" />
            <span>{videoFile ? videoFile.name : "Select local video"}</span>
          </button>
          <button className="secondary-button" type="button" onClick={handleDemoVideo}>
            <FileVideo size={16} aria-hidden="true" />
            <span>Use demo clip</span>
          </button>
          <dl className="metadata-list">
            <div>
              <dt>Source</dt>
              <dd>{videoFile ? "Local file" : "None selected"}</dd>
            </div>
            <div>
              <dt>Upload</dt>
              <dd>{videoStatus}</dd>
            </div>
            <div>
              <dt>API</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
          </dl>

          <div className="field-group">
            <label htmlFor="sport-selector">Sport</label>
            <select
              id="sport-selector"
              value={selectedSportId}
              disabled={sports.length === 0}
              onChange={(event) => handleSportChange(event.target.value)}
            >
              {sports.length === 0 ? (
                <option value="">Backend unavailable</option>
              ) : (
                sports.map((sport) => (
                  <option key={sport.sport_id} value={sport.sport_id}>
                    {sport.display_name}
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="field-group">
            <label htmlFor="ontology-selector">Ontology</label>
            <select
              id="ontology-selector"
              value={selectedOntologyId}
              disabled={!selectedSport}
              onChange={(event) => handleOntologyChange(event.target.value)}
            >
              {!selectedSport ? (
                <option value="">No sport selected</option>
              ) : (
                selectedSport.ontologies.map((ontology) => (
                  <option key={ontology.ontology_id} value={ontology.ontology_id}>
                    {ontology.display_name ?? ontology.ontology_id}
                  </option>
                ))
              )}
            </select>
          </div>

          <dl className="metadata-list">
            <div>
              <dt>Version</dt>
              <dd>{selectedOntology?.ontology_version ?? "Not loaded"}</dd>
            </div>
            <div>
              <dt>Labels</dt>
              <dd>{selectedOntology?.labels.length ?? 0}</dd>
            </div>
          </dl>
        </aside>

        <section className="panel player-panel">
          <PanelHeader icon={<Activity size={18} />} title="Video Review" />
          <div className="video-frame">
            {videoUrl ? (
              <video controls src={videoUrl} aria-label="Selected local video preview" />
            ) : (
              <div className="video-placeholder">
                <FileVideo size={42} aria-hidden="true" />
                <span>No video selected</span>
              </div>
            )}
          </div>
        </section>

        <aside className="panel prediction-panel">
          <PanelHeader icon={<Database size={18} />} title="Prediction Payload" />
          <div className="summary-grid">
            <Metric label="Backend" value={backendStatus.state} />
            <Metric label="Video" value={videoRecord ? "accepted" : "n/a"} />
            <Metric label="Predictions" value={String(predictions.length)} />
          </div>
          <button
            className="primary-button"
            type="button"
            disabled={!videoRecord || !selectedOntology || isRequestingPredictions}
            onClick={() => void handleRequestPredictions()}
          >
            <Play size={16} aria-hidden="true" />
            <span>{isRequestingPredictions ? "Requesting" : "Request mock predictions"}</span>
          </button>
          <p className="status-line">{predictionStatus}</p>
          <div className="prediction-list" aria-label="Mock prediction records">
            {predictions.map((prediction) => {
              const label = labelsById.get(prediction.label);
              const selected = prediction.prediction_id === selectedPredictionId;
              return (
                <button
                  className={`prediction-record ${selected ? "selected" : ""}`}
                  key={prediction.prediction_id}
                  type="button"
                  onClick={() => setSelectedPredictionId(prediction.prediction_id)}
                >
                  <div>
                    <strong>{label?.display_name ?? prediction.label}</strong>
                    <span>{prediction.label}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Time</dt>
                      <dd>{formatSeconds(prediction.timestamp)}</dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{formatConfidence(prediction.confidence)}</dd>
                    </div>
                    <div>
                      <dt>Evidence</dt>
                      <dd>{prediction.evidence.length}</dd>
                    </div>
                  </dl>
                </button>
              );
            })}
          </div>
        </aside>
      </section>

      <section className="review-grid" aria-label="Timeline and correction workflow">
        <section className="timeline-panel" aria-label="Timeline">
          <div className="timeline-header">
            <PanelHeader icon={<Clock3 size={18} />} title="Timeline" />
            <span>{selectedSport?.display_name ?? "No sport selected"}</span>
          </div>
          <Timeline predictions={predictions} labelsById={labelsById} />
        </section>

        <aside className="panel correction-panel">
          <PanelHeader icon={<ListChecks size={18} />} title="Correction" />
          <div className="correction-form">
            <div className="field-group">
              <label htmlFor="prediction-selector">Prediction</label>
              <select
                id="prediction-selector"
                value={selectedPredictionId}
                disabled={predictions.length === 0}
                onChange={(event) => setSelectedPredictionId(event.target.value)}
              >
                {predictions.length === 0 ? (
                  <option value="">No prediction selected</option>
                ) : (
                  predictions.map((prediction) => {
                    const label = labelsById.get(prediction.label);
                    return (
                      <option key={prediction.prediction_id} value={prediction.prediction_id}>
                        {formatSeconds(prediction.timestamp)} - {label?.display_name ?? prediction.label}
                      </option>
                    );
                  })
                )}
              </select>
            </div>

            <div className="field-group">
              <label htmlFor="corrected-label-selector">Corrected label</label>
              <select
                id="corrected-label-selector"
                value={correctedLabel}
                disabled={!selectedPrediction || !selectedOntology}
                onChange={(event) => setCorrectedLabel(event.target.value)}
              >
                {!selectedOntology ? (
                  <option value="">No ontology loaded</option>
                ) : (
                  selectedOntology.labels.map((label) => (
                    <option key={label.label_id} value={label.label_id}>
                      {label.display_name}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="field-group">
              <label htmlFor="correction-notes">Notes</label>
              <textarea
                id="correction-notes"
                value={correctionNotes}
                rows={3}
                onChange={(event) => setCorrectionNotes(event.target.value)}
              />
            </div>

            <button
              className="primary-button"
              type="button"
              disabled={!selectedPrediction || !correctedLabel || isSubmittingCorrection}
              onClick={() => void handleSubmitCorrection()}
            >
              <Send size={16} aria-hidden="true" />
              <span>{isSubmittingCorrection ? "Submitting" : "Submit correction"}</span>
            </button>
          </div>

          <p className="status-line">{correctionStatus}</p>
          {correctionSummary ? (
            <dl className="metadata-list correction-summary">
              <div>
                <dt>Preserved</dt>
                <dd>{correctionSummary.preserved_source_prediction_ids.join(", ")}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{correctionSummary.source_model_versions.join(", ")}</dd>
              </div>
              <div>
                <dt>Ontology</dt>
                <dd>{correctionSummary.source_ontology_versions.join(", ")}</dd>
              </div>
            </dl>
          ) : (
            <div className="correction-empty">
              <CheckCircle2 size={18} aria-hidden="true" />
              <span>Schema-ready</span>
            </div>
          )}
        </aside>
      </section>

      <FeedbackQualityDashboard
        dashboard={feedbackDashboard}
        isLoading={isLoadingFeedback}
        onRefresh={() => selectedOntologyId && void loadFeedbackDashboard(selectedOntologyId)}
        status={feedbackStatus}
      />
    </main>
  );
}

interface PanelHeaderProps {
  icon: ReactNode;
  title: string;
}

function PanelHeader({ icon, title }: PanelHeaderProps) {
  return (
    <div className="panel-header">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function StatusPill({ status }: { status: BackendStatus }) {
  const connected = status.state === "connected";
  const checking = status.state === "checking";
  const Icon = connected ? Wifi : WifiOff;

  return (
    <div className={`status-pill ${connected ? "connected" : ""} ${checking ? "checking" : ""}`}>
      <Icon size={16} aria-hidden="true" />
      <span>{status.message}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function FeedbackQualityDashboard({
  dashboard,
  isLoading,
  onRefresh,
  status,
}: {
  dashboard: FeedbackQualityDashboardContract | null;
  isLoading: boolean;
  onRefresh: () => void;
  status: string;
}) {
  return (
    <section className="feedback-dashboard" aria-label="Feedback quality dashboard">
      <div className="feedback-dashboard-header">
        <div>
          <PanelHeader icon={<Activity size={18} />} title="Feedback Quality" />
          <p className="status-line">{status}</p>
        </div>
        <button className="icon-button" type="button" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw size={16} aria-hidden="true" />
          <span>{isLoading ? "Refreshing" : "Refresh"}</span>
        </button>
      </div>

      {dashboard ? (
        <div className="quality-grid">
          <section className="quality-section">
            <h3>Correction Volume</h3>
            <div className="mode-list">
              {dashboard.correction_volume_by_mode.map((mode) => (
                <div className="mode-row" key={mode.learning_mode}>
                  <div>
                    <strong>{formatMode(mode.learning_mode)}</strong>
                    <span>Trust {formatConfidence(mode.average_trust_weight)}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Total</dt>
                      <dd>{mode.correction_count}</dd>
                    </div>
                    <div>
                      <dt>Accepted</dt>
                      <dd>{mode.accepted_count}</dd>
                    </div>
                    <div>
                      <dt>Review</dt>
                      <dd>{mode.needs_review_count}</dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          </section>

          <section className="quality-section acceptance-section">
            <h3>Acceptance Rate</h3>
            <strong>{formatConfidence(dashboard.correction_acceptance_rate.acceptance_rate)}</strong>
            <dl className="compact-metrics">
              <div>
                <dt>Accepted</dt>
                <dd>{dashboard.correction_acceptance_rate.accepted_count}</dd>
              </div>
              <div>
                <dt>Total</dt>
                <dd>{dashboard.correction_acceptance_rate.total_corrections}</dd>
              </div>
              <div>
                <dt>Needs review</dt>
                <dd>{dashboard.correction_acceptance_rate.needs_review_count}</dd>
              </div>
            </dl>
          </section>

          <section className="quality-section">
            <h3>High-Disagreement Labels</h3>
            <div className="quality-list">
              {dashboard.high_disagreement_labels.map((label) => (
                <article className="quality-item" key={label.label}>
                  <div>
                    <strong>{label.label_display_name}</strong>
                    <span>{label.label}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Disagreement</dt>
                      <dd>{formatConfidence(label.disagreement_rate)}</dd>
                    </div>
                    <div>
                      <dt>Agreement</dt>
                      <dd>{formatConfidence(label.average_model_agreement)}</dd>
                    </div>
                    <div>
                      <dt>Delta</dt>
                      <dd>{formatSignedPercent(label.average_confidence_delta)}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

          <section className="quality-section">
            <h3>Reviewer Reliability</h3>
            <div className="quality-list">
              {dashboard.reviewer_reliability_indicators.map((reviewer) => (
                <article className="quality-item" key={reviewer.reviewer_id}>
                  <div>
                    <strong>{reviewer.reviewer_id}</strong>
                    <span>{formatMode(reviewer.reviewer_role)}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Reliability</dt>
                      <dd>{formatConfidence(reviewer.reliability_score)}</dd>
                    </div>
                    <div>
                      <dt>Accepted</dt>
                      <dd>
                        {reviewer.accepted_count}/{reviewer.reviewed_count}
                      </dd>
                    </div>
                    <div>
                      <dt>Conflicts</dt>
                      <dd>{reviewer.contradiction_count}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

          <section className="quality-section soft-patterns-section">
            <h3>Soft Feedback Review</h3>
            <div className="quality-list">
              {dashboard.soft_feedback_patterns.map((pattern) => (
                <article className="quality-item" key={pattern.pattern_id}>
                  <div>
                    <strong>{pattern.label_display_name}</strong>
                    <span>{pattern.label}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Signals</dt>
                      <dd>{pattern.occurrences}</dd>
                    </div>
                    <div>
                      <dt>Reviewers</dt>
                      <dd>{pattern.reviewer_count}</dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{formatConfidence(pattern.average_reviewer_confidence)}</dd>
                    </div>
                  </dl>
                  <p>{pattern.review_reason}</p>
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : (
        <div className="feedback-empty">
          <Activity size={20} aria-hidden="true" />
          <span>{status}</span>
        </div>
      )}
    </section>
  );
}

function Timeline({
  predictions,
  labelsById,
}: {
  predictions: PredictionContract[];
  labelsById: Map<string, { display_name: string }>;
}) {
  const duration = Math.max(30, ...predictions.map((prediction) => prediction.interval_end + 2));

  if (predictions.length === 0) {
    return (
      <div className="timeline-empty">
        <span>No mock predictions loaded</span>
      </div>
    );
  }

  return (
    <div className="timeline-track">
      <div className="timeline-axis">
        <span>0s</span>
        <span>{formatSeconds(duration)}</span>
      </div>
      <div className="timeline-lane" style={{ minHeight: `${predictions.length * 56 + 20}px` }}>
        {predictions.map((prediction, index) => {
          const start = (prediction.interval_start / duration) * 100;
          const width = Math.max(
            ((prediction.interval_end - prediction.interval_start) / duration) * 100,
            8,
          );
          const label = labelsById.get(prediction.label);

          return (
            <div
              className="timeline-item"
              key={prediction.prediction_id}
              style={{ left: `${start}%`, top: `${12 + index * 56}px`, width: `${width}%` }}
              title={`${label?.display_name ?? prediction.label} at ${formatSeconds(prediction.timestamp)}`}
            >
              <strong>{label?.display_name ?? prediction.label}</strong>
              <span>{formatConfidence(prediction.confidence)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function makeLocalId(prefix: string) {
  const random =
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function formatSeconds(value: number) {
  return `${value.toFixed(0)}s`;
}

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatSignedPercent(value: number) {
  const percentage = Math.round(value * 100);
  return `${percentage > 0 ? "+" : ""}${percentage}%`;
}

function formatMode(value: string) {
  return value
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default App;
