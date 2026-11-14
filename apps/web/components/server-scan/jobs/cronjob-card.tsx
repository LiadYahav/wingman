import { pill } from "@/components/server-scan/server-badges";
import { buttonVariants } from "@/components/ui/button";
import { formatRelative } from "@/lib/server-scan/datetime";
import {
  ENABLED_HINT, enabledLabel, manualText, noRunsText, podButtonLabel, runBlocked, runTimesHint, scheduleHint, UNCONFIRMED_START, type SelectedPod,
} from "@/lib/server-scan/jobs";
import { cn } from "@/lib/utils";
import type { CronJob, JobRun, JobState } from "@/types/server-scan-jobs";

/**
 * One of server-scan's CronJobs on the Jobs page, as its `CronJobCard` and
 * `JobRow` (team-redbull/server-scan at 92146d3,
 * `frontend/src/features/jobs/JobsPage.tsx`, decision 18): its name,
 * schedule, values.yaml flag and recent Jobs, newest first, each with its
 * state, who started it by hand, when, and a button per pod for its log;
 * and Run job, off (with why as its tooltip) while a Job of it is unfinished
 * or when it is not deployed.
 */

const STATE_TONE: Record<JobState, string> = {
  active: "bg-status-provisioning/15 text-status-provisioning-fg",
  succeeded: "bg-status-ready/15 text-status-ready-fg",
  failed: "bg-status-error/15 text-status-error-fg",
  pending: "bg-muted text-muted-foreground",
};

function StateChip({ state }: { state: JobState }) {
  return (
    <span className={cn(pill, STATE_TONE[state] ?? STATE_TONE.pending)} data-testid="ss-job-state">
      {state}
    </span>
  );
}

function JobLine({
  cronjob,
  job,
  selected,
  onSelect,
}: {
  cronjob: string;
  job: JobRun;
  selected: SelectedPod | null;
  onSelect: (pod: SelectedPod) => void;
}) {
  const manual = manualText(job);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-sm" data-testid="ss-job" data-job={job.name}>
      <StateChip state={job.state} />
      <span className="font-mono text-xs">{job.name}</span>
      {manual && <span className="text-xs text-muted-foreground">{manual}</span>}
      {job.created_at && (
        <span className="text-xs text-muted-foreground" title={runTimesHint(job)} data-testid="ss-job-time">
          {formatRelative(job.created_at)}
        </span>
      )}
      <span className="ml-auto flex flex-wrap gap-2">
        {job.pods.map((pod) => {
          const pressed = selected?.pod === pod.name;
          return (
            <button
              key={pod.name}
              type="button"
              aria-pressed={pressed}
              onClick={() => onSelect({ cronjob, job: job.name, pod: pod.name })}
              className={cn(
                "rounded-md border px-2 py-0.5 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
                pressed ? "border-foreground/40 text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {podButtonLabel(pod)}
            </button>
          );
        })}
      </span>
    </li>
  );
}

/** Run job: `aria-disabled`, not `disabled`, when off, so its tooltip still says why. */
function RunButton({ cronjob, onRun }: { cronjob: CronJob; onRun: () => void }) {
  const blocked = runBlocked(cronjob);
  return (
    <button
      type="button"
      title={blocked ?? undefined}
      aria-disabled={blocked ? true : undefined}
      aria-haspopup="dialog"
      onClick={() => {
        if (!blocked) onRun();
      }}
      className={cn(buttonVariants({ size: "sm" }), "ml-auto", blocked && "cursor-not-allowed opacity-40")}
      data-testid="ss-run-job"
    >
      Run job
    </button>
  );
}

/** A CronJob's card: dimmed when its values.yaml flag is off. */
export function CronJobCard({
  cronjob,
  selected,
  onSelect,
  onRun,
  unconfirmed = false,
}: {
  cronjob: CronJob;
  selected: SelectedPod | null;
  onSelect: (pod: SelectedPod) => void;
  /** Run job's click; none: no Run job. */
  onRun?: () => void;
  /** Its last start was sent and not answered. */
  unconfirmed?: boolean;
}) {
  return (
    <section
      aria-label={cronjob.name}
      className={cn("rounded-xl border bg-card p-4", !cronjob.enabled && "opacity-70")}
      data-testid="ss-cronjob"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-sm font-semibold">{cronjob.name}</h2>
        {cronjob.schedule && (
          <span className="font-mono text-xs text-muted-foreground" title={scheduleHint(cronjob)} data-testid="ss-cronjob-schedule">
            {cronjob.schedule}
          </span>
        )}
        {cronjob.suspend && <span className="text-xs text-muted-foreground">suspended</span>}
        <span
          className={cn(pill, cronjob.enabled ? "bg-status-ready/15 text-status-ready-fg" : "bg-muted text-muted-foreground")}
          title={ENABLED_HINT}
          data-testid="ss-cronjob-enabled"
        >
          {enabledLabel(cronjob)}
        </span>
        {onRun && <RunButton cronjob={cronjob} onRun={onRun} />}
      </div>
      {unconfirmed && (
        <p role="note" className="mt-3 rounded-md border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm text-status-warning-fg" data-testid="ss-run-unconfirmed">
          {UNCONFIRMED_START}
        </p>
      )}
      {cronjob.jobs.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground" data-testid="ss-cronjob-empty">
          {noRunsText(cronjob)}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border/60">
          {cronjob.jobs.map((job) => (
            <JobLine key={job.name} cronjob={cronjob.name} job={job} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </section>
  );
}
