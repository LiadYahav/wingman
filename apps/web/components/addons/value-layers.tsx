"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { RoleChip } from "@/components/addons/role-chip";
import { cn } from "@/lib/utils";
import { leaves, toYaml } from "@/lib/values";
import type { LeafApp, ValuesPreview } from "@/types/day2";

interface Row {
  key: string;
  role: string;
  path: string;
  exists: boolean;
  problem: string | null;
  values: Record<string, unknown>;
  edited: boolean;
}

/**
 * The value stack, lowest first, as the platform merges it: the chart's own
 * values.yaml, then each layer of the destination kind. `editedPath` is the
 * file this change writes.
 */
export function ValueLayers({ preview, editedPath }: { preview: ValuesPreview; editedPath: string }) {
  const { chart } = preview;
  const rows: Row[] = [
    {
      key: "chart",
      role: "chart",
      path: chart.project
        ? `${chart.project} @ ${chart.revision} · ${chart.path === "." ? "" : `${chart.path}/`}values.yaml`
        : "chart repo unknown",
      exists: !chart.problem,
      problem: chart.problem,
      values: preview.chart_values,
      edited: false,
    },
    ...preview.layers.map((layer) => ({
      key: `${layer.role}|${layer.path}`,
      role: layer.role,
      path: layer.path,
      exists: layer.exists,
      problem: layer.problem,
      values: layer.values,
      edited: layer.path === editedPath,
    })),
  ];
  return (
    <ol className="divide-y overflow-hidden rounded-lg border text-xs" aria-label="Value layers, lowest first">
      {rows.map((row, i) => (
        <LayerRow key={row.key} row={row} index={i + 1} />
      ))}
    </ol>
  );
}

function LayerRow({ row, index }: { row: Row; index: number }) {
  const [open, setOpen] = useState(false);
  const count = leaves(row.values).length;
  const expandable = row.exists && count > 0;
  return (
    <li className={cn(!row.exists && !row.edited && "bg-muted/20")}>
      <button
        type="button"
        onClick={() => expandable && setOpen((v) => !v)}
        aria-expanded={expandable ? open : undefined}
        className={cn(
          "grid w-full grid-cols-[1.5rem_8.5rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-2 text-left",
          expandable ? "hover:bg-muted/40" : "cursor-default",
        )}
      >
        <span className="tabular-nums text-muted-foreground">{index}</span>
        <RoleChip role={row.role} className="justify-self-start" />
        <span className={cn("break-all font-mono text-[11px]", row.exists ? "text-foreground" : "text-muted-foreground")}>
          {row.path}
        </span>
        <span className="flex items-center gap-1.5 whitespace-nowrap text-muted-foreground">
          {row.edited && <span className="rounded bg-primary/12 px-1.5 py-px text-[10px] font-medium text-primary">this edit</span>}
          {row.problem ? (
            <span className="text-status-warning-fg">{row.problem}</span>
          ) : row.exists ? (
            `${count} key${count === 1 ? "" : "s"}`
          ) : (
            "no file"
          )}
          {expandable && <ChevronRight className={cn("h-3.5 w-3.5 transition-transform duration-150", open && "rotate-90")} />}
        </span>
      </button>
      {open && (
        <pre className="max-h-64 overflow-auto border-t bg-muted/30 px-4 py-2 font-mono text-[11px] leading-relaxed">
          {toYaml(row.values)}
        </pre>
      )}
    </li>
  );
}

/** The leaf ArgoCD Application the platform generates: no live status, Wingman has no ArgoCD access. */
export function DeploySummary({ deploy }: { deploy: LeafApp }) {
  const items: [string, string][] = [
    ["Application", deploy.app_name],
    ["Argo CD", `${deploy.argo} · ${deploy.namespace}`],
    ["Chart", `${deploy.repo_url || "(no repourl)"}`],
    ["Revision", deploy.target_revision],
    ["Path", deploy.path],
    ["Release", deploy.release_name],
    ["Destination", `${deploy.destination}${deploy.destination_namespace ? ` / ${deploy.destination_namespace}` : ""}`],
    ["Sync", deploy.auto_sync ? "automated: syncs after merge" : "manual: someone syncs it after merge"],
  ];
  return (
    <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      {items.map(([term, value]) => (
        <div key={term} className="contents">
          <dt className="text-muted-foreground">{term}</dt>
          <dd className={cn("break-all font-mono text-[11px]", !value && "text-muted-foreground")}>{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
