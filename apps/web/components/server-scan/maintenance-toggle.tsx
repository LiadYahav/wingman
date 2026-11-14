"use client";

import { useState, type FormEvent } from "react";
import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { Play, Wrench } from "lucide-react";
import { toast } from "sonner";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessages } from "@/lib/api-client";
import { useMaintenanceChange } from "@/lib/api/server-scan";
import { cn } from "@/lib/utils";
import type { ServerRow } from "@/types/server-scan-servers";

/** What the toggle needs of a server: a row of the Servers page, or a server's page's record. */
type Switchable = Pick<ServerRow, "id" | "name" | "maintenance">;

/**
 * One row's maintenance switch, as server-scan's (team-redbull/server-scan at
 * 92146d3, `frontend/src/features/inventory/MaintenanceToggle.tsx`, decision
 * 14): entering maintenance asks why, in its words; leaving it is one click,
 * the operators' asked-for asymmetry. Wingman adds the optional expected end
 * server-scan's API takes. Never retried: an unanswered change says so
 * (`AMBIGUOUS_WRITE`), and the row shows what server-scan has.
 */

const EXPECTED_END_HELP =
  "When the maintenance should end. Optional: server-scan's API records it; its own dialog does not ask.";

/** A `datetime-local` value (the browser's local time) as an ISO instant; `null` when empty or unreadable. */
function isoOf(local: string): string | null {
  if (!local) return null;
  const at = new Date(local);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

function StartDialog({ server, open, onOpenChange }: { server: Switchable; open: boolean; onOpenChange: (open: boolean) => void }) {
  const change = useMaintenanceChange();
  const [reason, setReason] = useState("");
  const [end, setEnd] = useState("");
  const close = (next: boolean) => {
    if (!next) {
      setReason("");
      setEnd("");
      change.reset();
    }
    onOpenChange(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = reason.trim();
    change.mutate(
      { id: server.id, start: { reason: trimmed || null, expected_end: isoOf(end) } },
      { onSuccess: () => close(false) }
    );
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent aria-label={`Put ${server.name} into maintenance`} data-testid="ss-maintenance-dialog">
        <DialogHeader>
          <DialogTitle>Put into maintenance</DialogTitle>
          <DialogDescription className="truncate" title={server.name}>
            {server.name}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <label className="block space-y-1">
            <span className="block text-xs font-medium">Why is it going into maintenance?</span>
            <span className="block text-xs text-muted-foreground">Include the word “donor” to mark it as a parts donor.</span>
            <input
              autoFocus
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Replacing PSU 2 — INC-4417"
              maxLength={500}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </label>
          <label className="block space-y-1" title={EXPECTED_END_HELP}>
            <span className="block text-xs font-medium">
              Expected end <span className="font-normal text-muted-foreground">(optional)</span>
            </span>
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </label>
          {change.isError && (
            <p role="alert" data-testid="ss-maintenance-error" className="text-xs text-destructive">
              {errorMessages(change.error)[0]}
            </p>
          )}
          <DialogFooter>
            <button type="button" onClick={() => close(false)} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Cancel
            </button>
            <button type="submit" disabled={change.isPending} className={buttonVariants({ size: "sm" })}>
              {change.isPending ? "Starting…" : "Start maintenance"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The switch, on a Servers row and on a server's page. Greyed out with
 * `detail` as its tooltip when the deployment cannot write (no admin token):
 * `aria-disabled`, not `disabled`, so the tooltip still shows.
 */
function MaintenanceToggle({ server, available, detail }: { server: Switchable; available: boolean; detail: string | null }) {
  const end = useMaintenanceChange();
  const [asking, setAsking] = useState(false);
  const enabled = server.maintenance.enabled;
  const label = !available ? (detail ?? "Maintenance is not available here") : enabled ? `End maintenance on ${server.name}` : `Put ${server.name} into maintenance`;
  const onClick = () => {
    if (!available) return;
    if (!enabled) {
      setAsking(true);
      return;
    }
    end.mutate(
      { id: server.id, start: null },
      { onError: (error) => toast.error(`Maintenance on ${server.name} was not ended: ${errorMessages(error)[0]}`) }
    );
  };
  return (
    <>
      <button
        type="button"
        title={label}
        aria-label={label}
        aria-disabled={!available || undefined}
        aria-haspopup={enabled ? undefined : "dialog"}
        disabled={end.isPending}
        data-testid="ss-maintenance-toggle"
        data-state={enabled ? "on" : "off"}
        onClick={onClick}
        className={cn(
          "inline-flex h-7 w-7 items-center justify-center rounded-md border outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-40",
          !available && "cursor-not-allowed opacity-40",
          enabled
            ? "border-status-provisioning/40 bg-status-provisioning/15 text-status-provisioning-fg"
            : "text-muted-foreground hover:border-foreground/30 hover:text-foreground"
        )}
      >
        {enabled ? <Play aria-hidden className="h-3.5 w-3.5" /> : <Wrench aria-hidden className="h-3.5 w-3.5" />}
      </button>
      {!enabled && <StartDialog server={server} open={asking} onOpenChange={setAsking} />}
    </>
  );
}

/**
 * The table's last column, as server-scan's: the toggle. `available` and
 * `detail` are day1's `maintenance_available` and `maintenance_detail`.
 */
export function maintenanceColumn(available: boolean, detail: string | null): ColumnDef<ServerRow, never> {
  return createColumnHelper<ServerRow>().display({
    id: "maintenance",
    header: "Maintenance",
    meta: { label: "Maintenance", className: "whitespace-nowrap px-2 text-center" },
    cell: (c) => <MaintenanceToggle server={c.row.original} available={available} detail={detail} />,
  }) as ColumnDef<ServerRow, never>;
}
