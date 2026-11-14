"use client";

import Link from "next/link";
import { ServerCog } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { useServerScanSites } from "@/lib/api/server-scan";
import { fleetHealth, type HealthCount, type HealthRow } from "@/lib/overview/fleet-health";
import { serversHref } from "@/lib/server-scan/servers-view";
import { cn, plural } from "@/lib/utils";
import type { HealthSeverity } from "@/types/server-scan";
import { SegmentedBar } from "./bars";
import { OverviewCard, RowsSkeleton } from "./overview-card";

/** Sites shown; the Sites page has every one. */
const SITES_SHOWN = 8;

/** Each count's tone; the glyph and the word tell them apart first (server-scan's rule), as on the Sites page. */
const TONE: Record<HealthCount["kind"], string> = {
  healthy: "text-status-ready-fg",
  critical: "text-status-error-fg",
  major: "text-status-error-fg",
  warning: "text-status-warning-fg",
  maintenance: "text-status-provisioning-fg",
  unknown: "text-muted-foreground",
};

const FILL: Record<HealthSeverity, string> = {
  HEALTHY: "bg-status-ready",
  WARNING: "bg-status-warning",
  MAJOR: "bg-status-error/60",
  CRITICAL: "bg-status-error",
  UNKNOWN: "bg-muted-foreground/30",
};

const LINK = "rounded-sm outline-none underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring/50";

function Counts({ row }: { row: HealthRow }) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" data-testid="overview-health-counts">
      {row.counts.map((count) => (
        <Link key={count.kind} href={serversHref(count.filter)} data-kind={count.kind} data-filter={count.filter}
          className={cn(LINK, "inline-flex items-center gap-1 font-medium", TONE[count.kind])}>
          <span aria-hidden>{count.glyph}</span>
          <span><span className="tabular-nums">{count.count}</span> {count.word}</span>
        </Link>
      ))}
      {row.total === 0 && <span className="text-muted-foreground">no servers</span>}
    </span>
  );
}

function SiteRow({ row }: { row: HealthRow }) {
  return (
    <li className="grid gap-1.5 py-2 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)] sm:items-center sm:gap-x-6" data-testid="overview-health-site" data-site={row.key}>
      <span className="flex min-w-0 items-baseline justify-between gap-2">
        <Link href={serversHref(row.filter)} className={cn(LINK, "truncate text-sm font-medium")}>{row.name}</Link>
        <span className="shrink-0 text-sm font-semibold tabular-nums" title={plural(row.total, "server")}>{row.total}</span>
      </span>
      <span className="space-y-1.5">
        <SegmentedBar parts={row.parts.map((p) => ({ key: p.severity, count: p.count, fill: FILL[p.severity] }))} />
        <Counts row={row} />
      </span>
    </li>
  );
}

function HealthBody() {
  const sites = useServerScanSites();
  if (sites.isLoading) return <RowsSkeleton rows={4} className="h-10" />;
  if (!sites.data) return <ProblemList error={sites.error} title="server-scan's sites could not be read" />;
  const health = fleetHealth(sites.data);
  if (health.fleet.total === 0) {
    return <EmptyState icon={ServerCog} title="No servers yet" description="server-scan has not collected a server." data-testid="overview-health-empty" />;
  }
  const hidden = health.sites.length - SITES_SHOWN;
  return (
    <>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1" data-testid="overview-health-fleet">
        <p className="text-xs text-muted-foreground">
          <span className="mr-1 text-2xl font-semibold tabular-nums text-foreground">{health.fleet.total.toLocaleString()}</span>
          servers across {plural(health.siteCount, "site")}
        </p>
        <Counts row={health.fleet} />
      </div>
      <ul className="divide-y">
        {health.sites.slice(0, SITES_SHOWN).map((row) => <SiteRow key={row.key} row={row} />)}
      </ul>
      {hidden > 0 && (
        <Link href="/server-scan" className="mt-1 block text-xs text-muted-foreground hover:text-foreground">{plural(hidden, "more site")}</Link>
      )}
    </>
  );
}

/**
 * server-scan's fleet health by site, every count opening the Servers page
 * with its filter. Shown only to people with the Server Scan area (admins,
 * server-scan set up): the page mounts it then, so nobody else asks.
 */
export function FleetHealthCard() {
  return (
    <OverviewCard
      title="Server Fleet Health"
      hint="server-scan's servers per site by their overall health (its health policies' verdict), and those in maintenance. The bar splits the site's servers by health; each count opens the Servers page filtered to it."
      href="/server-scan"
      linkLabel="Sites"
      data-testid="overview-health"
    >
      <HealthBody />
    </OverviewCard>
  );
}
