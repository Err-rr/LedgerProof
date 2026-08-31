import { formatDateTime, formatPercent } from "@/lib/format";
import type { Chain, ChainHop } from "@/lib/provenance";

const METHOD_LABEL: Record<string, string> = {
  utr: "UTR verified",
  amount_date: "Amount + date fallback",
  tier1: "Exact order reference",
  tier2: "Receipt reference",
  tier3: "Amount + time + contact match",
  amount_reconciliation: "Settlement arithmetic",
};

function Node({ label, id }: { label: string; id: string }) {
  return (
    <div className="inline-block rounded-card border border-border-strong bg-surface-raised px-4 py-3">
      <p className="text-eyebrow uppercase text-accent">{label}</p>
      <p className="mt-1 font-mono text-sm text-text-primary">{id}</p>
    </div>
  );
}

function EvidenceList({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (entries.length === 0) return null;
  return (
    <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex justify-between gap-3 border-b border-border py-1">
          <dt className="text-text-muted">{key}</dt>
          <dd className="text-right text-text-secondary">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Connector({ hop }: { hop: ChainHop }) {
  if (hop.status === "matched" && hop.match) {
    const isUtrVerified = hop.match.method === "utr";
    const methodLabel = METHOD_LABEL[hop.match.method] ?? hop.match.method;
    return (
      <div className={`ml-4 border-l-2 py-4 pl-6 ${isUtrVerified ? "border-accent" : "border-border-strong"}`}>
        <div className="flex flex-wrap items-center gap-3">
          <span aria-hidden className={`h-2 w-2 rounded-full ${isUtrVerified ? "bg-accent" : "bg-text-muted"}`} />
          <span className="text-sm text-text-primary">{methodLabel}</span>
          <span className="tabular-nums text-sm text-text-secondary">{formatPercent(hop.match.confidence)} confidence</span>
          {isUtrVerified && (
            <span className="rounded-full border border-accent px-2 py-0.5 text-xs uppercase tracking-wide text-accent">Verified</span>
          )}
        </div>
        <p className="mt-1 text-xs text-text-muted">{formatDateTime(hop.match.matched_at)}</p>
        <EvidenceList evidence={hop.match.evidence} />
      </div>
    );
  }

  if (hop.status === "ambiguous") {
    return (
      <div className="ml-4 border-l-2 border-dashed border-sev-medium py-4 pl-6">
        <div className="flex items-center gap-2">
          <span aria-hidden className="h-2 w-2 rounded-full bg-sev-medium" />
          <span className="text-sm text-text-primary">Ambiguous match -- refused to guess</span>
        </div>
        <p className="mt-2 text-sm text-text-secondary">{hop.ambiguousReason}</p>
        {hop.ambiguousCandidates && hop.ambiguousCandidates.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {hop.ambiguousCandidates.map((candidate) => (
              <span key={candidate} className="rounded-md border border-border-strong px-2 py-1 font-mono text-xs text-text-secondary">
                {candidate}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="ml-4 border-l-2 border-dashed border-border-strong py-4 pl-6">
      <div className="flex items-center gap-2">
        <span aria-hidden className="h-2 w-2 rounded-full bg-text-muted" />
        <span className="text-sm text-text-secondary">No match</span>
      </div>
      <p className="mt-2 text-sm text-text-muted">{hop.missingReason}</p>
    </div>
  );
}

export function ChainView({ chain }: { chain: Chain }) {
  return (
    <div>
      <Node label="Order" id={chain.orderId} />
      {chain.hops.map((hop, index) => (
        <div key={index}>
          <Connector hop={hop} />
          {hop.status === "matched" && hop.nextId && <Node label={hop.to} id={hop.nextId} />}
        </div>
      ))}
    </div>
  );
}
