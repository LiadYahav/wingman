"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight, Ban, CheckCircle2, CircleHelp, CircleX, Clock, ExternalLink, GitPullRequest, GitPullRequestArrow, Loader2,
  RefreshCw, TriangleAlert,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { approvalHref } from "@/lib/approvals";
import { clusterHref } from "@/lib/clusters";
import { ROLLOUT_LABEL, ROLLOUT_ORDER, useRollout } from "@/lib/rollout";
import { cn, formatDateTime, plural } from "@/lib/utils";
import { writeErrorTitle } from "@/lib/write-errors";
import { useIsAdmin } from "@/stores/auth-store";
import type { RolloutCluster, RolloutRun, RolloutState } from "@/types";

const LOOK: Record<RolloutState, { Icon: typeof CheckCircle2; className: string }> = {
  needs_decision: { Icon: TriangleAlert, className: "bg-status-warning/10 text-status-warning-fg" },
  failed: { Icon: CircleX, className: "bg-destructive/10 text-destructive" },
  unknown: { Icon: CircleHelp, className: "bg-status-deleting/10 text-status-deleting-fg" },
  declined: { Icon: Ban, className: "bg-muted text-muted-foreground" },
  pending: { Icon: Clock, className: "bg-status-provisioning/10 text-status-provisioning-fg" },
  merge_request_open: { Icon: GitPullRequest, className: "bg-status-provisioning/10 text-status-provisioning-fg" },
  on_version: { Icon: CheckCircle2, className: "bg-status-ready/10 text-status-ready-fg" },
};

/** What a group of clusters means, and what a person can do about it. */
function groupNote(state: RolloutState, version: string): string {
  switch (state) {
    case "needs_decision":
      return "No merge request opens for these until a person decides: open the cluster and sync it by hand.";
    case "failed":
      return "The last attempt to open their merge request failed. The next run tries again, after checking each cluster's branch and merge request.";
    case "unknown":
      return "Their cluster files cannot be read.";
    case "declined":
      return `Their customer closed the merge request without merging it, so no new one opens for v${version}. A person can still sync one by hand from its cluster page.`;
    case "pending":
      return "A merge request opens for each on the next run, or the one running.";
    case "merge_request_open":
      return "Each merge request waits for its customer, who merges it when ready. Nothing changes on a cluster until its own merges.";
    case "on_version":
      return `Already on v${version}.`;
  }
}

const TRIGGER: Record<RolloutRun["trigger"], string> = {
  merge: "after the flavor's merge request merged",
  webhook: "on a push to the specs repo",
  reconcile: "on Reconcile now",
  read: "when the rollout was read with work pending",
};

function Count({ state, count }: { state: RolloutState; count: number }) {
  const { Icon, className } = LOOK[state];
  return (
    <span
      data-testid={`rollout-count-${state}`}
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      {ROLLOUT_LABEL[state]}
      <span className="tabular-nums">{count}</span>
    </span>
  );
}

