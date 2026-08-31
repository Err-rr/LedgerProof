"use client";

import { useRef, useState } from "react";

import { formatCount } from "@/lib/format";
import type { FilePreview } from "@/lib/file-preview";

interface DropZoneProps {
  label: string;
  hint: string;
  required: boolean;
  preview: FilePreview | null;
  disabled: boolean;
  onFile: (file: File) => void;
  onClear: () => void;
}

export function DropZone({ label, hint, required, preview, disabled, onFile, onClear }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const file = event.dataTransfer.files?.[0];
    if (file) onFile(file);
  }

  const borderClass = preview?.parseError
    ? "border-sev-high"
    : isDragging
      ? "border-accent"
      : "border-border";

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`rounded-card border bg-surface p-5 transition-colors ${borderClass}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-text-primary">
            {label}
            {!required && <span className="text-text-muted"> (optional)</span>}
          </p>
          <p className="mt-1 font-mono text-xs text-text-muted">{hint}</p>
        </div>
        {preview && (
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-text-secondary hover:text-text-primary"
            aria-label={`Remove ${label}`}
          >
            Remove
          </button>
        )}
      </div>

      {preview ? (
        <div className="mt-4 rounded-md border border-border-strong bg-surface-raised px-3 py-2.5">
          <p className="truncate text-sm text-text-primary">{preview.file.name}</p>
          {preview.parseError ? (
            <p className="mt-1 text-xs text-sev-high">{preview.parseError}</p>
          ) : (
            <p className="tabular-nums mt-1 text-xs text-text-secondary">
              {preview.rowCount === null ? "—" : formatCount(preview.rowCount)} rows
            </p>
          )}
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="mt-4 w-full rounded-md border border-dashed border-border-strong py-6 text-sm text-text-secondary transition-colors hover:border-accent hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          Drop file here or click to browse
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}
