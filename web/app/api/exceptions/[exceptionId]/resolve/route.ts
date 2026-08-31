import { NextRequest } from "next/server";

import { resolveException } from "@/lib/api-client";
import { proxyJson } from "@/lib/route-proxy";
import type { ResolveExceptionRequest } from "@/lib/api-types";

export async function POST(request: NextRequest, { params }: { params: { exceptionId: string } }) {
  const body = (await request.json()) as ResolveExceptionRequest;
  return proxyJson(() => resolveException(params.exceptionId, body));
}
