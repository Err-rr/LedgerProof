"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { DropZone } from "@/components/upload/drop-zone";
import { PipelineStatus } from "@/components/upload/pipeline-status";
import { previewFile, type FileKind, type FilePreview } from "@/lib/file-preview";
import { pollRun } from "@/lib/poll-run";
import { FetchFailure, fetchJson } from "@/lib/safe-fetch";
import type { RunCreateResponse } from "@/lib/api-types";

interface FieldMeta {
  kind: FileKind;
  label: string;
  hint: string;
  required: boolean;
}

const FIELDS: FieldMeta[] = [
  { kind: "orders", label: "Orders", hint: "orders.xlsx", required: true },
  { kind: "payments", label: "Payments", hint: "payments.json", required: true },
  { kind: "settlements", label: "Settlements", hint: "settlements.json", required: true },
  { kind: "bank_statement", label: "Bank statement", hint: "bank_statement.csv", required: true },
  { kind: "refunds", label: "Refunds", hint: "refunds.json", required: false },
];

type RunPhase =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "run_failed"; message: string }
  | { status: "request_failed"; message: string };

export function UploadRunner() {
  const router = useRouter();
  const [previews, setPreviews] = useState<Partial<Record<FileKind, FilePreview>>>({});
  const [phase, setPhase] = useState<RunPhase>({ status: "idle" });
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (phase.status !== "running") return;
    const startedAt = phase.startedAt;
    const timer = window.setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100);
    return () => window.clearInterval(timer);
  }, [phase]);

  async function handleFile(kind: FileKind, file: File) {
    const preview = await previewFile(kind, file);
    setPreviews((prev) => ({ ...prev, [kind]: preview }));
  }

  function handleClear(kind: FileKind) {
    setPreviews((prev) => {
      const next = { ...prev };
      delete next[kind];
      return next;
    });
  }

  const requiredFields = FIELDS.filter((field) => field.required);
  const canRun =
    phase.status !== "running" &&
    requiredFields.every((field) => {
      const preview = previews[field.kind];
      return preview !== undefined && preview.parseError === null;
    });

  async function handleRun() {
    setElapsed(0);
    setPhase({ status: "running", startedAt: Date.now() });

    const formData = new FormData();
    for (const field of FIELDS) {
      const preview = previews[field.kind];
      if (preview) formData.append(field.kind, preview.file);
    }

    try {
      const createBody = await fetchJson<RunCreateResponse>("/api/runs", { method: "POST", body: formData });

      const run = await pollRun(createBody.run_id);
      if (run.status === "failed") {
        setPhase({ status: "run_failed", message: run.error ?? "the reconciliation run failed for an unknown reason" });
        return;
      }
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      // A FetchFailure already carries a readable message for both causes
      // (network failure vs. an HTTP error response) -- see lib/safe-fetch.ts.
      setPhase({ status: "request_failed", message: err instanceof FetchFailure ? err.message : err instanceof Error ? err.message : "unknown error starting the run" });
    }
  }

  if (phase.status === "running") {
    return <PipelineStatus elapsedSeconds={elapsed} />;
  }

  return (
    <div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {FIELDS.map((field) => (
          <DropZone
            key={field.kind}
            label={field.label}
            hint={field.hint}
            required={field.required}
            preview={previews[field.kind] ?? null}
            disabled={false}
            onFile={(file) => handleFile(field.kind, file)}
            onClear={() => handleClear(field.kind)}
          />
        ))}
      </div>

      {(phase.status === "run_failed" || phase.status === "request_failed") && (
        <div className="mt-6 rounded-card border border-sev-high bg-surface p-4">
          <p className="text-sm text-text-primary">
            {phase.status === "run_failed" ? "The reconciliation run failed." : "Could not start the run."}
          </p>
          <p className="mt-2 text-sm text-text-secondary">{phase.message}</p>
        </div>
      )}

      <div className="mt-8 flex items-center gap-4">
        <button
          type="button"
          disabled={!canRun}
          onClick={handleRun}
          className="rounded-md bg-action px-5 py-2.5 text-sm text-action-text transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          Run reconciliation
        </button>
        <p className="text-sm text-text-muted">
          {canRun ? "Ready." : `Waiting on ${requiredFields.filter((f) => !previews[f.kind] || previews[f.kind]?.parseError).length} required file(s).`}
        </p>
      </div>
    </div>
  );
}
