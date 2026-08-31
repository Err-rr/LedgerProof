"use client";

import { useState } from "react";

import { ExceptionRow } from "@/components/exceptions/exception-row";
import { Filters } from "@/components/exceptions/filters";
import { Count } from "@/components/data-text";
import { useReviewerName } from "@/lib/use-reviewer-name";
import type { ExceptionOut } from "@/lib/api-types";

function uniqueInOrder(values: string[]): string[] {
  return [...new Set(values)];
}

export function ExceptionsTable({ runId, initialExceptions }: { runId: string; initialExceptions: ExceptionOut[] }) {
  const [exceptions, setExceptions] = useState(initialExceptions);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [codeFilter, setCodeFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reviewerName, setReviewerName] = useReviewerName();
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const severities = uniqueInOrder(exceptions.map((e) => e.severity));
  const codes = uniqueInOrder(exceptions.map((e) => e.code));

  // .filter() preserves the incoming order -- the API already sorted this
  // list by rupee_at_risk_paisa desc; filtering never re-sorts it.
  const visible = exceptions.filter(
    (exception) => (severityFilter === "all" || exception.severity === severityFilter) && (codeFilter === "all" || exception.code === codeFilter),
  );

  async function refresh() {
    try {
      const res = await fetch(`/api/runs/${runId}/exceptions`, { cache: "no-store" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "failed to refresh the exception queue");
      setExceptions(body as ExceptionOut[]);
      setRefreshError(null);
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : "failed to refresh the exception queue");
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Filters
          severities={severities}
          codes={codes}
          severityFilter={severityFilter}
          codeFilter={codeFilter}
          onSeverityChange={setSeverityFilter}
          onCodeChange={setCodeFilter}
        />
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          Reviewing as
          <input
            value={reviewerName}
            onChange={(event) => setReviewerName(event.target.value)}
            placeholder="Your name"
            className="rounded-md border border-border-strong bg-surface px-2 py-1 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
        </label>
      </div>

      <p className="mt-4 text-sm text-text-secondary">
        Showing <Count value={visible.length} /> of <Count value={exceptions.length} /> exceptions
      </p>

      {refreshError && <p className="mt-2 text-sm text-sev-high">{refreshError}</p>}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text-secondary">
              <th className="py-2 pr-4 font-normal">Severity</th>
              <th className="py-2 pr-4 font-normal">Code</th>
              <th className="py-2 pr-4 font-normal">Rupee at risk</th>
              <th className="py-2 pr-4 font-normal">Record</th>
              <th className="py-2 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((exception) => (
              <ExceptionRow
                key={exception.id}
                exception={exception}
                expanded={expandedId === exception.id}
                onToggle={() => setExpandedId((current) => (current === exception.id ? null : exception.id))}
                reviewerName={reviewerName}
                onResolved={refresh}
              />
            ))}
          </tbody>
        </table>
        {visible.length === 0 && <p className="py-8 text-center text-sm text-text-muted">No exceptions match these filters.</p>}
      </div>
    </div>
  );
}
