import { NextRequest, NextResponse } from "next/server";

import { createRun } from "@/lib/api-client";

/**
 * Proxies POST /runs (multipart upload) to the real FastAPI backend. Client
 * components upload here rather than to the API directly, so the API's
 * actual URL is never exposed in the browser and CORS is never a concern.
 */
export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const { status, body } = await createRun(formData);
  return NextResponse.json(body, { status });
}
