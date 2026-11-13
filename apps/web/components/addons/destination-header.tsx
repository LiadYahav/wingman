"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, CheckCircle2, Info } from "lucide-react";
import { api } from "@/lib/api-client";
import { KIND_LABEL, chartsHref, day2Api, day2Keys } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { FindingsList } from "@/components/addons/findings";
import type { Destination, DestinationCharts, DestinationKind, UpgradeCheck } from "@/types/day2";

const KIND_TONE: Record<DestinationKind, string> = {
  hub: "bg-chart-5/12 text-chart-5",
  mce: "bg-status-provisioning/12 text-status-provisioning-fg",
  hosted: "bg-primary/12 text-primary",
  upi: "bg-status-warning/12 text-status-warning-fg",
};

function KindBadge({ kind, className }: { kind: DestinationKind | string; className?: string }) {
  const known = kind in KIND_TONE;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        known ? KIND_TONE[kind as DestinationKind] : "bg-muted text-muted-foreground",
        className,
      )}
    >
      {known ? KIND_LABEL[kind as DestinationKind] : kind}
    </span>
  );
}

/** A destination's name where a list names it: the link to its charts page. */
export function DestinationLink({ id, name, className }: { id: string; name: string; className?: string }) {
  return (
    <Link href={chartsHref(id)} className={cn("font-semibold transition-colors hover:text-primary hover:underline", className)}>
      {name}
    </Link>
  );
}

/** Where a destination sits: kind, site, env, MCE, OCP version and its Argo. */
export function DestinationFacts({ charts, destination }: { charts: DestinationCharts; destination?: Destination }) {
  const facts: [string, string | null][] = [
    ["site", charts.site || null],
    ["env", charts.env || "unknown"],
    ["mce", charts.kind === "hosted" ? charts.mce : null],
    ["OCP", charts.ocp_version],
    ["Argo", destination?.argo ?? null],
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <KindBadge kind={charts.kind} />
      {facts
        .filter(([, v]) => v)
        .map(([k, v]) => (
          <span key={k} className="whitespace-nowrap">
            {k} <span className={cn("font-mono text-foreground", k === "env" && !charts.env && "text-status-warning-fg")}>{v}</span>
          </span>
        ))}
      <span className="min-w-0 break-all font-mono text-[11px] text-muted-foreground/80" title="Destination id">
        {charts.id}
      </span>
    </div>
  );
}

/** That Wingman cannot see ArgoCD: installed means "the platform generates an app", not "it runs". */
export function ArgoNote({ note }: { note: string }) {
  return (
    <p className="flex items-start gap-2 text-xs text-muted-foreground">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      {note}
    </p>
  );
}

/**
 * Which version-pinned charts would silently fall back to the add-on's revision
 * if the destination moved to another OCP version (no `ocp-versions/<to>/`).
 */
export function UpgradeCheckPanel({ clusterId, from }: { clusterId: string; from: string | null }) {
  const [input, setInput] = useState("");
  const [to, setTo] = useState("");
  const check = useQuery<UpgradeCheck>({
    queryKey: day2Keys.upgradeCheck(clusterId, to),
    queryFn: () => api.get<UpgradeCheck>(day2Api.upgradeCheck(clusterId, to)),
    enabled: Boolean(to),
    staleTime: 30_000,
  });
  return (
    <section className="space-y-2 rounded-xl border bg-card p-4">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setTo(input.trim());
        }}
      >
        <ArrowUpCircle className="h-4 w-4 text-muted-foreground" />
        <label htmlFor="upgrade-to" className="text-sm font-medium">
          Upgrade check
        </label>
        <span className="text-xs text-muted-foreground">from {from ?? "unknown"} to</span>
        <input
          id="upgrade-to"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="4.19.3"
          className="h-7 w-28 rounded-md border bg-background px-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="h-7 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          Check
        </button>
      </form>
      {check.isLoading ? (
        <div className="space-y-1.5 py-0.5" aria-busy="true" data-testid="upgrade-check-loading">
          <Skeleton className="h-3.5 w-2/3" />
          <Skeleton className="h-3.5 w-1/2" />
        </div>
      ) : check.error ? (
        <ProblemList error={check.error} title={`The upgrade check to ${to} could not be run`} />
      ) : check.data ? (
        check.data.warnings.length === 0 ? (
          <p className="flex items-center gap-2 text-xs text-status-ready-fg">
            <CheckCircle2 className="h-3.5 w-3.5" />
            No version-pinned chart loses its pin at {check.data.to_version}.
          </p>
        ) : (
          <FindingsList findings={check.data.warnings} showContext />
        )
      ) : (
        <p className="text-xs text-muted-foreground">
          Lists the charts pinned per OCP version that have no <code>ocp-versions/&lt;to&gt;/</code> folder and would
          fall back to the add-on&apos;s revision.
        </p>
      )}
    </section>
  );
}
