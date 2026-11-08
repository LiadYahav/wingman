"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { MapPin, RefreshCw, Search, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { DESTINATION_KINDS, KIND_LABEL, chartsHref, day2Api, day2Keys } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, EmptyStateLink, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { FindingsBadge } from "@/components/addons/findings";
import { KindBadge } from "@/components/addons/destination-header";
import type { Destination, DestinationKind } from "@/types/day2";

function Chips<T extends string>({
  label,
  options,
  value,
  onChange,
  format = (v) => v,
  count,
}: {
  label: string;
  options: readonly T[];
  value: T | "all";
  onChange: (v: T | "all") => void;
  format?: (v: T) => string;
  count?: (v: T) => number;
}) {
  if (options.length === 0) return null;
  const chip = (active: boolean) =>
    cn(
      "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
      active
        ? "border-primary bg-primary text-primary-foreground"
        : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground",
    );
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      <span className="text-xs font-medium text-muted-foreground">{label}:</span>
      <button type="button" onClick={() => onChange("all")} aria-pressed={value === "all"} className={chip(value === "all")}>
        All
      </button>
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(value === o ? "all" : o)}
          aria-pressed={value === o}
          className={chip(value === o)}
        >
          {format(o)}
          {count && <span className="ml-1 tabular-nums opacity-70">{count(o)}</span>}
        </button>
      ))}
    </div>
  );
}

const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort();

/** Every place a team can deploy charts to: the hub, MCEs, hosted clusters and UPI clusters (ADR-0020). */
export default function DestinationsPage() {
  const isAdmin = useIsAdmin();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<DestinationKind | "all">("all");
  const [site, setSite] = useState<string>("all");
  const [env, setEnv] = useState<string>("all");

  const { data, isLoading, isFetching, error, refetch } = useQuery<Destination[]>({
    queryKey: day2Keys.destinations,
    queryFn: () => api.get<Destination[]>(day2Api.destinations),
    staleTime: 60_000,
  });

  const all = data ?? [];
  const needle = search.trim().toLowerCase();
  const rows = all.filter(
    (d) =>
      (kind === "all" || d.kind === kind) &&
      (site === "all" || d.site === site) &&
      (env === "all" || d.env === env) &&
      (!needle || d.id.toLowerCase().includes(needle) || d.teams.some((t) => t.toLowerCase().includes(needle))),
  );
  const filtering = Boolean(needle) || kind !== "all" || site !== "all" || env !== "all";
  const clear = () => {
    setSearch("");
    setKind("all");
    setSite("all");
    setEnv("all");
  };

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6 lg:p-8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Destinations
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {data
              ? `${rows.length} of ${all.length} destination${all.length === 1 ? "" : "s"}${filtering ? " (filtered)" : ""}: where teams deploy charts`
              : "Where teams deploy charts: the hub, MCEs, hosted and UPI clusters"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="relative min-w-48 max-w-sm flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search names, ids or teams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card py-1.5 pl-8 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <Chips
          label="Kind"
          options={DESTINATION_KINDS}
          value={kind}
          onChange={setKind}
          format={(k) => KIND_LABEL[k]}
          count={(k) => all.filter((d) => d.kind === k).length}
        />
        <Chips label="Site" options={unique(all.map((d) => d.site))} value={site} onChange={setSite} />
        <Chips label="Env" options={unique(all.map((d) => d.env))} value={env} onChange={setEnv} />
        {filtering && (
          <button type="button" onClick={clear} className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
            <X className="h-3 w-3" />
            Clear filters
          </button>
        )}
      </div>

      {error ? (
        <ProblemList error={error} title="The destinations could not be loaded" />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="whitespace-nowrap border-b bg-muted/30 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Kind</th>
                <th className="px-4 py-3">Site / Env</th>
                <th className="px-4 py-3">MCE</th>
                <th className="px-4 py-3">OCP</th>
                <th className="px-4 py-3">Teams</th>
                <th className="px-4 py-3">Findings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((d) => (
                    <tr key={d.id} className="transition-colors hover:bg-primary/[0.03]">
                      <td className="max-w-80 px-4 py-2.5">
                        <Link href={chartsHref(d.id)} className="block truncate font-semibold transition-colors hover:text-primary" title={d.name}>
                          {d.name}
                        </Link>
                        <span className="block truncate font-mono text-[11px] text-muted-foreground" title={d.id}>
                          {d.id}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <KindBadge kind={d.kind} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5">
                        <span className="text-foreground">{d.site || "—"}</span>
                        <span className="block text-xs text-muted-foreground">
                          {d.env || (d.kind === "hub" ? "—" : <span className="text-status-warning-fg">env unknown</span>)}
                        </span>
                      </td>
                      <td className="max-w-56 truncate px-4 py-2.5 text-xs text-muted-foreground" title={d.mce}>
                        {d.kind === "hosted" || d.kind === "mce" ? d.mce : "—"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">{d.ocp_version ?? "—"}</td>
                      <td className="max-w-64 px-4 py-2.5 text-xs text-muted-foreground">
                        {d.teams.length === 0 ? (
                          <span title={d.in_day1 ? "In day1, but no team repo places it yet" : undefined}>none yet</span>
                        ) : (
                          <span className="line-clamp-2" title={d.teams.join(", ")}>
                            {d.teams.join(", ")}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <FindingsBadge findings={d.warnings} />
                      </td>
                    </tr>
                  ))}
              {!isLoading && rows.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    {all.length === 0 ? (
                      <EmptyState
                        icon={MapPin}
                        title="No destinations yet"
                        description="Day1 has no clusters and no team repo places one. Every hosted cluster in day1 is a destination."
                        action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
                        data-testid="destinations-empty"
                      />
                    ) : (
                      <NoMatches what="destinations" onClear={clear} />
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