function MergeRequestLinks({ cluster: c }: { cluster: RolloutCluster }) {
  const mr = c.merge_request;
  if (!mr) return null;
  return (
    <div className="flex shrink-0 items-center gap-3 text-xs font-medium">
      <Link
        href={approvalHref(mr)}
        className="inline-flex items-center gap-0.5 text-primary hover:underline"
        aria-label={`${c.state === "declined" ? "View" : "Review"} !${mr.iid} for ${c.name}`}
      >
        {c.state === "declined" ? "View" : "Review"} !{mr.iid}
        <ArrowRight className="h-3 w-3" aria-hidden />
      </Link>
      <a
        href={mr.web_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
        aria-label={`Open !${mr.iid} for ${c.name} in GitLab`}
      >
        GitLab
        <ExternalLink className="h-3 w-3" aria-hidden />
      </a>
    </div>
  );
}

/** day1 may start a reason with the cluster's name; inside its row that is said already. */
const withoutName = (reason: string, name: string) => (reason.startsWith(`${name}: `) ? reason.slice(name.length + 2) : reason);

function ClusterRow({ cluster: c }: { cluster: RolloutCluster }) {
  const byHand = c.state === "needs_decision" || c.state === "declined";
  return (
    <li
      data-testid={`rollout-cluster-${c.name}`}
      data-state={c.state}
      className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5 py-2.5"
    >
      <div className="min-w-0 space-y-0.5">
        <Link href={clusterHref(c)} className="text-sm font-semibold hover:text-primary transition-colors break-all">
          {c.name}
        </Link>
        <p className="text-xs text-muted-foreground break-all">
          {c.site} / {c.mce}
          {c.from_version && <> · on v{c.from_version}</>}
        </p>
        {c.merge_request && (
          <p className="text-xs break-words">
            <span className="font-mono text-muted-foreground">!{c.merge_request.iid}</span> {c.merge_request.title}
          </p>
        )}
        {c.reasons.length > 0 && (
          <ul
            className={cn(
              "list-disc pl-4 space-y-0.5 text-xs",
              c.state === "failed" ? "text-destructive" : c.state === "unknown" ? "text-status-deleting-fg" : "text-status-warning-fg"
            )}
          >
            {c.reasons.map((r, i) => <li key={i} className="break-words">{withoutName(r, c.name)}</li>)}
          </ul>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <MergeRequestLinks cluster={c} />
        {byHand && (
          <Link
            href={`${clusterHref(c)}&tab=drift`}
            className="inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline"
            aria-label={`Sync ${c.name} by hand`}
          >
            Sync by hand
            <ArrowRight className="h-3 w-3" aria-hidden />
          </Link>
        )}
      </div>
    </li>
  );
}

function Group({ state, clusters, version }: { state: RolloutState; clusters: RolloutCluster[]; version: string }) {
  const { Icon } = LOOK[state];
  return (
    <section data-testid={`rollout-group-${state}`} aria-label={ROLLOUT_LABEL[state]} className="rounded-lg border px-4 py-3">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {ROLLOUT_LABEL[state]} ({clusters.length})
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">{groupNote(state, version)}</p>
      {state === "on_version" ? (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Clusters on the version">
          {clusters.map((c) => (
            <li key={`${c.site}/${c.mce}/${c.name}`} data-testid={`rollout-cluster-${c.name}`} data-state={c.state}>
              <Link
                href={clusterHref(c)}
                className="inline-flex rounded-md border px-2 py-0.5 text-xs font-medium hover:border-primary/50 hover:text-primary transition-colors break-all"
              >
                {c.name}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="divide-y divide-border">
          {clusters.map((c) => <ClusterRow key={`${c.site}/${c.mce}/${c.name}`} cluster={c} />)}
        </ul>
      )}
    </section>
  );
}

function PanelSkeleton() {
  return (
    <div className="bg-card rounded-xl border shadow-sm p-5 space-y-3" data-testid="rollout-loading">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-3 w-full max-w-lg" />
      <div className="flex gap-2">
        <Skeleton className="h-5 w-24 rounded-full" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
    </div>
  );
}

/**
 * The rollout of a flavor's newest version (ADR-0044): one day1 MR per
 * cluster that follows it on an older version, opened by day1 on its own.
 * Counts by state, then the clusters that need a person first, each with its
 * reasons and its MR. Read again every few seconds while day1 is opening MRs;
 * admins can reconcile now.
 */
export function RolloutPanel({ flavor }: { flavor: string }) {
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useRollout(flavor);

  const reconcile = useMutation({
    mutationFn: () => day1Api.specs.reconcileRollout(flavor),
    onSuccess: (status) => {
      queryClient.setQueryData(day1Keys.specs.rollout(flavor), status);
      toast.success(status.running ? "Reconciling: opening the merge requests that are due" : "Nothing to open: every cluster has its merge request");
    },
  });

  // A run that finishes changes the clusters' badges: read them again
  const wasRunning = useRef(false);
  useEffect(() => {
    if (!data) return;
    if (wasRunning.current && !data.running) {
      void queryClient.invalidateQueries({ queryKey: day1Keys.specs.clusters(flavor) });
      void queryClient.invalidateQueries({ queryKey: day1Keys.specs.drift(flavor) });
    }
    wasRunning.current = data.running;
  }, [data, flavor, queryClient]);

  if (isLoading) return <PanelSkeleton />;
  if (error) return <ProblemList error={error} title="The flavor's rollout could not be read" />;
  if (!data) return null;

  const { version, clusters, running, last_run: run } = data;
  const byState = new Map<RolloutState, RolloutCluster[]>();
  for (const c of clusters) byState.set(c.state, [...(byState.get(c.state) ?? []), c]);
  const counted = ROLLOUT_ORDER.filter((state) => (data.counts[state] ?? 0) > 0);
  const allOn = clusters.length > 0 && clusters.every((c) => c.state === "on_version");
  const nothingToDo = version !== null && clusters.length === 0;

  return (
    <section
      data-testid="rollout-panel"
      data-running={running}
      aria-labelledby="rollout-heading"
      className="bg-card rounded-xl border shadow-sm p-5 space-y-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2 id="rollout-heading" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold">
            <GitPullRequestArrow className="h-4 w-4 text-primary" aria-hidden />
            {version ? <>Rollout of v{version}</> : "Rollout"}
            {running && (
              <span role="status" data-testid="rollout-running" className="inline-flex items-center gap-1 text-xs font-normal text-status-provisioning-fg">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                Opening merge requests…
              </span>
            )}
          </h2>
          {version && (
            <p className="text-xs text-muted-foreground max-w-2xl">
              Each cluster that follows {flavor} on an older version gets its own merge request to v{version}, opened
              on its own. Its customer merges it when ready, and nothing changes on a cluster until its merge request
              merges.
            </p>
          )}
          {run && (
            <p className="text-xs text-muted-foreground" data-testid="rollout-last-run">
              {run.finished_at ? `Last run ${formatDateTime(run.finished_at)}` : `Running since ${formatDateTime(run.started_at)}`},{" "}
              {TRIGGER[run.trigger] ?? run.trigger}: {plural(run.opened, "merge request")} opened
              {run.failed > 0 && <>, {run.failed} failed</>}.
            </p>
          )}
        </div>
        {isAdmin && !nothingToDo && (
          <button
            type="button"
            onClick={() => reconcile.mutate()}
            disabled={reconcile.isPending || running}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", (reconcile.isPending || running) && "animate-spin")} aria-hidden />
            Reconcile now
          </button>
        )}
      </div>

      {Boolean(reconcile.error) && (
        <ProblemList error={reconcile.error} title={writeErrorTitle(reconcile.error, "Reconcile was refused")} />
      )}

      {version === null ? (
        <p className="flex items-start gap-1.5 text-sm text-status-warning-fg" data-testid="rollout-unreadable">
          <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
          The flavor could not be read, so where its clusters stand with it is unknown.
        </p>
      ) : nothingToDo ? (
        <p className="text-sm text-muted-foreground" data-testid="rollout-empty">
          No cluster follows {flavor}, so v{version} has nowhere to roll out. A cluster created from it, or added to
          it, starts on its newest version.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2" data-testid="rollout-counts">
            <span className="text-sm font-medium mr-1">{plural(clusters.length, "cluster")}</span>
            {counted.map((state) => <Count key={state} state={state} count={data.counts[state]} />)}
          </div>
          {allOn && (
            <p className="flex items-center gap-1.5 text-sm font-medium text-status-ready-fg" data-testid="rollout-done">
              <CheckCircle2 className="h-4 w-4" aria-hidden />
              Every cluster that follows {flavor} is on v{version}.
            </p>
          )}
          <div className="space-y-3">
            {ROLLOUT_ORDER.filter((state) => byState.has(state)).map((state) => (
              <Group key={state} state={state} clusters={byState.get(state)!} version={version} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
