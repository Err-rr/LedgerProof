import { NextRequest } from "next/server";

import { listRunExceptions } from "@/lib/api-client";
import { proxyJson } from "@/lib/route-proxy";

/** Used by screen 03 to refresh the table client-side after a resolve action. */
export async function GET(_request: NextRequest, { params }: { params: { runId: string } }) {
  return proxyJson(() => listRunExceptions(params.runId));
}
