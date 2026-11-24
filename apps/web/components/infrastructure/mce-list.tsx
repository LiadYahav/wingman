"use client";

import { ServerCog, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { customerMcesBySite } from "@/lib/infrastructure";
import { plural } from "@/lib/utils";
import type { Mce } from "@/types";
import { Chip, OffConvention, PageHeader, SiteHeading } from "./page-parts";
import { useMces } from "./use-infrastructure";

const CELL = "px-4 py-2.5 align-middle";

function MceProblems({ mce }: { mce: Mce }) {
  const lines = [
    ...mce.problems,
    ...(mce.stray_files.length > 0
      ? [`${plural(mce.stray_files.length, "file")} in hostedClusters/ that ${mce.stray_files.length === 1 ? "is" : "are"} not a cluster, each a broken Application: ${mce.stray_files.join(", ")}`]
      : []),
  ];
  if (lines.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-[11px] text-status-warning-fg" data-testid="mce-problems">
      {lines.map((line) => (
        <li key={line} className="flex items-start gap-1 break-words">
          <TriangleAlert aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
          {line}
        </li>
      ))}
    </ul>
  );
}

function MceRow({ mce }: { mce: Mce }) {
  return (
    <tr className="border-t" data-testid="mce-row" data-mce={mce.name}>
      <td className={CELL}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[13px] font-medium break-all">{mce.name}</span>
          <OffConvention problems={mce.naming_problems} testId="mce-off-convention" />
        </div>
        <MceProblems mce={mce} />
      </td>
      <td className={CELL}>{mce.env ? <Chip>{mce.env}</Chip> : <span className="text-muted-foreground">—</span>}</td>
      <td className={`${CELL} font-mono text-xs`}>{mce.hub_version ?? <span className="text-muted-foreground">—</span>}</td>
      <td className={`${CELL} font-mono text-xs`}>{mce.default_mastertag ?? <span className="text-muted-foreground">—</span>}</td>
      <td className={`${CELL} text-right tabular-nums font-semibold`}>{mce.cluster_count}</td>
    </tr>
  );
}

function SiteMces({ site, mces }: { site: string; mces: Mce[] }) {
  return (
    <section className="space-y-2" aria-label={`Site ${site}`} data-testid="mce-site" data-site={site}>
      <SiteHeading site={site} count={plural(mces.length, "MCE")} />
      <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
        {/* Fixed columns, so every site's table lines up with the others */}
        <table className="w-full min-w-[640px] table-fixed text-sm">
          <colgroup>
            <col className="w-[42%]" /><col className="w-[10%]" /><col className="w-[18%]" /><col className="w-[18%]" /><col className="w-[12%]" />
          </colgroup>
          <thead className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-2 font-medium">MCE</th>
              <th scope="col" className="px-4 py-2 font-medium">Env</th>
              <th scope="col" className="px-4 py-2 font-medium" title="version.yaml: the hub's own OpenShift version">Hub version</th>
              <th scope="col" className="px-4 py-2 font-medium" title="values.yaml: the mastertag its new hosted clusters start from">Default mastertag</th>
              <th scope="col" className="px-4 py-2 text-right font-medium">Clusters</th>
            </tr>
          </thead>
          <tbody>
            {mces.map((mce) => <MceRow key={mce.name} mce={mce} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Body() {
  const mces = useMces();
  if (mces.isLoading) return <div className="space-y-3"><Skeleton className="h-5 w-32" /><Skeleton className="h-40 w-full rounded-xl" /></div>;
  if (mces.error) return <ProblemList error={mces.error} title="The MCEs could not be read from the day1 repo" />;
  const sites = customerMcesBySite(mces.data ?? []);
  if (sites.length === 0) {
    return (
      <EmptyState
        icon={ServerCog} bordered title="No Customer MCEs"
        description="Each is a folder of the day1 repo, sites/<site>/mces/<mce>/; Wingman lists them and never creates one."
        data-testid="mces-empty"
      />
    );
  }
  return <div className="space-y-6">{sites.map((group) => <SiteMces key={group.site} site={group.site} mces={group.items} />)}</div>;
}

/**
 * Customer MCEs (ADR-0067, ADR-0018): the hubs of the customers' hosted
 * clusters, by site, as the day1 repo's folders say them. Read only: Wingman
 * never creates or changes an MCE. The seeds are on their own page.
 */
export function MceList() {
  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-300">
      <PageHeader
        title="Customer MCEs"
        subtitle="The hubs that host the customers' hosted clusters, by site, read from the day1 repo. Wingman never creates or changes one; placement picks among them for a new cluster."
      />
      <Body />
    </div>
  );
}
