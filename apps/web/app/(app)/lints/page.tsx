"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, Search, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { bySeverity, chartsHref, day2Api, day2Keys } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { severityTone } from "@/components/addons/findings";
import type { Finding } from "@/types/day2";

const SEVERITIES = ["error", "warning", "info"] as const;

function chip(active: boolean) {
  return cn(
    "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
    active
      ? "border-primary bg-primary text-primary-foreground"
      : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground",
  );
}

/**
 * Every check on the team repos (ADR-0023): render_chain.py's rules, which the
 * platform fails on, plus Wingman's own. An MR that adds an error is refused.
 */
export default function LintsPage() {
  const [search, setSearch] = useState("");
  const [team, setTeam] = useState("all");
  const [severity, setSeverity] = useState("all");

  const { data, isLoading, isFetching, error, refetch } = useQuery<Finding[]>({
    queryKey: day2Keys.lints,
    queryFn: () => api.get<Finding[]>(day2Api.lints()),
    staleTime: 60_000,
  });

  const all = data ?? [];
  const teams = [...new Set(all.map((f) => f.team).filter(Boolean))].sort();
  const needle = search.trim().toLowerCase();
  const rows = all
    .filter(
      (f) =>
        (team === "all" || f.team === team) &&
        (severity === "all" || f.severity === severity) &&
        (!needle ||
          [f.rule, f.message, f.path, f.cluster, f.chart].some((s) => s.toLowerCase().includes(needle))),
    )
    .sort((a, b) => bySeverity(a, b) || a.team.localeCompare(b.team) || a.rule.localeCompare(b.rule));
  const filtering = Boolean(needle) || team !== "all" || severity !== "all";
  const count = (s: string) => all.filter((f) => f.severity === s).length;
  const clear = () => {
    setSearch("");
    setTeam("all");
    setSeverity("all");
  };

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6 lg:p-8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Lints
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {data
              ? `${count("error")} error${count("error") === 1 ? "" : "s"} · ${count("warning")} warning${count("warning") === 1 ? "" : "s"} across the team repos. A change that adds an error is refused.`
              : "Checks on the team repos"}
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
            placeholder="Search rules, messages, paths..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card py-1.5 pl-8 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Severity">
          <span className="text-xs font-medium text-muted-foreground">Severity:</span>
          {(["all", ...SEVERITIES] as const).map((s) => (
            <button key={s} type="button" onClick={() => setSeverity(s)} aria-pressed={severity === s} className={cn(chip(severity === s), "capitalize")}>
              {s}
              {s !== "all" && <span className="ml-1 tabular-nums opacity-70">{count(s)}</span>}
            </button>
          ))}
        </div>
        {teams.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Team">
            <span className="text-xs font-medium text-muted-foreground">Team:</span>
            {["all", ...teams].map((t) => (
              <button key={t} type="button" onClick={() => setTeam(t)} aria-pressed={team === t} className={chip(team === t)}>
                {t === "all" ? "All" : t}
              </button>
            ))}
          </div>
        )}
        {filtering && (
          <button
            type="button"
            onClick={clear}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-3 w-3" />
            Clear filters
          </button>
        )}
      </div>

      {error ? (
        <ProblemList error={error} title="The lints could not be loaded" />
      ) : !isLoading && all.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          tone="success"
          bordered
          title="No findings"
          description="Every team repo passes every check."
          data-testid="lints-empty"
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="w-8 px-4 py-3" aria-label="Severity" />
                <th className="px-4 py-3">Finding</th>
                <th className="px-4 py-3">Team</th>
                <th className="px-4 py-3">Where</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 4 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((f, i) => {
                    const tone = severityTone(f.severity);
                    const Icon = tone.icon;
                    return (
                      <tr key={`${f.rule}|${f.path}|${f.cluster}|${i}`} className="align-top">
                        <td className="px-4 py-3">
                          <Icon className={cn("h-4 w-4", tone.text)} aria-label={tone.label} />
                        </td>
                        <td className="max-w-xl px-4 py-3">
                          <p className="break-words text-sm">{f.message}</p>
                          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{f.rule}</p>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs">{f.team || "—"}</td>
                        <td className="min-w-80 max-w-lg px-4 py-3 text-xs">
                          {f.path && <p className="break-all font-mono text-[11px]">{f.path}</p>}
                          {(f.cluster || f.chart) && (
                            <p className="mt-0.5 text-muted-foreground">
                              {f.chart && <span className="font-medium text-foreground">{f.chart}</span>}
                              {f.chart && f.cluster && " on "}
                              {f.cluster && (
                                <Link href={chartsHref(f.cluster)} className="break-all font-mono text-[11px] hover:text-primary hover:underline">
                                  {f.cluster}
                                </Link>
                              )}
                            </p>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              {!isLoading && rows.length === 0 && all.length > 0 && (
                <tr>
                  <td colSpan={4}>
                    <NoMatches what="findings" onClear={clear} />
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
