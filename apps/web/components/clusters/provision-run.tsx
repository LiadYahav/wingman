"use client";

import { CircleCheck, CircleX, ExternalLink, GitPullRequest, Loader2 } from "lucide-react";
import { ProblemList } from "@/components/common/problem-list";
import { humanize, isRunning } from "@/lib/nodes";
import { useProvisionRun } from "@/lib/provision";
import { cn } from "@/lib/utils";
import type { ProvisionRun } from "@/types";

/**
 * A new cluster's provision-cluster run (ADR-0042), in the workflow's own
 * words: its status, the phase it is on (humanized, never from a list Wingman
 * keeps), the merge request once the workflow has opened one, and its error.
 * Read again every 10 s while it runs.
 */
export function ProvisionRunPanel({ started }: { started: ProvisionRun }) {
  const { data, error } = useProvisionRun(started.cluster, started);
  const run = data ?? started;
  const running = isRunning(run);
  const completed = run.status === "completed";
  return (
    <section
      data-testid="provision-run"
      aria-labelledby="provision-run-title"
      className={cn(
        "rounded-2xl border p-5 space-y-4",
        running && "border-status-provisioning/30 bg-status-provisioning/5",
        completed && "border-status-ready/30 bg-status-ready/5",
        !running && !completed && "border-status-error/30 bg-status-error/5"
      )}
    >
      <div className="flex items-start gap-3">
        {running ? (
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-status-provisioning-fg motion-reduce:animate-none" aria-hidden />
        ) : completed ? (
          <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-status-ready-fg" aria-hidden />
        ) : (
          <CircleX className="mt-0.5 h-5 w-5 shrink-0 text-status-error-fg" aria-hidden />
        )}
        <div className="min-w-0 space-y-1">
          <h2 id="provision-run-title" className="text-base font-semibold">
            {running
              ? "Provisioning"
              : completed
                ? "Provisioned"
                : `Provisioning ${humanize(run.status).toLowerCase()}`}{" "}
            <span className="font-mono">{run.cluster}</span>
          </h2>
          <p className="text-sm text-muted-foreground">
            The platform&apos;s provision-cluster workflow reserves the cluster&apos;s segment, opens the merge request and
            waits for a person to merge it.
          </p>
        </div>
      </div>

      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[8rem_1fr]">
        <dt className="text-muted-foreground">Status</dt>
        <dd data-testid="provision-run-status" className="font-medium">{humanize(run.status)}</dd>
        <dt className="text-muted-foreground">Phase</dt>
        <dd data-testid="provision-run-phase" className="font-medium">{run.phase ? humanize(run.phase) : "Starting"}</dd>
        <dt className="text-muted-foreground">Merge request</dt>
        <dd>
          {run.merge_request_url ? (
            <a
              data-testid="provision-run-merge-request"
              href={run.merge_request_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
            >
              <GitPullRequest className="h-3.5 w-3.5" aria-hidden />
              Review it{run.merge_request_state ? ` (${humanize(run.merge_request_state).toLowerCase()})` : ""}
              <ExternalLink className="h-3 w-3 opacity-60 group-hover:opacity-100" aria-hidden />
            </a>
          ) : (
            <span className="text-muted-foreground">Not opened yet</span>
          )}
        </dd>
        <dt className="text-muted-foreground">Run</dt>
        <dd className="font-mono text-xs break-all text-muted-foreground">{run.workflow_id}</dd>
      </dl>

      {run.error && (
        <p data-testid="provision-run-error" className="rounded-md bg-status-error/10 px-3 py-2 text-sm text-status-error-fg break-words">
          {run.error}
        </p>
      )}
      {error && <ProblemList error={error} title="The run could not be read again" />}
    </section>
  );
}
