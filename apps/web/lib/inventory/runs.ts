/**
 * How an add-server run reads on the page (ADR-0057). Who started a pool draw
 * cannot be told (the orchestrator records no `requested_by`), so it is never
 * guessed; phases are the workflow's own words, only made readable.
 */

import type { InventoryRun, RunOrigin } from "@/types/inventory";

export type RunTone = "running" | "completed" | "failed" | "other";

/** Who may have started a run, in a word or two. */
export function originLabel(origin: RunOrigin | null): string {
  if (origin === "named") return "Person";
  if (origin === "pool") return "herzi or a person";
  return "Unknown";
}

/** The tooltip that says why the origin reads as it does. */
export function originHint(origin: RunOrigin | null): string {
  if (origin === "named") return "A named install: herzi never names a server.";
  if (origin === "pool") return "A pool draw: herzi and people start the same request, and the orchestrator records no author.";
  return "The run's id is not one of add-server-to-mce's shapes.";
}

/** The run's slot (a pool draw) or server (a named install, or the one a draw took). */
export function runSubject(run: InventoryRun): string {
  if (run.server_name) return run.server_name;
  if (run.slot !== null) return `slot ${run.slot}`;
  return "—";
}

/** `waiting-for-agent` → `waiting for agent`; the word stays the workflow's. `null` when it adds nothing. */
export function readablePhase(phase: string | null, status = ""): string | null {
  if (!phase || phase.toLowerCase() === status.toLowerCase()) return null;
  return phase.replace(/[-_]+/g, " ").trim();
}

/** The status's colour family; anything new is `other`. */
export function runTone(status: string): RunTone {
  const lowered = status.toLowerCase();
  if (lowered === "running" || lowered === "continued_as_new") return "running";
  if (lowered === "completed") return "completed";
  if (["failed", "terminated", "timed_out", "canceled", "cancelled"].includes(lowered)) return "failed";
  return "other";
}

/** How many runs are still going: the page says so beside its heading. */
export const runningCount = (runs: InventoryRun[]): number =>
  runs.filter((run) => runTone(run.status) === "running").length;
