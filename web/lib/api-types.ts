/**
 * Types mirror api/schemas.py exactly -- verified against a real run through
 * the actual FastAPI app (scripts/dev_api_server.py), not guessed from the
 * source. If the backend schema changes, update both together.
 */

export type RunStatus = "pending" | "processing" | "completed" | "failed";

export interface StageResult {
  pass_number: number;
  name: string;
  matches: number;
  exceptions: number;
  duration_ms: number;
}

export interface RunSummary {
  total_orders: number;
  total_matches: number;
  total_exceptions: number;
  match_rate: number;
  auto_resolve_rate: number;
  money_at_rest_paisa: number;
  money_at_rest_codes: string[];
  exceptions_by_code: Record<string, number>;
  stages: StageResult[];
  duration_ms: number;
  throughput_rps: number;
}

export interface RunCreateResponse {
  run_id: string;
  status: RunStatus;
}

export interface RunOut {
  run_id: string;
  status: RunStatus;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  summary: RunSummary | null;
}

export type ExceptionStatus = "open" | "resolved";

export interface ExceptionResolution {
  resolved_by: string;
  resolution_notes: string;
  proposal: ResolutionProposal | null;
  approved: boolean;
}

export interface ResolutionProposal {
  hypothesis?: string;
  proposed_resolution?: string;
  confidence?: number;
  evidence_ids?: string[];
  [key: string]: unknown;
}

export interface ExceptionOut {
  id: string;
  run_id: string;
  code: string;
  severity: "critical" | "high" | "medium" | "low";
  record_type: string;
  record_id: string;
  amount_paisa: number;
  rupee_at_risk_paisa: number;
  details: Record<string, unknown>;
  status: ExceptionStatus;
  resolution: ExceptionResolution | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ResolveExceptionRequest {
  approved: boolean;
  resolved_by: string;
  resolution_notes: string;
  proposal?: ResolutionProposal | null;
}

export interface ResolveExceptionResponse {
  exception: ExceptionOut;
}

export interface MatchRecordOut {
  id: string;
  pass_number: number;
  method: string;
  confidence: number;
  evidence: Record<string, unknown>;
  matched_at: string;
  record_type: string;
  left_id: string;
  right_id: string;
}

export interface ProposalOut {
  hypothesis: string;
  proposed_resolution: string;
  confidence: number;
  evidence_ids: string[];
}

export interface AskRequest {
  question: string;
}

export interface AskResponse {
  run_id: string;
  question: string;
  answer: string;
  grounded_in: Record<string, number>;
}

/** Shape of a FastAPI HTTPException response body: {"detail": "..."}. */
export interface ApiErrorBody {
  detail: string;
}
