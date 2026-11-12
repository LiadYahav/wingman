"use client";

import { useState } from "react";
import { Layers, Pencil } from "lucide-react";
import { scopeLabel, syncSummary } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { leaves } from "@/lib/values";
import { buttonVariants } from "@/components/ui/button";
import { FindingsBadge } from "@/components/addons/findings";
import { EditFleetDefaultDialog } from "@/components/addons/default-dialogs";
import type { AuthoringChange, FleetDefault } from "@/types/day2";

/** Why there is no "stop being a default" yet: what it would do to running workloads. */
export const NO_STOP_NOTE =
  "Stopping being a default is not in Wingman yet: deleting the folder deletes the default's Applications on every destination it reaches, and with prune: false ArgoCD orphans the workloads, which keep running. Until then, keep it off one cluster with exclusions.yaml (runbook R10), or remove it by hand.";

function FleetDefaultRow({
  fd,
  canWrite,
  readOnlyReason,
  onOpened,
}: {
  fd: FleetDefault;
  canWrite: boolean;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const [open, setOpen] = useState(false);
  const count = leaves(fd.values).length;
  return (
    <li
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border bg-card px-4 py-3 shadow-sm"
      data-testid={`fleet-default-${fd.team}-${fd.chart}-${fd.scope}`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-chart-5/15 text-chart-5">
        <Layers className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1 basis-48">
        <span className="block truncate text-sm font-semibold" title={fd.chart}>
          {fd.chart}
          <span className="font-normal text-muted-foreground"> · {fd.scope_label || scopeLabel(fd.scope)}</span>
        </span>
        <span className="block text-xs text-muted-foreground">
          reaches {fd.reach.length} destination{fd.reach.length === 1 ? "" : "s"}
          {fd.excluded.length > 0 && ` · ${fd.excluded.length} excluded`}
          {` · ${count} value${count === 1 ? "" : "s"}`}
          {fd.tweaks.length > 0 && ` · ${fd.tweaks.length} per-cluster file${fd.tweaks.length === 1 ? "" : "s"}`}
        </span>
        <span className="block truncate text-xs" title={syncSummary(fd.sync)}>
          <span className="text-foreground/90">{syncSummary(fd.sync)}</span>
          <span className="text-muted-foreground">{fd.sync_overridden ? " · set by the fleet default" : " · the team default's"}</span>
        </span>
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {!fd.in_catalog && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground" title="The team has no operators/<chart>/ for it">
            not in the catalog
          </span>
        )}
        <FindingsBadge findings={fd.warnings} />
        {canWrite && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={Boolean(readOnlyReason)}
            title={readOnlyReason ?? undefined}
            aria-label="Edit fleet default"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 gap-1.5")}
          >
            <Pencil className="h-3 w-3" />
            Edit
          </button>
        )}
      </span>
      {open && (
        <EditFleetDefaultDialog
          fleetDefault={fd}
          open
          onOpenChange={setOpen}
          readOnlyReason={readOnlyReason}
          onOpened={onOpened}
        />
      )}
    </li>
  );
}

/** A team's fleet defaults (`defaults/<scope>/<chart>/`), each editable in place (ADR-0043). */
export function FleetDefaultsList({
  team,
  items,
  canWrite,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  items: FleetDefault[];
  /** The viewer is an admin: offer Edit (disabled while the team is read-only). */
  canWrite: boolean;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2" aria-label={`Fleet defaults of ${team}`} role="group">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Layers className="h-3.5 w-3.5" />
        Fleet defaults
        <span className="rounded-full bg-muted px-2 py-0.5 font-medium normal-case tracking-normal">{items.length}</span>
      </p>
      <ul className="space-y-2">
        {[...items]
          .sort((a, b) => a.chart.localeCompare(b.chart) || a.scope.localeCompare(b.scope))
          .map((fd) => (
            <FleetDefaultRow key={`${fd.chart}|${fd.scope}`} fd={fd} canWrite={canWrite} readOnlyReason={readOnlyReason} onOpened={onOpened} />
          ))}
      </ul>
      <p className="text-[11px] text-muted-foreground" data-testid="no-stop-default-note">
        {NO_STOP_NOTE}
      </p>
    </div>
  );
}
