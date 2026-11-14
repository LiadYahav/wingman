"use client";

import { useEffect, useState } from "react";
import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/data-table/data-table";
import { useDataTable } from "@/components/data-table/use-data-table";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ServerLink } from "@/components/server-scan/server-link";
import { useServerScanArea } from "@/lib/api/server-scan";
import { originHint, originLabel, readablePhase, runSubject, runTone, type RunTone } from "@/lib/inventory/runs";
import { updatedAgo } from "@/lib/segments/sites";
import { cn } from "@/lib/utils";
import type { InventoryRun } from "@/types/inventory";

const TONE: Record<RunTone, string> = {
  running: "bg-primary/12 text-primary",
  completed: "bg-status-ready/15 text-status-ready-fg",
  failed: "bg-status-error/12 text-status-error",
  other: "bg-muted text-muted-foreground",
};

const NO_VISIBILITY = {};
const keepVisibility = () => {};

function Started({ run, now }: { run: InventoryRun; now: number }) {
  if (!run.started_at) return <span className="text-muted-foreground">—</span>;
  const at = Date.parse(run.started_at);
  return (
    <span className="whitespace-nowrap text-xs tabular-nums" title={run.started_at}>
      {updatedAgo(at, Math.max(now, at))}
    </span>
  );
}

function Origin({ run }: { run: InventoryRun }) {
  return (
    <Hint hint={originHint(run.origin)} label={`${originLabel(run.origin)}: why`}>
      <span
        data-testid="run-origin"
        className={cn(
          "whitespace-nowrap rounded-full px-2 py-px text-xs",
          run.origin === "named" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
        )}
      >
        {originLabel(run.origin)}
      </span>
    </Hint>
  );
}

function Status({ run }: { run: InventoryRun }) {
  const phase = readablePhase(run.phase, run.status);
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span className={cn("rounded-full px-2 py-px text-xs font-medium", TONE[runTone(run.status)])}>{run.status}</span>
      {phase && <span className="text-xs text-muted-foreground">{phase}</span>}
    </span>
  );
}

/** The run's server: a link to its page in the Server Scan area when `linked` and server-scan names it, else text. */
function Server({ run, linked }: { run: InventoryRun; linked: boolean }) {
  const subject = runSubject(run);
  if (linked && run.server_id) {
    return (
      <ServerLink id={run.server_id} className="font-mono text-xs">
        {subject}
      </ServerLink>
    );
  }
  return <span className="font-mono text-xs">{subject}</span>;
}

const column = createColumnHelper<InventoryRun>();

function runColumns(now: number, linked: boolean): ColumnDef<InventoryRun, never>[] {
  return [
    column.display({ id: "started", header: "Started", meta: { label: "Started" }, cell: (c) => <Started run={c.row.original} now={now} /> }),
    column.display({ id: "origin", header: "Who", meta: { label: "Who" }, cell: (c) => <Origin run={c.row.original} /> }),
    column.display({
      id: "pool",
      header: "Pool",
      meta: { label: "Pool" },
      cell: (c) => (
        <span className="block min-w-0">
          <span className="block font-mono text-xs">{c.row.original.infra_env ?? "—"}</span>
          <span className="block font-mono text-[11px] text-muted-foreground">{c.row.original.mce ?? c.row.original.workflow_id}</span>
        </span>
      ),
    }),
    column.display({
      id: "server",
      header: "Server",
      meta: { label: "Server" },
      cell: (c) => <Server run={c.row.original} linked={linked} />,
    }),
    column.display({ id: "status", header: "Status", meta: { label: "Status" }, cell: (c) => <Status run={c.row.original} /> }),
    column.display({
      id: "error",
      header: "Error",
      meta: { label: "Error", className: "max-w-xs" },
      cell: (c) =>
        c.row.original.error ? (
          <span className="block truncate text-xs text-status-error" title={c.row.original.error}>
            {c.row.original.error}
          </span>
        ) : null,
    }),
  ] as ColumnDef<InventoryRun, never>[];
}

/**
 * The add-server runs, newest first, as the orchestrator lists them. A run's
 * server links to its page for whoever has the Server Scan area.
 */
export function RunsTable({ runs }: { runs: InventoryRun[] }) {
  const linked = useServerScanArea() === true;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);
  const table = useDataTable({
    data: runs,
    columns: runColumns(now, linked),
    getRowId: (run) => `${run.workflow_id}@${run.started_at ?? ""}`,
    columnVisibility: NO_VISIBILITY,
    onColumnVisibilityChange: keepVisibility,
  });
  return (
    <DataTable
      table={table}
      label="Add-server runs"
      sort={null}
      rowProps={(run) => ({ "data-testid": "run-row", "data-workflow": run.workflow_id })}
      empty={<EmptyState title="No add-server runs" description="Neither herzi nor a person has added servers lately." />}
    />
  );
}
