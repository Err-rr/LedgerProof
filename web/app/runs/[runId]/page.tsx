import Link from "next/link";

import { Eyebrow } from "@/components/eyebrow";
import { ErrorState } from "@/components/error-state";
import { MoneyAtRestHero } from "@/components/summary/money-at-rest-hero";
import { MetricRow } from "@/components/summary/metric-row";
import { VarianceBars } from "@/components/summary/variance-bars";
import { PipelineDetail } from "@/components/summary/pipeline-detail";
import { ApiError, getRun, listRunExceptions } from "@/lib/api-client";
import { groupExceptionsByCode } from "@/lib/aggregate";

export default async function SummaryPage({ params }: { params: { runId: string } }) {
  let run;
  try {
    run = await getRun(params.runId);
  } catch (err) {
    const message = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "unknown error";
    return (
      <div>
        <Eyebrow>02 — Summary</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Summary</h1>
        <div className="mt-8">
          <ErrorState title="Could not load this run" message={message} />
        </div>
      </div>
    );
  }

  if (run.status === "failed") {
    return (
      <div>
        <Eyebrow>02 — Summary</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Summary</h1>
        <div className="mt-8">
          <ErrorState title="This run failed" message={run.error ?? "No error detail was recorded."} />
        </div>
      </div>
    );
  }

  if (run.status !== "completed" || !run.summary) {
    return (
      <div>
        <Eyebrow>02 — Summary</Eyebrow>
        <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Summary</h1>
        <p className="mt-8 text-text-secondary">
          This run is still {run.status}. Refresh in a moment, or go back to{" "}
          <Link href="/" className="text-accent underline underline-offset-4">
            start a new run
          </Link>
          .
        </p>
      </div>
    );
  }

  const exceptions = await listRunExceptions(params.runId);
  const variance = groupExceptionsByCode(exceptions);
  const { summary } = run;

  return (
    <div>
      <Eyebrow>02 — Summary</Eyebrow>
      <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Run summary</h1>
      <p className="mt-2 font-mono text-xs text-text-muted">{run.run_id}</p>

      <div className="mt-12">
        <MoneyAtRestHero paisa={summary.money_at_rest_paisa} codes={summary.money_at_rest_codes} />
      </div>

      <MetricRow matchRate={summary.match_rate} autoResolveRate={summary.auto_resolve_rate} throughputRps={summary.throughput_rps} />

      <VarianceBars items={variance} />

      <PipelineDetail stages={summary.stages} durationMs={summary.duration_ms} />

      <div className="mt-14 flex gap-3 border-t border-border pt-8">
        <Link
          href={`/runs/${run.run_id}/exceptions`}
          className="rounded-md bg-action px-5 py-2.5 text-sm text-action-text"
        >
          Review exception queue
        </Link>
        <Link
          href={`/runs/${run.run_id}/provenance`}
          className="rounded-md border border-border-strong px-5 py-2.5 text-sm text-text-secondary transition-colors hover:text-text-primary"
        >
          Provenance drill-down
        </Link>
      </div>
    </div>
  );
}
