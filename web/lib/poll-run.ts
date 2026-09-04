import { fetchJson } from "./safe-fetch";
import type { RunOut } from "./api-types";

/**
 * POST /runs (via our own /api/runs proxy) already runs the reconciliation
 * synchronously and returns the final status, so in practice this resolves
 * on its first check. It still genuinely polls -- RunOut.status allows
 * "pending"/"processing", and if the backend ever moves to an async worker,
 * this keeps working without a frontend change, rather than assuming
 * synchronous behavior it isn't guaranteed to keep.
 */
export async function pollRun(runId: string, { timeoutMs = 60_000, intervalMs = 1200 } = {}): Promise<RunOut> {
  const start = Date.now();
  for (;;) {
    const run = await fetchJson<RunOut>(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
    if (run.status === "completed" || run.status === "failed") {
      return run;
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(`timed out waiting for run ${runId} to finish`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
