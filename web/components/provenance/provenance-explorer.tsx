"use client";

import { useState } from "react";

import { ChainView } from "@/components/provenance/chain";
import { buildChain } from "@/lib/provenance";
import type { ExceptionOut, MatchRecordOut } from "@/lib/api-types";

interface Props {
  orderIds: string[];
  matchRecords: MatchRecordOut[];
  exceptions: ExceptionOut[];
}

export function ProvenanceExplorer({ orderIds, matchRecords, exceptions }: Props) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(orderIds[0] ?? null);

  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed ? orderIds.filter((id) => id.toLowerCase().includes(trimmed)) : orderIds;
  const chain = selected ? buildChain(selected, matchRecords, exceptions) : null;

  return (
    <div className="flex flex-col gap-8 md:flex-row md:items-start">
      <div className="w-full shrink-0 md:w-64">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search order ID"
          aria-label="Search order ID"
          className="w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
        />
        <ul className="mt-3 max-h-[28rem] space-y-1 overflow-y-auto">
          {filtered.map((id) => (
            <li key={id}>
              <button
                type="button"
                onClick={() => setSelected(id)}
                aria-current={selected === id}
                className={`w-full rounded-md px-3 py-2 text-left font-mono text-xs transition-colors ${
                  selected === id
                    ? "bg-surface-raised text-text-primary"
                    : "text-text-secondary hover:bg-surface-raised hover:text-text-primary"
                }`}
              >
                {id}
              </button>
            </li>
          ))}
          {filtered.length === 0 && <li className="px-3 py-2 text-sm text-text-muted">No orders match.</li>}
        </ul>
      </div>

      <div className="min-w-0 flex-1">
        {chain ? (
          <ChainView chain={chain} />
        ) : (
          <p className="text-sm text-text-secondary">Select an order on the left to see its chain.</p>
        )}
      </div>
    </div>
  );
}
