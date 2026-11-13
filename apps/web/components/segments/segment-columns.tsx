"use client";

import Link from "next/link";
import { createColumnHelper } from "@tanstack/react-table";
import { CopyCell } from "@/components/data-table/copy-cell";
import { MismatchMarker } from "./mismatch-marker";
import { clusterHref } from "@/lib/clusters";
import { COLUMN_LABELS, cellText, dhcpLabel, isAllocated, statusLabel, type ColumnId } from "@/lib/segments/columns";
import { cn } from "@/lib/utils";
import type { Segment } from "@/types/segments";

const Empty = () => <span className="text-muted-foreground">—</span>;

function TypeBadge({ type }: { type: string | null }) {
  if (!type) return <Empty />;
  return (
    <span className="inline-flex rounded-md border px-1.5 py-px font-mono text-[11px] font-medium tracking-wide text-foreground/80">
      {type}
    </span>
  );
}

function SiteChip({ site }: { site: string | null }) {
  if (!site) return <Empty />;
  return <span className="inline-flex rounded-full bg-muted px-2 py-px text-xs text-muted-foreground">{site}</span>;
}

function Dhcp({ segment }: { segment: Segment }) {
  const label = dhcpLabel(segment);
  if (!label) return <Empty />;
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-px text-xs font-medium",
        segment.dhcp ? "bg-status-ready/15 text-status-ready-fg" : "bg-muted text-muted-foreground"
      )}
    >
      {label}
    </span>
  );
}

/** Each holder: a hosted cluster whose file is in day1 links to its page; any other is text. */
function Holders({ segment }: { segment: Segment }) {
  if (segment.holders.length === 0) return <Empty />;
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5" data-testid="segment-holders">
      {segment.holders.map((holder) =>
        holder.day1 ? (
          <Link
            key={holder.name}
            href={clusterHref({ name: holder.name, site: holder.day1.site, mce: holder.day1.mce })}
            className="font-mono text-xs text-primary underline-offset-2 hover:underline"
          >
            {holder.name}
          </Link>
        ) : (
          <span key={holder.name} className="font-mono text-xs">
            {holder.name}
          </span>
        )
      )}
    </span>
  );
}

function Status({ segment }: { segment: Segment }) {
  const allocated = isAllocated(segment);
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-px text-xs font-medium",
        allocated ? "bg-primary/12 text-primary" : "bg-status-ready/15 text-status-ready-fg"
      )}
    >
      {statusLabel(segment)}
    </span>
  );
}

const column = createColumnHelper<Segment>();
/** Every column filters by its cell's text, as the original's header filters do (and as the page's filtering reads it). */
const meta = (id: ColumnId, className?: string) => ({
  label: COLUMN_LABELS[id],
  className,
  filterValue: (segment: Segment) => cellText(segment, id),
});

/** The table's columns, in the original's order, with its headers and their value filters. */
export const SEGMENT_COLUMNS = [
  column.accessor("type", { header: COLUMN_LABELS.type, meta: meta("type"), cell: (c) => <TypeBadge type={c.getValue()} /> }),
  column.accessor("site", { header: COLUMN_LABELS.site, meta: meta("site"), cell: (c) => <SiteChip site={c.getValue()} /> }),
  column.accessor("vlan_id", {
    header: COLUMN_LABELS.vlan_id,
    meta: meta("vlan_id", "tabular-nums"),
    cell: (c) => (
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        <CopyCell value={c.getValue() === null ? null : String(c.getValue())} label="VLAN ID" className="font-semibold" />
        <MismatchMarker segment={c.row.original} />
      </span>
    ),
  }),
  column.accessor("epg_name", {
    header: COLUMN_LABELS.epg_name,
    meta: meta("epg_name"),
    cell: (c) => <CopyCell value={c.getValue()} label="EPG name" className="font-mono text-xs" />,
  }),
  column.accessor("segment", {
    header: COLUMN_LABELS.segment,
    meta: meta("segment"),
    cell: (c) => <CopyCell value={c.getValue()} label="Segment" className="font-mono text-xs" />,
  }),
  column.accessor("dhcp", { header: COLUMN_LABELS.dhcp, meta: meta("dhcp"), cell: (c) => <Dhcp segment={c.row.original} /> }),
  column.accessor((s) => s.holders.map((h) => h.name).join(", "), {
    id: "cluster",
    header: COLUMN_LABELS.cluster,
    meta: meta("cluster"),
    cell: (c) => <Holders segment={c.row.original} />,
  }),
  column.accessor("status", { header: COLUMN_LABELS.status, meta: meta("status"), cell: (c) => <Status segment={c.row.original} /> }),
];
