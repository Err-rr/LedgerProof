import { NextRequest } from "next/server";

import { proposeResolution } from "@/lib/api-client";
import { proxyJson } from "@/lib/route-proxy";

export async function POST(_request: NextRequest, { params }: { params: { exceptionId: string } }) {
  return proxyJson(() => proposeResolution(params.exceptionId));
}
