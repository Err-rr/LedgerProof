import { NextRequest } from "next/server";

import { getRun } from "@/lib/api-client";
import { proxyJson } from "@/lib/route-proxy";

/** Used by screen 01's client-side polling loop after a run is created. */
export async function GET(_request: NextRequest, { params }: { params: { runId: string } }) {
  return proxyJson(() => getRun(params.runId));
}
