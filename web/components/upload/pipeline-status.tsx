const STAGES = [
  "Bank credit ↔ settlement matching",
  "Settlement ↔ payment arithmetic",
  "Payment ↔ order matching",
  "Journal generation",
];

/**
 * POST /runs runs all four passes synchronously in one request/response --
 * there is no mid-run status to poll, so this cannot honestly animate one
 * stage at a time without fabricating a signal the backend doesn't send.
 * What's real here: the elapsed timer, and the fact that all four passes
 * genuinely did run once the response comes back. The actual per-pass
 * match/exception counts and timings ARE real and get shown on the summary
 * screen once they're known -- see components/summary/pipeline-detail.tsx.
 */
export function PipelineStatus({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="rounded-card border border-border bg-surface p-6">
      <div className="flex items-center justify-between">
        <p className="text-text-primary">Running reconciliation</p>
        <p className="tabular-nums text-sm text-text-secondary">{elapsedSeconds.toFixed(1)}s elapsed</p>
      </div>
      <ul className="mt-5 space-y-3">
        {STAGES.map((stage, index) => (
          <li key={stage} className="flex items-center gap-3">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" aria-hidden />
            <span className="font-mono text-xs text-text-muted">{String(index + 1).padStart(2, "0")}</span>
            <span className="text-sm text-text-secondary">{stage}</span>
          </li>
        ))}
      </ul>
      <p className="mt-5 text-xs text-text-muted">
        These four passes run as a single deterministic sequence over your files -- there is no partial state to
        report mid-run. What each pass actually found appears on the summary screen once this finishes.
      </p>
    </div>
  );
}
