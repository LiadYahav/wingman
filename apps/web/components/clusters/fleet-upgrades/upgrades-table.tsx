"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/data-table/data-table";
import { useDataTable } from "@/components/data-table/use-data-table";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { brief, fleetTone, stateWord, upgradeHref, type FleetTone } from "@/lib/fleet-upgrades";
import { humanize } from "@/lib/nodes";
import { updatedAgo } from "@/lib/segments/sites";
import { cn } from "@/lib/utils";
import type { FleetUpgrade } from "@/types";

const TONE: Record<FleetTone, string> = {
  open: "bg-status-provisioning/12 text-status-provisioning-fg",
  done: "bg-status-ready/15 text-status-ready-fg",
  stopped: "bg-muted text-muted-foreground",
  failed: "bg-status-error/12 text-status-error-fg",
};

const NO_VISIBILITY = {};
const keepVisibility = () => {};

function Cluster({ run }: { run: FleetUpgrade }) {
  return (
    <span className="block min-w-0">
      <Link href={upgradeHref(run)} className="block truncate font-semibold hover:text-primary" title={run.cluster}>
        {run.cluster}
      </Link>
      {run.mce ? (
        <span className="block text-xs text-muted-foreground">{run.mce}</span>
      ) : (
        <Hint hint="The orchestrator upgrades a cluster this Wingman's day1 repo has no file for (or several)." label="Not in this day1 repo">
          <span className="text-xs text-status-warning-fg">not in this day1 repo</span>
        </Hint>
      )}
    </span>
  );
}

function State({ run }: { run: FleetUpgrade }) {
  const word = stateWord(run);
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span className={cn("rounded-full px-2 py-px text-xs font-medium", TONE[fleetTone(run)])} data-testid="fleet-upgrade-status">
        {run.status}
      </span>
      {word && word !== run.status && (
        <span className="text-xs text-muted-foreground" data-testid="fleet-upgrade-phase" title={word}>
          {humanize(word)}
        </span>
      )}
    </span>
  );
}

function WaitingFor({ text }: { text: string | null }) {
  if (!text) return <span className="text-muted-foreground">—</span>;
  const short = brief(text);
  if (short === text) return <span className="text-xs" data-testid="fleet-upgrade-waiting">{text}</span>;
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} />} className="cursor-help text-xs" data-testid="fleet-upgrade-waiting">
        {short}
      </TooltipTrigger>
      <TooltipContent className="max-w-md">{text}</TooltipContent>
    </Tooltip>
  );
}

function Started({ at, now }: { at: string | null; now: number }) {
  if (!at) return <span className="text-muted-foreground">—</span>;
  const then = Date.parse(at);
  return (
    <span className="whitespace-nowrap text-xs tabular-nums" title={at}>
      {updatedAgo(then, Math.max(now, then))}
    </span>
  );
}

const column = createColumnHelper<FleetUpgrade>();

function columns(now: number): ColumnDef<FleetUpgrade, never>[] {
  return [
    column.display({ id: "cluster", header: "Cluster", meta: { label: "Cluster", className: "max-w-[22rem]" }, cell: (c) => <Cluster run={c.row.original} /> }),
    column.display({ id: "state", header: "Status", meta: { label: "Status" }, cell: (c) => <State run={c.row.original} /> }),
    column.display({
      id: "waiting",
      header: "Waiting for",
      meta: { label: "Waiting for", className: "max-w-md" },
      cell: (c) => <WaitingFor text={c.row.original.waiting_for} />,
    }),
    column.display({ id: "started", header: "Started", meta: { label: "Started" }, cell: (c) => <Started at={c.row.original.started_at} now={now} /> }),
  ] as ColumnDef<FleetUpgrade, never>[];
}

/** Every cluster's newest upgrade run, open ones first; each row links to its cluster's page. */
export function UpgradesTable({ runs }: { runs: FleetUpgrade[] }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, []);
  const table = useDataTable({
    data: runs,
    columns: columns(now),
    getRowId: (run) => run.workflow_id,
    columnVisibility: NO_VISIBILITY,
    onColumnVisibilityChange: keepVisibility,
  });
  return (
    <DataTable
      table={table}
      label="Upgrade runs"
      sort={null}
      rowProps={(run) => ({ "data-testid": "fleet-upgrade-row", "data-cluster": run.cluster })}
      empty={
        <EmptyState
          title="No upgrade runs"
          description="The orchestrator lists none. An admin starts one with Upgrade on a cluster's Mastertag row."
          data-testid="fleet-upgrades-empty"
        />
      }
    />
  );
}
