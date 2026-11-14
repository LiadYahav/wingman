"use client";

import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/data-table/copy-cell";
import { columnText } from "@/lib/server-scan/servers-model";
import type { ServerRow } from "@/types/server-scan-servers";
import { InstallationCell, StateCell } from "./server-badges";
import { ServerLink } from "./server-link";

/**
 * The Servers table's columns, server-scan's own in its order and words
 * (team-redbull/server-scan at 92146d3, `frontend/src/features/inventory/InventoryTable.tsx`,
 * decision 18): Name (a link to the server's page), BMC, Installation, MCE
 * (only when a row on the page has one), Cluster, Model, State, then
 * Maintenance. Name, Installation, MCE,
 * Cluster, Model and State sort; Model also has Wingman's value filter, the
 * one column server-scan cannot filter.
 */

const Empty = () => <span className="text-muted-foreground">—</span>;

/**
 * Opens the BMC's own web console in a new tab (`https://`, the one scheme
 * every vendor's BMC serves); nothing for a server whose BMC host was not read.
 */
function BmcLink({ row }: { row: ServerRow }) {
  if (!row.bmc_host) return null;
  const label = `Open BMC console for ${row.name}`;
  return (
    <a
      href={`https://${row.bmc_host}`}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      aria-label={label}
      className="inline-flex h-6 w-6 items-center justify-center rounded-md border text-muted-foreground outline-none transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      <ExternalLink aria-hidden className="h-3.5 w-3.5" />
    </a>
  );
}

function ClusterCell({ row }: { row: ServerRow }) {
  if (!row.cluster_name && !row.contested_with) return <Empty />;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {row.cluster_name ?? <Empty />}
      {row.contested_with && (
        <span
          title="Claimed by two OpenShift clusters at once: one physical server in two memberships"
          className="inline-flex whitespace-nowrap rounded-full bg-status-warning/15 px-2 py-px text-xs font-medium text-status-warning-fg"
        >
          Contested with {row.contested_with}
        </span>
      )}
    </span>
  );
}

/**
 * server-scan keeps every cell on one line, so a row is one line high, and
 * pads its cells as tightly (`px-2`): the fleet's eight columns then fit beside
 * the cluster sidebar on a 1920-pixel screen.
 */
const NOWRAP = "whitespace-nowrap px-2";

const column = createColumnHelper<ServerRow>();
const muted = (value: string | null) => (value ? <span className="text-muted-foreground">{value}</span> : <Empty />);

/** The name, a link to the server's page (remembering this view for its "← Servers"), and a copy button on hover. */
function NameCell({ row }: { row: ServerRow }) {
  return (
    <span className="group inline-flex items-center gap-0.5">
      <ServerLink id={row.id} fromServers className="font-medium">
        {row.name}
      </ServerLink>
      <CopyButton value={row.name} label="server name" reveal />
    </span>
  );
}

/** The columns. `trailing` are the columns after State (the maintenance toggle). */
export function serverColumns(withMce: boolean, trailing: ColumnDef<ServerRow, never>[] = []): ColumnDef<ServerRow, never>[] {
  const columns = [
    column.accessor("name", {
      header: "Name",
      meta: { label: "Name", className: NOWRAP },
      cell: (c) => <NameCell row={c.row.original} />,
    }),
    column.display({ id: "bmc", header: "BMC", meta: { label: "BMC", className: NOWRAP }, cell: (c) => <BmcLink row={c.row.original} /> }),
    column.accessor("openshift_state", {
      header: "Installation",
      meta: { label: "Installation", className: NOWRAP },
      cell: (c) => <InstallationCell row={c.row.original} />,
    }),
    ...(withMce ? [column.accessor("mce_name", { header: "MCE", meta: { label: "MCE", className: NOWRAP }, cell: (c) => muted(c.getValue()) })] : []),
    column.accessor("cluster_name", { header: "Cluster", meta: { label: "Cluster", className: NOWRAP }, cell: (c) => <ClusterCell row={c.row.original} /> }),
    column.accessor("model", {
      header: "Model",
      meta: { label: "Model", className: NOWRAP, filterValue: (row: ServerRow) => columnText(row, "model") },
      cell: (c) => muted(c.getValue()),
    }),
    column.accessor("health", { header: "State", meta: { label: "State", className: NOWRAP }, cell: (c) => <StateCell row={c.row.original} /> }),
  ] as ColumnDef<ServerRow, never>[];
  return [...columns, ...trailing];
}

/** A left edge on the rows that need attention, nothing on the rest. */
export function rowAccent(row: ServerRow): string | undefined {
  if (row.health === "CRITICAL" || row.health === "MAJOR") return "shadow-[inset_2px_0_0_var(--status-error)]";
  if (row.health === "WARNING") return "shadow-[inset_2px_0_0_var(--status-warning)]";
  return undefined;
}

