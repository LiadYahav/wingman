"use client";

import { useState } from "react";
import { CalendarOff, Info, KeyRound, Timer } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessages, isApiError } from "@/lib/api-client";
import { useServerScanJobs } from "@/lib/api/server-scan-jobs";
import { backendNote, FEATURE_OFF, isUnfinished, NO_CRONJOBS, startedPod, type SelectedPod } from "@/lib/server-scan/jobs";
import type { CronJob, JobsOverview } from "@/types/server-scan-jobs";
import { Blocked, needsAdminToken } from "../blocked";
import { CronJobCard } from "./cronjob-card";
import { LogsDialog } from "./logs-dialog";
import { RunDialog } from "./run-dialog";

/** server-scan's introduction, and who Wingman records, in the heading's tooltip. */
const ABOUT =
  "Start a collector or prune CronJob now, like oc create job --from, and read its logs. Every run is recorded in server-scan's audit trail, as Wingman's admin token; Wingman's own log names the person.";

function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" data-testid="ss-jobs-loading">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-28 w-full rounded-xl" />
      ))}
    </div>
  );
}

/**
 * Why the page shows nothing: not an admin (403) or no server-scan at all
 * (the area's own words), or day1's 501 naming the admin token
 * (`details.setting`), in its words.
 */
function Off({ error }: { error: unknown }) {
  if (!needsAdminToken(error)) return <Blocked error={error} />;
  return (
    <EmptyState
      icon={KeyRound}
      bordered
      title="Jobs is not set up"
      description={errorMessages(error)[0]}
      data-testid="ss-jobs-off"
    />
  );
}

interface Cards {
  data: JobsOverview;
  selected: SelectedPod | null;
  onSelect: (pod: SelectedPod) => void;
  onRun: (cronjob: CronJob) => void;
  /** The CronJobs whose last start was not answered. */
  unconfirmed: string[];
}

function CronJobs({ data, selected, onSelect, onRun, unconfirmed }: Cards) {
  if (!data.enabled) {
    return (
      <EmptyState
        icon={CalendarOff}
        bordered
        title={FEATURE_OFF}
        description="server-scan's chart decides it (jobTrigger.enabled)."
        data-testid="ss-jobs-feature-off"
      />
    );
  }
  if (data.cronjobs.length === 0) {
    return <EmptyState icon={Timer} bordered title={NO_CRONJOBS} data-testid="ss-jobs-empty" />;
  }
  return (
    <div className="space-y-4">
      {data.cronjobs.map((cronjob) => (
        <CronJobCard
          key={cronjob.name}
          cronjob={cronjob}
          selected={selected}
          onSelect={onSelect}
          onRun={() => onRun(cronjob)}
          unconfirmed={unconfirmed.includes(cronjob.name)}
        />
      ))}
    </div>
  );
}

/**
 * The Server Scan area's Jobs page (ADR-0048's 3.32.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §15): server-scan's
 * triggerable CronJobs, their recent Jobs and a pod's log, its cards, words
 * and log view, in Wingman's design. Read every 5 seconds while a Job runs,
 * every 30 otherwise, as the original. Run job starts one now (§15.6): on
 * success the list is read again and the new Job's log opens.
 */
export function JobsPage() {
  const jobs = useServerScanJobs();
  const [selected, setSelected] = useState<SelectedPod | null>(null);
  const [asking, setAsking] = useState<CronJob | null>(null);
  const [unconfirmed, setUnconfirmed] = useState<string[]>([]);
  const mark = (name: string, unanswered: boolean) =>
    setUnconfirmed((names) => [...names.filter((n) => n !== name), ...(unanswered ? [name] : [])]);
  const off = isApiError(jobs.error, "FORBIDDEN") || isApiError(jobs.error, "FEATURE_DISABLED");
  const data = off ? undefined : jobs.data;
  const note = backendNote(data);
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-1">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Jobs
          </h1>
          <Hint hint={ABOUT} label="About Jobs" testId="ss-jobs-about">
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground" data-testid="ss-jobs-intro">
          server-scan&apos;s collector and prune CronJobs, their runs and logs.{note && ` ${note}`}
        </p>
      </header>
      {off ? (
        <Off error={jobs.error} />
      ) : jobs.isPending ? (
        <Loading />
      ) : !data ? (
        <ProblemList error={jobs.error} title="The jobs could not be loaded from server-scan" />
      ) : (
        <>
          {jobs.error !== null && <ProblemList error={jobs.error} title="The last read failed; this is the read before it" />}
          <CronJobs data={data} selected={selected} onSelect={setSelected} onRun={setAsking} unconfirmed={unconfirmed} />
        </>
      )}
      {asking && (
        <RunDialog
          key={asking.name}
          cronjob={asking}
          onClose={() => setAsking(null)}
          onStarted={(job) => {
            mark(asking.name, false);
            setAsking(null);
            const pod = startedPod(asking.name, job);
            if (pod) setSelected(pod);
          }}
          onUnconfirmed={() => mark(asking.name, true)}
        />
      )}
      {selected && (
        <LogsDialog
          key={selected.pod}
          selected={selected}
          active={isUnfinished(data?.cronjobs, selected)}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
