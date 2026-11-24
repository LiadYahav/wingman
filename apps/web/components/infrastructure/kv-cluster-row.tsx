"use client";

import Link from "next/link";
import { ChevronRight, MapPinOff, TriangleAlert } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { StatusBadge } from "@/components/clusters/status-badge";
import { clusterHref } from "@/lib/clusters";
import { FILL_LABELS, ordinal, type FillEntry } from "@/lib/kv-clusters";
import { liveStatusToPhase, type LiveStatuses } from "@/lib/live-status";
import { cn } from "@/lib/utils";
import type { ClusterStatus } from "@/types";
import { OffConvention } from "./page-parts";

/** NodePools that name no zone, or another than the name's: create-vm never places a VM there (ADR-0067). */
function ZoneProblems({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null;
  return (
    <Hint hint={problems.join(" ")} label="Never offered to VM placement" testId="kv-zone-problems">
      <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-[11px] font-medium text-status-warning-fg">
        <MapPinOff aria-hidden className="h-3 w-3" />Zone
      </span>
    </Hint>
  );
}

const FILL_TONE = {
  full: "bg-muted text-muted-foreground",
  filling: "bg-status-provisioning/12 text-status-provisioning-fg",
  next: "bg-status-ready/12 text-status-ready-fg",
} as const;

/** Its place in the zone's fill order and what it is there: Full, Filling or Next (ADR-0069). */
function FillPlace({ entry }: { entry: FillEntry }) {
  const { label, hint } = FILL_LABELS[entry.state];
  return (
    <span className="inline-flex items-center gap-1.5" data-testid="kv-fill" data-state={entry.state} data-place={entry.place}>
      <span className="w-8 text-right font-mono text-[11px] text-muted-foreground" title="Its place in the fill order: the 1st fills first">
        {ordinal(entry.place)}
      </span>
      <Hint hint={hint} label={`${label}: what it is in the fill order`}>
        <span className={cn("inline-block min-w-14 rounded-full px-2 py-0.5 text-center text-[11px] font-medium", FILL_TONE[entry.state])}>{label}</span>
      </Hint>
    </span>
  );
}

/** Its workers against the most a KV cluster holds, as a small bar. */
function WorkersBar({ workers, max }: { workers: number; max: number }) {
  const share = Math.min(1, workers / Math.max(1, max));
  return (
    <span className="inline-flex items-center gap-2" data-testid="kv-workers">
      <span
        role="meter" aria-label="Workers" aria-valuemin={0} aria-valuemax={max} aria-valuenow={workers}
        className="h-1.5 w-16 overflow-hidden rounded-full bg-muted"
      >
        <span className={cn("block h-full rounded-full", share >= 1 ? "bg-muted-foreground" : "bg-status-ready")} style={{ width: `${share * 100}%` }} />
      </span>
      <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{workers}/{max}</span>
    </span>
  );
}

/**
 * One KV cluster: a row to its page, managed there like any hosted cluster.
 * In a zone's fill order it shows its place, its state and its workers.
 */
export function KvClusterRow({ cluster, status, entry }: { cluster: ClusterStatus; status: LiveStatuses | undefined; entry?: FillEntry }) {
  const live = status?.[cluster.name];
  return (
    <li>
      <Link
        href={clusterHref(cluster)}
        data-testid="kv-cluster"
        data-cluster={cluster.name}
        className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-2.5 transition-colors hover:bg-muted/50 outline-none focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50"
      >
        {/* Two lines in three columns: its place, then its name and marks over its workers and version, then its status */}
        <span className="row-span-2 self-start pt-0.5">{entry && <FillPlace entry={entry} />}</span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="min-w-0 font-mono text-[13px] font-medium break-all">{cluster.name}</span>
          {!cluster.naming.follows_convention && <OffConvention problems={cluster.naming.problems} />}
          {cluster.problems.length > 0 && (
            <span className="inline-flex items-center gap-1 text-[11px] text-status-error-fg" title={cluster.problems.join(" ")}>
              <TriangleAlert aria-hidden className="h-3 w-3" />Does not parse
            </span>
          )}
          <ZoneProblems problems={cluster.kv?.zone_problems ?? []} />
        </span>
        <span className="row-span-2 flex items-center gap-2">
          {live && <StatusBadge phase={liveStatusToPhase(live)} />}
          <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          {cluster.kv && <WorkersBar workers={cluster.kv.workers} max={cluster.kv.max_workers} />}
          <span className="font-mono text-xs text-muted-foreground">{cluster.mastertag ?? "no mastertag"}</span>
        </span>
      </Link>
    </li>
  );
}
