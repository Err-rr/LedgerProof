"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "ledgerproof.reviewer-name";

/** There is no auth system in this dashboard -- resolved_by is whatever the
 * reviewer types once, remembered per-browser via localStorage so they
 * don't retype it for every exception. */
export function useReviewerName(): [string, (name: string) => void] {
  const [name, setName] = useState("");

  useEffect(() => {
    try {
      setName(window.localStorage.getItem(STORAGE_KEY) ?? "");
    } catch {
      // localStorage unavailable (private browsing, etc.) -- fall back to empty
    }
  }, []);

  function update(next: string) {
    setName(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // best-effort only
    }
  }

  return [name, update];
}
