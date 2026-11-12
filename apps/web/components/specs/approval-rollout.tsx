"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GitPullRequestArrow, Package, RotateCw, TriangleAlert, Unplug } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { rollText } from "@/components/clusters/sync-dialog";
import { api } from "@/lib/api-client";
import { clusterHref } from "@/lib/clusters";
import { cn } from "@/lib/utils";
import type { ApprovalRollout, RolloutClusterRef } from "@/types";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "Merging opens 12 cluster merge requests". */
export function opensText(r: ApprovalRollout): string {
  return `Merging opens ${r.opens === 0 ? "no" : r.opens} cluster merge request${r.opens === 1 ? "" : "s"}`;
}

/**
 * `GET /approvals/{iid}/rollout?repo=specs`: what merging a flavor MR opens
 * (ADR-0044). Read for an open specs MR only, at the head on the page, and
 * never again in the background: it describes what this review merges.
 */
export function useApprovalRollout(id: string, iid: number, sha: string | undefined, enabled: boolean) {
  return useQuery<ApprovalRollout>({
    // Under the detail's key: a change elsewhere does not read it again, a reload of the MR does
    queryKey: ["approvals", "detail", id, "rollout", sha],
    queryFn: () => api.get<ApprovalRollout>(`/api/day1/approvals/${iid}/rollout?repo=specs`),
    enabled: enabled && Boolean(sha),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
}

function Section({
  title,
  icon: Icon,
  tone = "neutral",
  note,
  testId,
  children,
}: {
  title: string;
  icon: typeof RotateCw;
  tone?: "neutral" | "warning";
  note?: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      aria-label={title}
      className={cn("rounded-lg border p-3.5 space-y-2", tone === "warning" ? "border-status-warning/30 bg-status-warning/5" : "bg-muted/20")}
    >
      <h3
        className={cn(
          "flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide",
          tone === "warning" ? "text-status-warning-fg" : "text-muted-foreground"
        )}
      >
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {title}
      </h3>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      {children}
    </section>
  );
}

function ClusterName({ cluster: c }: { cluster: RolloutClusterRef }) {
  return (
    <p className="text-sm">
      <Link href={clusterHref(c)} className="font-semibold hover:text-primary transition-colors break-all">
        {c.name}
      </Link>
      <span className="text-xs text-muted-foreground break-all"> · {c.site} / {c.mce}</span>
    </p>
  );
}

/**
 * Before a flavor MR merges: the cluster MRs merging it opens, the clusters
 * whose nodes roll and how, the ones that lose configs, the ones that need a
 * decision, and the add-ons the version adds. Nothing when the MR gives no
 * existing flavor a new version (`applies: false`).
 */
export function ApprovalRolloutPanel({
  rollout,
  isLoading,
  error,
}: {
  rollout: ApprovalRollout | undefined;
  isLoading: boolean;
  error: unknown;
}) {
  if (isLoading) {
    return (
      <div className="bg-card rounded-xl border shadow-sm p-5 space-y-3" data-testid="approval-rollout-loading">
        <Skeleton className="h-4 w-56" />
        <Skeleton className="h-3 w-full max-w-xl" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
    );
  }
  if (error) return <ProblemList error={error} title="What merging this flavor MR opens could not be read" />;
  if (!rollout || !rollout.applies) return null;
  const r = rollout;

  return (
    <section data-testid="approval-rollout" aria-labelledby="approval-rollout-heading" className="bg-card rounded-xl border shadow-sm p-5 space-y-4">
      <div className="space-y-1.5">
        <h2 id="approval-rollout-heading" className="flex items-center gap-2 text-sm font-semibold">
          <GitPullRequestArrow className="h-4 w-4 text-primary" aria-hidden />
          <span data-testid="approval-rollout-opens">{opensText(r)}</span>
          <span className="font-normal text-muted-foreground" data-testid="approval-rollout-following">
            · {plural(r.following, "cluster")} follow{r.following === 1 ? "s" : ""} {r.spec_name}
            {r.already_on_version > 0 && <>, {r.already_on_version} already on v{r.version}</>}
          </span>
        </h2>
        <p className="text-xs text-muted-foreground max-w-3xl">
          This merge request moves {r.spec_name}
          {r.current_version && <> from v{r.current_version}</>} to v{r.version}. Merging it is the one confirmation:
          each cluster then gets its own merge request, which repeats what it does to that cluster, and its customer
          merges it when ready. Nothing changes on a cluster until its own merge request merges.
        </p>
      </div>

      {r.rolls_nodes.length > 0 && (
        <Section
          title={`Roll nodes when their merge request merges (${r.rolls_nodes.length})`}
          icon={RotateCw}
          tone="warning"
          note="OpenShift applies changed machine configs by rolling a nodepool's nodes."
          testId="approval-rollout-rolls"
        >
          <ul className="divide-y">
            {r.rolls_nodes.map((c) => (
              <li key={`${c.site}/${c.mce}/${c.name}`} className="py-2 space-y-1" data-testid={`approval-rollout-rolls-${c.name}`}>
                <ClusterName cluster={c} />
                <ul className="space-y-0.5 text-xs">
                  {c.nodepools.map((np) => (
                    <li key={np.name} data-replaces={np.replaces_nodes}>
                      <span className="font-medium break-all">{np.name}</span>: {rollText(np)}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {r.removes_configs.length > 0 && (
        <Section
          title={`Lose machine configs (${r.removes_configs.length})`}
          icon={Unplug}
          tone="warning"
          note="The version's configs are exact, so a config it does not list is removed from the nodepool."
          testId="approval-rollout-removes"
        >
          <ul className="divide-y">
            {r.removes_configs.map((c) => (
              <li key={`${c.site}/${c.mce}/${c.name}`} className="py-2 space-y-1" data-testid={`approval-rollout-removes-${c.name}`}>
                <ClusterName cluster={c} />
                <ul className="space-y-0.5 text-xs">
                  {c.removals.map((x) => (
                    <li key={`${x.nodepool}/${x.name}`}>
                      Removes <span className="font-mono font-medium">{x.name}</span> from nodepool{" "}
                      <span className="break-all">{x.nodepool}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {r.needs_decision.length > 0 && (
        <Section
          title={`Need a decision (${r.needs_decision.length})`}
          icon={TriangleAlert}
          tone="warning"
          note="No merge request opens for these: a person syncs each by hand from its cluster page."
          testId="approval-rollout-decisions"
        >
          <ul className="divide-y">
            {r.needs_decision.map((c) => (
              <li key={`${c.site}/${c.mce}/${c.name}`} className="py-2 space-y-1" data-testid={`approval-rollout-decision-${c.name}`}>
                <ClusterName cluster={c} />
                <ul className="list-disc pl-4 space-y-0.5 text-xs text-status-warning-fg">
                  {c.reasons.map((reason, i) => <li key={i} className="break-words">{reason}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {r.adds_addons.length > 0 && (
        <Section
          title={`Add-ons v${r.version} adds (${r.adds_addons.length})`}
          icon={Package}
          note="Where a cluster does not have one, day2's install merge requests open first, one per team, and its merge request links them."
          testId="approval-rollout-addons"
        >
          <ul className="flex flex-wrap gap-1.5">
            {r.adds_addons.map((a) => (
              <li key={a} className="rounded-md border bg-background px-2 py-0.5 font-mono text-xs">{a}</li>
            ))}
          </ul>
        </Section>
      )}
    </section>
  );
}
