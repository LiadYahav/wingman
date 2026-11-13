/**
 * Dismissing a finished upgrade's panel on the cluster page, in this browser
 * only (a per-viewer convenience). A cluster's run id is reused by its next
 * upgrade, so what is kept is the finished run's fingerprint: the next run,
 * or the same run reopened, shows again.
 */

import type { UpgradeRun } from "@/types";

const PREFIX = "wingman.upgrade-dismissed.";

/** Who kept a run's fingerprint: the cluster's run id. */
export const dismissKey = (workflowId: string): string => `${PREFIX}${workflowId}`;

/** What tells this finished run from the cluster's next one under the same id. */
export function runFingerprint(run: UpgradeRun): string {
  const last = run.log.length > 0 ? run.log[run.log.length - 1].at : "";
  return [run.workflow_id, run.outcome ?? run.status, run.plan?.target ?? "", last].join("|");
}

/** Whether `stored` dismissed this run: only a finished one can be. */
export const isDismissed = (run: UpgradeRun, stored: string | null): boolean =>
  run.status !== "running" && stored === runFingerprint(run);

/** The fingerprint kept for `workflowId`; `null` when none, or storage is unavailable. */
export function readDismissed(storage: Pick<Storage, "getItem"> | undefined, workflowId: string): string | null {
  try {
    return storage?.getItem(dismissKey(workflowId)) ?? null;
  } catch {
    return null;
  }
}

/** Keep `run`'s fingerprint; `false` when storage is unavailable (it shows again on reload). */
export function writeDismissed(storage: Pick<Storage, "setItem"> | undefined, run: UpgradeRun): boolean {
  try {
    storage?.setItem(dismissKey(run.workflow_id), runFingerprint(run));
    return storage !== undefined;
  } catch {
    return false;
  }
}
