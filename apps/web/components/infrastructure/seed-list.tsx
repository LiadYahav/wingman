"use client";

import { useMemo } from "react";
import { Sprout } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { seedsBySite, strayKvClusters } from "@/lib/infrastructure";
import type { LiveStatuses } from "@/lib/live-status";
import { plural } from "@/lib/utils";
import { isKvCluster } from "@/lib/workspaces";
import type { ClusterStatus } from "@/types";
import { KvClusterRow } from "./kv-cluster-row";
import { PageHeader, SiteHeading } from "./page-parts";
import { SeedCard } from "./seed-card";
import { useAllClusters, useMces } from "./use-infrastructure";

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
 * workers, in the order create-vm fills them, and Create KV cluster
 * (ADR-0069). A KV cluster opens on the cluster page, managed like any hosted
 * cluster; only its Delete asks for its name.
 */
export function SeedList() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-300">
      <PageHeader
        title="Seeds & KV Clusters"
        subtitle="Each zone's seed and its KV clusters, whose workers host the tenants' VMs, in the order create-vm fills them: oldest first, up to 40 workers each. A KV cluster is managed like any hosted cluster; deleting one asks for its name, since its VMs go with it."
      />
      <Body />
    </div>
  );
}
