"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ChevronRight, MapPinOff, Sprout, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { StatusBadge } from "@/components/clusters/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { clusterHref } from "@/lib/clusters";
import { seedsBySite, strayKvClusters, type SeedWithClusters } from "@/lib/infrastructure";
import { liveStatusToPhase, type LiveStatuses } from "@/lib/live-status";
import { plural } from "@/lib/utils";
import { isKvCluster } from "@/lib/workspaces";
import type { ClusterStatus } from "@/types";
import { Chip, OffConvention, PageHeader, SiteHeading } from "./page-parts";
import { useAllClusters, useMces } from "./use-infrastructure";

/** NodePools that name no zone, or another than the name's: create-vm never places a VM there (ADR-0067). */
function ZoneProblems({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null;
  return (
    <Hint hint={problems.join(" ")} label="Never offered to VM placement" testId="kv-zone-problems">
      <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-[11px] font-medium text-status-warning-fg">
        <MapPinOff aria-hidden className="h-3 w-3" />Zone
      </span>
    </Hint>
  );
}

/** One KV cluster: a row to its page, managed there like any hosted cluster. */
function KvClusterRow({ cluster, status }: { cluster: ClusterStatus; status: LiveStatuses | undefined }) {
  const live = status?.[cluster.name];
  return (
    <li>
      <Link
        href={clusterHref(cluster)}
        data-testid="kv-cluster"
        data-cluster={cluster.name}
        className="group flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 transition-colors hover:bg-muted/50 outline-none focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50"
      >
        {/* On a phone the name takes its own line, the facts the next */}
        <span className="min-w-0 basis-full font-mono text-[13px] font-medium break-all sm:basis-0 sm:flex-1">{cluster.name}</span>
        {!cluster.naming.follows_convention && <OffConvention problems={cluster.naming.problems} />}
        {cluster.problems.length > 0 && (
          <span className="inline-flex items-center gap-1 text-[11px] text-status-error-fg" title={cluster.problems.join(" ")}>
            <TriangleAlert aria-hidden className="h-3 w-3" />Does not parse
          </span>
        )}
        <ZoneProblems problems={cluster.kv?.zone_problems ?? []} />
        {/* Fixed widths from sm up, so each row's version and status line up with the others */}
        <span className="font-mono text-xs text-muted-foreground sm:w-32 sm:text-right">{cluster.mastertag ?? "no mastertag"}</span>
        <span className="flex sm:w-24 sm:justify-end">{live && <StatusBadge phase={liveStatusToPhase(live)} />}</span>
        <ChevronRight aria-hidden className="ml-auto h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none sm:ml-0" />
      </Link>
    </li>
  );
}

function SeedCard({ entry, status }: { entry: SeedWithClusters; status: LiveStatuses | undefined }) {
  const { seed, clusters } = entry;
  return (
    <article className="overflow-hidden rounded-xl border bg-card shadow-sm" data-testid="seed" data-seed={seed.name}>
      <header className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-3">
        <Sprout aria-hidden className="h-4 w-4 shrink-0 text-status-ready" />
        <h3 className="min-w-0 font-mono text-[13px] font-semibold break-all">{seed.name}</h3>
        {seed.zone && <Chip title="Availability zone">{seed.zone}</Chip>}
        {seed.env && <Chip title="Lifecycle">{seed.env}</Chip>}
        <OffConvention problems={seed.naming_problems} testId="seed-off-convention" />
        <span className="ml-auto text-xs text-muted-foreground">
          Hub <span className="font-mono">{seed.hub_version ?? "—"}</span>
        </span>
      </header>
      {clusters.length === 0 ? (
        <p className="px-4 py-3 text-xs text-muted-foreground" data-testid="seed-empty">No KV cluster in its folder yet.</p>
      ) : (
        <ul className="divide-y" aria-label={`${seed.name}: ${plural(clusters.length, "KV cluster")}`}>
          {clusters.map((cluster) => <KvClusterRow key={cluster.name} cluster={cluster} status={status} />)}
        </ul>
      )}
    </article>
  );
}

/** KV clusters named so under a Customer MCE: listed, since create-vm never finds them there. */
function StrayKvClusters({ clusters, status }: { clusters: ClusterStatus[]; status: LiveStatuses | undefined }) {
  if (clusters.length === 0) return null;
  return (
    <section className="space-y-2" aria-label="KV clusters outside a seed" data-testid="stray-kv-clusters">
      <h2 className="text-sm font-semibold">Outside a seed</h2>
      <p className="text-xs text-muted-foreground">
        Named as KV clusters, but not in a seed&apos;s folder: create-vm looks for a zone&apos;s KV clusters in its seed only.
      </p>
      <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-sm">
        {clusters.map((cluster) => <KvClusterRow key={cluster.name} cluster={cluster} status={status} />)}
      </ul>
    </section>
  );
}

function Body() {
  const mces = useMces();
  const clusters = useAllClusters();
  const kv = useMemo(() => (clusters.data ?? []).filter(isKvCluster), [clusters.data]);
  const status = useBulkStatus(kv);
  if (mces.isLoading || clusters.isLoading) {
    return <div className="space-y-3"><Skeleton className="h-5 w-32" /><Skeleton className="h-32 w-full rounded-xl" /></div>;
  }
  if (mces.error) return <ProblemList error={mces.error} title="The seeds could not be read from the day1 repo" />;
  if (clusters.error) return <ProblemList error={clusters.error} title="The KV clusters could not be read from the day1 repo" />;
  const sites = seedsBySite(mces.data ?? [], clusters.data ?? []);
  const stray = strayKvClusters(mces.data ?? [], clusters.data ?? []);
  if (sites.length === 0 && stray.length === 0) {
    return (
      <EmptyState
        icon={Sprout} bordered title="No seeds yet"
        description="A seed is a folder of the day1 repo, sites/<site>/mces/ocp4-<lc>-seed-<site>-<zone>-<id>/; each file in its hostedClusters/ is a KV cluster."
        data-testid="seeds-empty"
      />
    );
  }
  return (
    <div className="space-y-6">
      {sites.map((group) => (
        <section key={group.site} className="space-y-2" aria-label={`Site ${group.site}`} data-testid="seed-site">
          <SiteHeading site={group.site} count={plural(group.items.length, "seed")} />
          <div className="grid gap-4 lg:grid-cols-2">
            {group.items.map((entry) => <SeedCard key={entry.seed.name} entry={entry} status={status.data} />)}
          </div>
        </section>
      ))}
      <StrayKvClusters clusters={stray} status={status.data} />
    </div>
  );
}

/**
 * Seeds & KV Clusters (ADR-0067): each zone's seed, an MCE-level folder of the
 * day1 repo, and the KV clusters in it, whose workers host the tenants' VM
 * workers. A KV cluster opens on the cluster page, managed like any hosted
 * cluster; only its Delete asks for its name.
 */
export function SeedList() {
  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-300">
      <PageHeader
        title="Seeds & KV Clusters"
        subtitle="Each zone's seed and the KV clusters on it, whose workers host the tenants' VMs. A KV cluster is managed like any hosted cluster; deleting one asks for its name, since its VMs go with it."
      />
      <Body />
    </div>
  );
}
