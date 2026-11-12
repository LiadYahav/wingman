"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Boxes, ChevronRight, Layers, Plus, RefreshCw, Search, Tag } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, keyFromParam, newOperatorHref, operatorHref, syncSummary } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { ReadOnlyBadge, ReadOnlyNote } from "@/components/addons/team-access";
import { Breadcrumbs, PageTitle, useOperatorAccess } from "@/components/operators/page-header";
import type { OperatorSummary } from "@/types/day2";

function OperatorRow({ op }: { op: OperatorSummary }) {
  return (
    <li>
      <Link
        href={operatorHref(op.team, op.name)}
        className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-muted/40"
        data-testid={`operator-${op.name}`}
      >
        <span className="flex min-w-0 flex-1 basis-64 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary dark:bg-primary/15">
            <Boxes className="h-4 w-4" />
          </span>
          <span className="min-w-0 space-y-0.5">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold group-hover:text-primary">{op.name}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/8 px-2 py-0.5 font-mono text-[11px] text-primary dark:bg-primary/20">
                <Tag className="h-2.5 w-2.5" aria-hidden />
                {op.target_revision || "HEAD"}
              </span>
              {!op.in_catalog && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground" title={`No operators/${op.name}/: only a fleet default`}>
                  not in the catalog
                </span>
              )}
              {op.warnings > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-[11px] text-status-warning-fg">
                  <AlertTriangle className="h-3 w-3" aria-hidden />
                  {op.warnings} warning{op.warnings === 1 ? "" : "s"}
                </span>
              )}
            </span>
            <span className="block truncate text-xs text-muted-foreground" title={op.repourl || undefined}>
              {op.repourl ? op.repourl.replace(/^https?:\/\//, "") : "no repourl"} · {syncSummary(op.sync)}
            </span>
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1.5 text-xs">
          {op.defaults.map((d) => (
            <span
              key={d.scope}
              className="inline-flex items-center gap-1 rounded-full bg-chart-5/12 px-2 py-0.5 text-chart-5"
              title={`A default on ${d.label}: deployed to ${d.reach}${d.excluded ? `, ${d.excluded} excluded` : ""}`}
            >
              <Layers className="h-3 w-3" aria-hidden />
              {d.label} · {d.reach}
              {d.excluded > 0 && <span className="opacity-80"> · {d.excluded} excluded</span>}
            </span>
          ))}
          {op.ocp_versions.length > 0 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
              {op.ocp_versions.length} OCP pin{op.ocp_versions.length === 1 ? "" : "s"}
            </span>
          )}
          <span className="text-muted-foreground">
            {op.installed_on} add-on{op.installed_on === 1 ? "" : "s"}
          </span>
          <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

/** A team's operators (ADR-0053): its catalog and the fleet defaults built from it. */
export default function TeamOperatorsPage() {
  const params = useParams<{ team: string }>();
  const team = keyFromParam(params.team);
  const [search, setSearch] = useState("");
  const access = useOperatorAccess(team);
  const operators = useQuery<OperatorSummary[]>({
    queryKey: day2Keys.operators(team),
    queryFn: () => api.get<OperatorSummary[]>(day2Api.operators(team)),
    staleTime: 60_000,
  });
  const needle = search.trim().toLowerCase();
  const all = [...(operators.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const shown = all.filter((op) => !needle || op.name.toLowerCase().includes(needle));

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6 lg:p-8">
      <div className="space-y-2">
        <Breadcrumbs items={[{ label: "Operators", href: "/operators" }, { label: team }]} />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <PageTitle>{team}&apos;s operators</PageTitle>
              {access.showReason && <ReadOnlyBadge />}
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {operators.data
                ? `${all.length} operator${all.length === 1 ? "" : "s"} in sigs/${team}: operators/ and the fleet defaults built from it`
                : `The catalog of sigs/${team} and its fleet defaults`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void operators.refetch()}
              disabled={operators.isFetching}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", operators.isFetching && "animate-spin")} />
              Refresh
            </button>
            {access.isAdmin &&
              (access.readOnlyReason ? (
                <button
                  type="button"
                  disabled
                  title={access.readOnlyReason}
                  className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
                >
                  <Plus className="h-3.5 w-3.5" />
                  New operator
                </button>
              ) : (
                <Link href={newOperatorHref(team)} className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}>
                  <Plus className="h-3.5 w-3.5" />
                  New operator
                </Link>
              ))}
          </div>
        </div>
        {access.isAdmin && access.showReason && access.readOnlyReason && <ReadOnlyNote reason={access.readOnlyReason} />}
      </div>

      {all.length > 6 && (
        <div className="relative max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search operators..."
            aria-label="Search operators"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
      )}

      {operators.error ? (
        <ProblemList error={operators.error} title={`${team}'s operators could not be loaded`} />
      ) : operators.isPending ? (
        <div className="space-y-2" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : all.length === 0 ? (
        <EmptyState
          icon={Boxes}
          bordered
          title="No operators yet"
          description={
            <>
              An operator appears here once sigs/{team} has <code>operators/&lt;chart&gt;/</code>
              {access.isAdmin && !access.readOnlyReason ? ": add one with New operator." : "."}
            </>
          }
          data-testid="operators-empty"
        />
      ) : shown.length === 0 ? (
        <NoMatches what="operators" onClear={() => setSearch("")} clearLabel="Clear search" bordered />
      ) : (
        <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-sm" aria-label={`Operators of ${team}`}>
          {shown.map((op) => (
            <OperatorRow key={op.name} op={op} />
          ))}
        </ul>
      )}
    </div>
  );
}
