/**
 * Severity is never conveyed by color alone: every badge pairs a color dot
 * with an explicit text label, so it survives a bad projector or a
 * colorblind viewer. The tokens only define three severity colors
 * (high/medium/low); the backend's "critical" severity reuses --sev-high
 * but gets its own label plus a ring around the dot, so it never reads as
 * identical to "high" even at a glance.
 */

const LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const DOT_CLASS: Record<string, string> = {
  critical: "bg-sev-high ring-2 ring-sev-high/40 ring-offset-2 ring-offset-surface",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
};

export function SeverityBadge({ severity }: { severity: string }) {
  const label = LABEL[severity] ?? severity;
  const dotClass = DOT_CLASS[severity] ?? "bg-text-muted";

  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} />
      <span className="text-text-primary">{label}</span>
    </span>
  );
}
