import "server-only";

import { describeResponseBody } from "./safe-fetch";
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

/** Thrown when the API can't be reached at all (DNS/connection failure) --
 * distinct from ApiError, which means the API responded but with an error
 * status. Getting this wrong looks identical to the user unless the two
 * causes are kept separate. */
export class ApiUnreachableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiUnreachableError";
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

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (err) {
    throw new ApiUnreachableError(
      err instanceof Error ? `could not reach the API at ${getApiBaseUrl()}: ${err.message}` : `could not reach the API at ${getApiBaseUrl()}`,
    );
  }

  if (!res.ok) {
    throw new ApiError(res.status, await describeResponseBody(res));
  }

  // Read as text first: a 2xx with an empty or non-JSON body must never
  // throw a raw JSON parse error out of this function.
  const text = await res.text();
  if (!text) {
    throw new ApiError(res.status, `API returned ${res.status} with an empty body`);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(res.status, `API returned a non-JSON body: ${text.slice(0, 500)}`);
  }
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

/**
 * Forwards a multipart/form-data upload straight through to POST /runs.
 * Returns a plain {status, body} pair -- ALWAYS, even when the upstream API
 * is unreachable or responds with an empty/non-JSON body -- because the
 * caller (app/api/runs/route.ts) hands this straight to NextResponse.json()
 * with no try/catch of its own. Letting this throw used to mean the route
 * handler crashed and Next.js returned its own opaque error response, which
 * is what "Failed to execute 'json' on 'Response': Unexpected end of JSON
 * input" in the browser actually was: this function's old unconditional
 * `res.json()` blowing up on an empty upstream body.
 */
export async function createRun(formData: FormData): Promise<{ status: number; body: unknown }> {
  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}/runs`, {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
  } catch (err) {
    const baseUrl = getApiBaseUrl();
    return {
      status: 502,
      body: { detail: err instanceof Error ? `could not reach the API at ${baseUrl}: ${err.message}` : `could not reach the API at ${baseUrl}` },
    };
  }

  const text = await res.text();
  if (!text) {
    return { status: res.status >= 400 ? res.status : 502, body: { detail: `API returned ${res.status} with an empty body` } };
  }
  try {
    return { status: res.status, body: JSON.parse(text) };
  } catch {
    return { status: 502, body: { detail: `API returned a non-JSON body (status ${res.status}): ${text.slice(0, 500)}` } };
  }
}
