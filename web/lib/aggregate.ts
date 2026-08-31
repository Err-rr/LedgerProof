import type { ExceptionOut } from "./api-types";

export interface CodeVariance {
  code: string;
  count: number;
  rupeeAtRiskPaisa: number;
}

/**
 * RunSummary.exceptions_by_code only carries counts, not rupee value per
 * code -- the variance-by-code breakdown needs both, so this aggregates the
 * real exception rows from GET /runs/{id}/exceptions rather than the API
 * inventing a new field for it.
 */
export function groupExceptionsByCode(exceptions: ExceptionOut[]): CodeVariance[] {
  const byCode = new Map<string, CodeVariance>();
  for (const exception of exceptions) {
    const existing = byCode.get(exception.code);
    if (existing) {
      existing.count += 1;
      existing.rupeeAtRiskPaisa += exception.rupee_at_risk_paisa;
    } else {
      byCode.set(exception.code, { code: exception.code, count: 1, rupeeAtRiskPaisa: exception.rupee_at_risk_paisa });
    }
  }
  return [...byCode.values()].sort((a, b) => b.rupeeAtRiskPaisa - a.rupeeAtRiskPaisa);
}
