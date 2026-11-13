"use client";

import { useCallback, useState, useSyncExternalStore } from "react";
import { isDismissed, readDismissed, runFingerprint, writeDismissed } from "@/lib/upgrade-dismiss";
import type { UpgradeRun } from "@/types";

/** Fired in this tab when a run is dismissed; other tabs hear `storage`. */
const DISMISSED_EVENT = "wingman:upgrade-dismissed";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(DISMISSED_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(DISMISSED_EVENT, onChange);
  };
}

const browserStorage = (): Storage | undefined => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

/**
 * Whether this finished run's panel was dismissed in this browser, and a way
 * to dismiss it. Never during the server render (nothing is stored there),
 * and kept for this page when storage is unavailable.
 */
export function useDismissedRun(run: UpgradeRun): [boolean, () => void] {
  const stored = useSyncExternalStore(
    subscribe,
    () => readDismissed(browserStorage(), run.workflow_id),
    () => null
  );
  const [here, setHere] = useState<string | null>(null);
  const dismiss = useCallback(() => {
    if (writeDismissed(browserStorage(), run)) window.dispatchEvent(new Event(DISMISSED_EVENT));
    else setHere(runFingerprint(run));
  }, [run]);
  return [isDismissed(run, stored) || isDismissed(run, here), dismiss];
}
