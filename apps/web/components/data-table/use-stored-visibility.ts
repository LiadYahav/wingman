"use client";

import { useCallback, useState } from "react";
import type { VisibilityState } from "@tanstack/react-table";

function read(key: string): VisibilityState {
  try {
    const raw: unknown = JSON.parse(window.localStorage.getItem(key) ?? "{}");
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return {};
    return Object.fromEntries(Object.entries(raw).filter(([, shown]) => typeof shown === "boolean"));
  } catch {
    return {};
  }
}

/**
 * Which columns a person hid, kept in this browser under `key` (a per-viewer
 * convenience, as segments-manager's UI keeps it): every column is shown when
 * nothing was stored, or storage is unavailable. Read once, in the browser:
 * call it only below a Suspense boundary that renders on the client.
 */
export function useStoredVisibility(key: string): [VisibilityState, (next: VisibilityState) => void] {
  const [visibility, setVisibility] = useState<VisibilityState>(() => (typeof window === "undefined" ? {} : read(key)));
  const update = useCallback(
    (next: VisibilityState) => {
      setVisibility(next);
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* storage unavailable: kept for this page only */
      }
    },
    [key]
  );
  return [visibility, update];
}
