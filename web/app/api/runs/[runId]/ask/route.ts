import { NextRequest } from "next/server";

import { askRun } from "@/lib/api-client";
import { proxyJson } from "@/lib/route-proxy";
import type { AskRequest } from "@/lib/api-types";

export async function POST(request: NextRequest, { params }: { params: { runId: string } }) {
  const body = (await request.json()) as AskRequest;
  return proxyJson(() => askRun(params.runId, body));
}
