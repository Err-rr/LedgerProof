import { Eyebrow } from "@/components/eyebrow";
import { Count, Money } from "@/components/data-text";
import { humanizeCode } from "@/lib/format";
import type { CodeVariance } from "@/lib/aggregate";

export function VarianceBars({ items }: { items: CodeVariance[] }) {
  if (items.length === 0) {
    return (
      <div className="mt-14">
        <Eyebrow>Variance by exception code</Eyebrow>
        <p className="mt-4 text-sm text-text-secondary">No exceptions were raised this run.</p>
      </div>
    );
  }

  const max = Math.max(...items.map((item) => item.rupeeAtRiskPaisa), 1);

  return (
    <div className="mt-14">
      <Eyebrow>Variance by exception code</Eyebrow>
      <div className="mt-5 space-y-5">
        {items.map((item) => (
          <div key={item.code}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <span className="text-text-primary">{humanizeCode(item.code)}</span>
              <span className="flex items-baseline gap-3 whitespace-nowrap">
                <span className="text-sm text-text-secondary">
                  <Count value={item.count} /> record{item.count === 1 ? "" : "s"}
                </span>
                <Money paisa={item.rupeeAtRiskPaisa} withSymbol className="text-sm" />
              </span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-surface-raised">
              <div
                className="h-2 rounded-full bg-accent"
                style={{ width: `${Math.max(2, (item.rupeeAtRiskPaisa / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
