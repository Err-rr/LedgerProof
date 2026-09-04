/**
 * Every fetch in this app must go through here (or api-client.ts's server-side
 * equivalent, which uses the same body-reading logic). The bug this fixes:
 * calling res.json() without checking res.ok first discards the API's actual
 * error and replaces it with "Unexpected end of JSON input" whenever the
 * error response has no body (or a non-JSON one) -- which a raw 500 often
 * does. Reading the body as text first means there is no code path left that
 * can throw a JSON parse error out of a fetch call.
 */

interface FastApiValidationError {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

function isValidationErrorArray(value: unknown): value is FastApiValidationError[] {
  return Array.isArray(value) && value.length > 0 && value.every((v) => v && typeof v === "object" && "msg" in v);
}

/** FastAPI's own 422 shape: {"detail": [{"loc": ["body", "orders"], "msg": "Field required", "type": "missing"}]}. */
function formatValidationErrors(errors: FastApiValidationError[]): string {
  return errors
    .map((e) => {
      const field = (e.loc ?? []).filter((part) => part !== "body").join(".") || "request body";
      return `${field}: ${e.msg ?? "invalid"}`;
    })
    .join("; ");
}

function statusLabel(res: Response): string {
  return `${res.status}${res.statusText ? ` ${res.statusText}` : ""}`;
}

/**
 * Reads a Response body as text (never throws on empty/non-JSON) and turns
 * it into a human-readable message: the API's own `detail` string, a
 * readably-rendered 422 validation array, or -- if the body is empty or not
 * JSON -- the status code and status text, e.g.
 * "API returned 500 Internal Server Error with an empty body".
 */
export async function describeResponseBody(res: Response): Promise<string> {
  let text: string;
  try {
    text = await res.text();
  } catch {
    return `API returned ${statusLabel(res)} and the response body could not be read`;
  }

  if (!text) {
    return `API returned ${statusLabel(res)} with an empty body`;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return `API returned ${statusLabel(res)} with a non-JSON body: ${text.slice(0, 500)}`;
  }

  if (parsed && typeof parsed === "object" && "detail" in parsed) {
    const detail = (parsed as { detail: unknown }).detail;
    if (isValidationErrorArray(detail)) return formatValidationErrors(detail);
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  }

  return `API returned ${statusLabel(res)}: ${text.slice(0, 500)}`;
}

export type FetchFailureKind = "network" | "http";

export class FetchFailure extends Error {
  kind: FetchFailureKind;
  status?: number;

  constructor(kind: FetchFailureKind, message: string, status?: number) {
    super(message);
    this.name = "FetchFailure";
    this.kind = kind;
    this.status = status;
  }
}

/**
 * fetch() + JSON-parse a successful body, with every failure mode STEP 1
 * requires distinguished and readable:
 *  - a thrown fetch() (DNS failure, connection refused, offline) becomes a
 *    FetchFailure with kind "network" -- a completely different cause than
 *    an HTTP error response, and is reported as such.
 *  - a non-2xx response becomes a FetchFailure with kind "http", carrying
 *    the API's own error message (see describeResponseBody).
 *  - a 2xx response with an empty or non-JSON body -- which should never
 *    happen, but must never crash the caller either -- becomes a FetchFailure
 *    too, rather than throwing a raw SyntaxError.
 */
export async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch (err) {
    throw new FetchFailure(
      "network",
      err instanceof Error ? `Could not reach the API: ${err.message}` : "Could not reach the API.",
    );
  }

  if (!res.ok) {
    throw new FetchFailure("http", await describeResponseBody(res), res.status);
  }

  const text = await res.text();
  if (!text) {
    throw new FetchFailure("http", `API returned ${statusLabel(res)} with an empty body`, res.status);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new FetchFailure("http", `API returned a non-JSON body: ${text.slice(0, 500)}`, res.status);
  }
}
