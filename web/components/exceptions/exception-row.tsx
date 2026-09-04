"use client";

import { useEffect, useState } from "react";

import { SeverityBadge } from "@/components/severity-badge";
import { Money } from "@/components/data-text";
import { formatDateTime, formatPercent, humanizeCode } from "@/lib/format";
import { FetchFailure, fetchJson } from "@/lib/safe-fetch";
import type { ExceptionOut, ProposalOut, ResolveExceptionResponse } from "@/lib/api-types";

type ProposalState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; proposal: ProposalOut }
  | { status: "error"; message: string };

type ActionState = { status: "idle" | "submitting" } | { status: "error"; message: string };

interface Props {
  exception: ExceptionOut;
  expanded: boolean;
  onToggle: () => void;
  reviewerName: string;
  onResolved: () => void;
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={status === "resolved" ? "text-text-primary" : "text-text-secondary"}>
      {status === "resolved" ? "Resolved" : "Open"}
    </span>
  );
}

export function ExceptionRow({ exception, expanded, onToggle, reviewerName, onResolved }: Props) {
  const [proposalState, setProposalState] = useState<ProposalState>({ status: "idle" });
  const [notes, setNotes] = useState("");
  const [actionState, setActionState] = useState<ActionState>({ status: "idle" });

  useEffect(() => {
    if (!expanded || exception.status !== "open" || proposalState.status !== "idle") return;
    let cancelled = false;
    setProposalState({ status: "loading" });
    fetchJson<ProposalOut>(`/api/exceptions/${exception.id}/propose`, { method: "POST" })
      .then((proposal) => {
        if (!cancelled) setProposalState({ status: "loaded", proposal });
      })
      .catch((err) => {
        if (!cancelled) {
          setProposalState({
            status: "error",
            message: err instanceof FetchFailure ? err.message : err instanceof Error ? err.message : "unknown error generating a proposal",
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, exception.id, exception.status]);

  async function submit(kind: "approve" | "reject") {
    setActionState({ status: "submitting" });
    const proposal = proposalState.status === "loaded" ? proposalState.proposal : null;
    const reviewedBy = reviewerName.trim() || "Unnamed reviewer";
    const body =
      kind === "approve"
        ? { approved: true, resolved_by: reviewedBy, resolution_notes: notes.trim() || "Approved.", proposal }
        : {
            approved: true, // the API's write gate requires this on every resolution -- it confirms a human took the action, not that they agreed with the proposal. Rejecting a hypothesis is itself a human decision that closes the exception; resolution_notes says "Rejected" so this is never ambiguous in the audit trail.
            resolved_by: reviewedBy,
            resolution_notes: `Rejected: ${notes.trim() || "no reason given"}`,
            proposal: null,
          };

    try {
      await fetchJson<ResolveExceptionResponse>(`/api/exceptions/${exception.id}/resolve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      setActionState({ status: "idle" });
      onResolved();
    } catch (err) {
      setActionState({
        status: "error",
        message: err instanceof FetchFailure ? err.message : err instanceof Error ? err.message : "unknown error submitting the resolution",
      });
    }
  }

  return (
    <>
      <tr
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggle();
          }
        }}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
        className="cursor-pointer border-b border-border transition-colors hover:bg-surface-raised focus-visible:bg-surface-raised"
      >
        <td className="py-3 pr-4">
          <SeverityBadge severity={exception.severity} />
        </td>
        <td className="py-3 pr-4 text-text-primary">{humanizeCode(exception.code)}</td>
        <td className="py-3 pr-4">
          <Money paisa={exception.rupee_at_risk_paisa} withSymbol />
        </td>
        <td className="py-3 pr-4 font-mono text-xs text-text-secondary">{exception.record_id}</td>
        <td className="py-3">
          <StatusPill status={exception.status} />
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-border bg-surface-raised">
          <td colSpan={5} className="px-5 py-6">
            {exception.status === "resolved" && exception.resolution ? (
              <div>
                <p className="text-eyebrow uppercase text-accent">Resolution</p>
                <p className="mt-2 text-sm text-text-primary">{exception.resolution.resolution_notes}</p>
                <p className="mt-1 text-xs text-text-muted">
                  By {exception.resolution.resolved_by}
                  {exception.resolved_at ? ` · ${formatDateTime(exception.resolved_at)}` : ""}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
                <div>
                  <p className="text-eyebrow uppercase text-accent">Resolution agent</p>
                  {proposalState.status === "loading" && (
                    <p className="mt-3 text-sm text-text-secondary">Generating a hypothesis…</p>
                  )}
                  {proposalState.status === "error" && (
                    <p className="mt-3 text-sm text-sev-high">{proposalState.message}</p>
                  )}
                  {proposalState.status === "loaded" && (
                    <div className="mt-3 space-y-3">
                      <p className="text-sm text-text-primary">{proposalState.proposal.hypothesis}</p>
                      <p className="text-sm text-text-secondary">{proposalState.proposal.proposed_resolution}</p>
                      <p className="text-sm text-text-secondary">
                        Confidence: <span className="tabular-nums text-text-primary">{formatPercent(proposalState.proposal.confidence)}</span>
                      </p>
                      {proposalState.proposal.evidence_ids.length > 0 && (
                        <p className="text-sm text-text-secondary">
                          Evidence:{" "}
                          {proposalState.proposal.evidence_ids.map((id, index) => (
                            <span key={id} className="font-mono text-xs text-text-primary">
                              {id}
                              {index < proposalState.proposal.evidence_ids.length - 1 ? ", " : ""}
                            </span>
                          ))}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <div>
                  <p className="text-eyebrow uppercase text-accent">Your decision</p>
                  <textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Notes (required)"
                    rows={3}
                    className="mt-3 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
                  />
                  {actionState.status === "error" && <p className="mt-2 text-sm text-sev-high">{actionState.message}</p>}
                  <div className="mt-3 flex gap-3">
                    <button
                      type="button"
                      disabled={actionState.status === "submitting" || !notes.trim()}
                      onClick={(event) => {
                        event.stopPropagation();
                        submit("approve");
                      }}
                      className="rounded-md bg-action px-4 py-2 text-sm text-action-text disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={actionState.status === "submitting" || !notes.trim()}
                      onClick={(event) => {
                        event.stopPropagation();
                        submit("reject");
                      }}
                      className="rounded-md border border-border-strong px-4 py-2 text-sm text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
