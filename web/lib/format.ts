/**
 * Money is always integer paisa on the wire (CLAUDE.md rule 1) and is only
 * ever converted to a display string here, at the presentation layer.
 */

const RUPEE_FORMATTER = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const INTEGER_FORMATTER = new Intl.NumberFormat("en-IN");

/** paisa -> "18,42,150.00" (Indian lakh/crore grouping, no currency symbol). */
export function formatRupeesFromPaisa(paisa: number): string {
  return RUPEE_FORMATTER.format(paisa / 100);
}

/** paisa -> "₹18,42,150.00" */
export function formatCurrencyFromPaisa(paisa: number): string {
  return `₹${formatRupeesFromPaisa(paisa)}`;
}

/** A plain count, Indian-grouped: 12450 -> "12,450". */
export function formatCount(value: number): string {
  return INTEGER_FORMATTER.format(value);
}

/** A 0..1 fraction -> "94.7%" (one decimal place, tabular-nums friendly). */
export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatRecordsPerSecond(count: number, seconds: number): string {
  if (seconds <= 0) return "—";
  return `${(count / seconds).toFixed(1)}/s`;
}

/** Sentence case for a SCREAMING_SNAKE exception code: UNMATCHED_BANK_CREDIT -> "Unmatched bank credit". */
export function humanizeCode(code: string): string {
  const lower = code.toLowerCase().replace(/_/g, " ");
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
