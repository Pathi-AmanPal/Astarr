/** Backend calls. The base URL is hardcoded per PRD Section 14 -- no env setup. */

export const API_BASE = "http://localhost:8000";

/** Shown whenever the backend cannot be reached at all (PRD Section 15). */
export const UNREACHABLE =
  "Cannot reach backend — is it running on localhost:8000?";

export interface EntitySummary {
  entity_id: string;
  entity_name: string;
  sector: string;
  risk_score: number;
  risk_score_raw: number;
  capped: boolean;
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

export interface ResetResult {
  status: string;
  entities_loaded: number;
  findings_generated: number;
}

/** Thrown for every failure, always carrying a message safe to render. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
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
    try {
      const body = await response.json();
      if (body && typeof body.error === "string") message = body.error;
    } catch {
      // Non-JSON error body; keep the generic message rather than crashing.
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const getEntities = () => request<EntitySummary[]>("/api/entities");

export const getEntity = (entityId: string) =>
  request<EntityDetail>(`/api/entities/${encodeURIComponent(entityId)}`);

export const getEvidence = (findingId: string) =>
  request<Evidence>(`/api/findings/${encodeURIComponent(findingId)}/evidence`);

export const resetDemo = () =>
  request<ResetResult>("/api/demo/reset", { method: "POST" });
