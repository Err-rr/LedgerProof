import { formatCount, formatCurrencyFromPaisa, formatPercent, formatRupeesFromPaisa } from "@/lib/format";

/**
 * The only place money/percentage/count figures are rendered. Every table
 * cell, rupee figure, and percentage must hit at least 7:1 contrast -- on
 * this palette that means --text-primary, never --text-secondary, even
 * inside a card. Routing every such figure through these three components
 * makes that a structural guarantee rather than a per-instance judgment
 * call. See app/tokens.css for the measured contrast ratios.
 */

interface DataTextProps {
  className?: string;
}

export function Money({ paisa, withSymbol = false, className }: DataTextProps & { paisa: number; withSymbol?: boolean }) {
  return (
    <span className={`tabular-nums text-text-primary ${className ?? ""}`}>
      {withSymbol ? formatCurrencyFromPaisa(paisa) : formatRupeesFromPaisa(paisa)}
    </span>
  );
}

export function Percent({ fraction, className }: DataTextProps & { fraction: number }) {
  return <span className={`tabular-nums text-text-primary ${className ?? ""}`}>{formatPercent(fraction)}</span>;
}

export function Count({ value, className }: DataTextProps & { value: number }) {
  return <span className={`tabular-nums text-text-primary ${className ?? ""}`}>{formatCount(value)}</span>;
}
