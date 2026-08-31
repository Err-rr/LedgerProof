"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/error-state";

export default function ProvenanceError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div>
      <ErrorState title="Something went wrong loading provenance" message={error.message} />
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded-md border border-border-strong px-4 py-2 text-sm text-text-secondary hover:text-text-primary"
      >
        Try again
      </button>
    </div>
  );
}
