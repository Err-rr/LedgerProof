import "server-only";

import type {
  AskRequest,
  AskResponse,
  ExceptionOut,
  MatchRecordOut,
  ProposalOut,
  ResolveExceptionRequest,
  ResolveExceptionResponse,
  RunOut,
} from "./api-types";

/**
 * Direct server-side calls to the real FastAPI backend. LEDGERPROOF_API_BASE_URL
 * is a server-only env var (never NEXT_PUBLIC_) -- the browser never talks to
 * the API directly; client components go through this app's own route
 * handlers instead (see app/api/**), which forward to the same functions
 * below. This file is imported only by Server Components and route handlers.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function getApiBaseUrl(): string {
  const url = process.env.LEDGERPROOF_API_BASE_URL;
  if (!url) {
    throw new Error(
      "LEDGERPROOF_API_BASE_URL is not set. Copy web/.env.example to web/.env.local and point it at your running api/ (see scripts/dev_api_server.py for local development).",
    );
  }
  return url.replace(/\/+$/, "");
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail ?? res.statusText;
  } catch {
    return res.statusText || `request failed with status ${res.status}`;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return (await res.json()) as T;
}

export async function getRun(runId: string): Promise<RunOut> {
  return apiFetch<RunOut>(`/runs/${encodeURIComponent(runId)}`);
}

export async function listRunExceptions(runId: string): Promise<ExceptionOut[]> {
  return apiFetch<ExceptionOut[]>(`/runs/${encodeURIComponent(runId)}/exceptions`);
}

export async function listMatchRecords(runId: string): Promise<MatchRecordOut[]> {
  return apiFetch<MatchRecordOut[]>(`/runs/${encodeURIComponent(runId)}/match-records`);
}

export async function resolveException(
  exceptionId: string,
  body: ResolveExceptionRequest,
): Promise<ResolveExceptionResponse> {
  return apiFetch<ResolveExceptionResponse>(`/exceptions/${encodeURIComponent(exceptionId)}/resolve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function proposeResolution(exceptionId: string): Promise<ProposalOut> {
  return apiFetch<ProposalOut>(`/exceptions/${encodeURIComponent(exceptionId)}/propose`, { method: "POST" });
}

export async function askRun(runId: string, body: AskRequest): Promise<AskResponse> {
  return apiFetch<AskResponse>(`/runs/${encodeURIComponent(runId)}/ask`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Forwards a multipart/form-data upload straight through to POST /runs. */
export async function createRun(formData: FormData): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${getApiBaseUrl()}/runs`, {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  const body = await res.json();
  return { status: res.status, body };
}
