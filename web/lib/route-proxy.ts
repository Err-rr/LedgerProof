import "server-only";

import { NextResponse } from "next/server";

import { ApiError } from "./api-client";

/**
 * Runs `fn` (a call into lib/api-client.ts) and turns its result or ApiError
 * into a NextResponse with the same status code and body shape the real API
 * returned -- so a 422 or 409 from FastAPI reaches the client as a 422 or
 * 409, never flattened into a generic failure.
 */
export async function proxyJson<T>(fn: () => Promise<T>): Promise<NextResponse> {
  try {
    const data = await fn();
    return NextResponse.json(data as object);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ detail: err.detail }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "unexpected error contacting the reconciliation API";
    return NextResponse.json({ detail: message }, { status: 502 });
  }
}
