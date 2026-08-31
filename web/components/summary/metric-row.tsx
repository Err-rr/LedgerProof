import { Card } from "@/components/card";
import { Eyebrow } from "@/components/eyebrow";
import { Percent } from "@/components/data-text";
import { formatPercent } from "@/lib/format";

/**
 * The auto-resolve rate is expected to sit below the match rate -- that gap
 * is CLAUDE.md's core product bet ("a lower auto-resolve rate with honest
 * exceptions is the goal, not a high match rate"), so it's stated here as a
 * deliberate design outcome, not apologized for as a shortfall.
 */
export function MetricRow({
  matchRate,
  autoResolveRate,
  throughputRps,
}: {
  matchRate: number;
  autoResolveRate: number;
  throughputRps: number;
}) {
  const gap = matchRate - autoResolveRate;

  return (
    <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
      <Card className="p-6">
        <Eyebrow>Match rate</Eyebrow>
        <Percent fraction={matchRate} className="mt-3 block text-3xl" />
        <p className="mt-2 text-sm text-text-secondary">Orders the system confidently identified a payment for.</p>
      </Card>

      <Card className="p-6">
        <Eyebrow>Auto-resolve rate</Eyebrow>
        <Percent fraction={autoResolveRate} className="mt-3 block text-3xl" />
        <p className="mt-2 text-sm text-text-secondary">
          {gap > 0.0005
            ? `${formatPercent(gap)} lower than the match rate, by design: the difference is records the system refused to guess at rather than confidently resolve.`
            : "Every confident match also cleared cleanly -- nothing was routed to the exception queue this run."}
        </p>
      </Card>

      <Card className="p-6">
        <Eyebrow>Throughput</Eyebrow>
        <p className="mt-3">
          <span className="tabular-nums text-3xl text-text-primary">{throughputRps.toFixed(1)}</span>
          <span className="ml-1 text-sm text-text-secondary">records/sec</span>
        </p>
        <p className="mt-2 text-sm text-text-secondary">Source records processed per second across all four passes.</p>
      </Card>
    </div>
  );
}
