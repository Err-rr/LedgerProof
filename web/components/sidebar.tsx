"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * There is no "list runs" endpoint on the API (by design -- see api/routers),
 * so there is no server-side way to know which run is "current." The
 * sidebar instead derives it from the URL: once you're anywhere under
 * /runs/[runId], screens 02-04 point at that same run. Before that, they're
 * visibly present (numbered 01-04, matching the microsite's track list) but
 * disabled with an explanation, rather than silently missing.
 */

interface Screen {
  number: string;
  label: string;
  href: (runId: string) => string;
}

const SCREENS: Screen[] = [
  { number: "01", label: "Upload and run", href: () => "/" },
  { number: "02", label: "Summary", href: (runId) => `/runs/${runId}` },
  { number: "03", label: "Exception queue", href: (runId) => `/runs/${runId}/exceptions` },
  { number: "04", label: "Provenance drill-down", href: (runId) => `/runs/${runId}/provenance` },
];

function extractRunId(pathname: string): string | null {
  const match = pathname.match(/^\/runs\/([^/]+)/);
  return match?.[1] ?? null;
}

export function Sidebar() {
  const pathname = usePathname();
  const runId = extractRunId(pathname);

  return (
    <nav aria-label="Screens" className="w-[var(--sidebar-width)] shrink-0 border-r border-border px-6 py-10">
      <div className="mb-12">
        <p className="text-eyebrow uppercase text-accent">LedgerProof</p>
        <p className="mt-2 text-sm text-text-secondary">Settlement reconciliation</p>
      </div>
      <ul className="space-y-1">
        {SCREENS.map((screen, index) => {
          const isUpload = index === 0;
          const href = isUpload ? "/" : runId ? screen.href(runId) : null;
          const isActive = href !== null && pathname === href;

          if (href === null) {
            return (
              <li key={screen.number}>
                <span
                  className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2.5 text-text-muted"
                  title="Run a reconciliation first"
                >
                  <span className="font-mono text-xs text-text-muted">{screen.number}</span>
                  <span>{screen.label}</span>
                </span>
              </li>
            );
          }

          return (
            <li key={screen.number}>
              <Link
                href={href}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors ${
                  isActive
                    ? "bg-surface-raised text-text-primary"
                    : "text-text-secondary hover:bg-surface-raised hover:text-text-primary"
                }`}
              >
                <span className={`font-mono text-xs ${isActive ? "text-accent" : "text-text-muted"}`}>{screen.number}</span>
                <span>{screen.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
