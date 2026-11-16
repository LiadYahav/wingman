"use client";

import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import { parseCollapsed, readCollapsedMces, serializeCollapsed, toggledMce, writeCollapsedMces } from "@/lib/inventory/collapsed";

/** Fired in this tab when a card collapses or expands; other tabs hear `storage`. */
const CHANGE_EVENT = "wingman:inventory-collapsed";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

const browserStorage = (): Storage | undefined => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

const stored = () => readCollapsedMces(browserStorage());

/**
 * The MCE cards this browser keeps collapsed, and a toggle. Every card is
 * expanded during the server render and when nothing is stored; with storage
 * unavailable a toggle holds for this page.
 */
export function useCollapsedMces(): [ReadonlySet<string>, (mce: string) => void] {
  const kept = useSyncExternalStore(subscribe, stored, () => null);
  const [here, setHere] = useState<string | null>(null);
  const collapsed = useMemo(() => parseCollapsed(here ?? kept), [here, kept]);
  const toggle = useCallback(
    (mce: string) => {
      const next = serializeCollapsed(toggledMce(collapsed, mce));
      if (writeCollapsedMces(browserStorage(), next)) {
        setHere(null);
        window.dispatchEvent(new Event(CHANGE_EVENT));
      } else {
        setHere(next);
      }
    },
    [collapsed]
  );
  return [collapsed, toggle];
}
