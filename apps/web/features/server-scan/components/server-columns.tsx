"use client";

import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/data-table/copy-cell";
import { columnText } from "@/features/server-scan/lib/servers-model";
import type { ServerRow } from "@/features/server-scan/types/server-scan-servers";
import { cn } from "@/lib/utils";
import { InstallationCell, StateCell } from "./server-badges";
import { ServerLink } from "./server-link";

/**
 * The Servers table's columns, server-scan's own in its order and words
 * (team-redbull/server-scan, `frontend/src/features/inventory/InventoryTable.tsx`,
 * decision 18), in its colours and cells (ADR-0048's 2026-11-18 amendment:
 * centred, uppercase headers, the name in plain text, `../palette.css`):
 * Name (a link to the server's page), BMC (its console and,
 * since v6.2.0, a copy of its address), Installation, MCE
 * (only when a row on the page has one), Cluster, Model, State, then
 * Maintenance. Name, Installation, MCE,
 * Cluster, Model and State sort; Model also has Wingman's value filter, the
 * one column server-scan cannot filter.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

const Empty = () => <span className="text-ss-text-secondary">—</span>;

/** server-scan's square icon buttons in a row (BMC, Fetch now): a hairline box, muted until hovered. */
const ROW_BUTTON =
  "inline-flex size-7 items-center justify-center rounded-md border border-ss-border-subtle text-ss-text-muted outline-none transition-colors hover:border-ss-border-strong hover:text-ss-text-primary focus-visible:ring-2 focus-visible:ring-ring/50";

/**
 * Opens the BMC's own web console in a new tab (`https://`, the one scheme
 * every vendor's BMC serves), and copies its address (server-scan v6.2.0,
 * its 4d9d171), each saying the address first on hover; nothing for a server
 * whose BMC host was not read.
 */
function BmcCell({ row }: { row: ServerRow }) {
  if (!row.bmc_host) return null;
  const label = `Open BMC console for ${row.name}`;
  return (
    <span className="inline-flex items-center gap-1">
      <a href={`https://${row.bmc_host}`} target="_blank" rel="noopener noreferrer" title={`${row.bmc_host} — open BMC console`} aria-label={label} className={ROW_BUTTON}>
        <ExternalLink aria-hidden className="h-3.5 w-3.5" />
      </a>
      <CopyButton value={row.bmc_host} label="BMC address" title={`${row.bmc_host} — copy`} className={ROW_BUTTON} />
    </span>
  );
}

function ClusterCell({ row }: { row: ServerRow }) {
  if (!row.cluster_name && !row.contested_with) return <Empty />;
  return (
    <span className="inline-flex flex-wrap items-center justify-center gap-1.5 text-ss-text-secondary">
      {row.cluster_name ?? <Empty />}
      {row.contested_with && (
        <span
          title="Claimed by two OpenShift clusters at once: one physical server in two memberships"
          className="inline-flex whitespace-nowrap rounded-full bg-ss-tint-warning px-2 py-0.5 text-xs font-medium text-ss-on-warning"
        >
          Contested with {row.contested_with}
        </span>
      )}
    </span>
  );
}

/**
 * server-scan keeps every cell on one line, so a row is one line high, and
 * pads its cells as tightly (`px-2 py-2.5`), each centred but the name's:
 * the fleet's columns then fit beside the cluster sidebar on a 1920-pixel
 * screen. Its headers are small, uppercase and spaced.
 */
const NOWRAP = "whitespace-nowrap px-2 py-2.5 text-center";
const HEADER = "px-2 py-2.5 text-center font-medium uppercase tracking-wide text-ss-text-secondary [&_button]:uppercase";
const NAME_HEADER = `${HEADER} text-left`;

/** A column's look: server-scan's cell and header (the toggle's and Fetch now's columns too). */
export const look = (label: string, extra: Partial<{ className: string; headerClassName: string }> = {}) => ({
  label,
  className: NOWRAP,
  headerClassName: HEADER,
  ...extra,
});

const column = createColumnHelper<ServerRow>();
const muted = (value: string | null) => (value ? <span className="text-ss-text-secondary">{value}</span> : <Empty />);

/** The name in plain text, a link to the server's page (remembering this view for its "← Servers"), and a copy button on hover. */
function NameCell({ row }: { row: ServerRow }) {
  return (
    <span className="group inline-flex items-center gap-1">
      <ServerLink id={row.id} fromServers className="font-medium text-ss-text-primary">
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
      meta: look("Name", { className: "whitespace-nowrap px-2 py-2.5 text-left", headerClassName: NAME_HEADER }),
      cell: (c) => <NameCell row={c.row.original} />,
    }),
    column.display({ id: "bmc", header: "BMC", meta: look("BMC"), cell: (c) => <BmcCell row={c.row.original} /> }),
    column.accessor("openshift_state", { header: "Installation", meta: look("Installation"), cell: (c) => <InstallationCell row={c.row.original} /> }),
    ...(withMce ? [column.accessor("mce_name", { header: "MCE", meta: look("MCE"), cell: (c) => muted(c.getValue()) })] : []),
    column.accessor("cluster_name", { header: "Cluster", meta: look("Cluster"), cell: (c) => <ClusterCell row={c.row.original} /> }),
    column.accessor("model", {
      header: "Model",
      meta: { ...look("Model"), filterValue: (row: ServerRow) => columnText(row, "model") },
      cell: (c) => muted(c.getValue()),
    }),
    column.accessor("health", { header: "State", meta: look("State"), cell: (c) => <StateCell row={c.row.original} /> }),
  ] as ColumnDef<ServerRow, never>[];
  return [...columns, ...trailing];
}

/** A left edge on the rows that need attention, in server-scan's colours (its ROW_ACCENT); nothing on the rest. */
function rowAccent(row: ServerRow): string | undefined {
  if (row.health === "CRITICAL") return "shadow-[inset_2px_0_0_var(--ss-critical)]";
  if (row.health === "MAJOR") return "shadow-[inset_2px_0_0_var(--ss-on-major)]";
  if (row.health === "WARNING") return "shadow-[inset_2px_0_0_var(--ss-warning)]";
  return undefined;
}

/** The table's own look, server-scan's: its sunken header, hairline rows and corner (`DataTable`'s `className`). */
export const SERVERS_TABLE =
  "relative rounded-[0.625rem] overscroll-contain [&_thead]:bg-ss-surface-sunken [&_thead_tr]:border-ss-border-subtle [&_tbody]:divide-ss-border-subtle";

/** A row's look: server-scan's hover, and its left edge. */
export const rowLook = (row: ServerRow) => cn("hover:bg-ss-surface-hover", rowAccent(row));

