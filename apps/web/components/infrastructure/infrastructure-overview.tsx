"use client";

import Link from "next/link";
import { Boxes, Server, ServerCog, Sprout } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ClustersBySiteCard } from "@/components/overview/clusters-by-site-card";
import { FreeServersCard } from "@/components/overview/free-servers-card";
import { StatCard } from "@/components/overview/stat-cards";
import { isApiError } from "@/lib/api-client";
import { useInventory } from "@/lib/api/inventory";
import { infrastructureCounts } from "@/lib/infrastructure";
import { serverCapacity } from "@/lib/overview/capacity";
import { plural } from "@/lib/utils";
import { PageHeader } from "./page-parts";
import { useAllClusters, useMces } from "./use-infrastructure";

const SECONDARY = buttonVariants({ variant: "outline", size: "sm" });

/** The four numbers: Customer MCEs and their sites, seeds and their zones, KV clusters, free servers. */
function InfrastructureStats() {
  const mces = useMces();
  const clusters = useAllClusters();
  const inventory = useInventory();
  const counts = infrastructureCounts(mces.data ?? [], clusters.data ?? []);
  const off = isApiError(inventory.error, "FEATURE_DISABLED");
  const free = inventory.data ? serverCapacity(inventory.data.mces).free : undefined;
  const failed = (error: unknown) => (error ? "Could not be loaded" : undefined);
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        title="Customer MCEs" value={mces.data ? counts.mces : undefined}
        hint={failed(mces.error) ?? plural(counts.sites, "site")}
        icon={ServerCog} href="/mces" loading={mces.isLoading}
      />
      <StatCard
        title="Seeds" value={mces.data ? counts.seeds : undefined}
        hint={failed(mces.error) ?? plural(counts.zones, "zone")}
        icon={Sprout} href="/seeds" loading={mces.isLoading} color="green"
      />
      <StatCard
        title="KV Clusters" value={clusters.data ? counts.kvClusters : undefined}
        hint={failed(clusters.error) ?? "Hosting the tenants' VMs"}
        icon={Server} href="/seeds" loading={clusters.isLoading}
      />
      <StatCard
        title="Free Servers" value={off ? undefined : free}
        hint={off ? "Not set up here" : failed(inventory.error) ?? "In the MCEs' inventories"}
        icon={Boxes} href="/inventory" loading={inventory.isLoading} color={free === 0 ? "orange" : "blue"}
      />
    </div>
  );
}

/**
 * The Infrastructure workspace's home (ADR-0067): what serves the customers'
 * clusters at a glance. The MCEs and seeds from the day1 repo, the KV
 * clusters, and Inventory Management's free servers; then where the tenants'
 * clusters run and each MCE's free servers, the two cards that name MCEs and
 * so left the Customers Overview.
 */
export function InfrastructureOverview() {
  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      <PageHeader title="Infrastructure" subtitle="The MCEs, seeds and servers behind the customers' clusters">
        <div className="flex flex-wrap items-center gap-2" data-testid="infrastructure-actions">
          <Link href="/inventory" className={SECONDARY}><Boxes aria-hidden />Inventory Management</Link>
        </div>
      </PageHeader>

      <InfrastructureStats />

      <div className="grid gap-4 lg:grid-cols-2" data-testid="infrastructure-sections">
        <ClustersBySiteCard />
        <FreeServersCard />
      </div>
    </div>
  );
}
