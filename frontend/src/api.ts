/** Backend calls. The base URL is hardcoded per PRD Section 14 -- no env setup. */

export const API_BASE = "http://localhost:8000";

/** Shown whenever the backend cannot be reached at all (PRD Section 15). */
export const UNREACHABLE =
  "Cannot reach backend — is it running on localhost:8000?";

/** One tier's line in the weighted-tier score (PRD Section 5 amendment).
    `raw` is the tier's unweighted weight-sum, `capped_value` is that sum after the
    tier's individual 100-point cap, and `contribution` is capped_value x weight. The
    three contributions foot to `risk_score`. */
export interface TierScore {
  tier: "EXECUTION_GAP" | "NEGATIVE_SPACE" | "ML_CORROBORATION";
  raw: number;
  capped_value: number;
  capped: boolean;
  weight: number;
  contribution: number;
}

export interface EntitySummary {
  entity_id: string;
  entity_name: string;
  sector: string;
  risk_score: number;
  risk_score_raw: number;
  capped: boolean;
  tiers: TierScore[];
  finding_count: number;
  record_count: number;
}

export interface Finding {
  finding_id: string;
  rule_id: string;
  finding_type: "EXECUTION_GAP" | "NEGATIVE_SPACE" | "ML_CORROBORATION";
  title: string;
  weight: number;
  explanation: string;
}

export interface EntityDetail {
  entity_id: string;
  entity_name: string;
  sector: string;
  risk_score: number;
  risk_score_raw: number;
  capped: boolean;
  tiers: TierScore[];
  findings: Finding[];
}

export interface AlertRecord {
  record_id: string;
  entity_id: string;
  asset_id: string;
  severity: string;
  category: string;
  opened_at: string;
  closed_at: string | null;
  escalated: boolean;
  disposition: string;
  investigation_notes: string | null;
  closure_time_minutes: number | null;
}

export interface Evidence {
  finding_id: string;
  rule_id: string;
  finding_type: string;
  title: string;
  weight: number;
  explanation: string;
  entity_id: string;
  entity_name: string;
  records: AlertRecord[];
}

/** Which dataset the current schedule was computed over. */
export interface DatasetInfo {
  source: "demo_seed" | "upload" | "empty";
  label: string;
  /** Null when nothing is loaded. The endpoint names the empty state rather than
      404ing, so every caller has to handle a dataset that is not there. */
  loaded_at: string | null;
  entity_count: number;
  record_count: number;
}

export interface UploadResult {
  status: string;
  label: string;
  entities_loaded: number;
  records_loaded: number;
  findings_generated: number;
  /** Every column the parser translated or ignored. Empty for a canonical file. */
  mapping_notes: string[];
}

/** One feature of one entity, with the peer-group figure it is judged against. */
export interface MlFeature {
  feature: string;
  label: string;
  value: number;
  dataset_mean: number;
  deviation: number;
  contribution: number;
}

export interface MlProfile {
  entity_id: string;
  available: boolean;
  method: "shap" | "zscore" | "none";
  anomalous: boolean;
  corroborated: boolean;
  peer_count: number;
  features: MlFeature[];
}

export interface ClearResult {
  status: string;
}

/** The analytics surface is four endpoints, not one, because that is how the backend
    exposes it. The Overview fetches them together and renders nothing until all four
    have landed, so its panels can never show two different datasets side by side. */

export interface OverviewMetrics {
  entities_count: number;
  alerts_count: number;
  findings_count: number;
  attention_entities_count: number;
  clean_entity_share: number;
  mean_closure_minutes: number | null;
  median_closure_minutes: number | null;
  p90_closure_minutes: number | null;
  mean_median_gap_minutes: number | null;
  confidence: string;
}

/** One time bucket with its severity split. The severities foot to `total` — asserted
    in verify.py, because a stacked chart drawn from a breakdown that does not foot is
    quietly short and nothing on screen says so. */
export interface TimeBucket {
  period: string;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface DistributionItem {
  name: string;
  count: number;
  percentage: number;
}

export interface Distribution {
  by: string;
  total: number;
  items: DistributionItem[];
}

export interface HandlingQuality {
  total_records: number;
  mean_closure_minutes: number | null;
  median_closure_minutes: number | null;
  p90_closure_minutes: number | null;
  rapid_closure_rate: number;
  critical_escalation_rate: number;
  undocumented_dismissal_rate: number;
  note_duplication_rate: number;
}

/** Thrown for every failure, always carrying a message safe to render.
    `details` carries per-line validation problems from a rejected upload; it is empty
    for every other kind of failure. */
export class ApiError extends Error {
  status: number;
  details: string[];
  constructor(message: string, status: number, details: string[] = []) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // Network-level failure: the server is not running, or the port is wrong.
    throw new ApiError(UNREACHABLE, 0);
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    let details: string[] = [];
    try {
      const body = await response.json();
      if (body && typeof body.error === "string") message = body.error;
      if (body && Array.isArray(body.details)) details = body.details.map(String);
    } catch {
      // Non-JSON error body; keep the generic message rather than crashing.
    }
    throw new ApiError(message, response.status, details);
  }

  return (await response.json()) as T;
}

export const getEntities = () => request<EntitySummary[]>("/api/entities");

export const getEntity = (entityId: string) =>
  request<EntityDetail>(`/api/entities/${encodeURIComponent(entityId)}`);

export const getEvidence = (findingId: string) =>
  request<Evidence>(`/api/findings/${encodeURIComponent(findingId)}/evidence`);

export const getDataset = () => request<DatasetInfo>("/api/dataset");

export const getOverview = () =>
  request<OverviewMetrics>("/api/analytics/overview");

export const getTimeseries = (bucket: "day" | "week") =>
  request<TimeBucket[]>(`/api/analytics/timeseries?bucket=${bucket}`);

export const getDistribution = (
  by: "severity" | "category" | "disposition" | "score",
) => request<Distribution>(`/api/analytics/distribution?by=${by}`);

export const getHandling = () =>
  request<HandlingQuality>("/api/analytics/handling");

export const clearDataset = () =>
  request<ClearResult>("/api/dataset", { method: "DELETE" });

export const getMlProfile = (entityId: string) =>
  request<MlProfile>(`/api/entities/${encodeURIComponent(entityId)}/ml`);

/** The template is a plain download, not a fetch — the browser saves the file. */
export const TEMPLATE_URL = `${API_BASE}/api/dataset/template.csv`;

export function uploadDataset(file: File) {
  const body = new FormData();
  body.append("file", file);
  // No Content-Type header: the browser must set the multipart boundary itself.
  return request<UploadResult>("/api/dataset/upload", { method: "POST", body });
}
