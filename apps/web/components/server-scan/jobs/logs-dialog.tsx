"use client";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessages } from "@/lib/api-client";
import { useJobLogs } from "@/lib/api/server-scan-jobs";
import { logsBody, logsCaption, type SelectedPod } from "@/lib/server-scan/jobs";

const LINK = "text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 rounded";

/**
 * A pod's log over the Jobs page, as server-scan's `LogPane`
 * (team-redbull/server-scan at 92146d3, `frontend/src/features/jobs/JobsPage.tsx`,
 * decision 18): the pod and its Job, Refresh and Close, the last 500 lines,
 * read again every 3 seconds while the Job is unfinished (`active`). Escape
 * or a click outside closes it.
 */
export function LogsDialog({ selected, active, onClose }: { selected: SelectedPod; active: boolean; onClose: () => void }) {
  const logs = useJobLogs(selected, active);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="flex max-h-[85vh] flex-col sm:max-w-4xl"
        data-testid="ss-job-logs"
      >
        <DialogHeader className="flex-row items-start justify-between gap-4">
          <div className="min-w-0">
            <DialogTitle className="break-all font-mono text-sm">{selected.pod}</DialogTitle>
            <DialogDescription className="break-all font-mono text-xs">{selected.job}</DialogDescription>
          </div>
          <div className="flex shrink-0 gap-4">
            <button type="button" className={LINK} onClick={() => void logs.refetch()}>
              Refresh
            </button>
            <button type="button" className={LINK} onClick={onClose}>
              Close
            </button>
          </div>
        </DialogHeader>
        <p className="text-xs text-muted-foreground" data-testid="ss-job-logs-caption">
          {logsCaption(active)}
        </p>
        {logs.isError && !logs.data ? (
          <p role="alert" className="text-sm text-destructive" data-testid="ss-job-logs-error">
            {errorMessages(logs.error)[0]}
          </p>
        ) : (
          <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-xs" data-testid="ss-job-logs-text">
            {logsBody(logs.data)}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
