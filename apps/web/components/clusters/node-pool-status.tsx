"use client";

import { useState } from "react";
import { CircleX, Loader2, TriangleAlert } from "lucide-react";
import { humanize } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { NodePoolUpdate } from "@/types";

/*
 * What a NodePool card says about the NodePool's state, under its header: an
 * update in progress, and the conditions that are not True.
 */

const UPDATE_KIND: Record<NodePoolUpdate["kind"], string> = {
  version: "version",
  config: "config",
  machine_template: "machine template",
};

/**
 * An update in progress, as the NodePool's condition says it: what is being
 * updated, how far (when an in-place update counts its nodes), and the
 * condition's own message. A failed one is in the destructive style.
 */
export function UpdateBanner({ update }: { update: NodePoolUpdate }) {
  const what = UPDATE_KIND[update.kind] ?? humanize(update.kind).toLowerCase();
  const { progress, failed } = update;
  const percent = progress && progress.total > 0 ? Math.round((Math.min(progress.updated, progress.total) / progress.total) * 100) : 0;
  return (
    <div
      role="status"
      data-testid="node-pool-update"
      className={cn(
        "mx-4 mb-3 rounded-lg border px-3 py-2.5",
        failed ? "border-destructive/30 bg-destructive/5" : "border-status-provisioning/25 bg-status-provisioning/5"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p
          className={cn(
            "flex items-center gap-1.5 text-sm font-medium",
            failed ? "text-destructive" : "text-status-provisioning-fg"
          )}
        >
          {failed ? (
            <CircleX className="h-4 w-4" aria-hidden />
          ) : (
            <Loader2 className="h-4 w-4 animate-spin [animation-duration:2s] motion-reduce:animate-none" aria-hidden />
          )}
          {failed ? `${humanize(what)} update failed` : `Updating ${what}`}
        </p>
        {progress && (
          <p className="text-xs tabular-nums text-foreground" data-testid="node-pool-update-progress">
            {progress.updated} of {progress.total} node{progress.total !== 1 ? "s" : ""} updated
          </p>
        )}
      </div>
      {progress && (
        <div
          role="progressbar"
          aria-label="Nodes updated"
          aria-valuemin={0}
          aria-valuemax={progress.total}
          aria-valuenow={progress.updated}
          className={cn("mt-2 h-1 overflow-hidden rounded-full", failed ? "bg-destructive/15" : "bg-status-provisioning/15")}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-out motion-reduce:transition-none",
              failed ? "bg-destructive" : "bg-status-provisioning"
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {update.message && (
        <p className={cn("mt-1.5 text-xs break-words", failed ? "text-destructive/80" : "text-muted-foreground")}>
          {update.message}
        </p>
      )}
    </div>
  );
}

/** How many problems show before "Show more". */
const PROBLEMS_SHOWN = 2;

/** "<Type>: <reason>: <message>", with the condition's type set apart. */
function ProblemLine({ text }: { text: string }) {
  const at = text.indexOf(": ");
  return (
    <span className="break-words">
      {at > 0 ? (
        <>
          <span className="font-medium text-foreground/80">{text.slice(0, at)}</span>
          {text.slice(at)}
        </>
      ) : (
        text
      )}
    </span>
  );
}

/** The NodePool's conditions that are not True: a quiet list, folded when long. */
export function NodePoolProblems({ problems, id }: { problems: string[]; id: string }) {
  const [open, setOpen] = useState(false);
  if (problems.length === 0) return null;
  const folded = problems.length > PROBLEMS_SHOWN && !open;
  const shown = folded ? problems.slice(0, PROBLEMS_SHOWN) : problems;
  return (
    <div className="mx-4 mb-3" data-testid="node-pool-problems">
      <ul id={id} className="space-y-1 text-xs text-muted-foreground">
        {shown.map((p, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0 text-status-warning-fg" aria-hidden />
            <ProblemLine text={p} />
          </li>
        ))}
      </ul>
      {problems.length > PROBLEMS_SHOWN && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={id}
          className="mt-1 ml-[1.125rem] rounded-sm text-xs font-medium text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {open ? "Show fewer" : `Show ${problems.length - PROBLEMS_SHOWN} more`}
        </button>
      )}
    </div>
  );
}
