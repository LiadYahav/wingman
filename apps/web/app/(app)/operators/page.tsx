"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Boxes, ChevronRight, RefreshCw, Users } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, teamOperatorsHref } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { ReadOnlyBadge, useTeams } from "@/components/addons/team-access";
import { PageTitle } from "@/components/operators/page-header";
import type { CatalogEntry, FleetDefault } from "@/types/day2";

/**
 * Operators: pick a team (ADR-0053). An operator is a chart in a team's
 * catalog (`operators/<op>/`) and the fleet defaults built from it; this page
 * lists the teams, whether Wingman may write to each, and how many operators
 * each has. With one team it goes straight to that team's operators.
 */
export default function OperatorsPage() {
  const router = useRouter();
  const teams = useTeams();
  const catalog = useQuery<CatalogEntry[]>({
    queryKey: day2Keys.catalog,
    queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
    staleTime: 120_000,
  });
  const fleet = useQuery<FleetDefault[]>({
    queryKey: day2Keys.fleetDefaults,
    queryFn: () => api.get<FleetDefault[]>(day2Api.fleetDefaults()),
    staleTime: 120_000,
  });

  const only = teams.data?.length === 1 ? teams.data[0].name : null;
  useEffect(() => {
    if (only) router.replace(teamOperatorsHref(only));
  }, [only, router]);

  // One per operators/<op>/ folder, plus one per fleet default whose chart is not in the catalog.
  const counts = new Map<string, Set<string>>();
  for (const e of catalog.data ?? []) counts.set(e.team, (counts.get(e.team) ?? new Set()).add(e.name));
  for (const fd of fleet.data ?? []) counts.set(fd.team, (counts.get(fd.team) ?? new Set()).add(fd.chart));
  const defaultsOf = (team: string) => (fleet.data ?? []).filter((fd) => fd.team === team).length;
  const countsKnown = Boolean(catalog.data && fleet.data);
  const list = [...(teams.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6 lg:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <PageTitle>Operators</PageTitle>
          <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
            A team&apos;s operators are the charts in its catalog (<code>operators/</code>) and the fleet defaults built from
            them: which hosted clusters, MCEs, hub or UPI clusters get each one, and with which values. On one cluster, the
            same chart is an add-on, managed from the cluster&apos;s page.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void teams.refetch();
            void catalog.refetch();
            void fleet.refetch();
          }}
          disabled={teams.isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", teams.isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {(catalog.error || fleet.error) && !teams.error && (
        <ProblemList error={catalog.error ?? fleet.error} title="The operator counts could not be loaded" />
      )}

      {teams.error ? (
        <ProblemList error={teams.error} title="The teams could not be loaded" />
      ) : teams.isPending || only ? (
        <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={Users}
          bordered
          title="No teams yet"
          description="A team appears here once it has a project under the sigs group."
          data-testid="operators-no-teams"
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2" aria-label="Teams">
          {list.map((team) => {
            const count = counts.get(team.name)?.size ?? 0;
            const defaults = defaultsOf(team.name);
            const readOnly = !team.writable || team.access_role === "unknown";
            return (
              <li key={team.name}>
                <Link
                  href={teamOperatorsHref(team.name)}
                  className="group flex items-start gap-3 rounded-xl border bg-card p-4 shadow-sm transition-[box-shadow,border-color] duration-150 hover:border-primary/30 hover:shadow-md"
                  data-testid={`operators-team-${team.name}`}
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary dark:bg-primary/15">
                    <Boxes className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold group-hover:text-primary">{team.name}</span>
                      {readOnly && <ReadOnlyBadge />}
                    </span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">{team.path_with_namespace}</span>
                    <span className="block text-xs text-muted-foreground" data-testid="operator-count">
                      {countsKnown
                        ? `${count} operator${count === 1 ? "" : "s"}${defaults ? ` · ${defaults} fleet default${defaults === 1 ? "" : "s"}` : ""}`
                        : "…"}
                    </span>
                  </span>
                  <ChevronRight className="mt-2 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
