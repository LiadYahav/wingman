/**
 * Adding servers to a pool (ADR-0057): what the dialog may send and how an
 * answer reads. A start is never retried; after an unanswered one the dialog
 * sends nothing more (some runs may have started).
 */

import { isApiError } from "@/lib/api-client";
import type { ErrorCode } from "@/types";
import type { AddServersRequest, AddServersResult } from "@/types/inventory";

/** The orchestrator's limit, by count or by name. */
export const MAX_SERVERS = 20;

export type AddMode = "count" | "named";

/** The body to send, or `null` while the choice is not one day1 accepts. */
export function addRequest(mode: AddMode, count: number, names: string[]): AddServersRequest | null {
  if (mode === "count") {
    return Number.isInteger(count) && count >= 1 && count <= MAX_SERVERS ? { count } : null;
  }
  return names.length >= 1 && names.length <= MAX_SERVERS ? { server_names: names } : null;
}

/** Add or remove one name; a full list takes no more. */
export function toggled(names: string[], name: string): string[] {
  if (names.includes(name)) return names.filter((n) => n !== name);
  return names.length >= MAX_SERVERS ? names : [...names, name];
}

/** `2 started · 1 already running`: the per-run answer, in one line. */
export function startSummary(result: AddServersResult): string {
  const parts = [
    [result.started, "started"],
    [result.already_running, "already running"],
    [result.failed, "failed"],
  ] as const;
  const said = parts.filter(([n]) => n > 0).map(([n, word]) => `${n} ${word}`);
  return said.length > 0 ? said.join(" · ") : "Nothing started";
}

const SETTLED: readonly ErrorCode[] = ["AMBIGUOUS_WRITE", "ADD_SERVER_ALREADY_RUNNING", "FEATURE_DISABLED"];

/** After these the dialog sends nothing more: the page is read again instead (ADR-0006). */
export const isSettled = (error: unknown): boolean => SETTLED.some((code) => isApiError(error, code));

/** The heading of a refused start, by its `code`; the problem's lines go under it. */
export function refusalTitle(error: unknown): string {
  if (isApiError(error, "AMBIGUOUS_WRITE")) return "No answer: some may have started. Look at the runs before sending again.";
  if (isApiError(error, "ADD_SERVER_ALREADY_RUNNING")) return "Already running: the runs show it.";
  if (isApiError(error, "VALIDATION_ERROR")) return "Not started.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: a service did not answer.";
  if (isApiError(error, "FEATURE_DISABLED")) return "Adding servers is not available here.";
  return "Not started.";
}
