"use client";

import Link from "next/link";
import { MapPin } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { clustersBySite, percent, type SiteCount } from "@/lib/overview/clusters";
import { plural } from "@/lib/utils";
import { Bar } from "./bars";
import { CardNote, OverviewCard, RowsSkeleton } from "./overview-card";
import { useOverviewClusters } from "./use-overview";

/** Sites shown; the rest are summed in one line. */
const SITES_SHOWN = 5;

function SiteRow({ site, total }: { site: SiteCount; total: number }) {
  return (
    <Link
      href="/clusters"
      data-testid="overview-site"
      data-site={site.site}
      aria-label={`${site.site}: ${plural(site.count, "cluster")}`}
      className="block rounded-lg px-3 py-2 hover:bg-muted/50 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      <span className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate font-medium">{site.site}</span>
        <span className="shrink-0 font-semibold tabular-nums">{site.count}</span>
      </span>
      <Bar percent={percent(site.count, total)} className="mt-1.5" />
      <span className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground" data-testid="overview-site-mces">
        {site.mces.map((mce) => (
          <span key={mce.mce} className="inline-flex min-w-0 items-baseline gap-1">
            <span className="truncate font-mono">{mce.mce}</span>
            <span className="tabular-nums text-foreground">{mce.count}</span>
          </span>
        ))}
      </span>
    </Link>
  );
}

function SitesBody() {
  const clusters = useOverviewClusters();
  if (clusters.isLoading) return <RowsSkeleton className="h-14" />;
  if (clusters.error) return <CardNote data-testid="overview-sites-failed">The clusters could not be loaded: Cluster Health says why.</CardNote>;
  const list = clusters.data ?? [];
  if (list.length === 0) {
    return <EmptyState icon={MapPin} title="No clusters yet" description="Where they run shows here once the day1 repo has hosted clusters." data-testid="overview-sites-empty" />;
  }
  const sites = clustersBySite(list);
  const hidden = sites.slice(SITES_SHOWN);
  return (
    <div className="-mx-3 space-y-1">
      {sites.slice(0, SITES_SHOWN).map((site) => <SiteRow key={site.site} site={site} total={list.length} />)}
      {hidden.length > 0 && (
        <Link href="/clusters" className="block px-3 pt-1 text-xs text-muted-foreground hover:text-foreground" data-testid="overview-sites-more">
          {plural(hidden.length, "more site")} · {plural(hidden.reduce((n, s) => n + s.count, 0), "cluster")}
        </Link>
      )}
    </div>
  );
}

/** The clusters by site and MCE: the day1 repo's folders each cluster file sits in. */
export function ClustersBySiteCard() {
  return (
    <OverviewCard
      title="Where Clusters Run"
      hint="Clusters per site, from the day1 repo's site and MCE folders; each bar is the site's share of all clusters, and the line below it counts each MCE's."
      href="/clusters"
      data-testid="overview-sites"
    >
      <SitesBody />
    </OverviewCard>
  );
}
