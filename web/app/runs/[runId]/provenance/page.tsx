import { Eyebrow } from "@/components/eyebrow";
import { ErrorState } from "@/components/error-state";
import { ProvenanceExplorer } from "@/components/provenance/provenance-explorer";
import { ApiError, getRun, listMatchRecords, listRunExceptions } from "@/lib/api-client";
import { listKnownOrderIds } from "@/lib/provenance";

export default async function ProvenancePage({ params }: { params: { runId: string } }) {
  try {
    const run = await getRun(params.runId);
    if (run.status !== "completed") {
      return (
        <div>
          <Eyebrow>04 — Provenance drill-down</Eyebrow>
          <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Provenance</h1>
          <p className="mt-8 text-text-secondary">This run is {run.status} -- there is nothing to trace yet.</p>
        </div>
      );
    }

    const [matchRecords, exceptions] = await Promise.all([listMatchRecords(params.runId), listRunExceptions(params.runId)]);
    const orderIds = listKnownOrderIds(matchRecords, exceptions);

    return (
      <div>
        <Eyebrow>04 — Provenance drill-down</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Provenance drill-down</h1>
        <p className="mt-2 max-w-2xl text-text-secondary">
          Order → payment → settlement → bank credit, with the matching method, confidence, and field values that
          drove each hop.
        </p>

        <div className="mt-10">
          {orderIds.length === 0 ? (
            <p className="text-sm text-text-secondary">No orders with match evidence were found for this run.</p>
          ) : (
            <ProvenanceExplorer orderIds={orderIds} matchRecords={matchRecords} exceptions={exceptions} />
          )}
        </div>
      </div>
    );
  } catch (err) {
    const message = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "unknown error";
    return (
      <div>
        <Eyebrow>04 — Provenance drill-down</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Provenance drill-down</h1>
        <div className="mt-8">
          <ErrorState title="Could not load provenance data" message={message} />
        </div>
      </div>
    );
  }
}
