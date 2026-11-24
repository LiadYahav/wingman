"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { originHint, originLabel, readablePhase, runSubject, runTone, startedAgo, type RunTone } from "@/lib/inventory/runs";
import { cn } from "@/lib/utils";
import type { InventoryRun } from "@/types/inventory";

const TONE: Record<RunTone, string> = {
  running: "bg-primary/12 text-primary",
  completed: "bg-status-ready/15 text-status-ready-fg",
  failed: "bg-status-error/12 text-status-error",
  other: "bg-muted text-muted-foreground",
};

function Started({ run, now }: { run: InventoryRun; now: number }) {
  if (!run.started_at) return <span className="text-muted-foreground">—</span>;
  const at = Date.parse(run.started_at);
  return (
    <span className="whitespace-nowrap text-xs tabular-nums" title={run.started_at}>
      {startedAgo(at, Math.max(now, at))}
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

/** The health checks a named install waived on request (`allow_unhealthy`), listed in its tooltip. */
function Waived({ run }: { run: InventoryRun }) {
  if (run.health_checks_waived.length === 0) return null;
  return (
    <Hint hint={`Installed with health checks waived: ${run.health_checks_waived.join("; ")}.`} label="Health checks waived: which">
      <span data-testid="run-waived" className="whitespace-nowrap rounded-full bg-status-warning/15 px-2 py-px text-xs text-status-warning-fg">
        checks waived
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
      <Waived run={run} />
    </span>
  );
}

/**
 * The lines between rows, and the firmer one under the header, from the
 * foreground so they show in both themes (1.4-1.5:1 and 1.5-1.8:1, about
 * Apple's separators; the theme's `border` at 60% was 1.15:1), and 3:1 or
 * more when the system asks for more contrast.
 */
const DIVIDER = {
  rows: "divide-foreground/15 contrast-more:divide-foreground/50",
  header: "border-foreground/20 contrast-more:border-foreground/55",
};

const HEADERS = ["Started", "Who", "Pool", "Server", "Status", "Error"] as const;

function RunRow({ run, now }: { run: InventoryRun; now: number }) {
  return (
    <tr data-testid="run-row" data-workflow={run.workflow_id} className="transition-colors hover:bg-muted/40">
      <td className="px-3 py-1.5 align-middle">
        <Started run={run} now={now} />
      </td>
      <td className="px-3 py-1.5 align-middle">
        <Origin run={run} />
      </td>
      <td className="px-3 py-1.5 align-middle">
        <span className="block min-w-0">
          <span className="block font-mono text-xs">{run.infra_env ?? "—"}</span>
          <span className="block font-mono text-[11px] text-muted-foreground">{run.mce ?? run.workflow_id}</span>
        </span>
      </td>
      <td className="px-3 py-1.5 align-middle">
        <span className="font-mono text-xs">{runSubject(run)}</span>
      </td>
      <td className="px-3 py-1.5 align-middle">
        <Status run={run} />
      </td>
      <td className="max-w-xs px-3 py-1.5 align-middle">
        {run.error && (
          <span className="block truncate text-xs text-status-error" title={run.error}>
            {run.error}
          </span>
        )}
      </td>
    </tr>
  );
}

/** The add-server runs, newest first, as the orchestrator lists them: dense rows under a sticky header. */
export function RunsTable({ runs }: { runs: InventoryRun[] }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="overflow-auto rounded-xl border bg-card">
      <table aria-label="Add-server runs" className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-muted/90 backdrop-blur supports-[backdrop-filter]:bg-muted/75">
          <tr className={cn("border-b", DIVIDER.header)}>
            {HEADERS.map((header) => (
              <th
                key={header}
                scope="col"
                className={cn(
                  "whitespace-nowrap px-3 py-2 text-left text-xs font-semibold tracking-[0.01em] text-foreground/75",
                  header === "Error" && "max-w-xs"
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={cn("divide-y", DIVIDER.rows)}>
          {runs.length === 0 ? (
            <tr>
              <td colSpan={HEADERS.length}>
                <EmptyState title="No add-server runs" description="Neither herzi nor a person has added servers lately." />
              </td>
            </tr>
          ) : (
            runs.map((run) => <RunRow key={`${run.workflow_id}@${run.started_at ?? ""}`} run={run} now={now} />)
          )}
        </tbody>
      </table>
    </div>
  );
}
