"use client";

import { useRef } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessages, isApiError } from "@/lib/api-client";
import { useRunJob } from "@/lib/api/server-scan-jobs";
import { RUN_WORDS } from "@/lib/server-scan/jobs";
import type { CronJob, JobRun } from "@/types/server-scan-jobs";

/**
 * Run job's confirmation, as server-scan's `ConfirmRun`
 * (team-redbull/server-scan at 92146d3, `frontend/src/features/jobs/JobsPage.tsx`,
 * decision 18): its question and words, the CronJob's warning, its problem
 * in its words (409 "already has an unfinished Job", 404). It starts a real
 * collector or prune, so it is sent once per click: the submit is disabled
 * while sending, the dialog cannot be closed until the answer comes, and
 * after an unanswered start (`AMBIGUOUS_WRITE`) Run job stays off here and
 * day1's words say to look at the runs first.
 */
export function RunDialog({
  cronjob,
  onClose,
  onStarted,
  onUnconfirmed,
}: {
  cronjob: CronJob;
  onClose: () => void;
  onStarted: (job: JobRun) => void;
  onUnconfirmed: () => void;
}) {
  const run = useRunJob();
  const sending = useRef(false);
  const unanswered = isApiError(run.error, "AMBIGUOUS_WRITE");
  const close = () => {
    if (!run.isPending) onClose();
  };
  const confirm = () => {
    if (sending.current) return;
    sending.current = true;
    run.mutate(cronjob.name, {
      onSuccess: onStarted,
      onError: (error) => {
        if (isApiError(error, "AMBIGUOUS_WRITE")) onUnconfirmed();
      },
      onSettled: () => {
        sending.current = false;
      },
    });
  };
  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent showCloseButton={false} data-testid="ss-run-dialog">
        <DialogHeader>
          <DialogTitle>Run this job now?</DialogTitle>
          <DialogDescription className="break-all font-mono text-xs">{cronjob.name}</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{RUN_WORDS}</p>
        {cronjob.warning && (
          <p role="note" className="rounded-md border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm text-status-warning-fg" data-testid="ss-run-warning">
            {cronjob.warning}
          </p>
        )}
        {run.isError && (
          <p role="alert" className="text-sm text-destructive" data-testid="ss-run-error">
            {errorMessages(run.error)[0]}
          </p>
        )}
        <DialogFooter>
          <button type="button" onClick={close} disabled={run.isPending} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Cancel
          </button>
          <button type="button" onClick={confirm} disabled={run.isPending || unanswered} className={buttonVariants({ size: "sm" })}>
            {run.isPending ? "Starting…" : "Run job"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
