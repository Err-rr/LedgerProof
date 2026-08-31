import { formatRupeesFromPaisa, humanizeCode } from "@/lib/format";

function joinCodes(codes: string[]): string {
  const labels = codes.map(humanizeCode);
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

export function MoneyAtRestHero({ paisa, codes }: { paisa: number; codes: string[] }) {
  return (
    <div>
      <p className="text-eyebrow uppercase text-accent">Money at rest</p>
      <p className="tabular-nums mt-3 text-[clamp(3rem,7vw,5.5rem)] leading-none tracking-tight2 text-text-primary">
        ₹{formatRupeesFromPaisa(paisa)}
      </p>
      <p className="mt-4 max-w-2xl text-text-secondary">
        The total value sitting in unresolved exceptions this run could not confidently place: {joinCodes(codes)}.
        This is money the reconciliation found but has not yet closed the loop on.
      </p>
    </div>
  );
}
