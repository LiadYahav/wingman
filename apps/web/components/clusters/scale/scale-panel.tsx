"use client";

import { Scaling } from "lucide-react";
import { ProblemList } from "@/components/common/problem-list";
import { useScaleOptions, useScaleRun } from "@/lib/scale";
import { plural } from "@/lib/utils";
import type { ScaleNodePool, ScaleOptions } from "@/types";
import { ScaleKindButton } from "./scale-kind-dialog";
import { SizeRow } from "./scale-pool";
import { ScaleRunCard } from "./scale-run-card";
import { BUSY_ID, useScaleTab } from "./scale-tab";

/**
 * Which NodePools the Nodes tab shows as cards from the MCE: their names,
 * `none` (live status off, the nodes unreadable or none listed), or
 * `loading`. Each card scales its own NodePool; the rest are rows here.
 */
export type LiveCards = ReadonlySet<string> | "none" | "loading";

function Subtitle({ options, cards }: { options: ScaleOptions; cards: ReadonlySet<string> | null }) {
  const lock = options.flavor ? <>; replicas flavor {options.flavor} locks stay as it sets them</> : null;
  if (!cards) {
    return <>As the day1 file sets them. Only the platform&apos;s update-nodepool workflow changes them{lock}.</>;
  }
  const total = options.nodepools.every((p) => p.replicas !== null) ? options.nodepools.reduce((n, p) => n + (p.replicas ?? 0), 0) : null;
  return (
    <>
      {plural(options.nodepools.length, "NodePool")}
      {total !== null && <>, {plural(total, "replica")}</>}, as the day1 file sets them; each card below scales its own. Only the
      platform&apos;s update-nodepool workflow changes them{lock}.
    </>
  );
}

/** The NodePools the cards do not show: all of them without cards, none while the cards load. */
function rowsOf(nodepools: ScaleNodePool[], live: LiveCards): ScaleNodePool[] {
  if (live === "none") return nodepools;
  if (live === "loading") return [];
  return nodepools.filter((p) => p.name === null || !live.has(p.name));
}

/**
 * The Nodes tab's NodePool sizes, from the cluster's day1 file (ADR-0062,
 * its 2026-11-16 amendment): with the MCE's cards shown, a line, since each
 * card scales its own NodePool; without them, a row per NodePool, an
 * admin's a stepper. "Scale hardware type" opens a hardware type's total.
 * Why nothing can change now is said here, once. The cluster's run shows
 * below it for everyone. Nothing at all while scaling is off.
 */
export function ScalePanel({ name, where, enabled = true, live }: { name: string; where: string; enabled?: boolean; live: LiveCards }) {
  const tab = useScaleTab();
  const options = useScaleOptions(name, where, { enabled });
  const run = useScaleRun(name, where, { enabled });
  const shown = run.data?.state === "run" ? run.data.run : null;

  if (options.error) {
    return (
      <div data-testid="scale-error-read">
        <ProblemList error={options.error} title="The NodePool sizes could not be read" />
      </div>
    );
  }
  if (!tab) return null;
  const read = tab.options;
  const empty = read.nodepools.length === 0;
  const rows = rowsOf(read.nodepools, live);
  const cards = typeof live === "string" ? null : live;

  return (
    <div className="space-y-3">
      <section aria-labelledby="scale-heading" data-testid="scale-panel" className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 px-4 pb-3 pt-3.5">
          <div className="min-w-0 space-y-1">
            <h2 id="scale-heading" className="flex items-center gap-2 text-sm font-semibold">
              <Scaling className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              NodePool sizes
            </h2>
            <p className="max-w-2xl text-xs text-muted-foreground" data-testid="scale-summary">
              <Subtitle options={read} cards={cards} />
            </p>
          </div>
          <ScaleKindButton />
        </header>
        {tab.isAdmin && tab.busy && !empty && (
          <p id={BUSY_ID} data-testid="scale-busy-reason" className="border-t bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
            {tab.busy}
          </p>
        )}
        {empty ? (
          <p className="border-t px-4 py-3 text-xs text-muted-foreground">The cluster file has no NodePool.</p>
        ) : (
          rows.length > 0 && (
            <ul className="divide-y border-t" aria-label={cards ? "NodePools of the day1 file without a card below" : "NodePools in the day1 file"}>
              {rows.map((p) => (
                <SizeRow key={p.index} tab={tab} pool={p} />
              ))}
            </ul>
          )
        )}
      </section>
      {run.error ? (
        <ProblemList error={run.error} title="The cluster's update-nodepool run could not be read" />
      ) : (
        shown && <ScaleRunCard run={shown} />
      )}
    </div>
  );
}
