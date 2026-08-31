import { Eyebrow } from "@/components/eyebrow";
import { ErrorState } from "@/components/error-state";
import { ExceptionsTable } from "@/components/exceptions/exceptions-table";
import { ApiError, getRun, listRunExceptions } from "@/lib/api-client";

export default async function ExceptionsPage({ params }: { params: { runId: string } }) {
  try {
    const run = await getRun(params.runId);
    if (run.status !== "completed") {
      return (
        <div>
          <Eyebrow>03 — Exception queue</Eyebrow>
          <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Exception queue</h1>
          <p className="mt-8 text-text-secondary">This run is {run.status} -- there is nothing to review yet.</p>
        </div>
      );
    }

    const exceptions = await listRunExceptions(params.runId);

    return (
      <div>
        <Eyebrow>03 — Exception queue</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Exception queue</h1>
        <p className="mt-2 font-mono text-xs text-text-muted">{run.run_id}</p>

        <div className="mt-10">
          <ExceptionsTable runId={params.runId} initialExceptions={exceptions} />
        </div>
      </div>
    );
  } catch (err) {
    const message = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "unknown error";
    return (
      <div>
        <Eyebrow>03 — Exception queue</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Exception queue</h1>
        <div className="mt-8">
          <ErrorState title="Could not load the exception queue" message={message} />
        </div>
      </div>
    );
  }
}
