"use client";

import { toast } from "sonner";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { changeWords, refusalTitle, STALE_RUN_CODES } from "@/lib/scale-model";
import type { ScaleTabValue } from "./scale-tab";

/** Focus an element once React has drawn it (or the one it replaced). */
export function focusSoon(id: string) {
  requestAnimationFrame(() => document.getElementById(id)?.focus());
}

/** Whether the last start's refusal said the page is out of date (a run started, or may have): it is read again. */
export function settled(tab: ScaleTabValue): boolean {
  return STALE_RUN_CODES.some((code) => isApiError(tab.state.start.error, code));
}

/**
 * Whether the change can be sent now, and why not: a run is going, the refusal said the page was out of date, no
 * number, or a scale-down that picks its servers has not ticked as many as leave.
 */
export function sendable(tab: ScaleTabValue): boolean {
  const { start, asked, ready } = tab.state;
  return tab.busy === null && !settled(tab) && asked !== null && !start.isPending && ready;
}

/** Sends the change once; on its start, a toast, and focus on the run where it shows. */
export function sendChange(tab: ScaleTabValue) {
  const { change, current, asked } = tab.state;
  if (!change) return;
  tab.state.send(() => {
    toast.success("update-nodepool started", { description: `${change.nodepool}: ${changeWords(current, asked)} replicas` });
    focusSoon("scale-run");
  });
}

/** The refusal of a start, in the problem's words. */
export function StartError({ tab }: { tab: ScaleTabValue }) {
  const { error } = tab.state.start;
  if (!error) return null;
  return (
    <div data-testid="scale-error">
      <ProblemList error={error} title={refusalTitle(error)} />
    </div>
  );
}
