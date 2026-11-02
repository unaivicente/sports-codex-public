import type {
  ApiResponse,
  CorrectionSubmissionDataContract,
  FeedbackQualityDashboardDataContract,
  HealthContract,
  HumanCorrectionContract,
  MockPredictionsDataContract,
  OntologyListDataContract,
  SportsDataContract,
  VideoUploadDataContract,
} from "./contracts";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_API_BASE_URL;

export async function fetchHealth(signal?: AbortSignal): Promise<HealthContract> {
  return request<HealthContract>("/health", { signal });
}

export async function fetchOntologies(signal?: AbortSignal): Promise<OntologyListDataContract> {
  const response = await request<ApiResponse<OntologyListDataContract>>("/api/ontologies", {
    signal,
  });
  if (!response.data) {
    throw new Error("Ontology response did not include data.");
  }
  return response.data;
}

export async function fetchSports(signal?: AbortSignal): Promise<SportsDataContract> {
  const response = await request<ApiResponse<SportsDataContract>>("/api/sports", {
    signal,
  });
  if (!response.data) {
    throw new Error("Sports response did not include data.");
  }
  return response.data;
}

export async function fetchFeedbackQualityDashboard(
  ontologyId?: string,
  signal?: AbortSignal,
): Promise<FeedbackQualityDashboardDataContract> {
  const query = ontologyId ? `?ontology_id=${encodeURIComponent(ontologyId)}` : "";
  const response = await request<ApiResponse<FeedbackQualityDashboardDataContract>>(
    `/api/feedback/quality${query}`,
    { signal },
  );
  if (!response.data) {
    throw new Error("Feedback quality response did not include data.");
  }
  return response.data;
}

export async function uploadVideo(
  file: File,
  signal?: AbortSignal,
): Promise<VideoUploadDataContract> {
  const body = new FormData();
  body.set("file", file, file.name);

  const response = await request<ApiResponse<VideoUploadDataContract>>("/api/videos", {
    method: "POST",
    body,
    headers: {
      "X-Local-Filename": file.name,
      "X-Local-Content-Type": file.type || "application/octet-stream",
    },
    signal,
  });
  if (!response.data) {
    throw new Error("Video upload response did not include data.");
  }
  return response.data;
}

export async function fetchMockPredictions(
  ontologyId: string,
  videoId: string,
  signal?: AbortSignal,
): Promise<MockPredictionsDataContract> {
  const response = await request<ApiResponse<MockPredictionsDataContract>>(
    "/api/predictions/mock",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ontology_id: ontologyId, video_id: videoId }),
      signal,
    },
  );
  if (!response.data) {
    throw new Error("Prediction response did not include data.");
  }
  return response.data;
}

export async function submitCorrection(
  correction: HumanCorrectionContract,
  signal?: AbortSignal,
): Promise<CorrectionSubmissionDataContract> {
  const response = await request<ApiResponse<CorrectionSubmissionDataContract>>("/api/corrections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(correction),
    signal,
  });
  if (!response.data) {
    throw new Error("Correction response did not include data.");
  }
  return response.data;
}

interface RequestOptions {
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit;
  signal?: AbortSignal;
}

async function request<TPayload>(path: string, options: RequestOptions = {}): Promise<TPayload> {
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body,
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = `API request failed with ${response.status}`;
    try {
      const payload = (await response.json()) as ApiResponse;
      if (payload.error) {
        detail = payload.errors?.length ? `${payload.error}: ${payload.errors.join("; ")}` : payload.error;
      }
    } catch {
      // Preserve the status-only message when the response is not JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as TPayload;
}
