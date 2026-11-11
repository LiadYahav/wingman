"use client";

import { CircleCheck, CircleX, ClockAlert, Loader2, Replace, Split, WifiOff, Wrench, type LucideIcon } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { humanize, isRunning } from "@/lib/nodes";
import { cn, formatDateTime } from "@/lib/utils";
import type { NodeHealth, NodeState, ServerRecord, WorkflowRun } from "@/types";

/**
 * The small marks of the Nodes tab. Quiet when all is well (a dot and muted
 * text), filled when something needs a look, so a board of healthy nodes
 * reads calm and the exception stands out.
 */

type Tone = "quiet" | "progress" | "warning" | "error" | "muted";

const CHIP: Record<Tone, { chip: string; dot: string }> = {
  quiet: { chip: "text-muted-foreground", dot: "bg-status-ready" },
  progress: { chip: "bg-status-provisioning/12 text-status-provisioning-fg ring-1 ring-inset ring-status-provisioning/25", dot: "bg-status-provisioning" },
  warning: { chip: "bg-status-warning/12 text-status-warning-fg ring-1 ring-inset ring-status-warning/25", dot: "bg-status-warning" },
  error: { chip: "bg-status-error/12 text-status-error-fg ring-1 ring-inset ring-status-error/30", dot: "bg-status-error" },
  muted: { chip: "bg-status-deleting/12 text-status-deleting-fg ring-1 ring-inset ring-status-deleting/25", dot: "bg-status-deleting" },
};

function Chip({ tone, label, testId, className }: { tone: Tone; label: string; testId?: string; className?: string }) {
  const { chip, dot } = CHIP[tone];
  return (
    <span
      data-testid={testId}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full text-xs font-medium",
        tone === "quiet" ? "px-0" : "px-2 py-0.5",
        chip,
        className
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} aria-hidden />
      {label}
    </span>
  );
}

const HEALTH: Record<NodeHealth, { label: string; tone: Tone }> = {
  HEALTHY: { label: "Healthy", tone: "quiet" },
  WARNING: { label: "Warning", tone: "warning" },
  MAJOR: { label: "Major", tone: "error" },
  CRITICAL: { label: "Critical", tone: "error" },
  // Not a verdict: never shown as healthy
  UNKNOWN: { label: "Unknown", tone: "muted" },
};

/** server-scan's overall verdict; anything it adds later reads as unknown, not healthy. */
export function HealthBadge({ health }: { health: NodeHealth }) {
  const known = HEALTH[health];
  return (
    <Chip
      testId="node-health"
      tone={known?.tone ?? "muted"}
      label={known?.label ?? humanize(String(health))}
      className={health === "CRITICAL" ? "font-semibold" : undefined}
    />
  );
}

/** Day1's states for a Machine (the API note's §1); a state it adds later is shown in words. */
const STATE: Record<NodeState, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "quiet" },
  not_ready: { label: "Not ready", tone: "warning" },
  joining: { label: "Joining", tone: "progress" },
  installing: { label: "Installing", tone: "progress" },
  deleting: { label: "Deleting", tone: "warning" },
  waiting: { label: "Waiting", tone: "muted" },
  missing: { label: "Missing", tone: "muted" },
  failed: { label: "Failed", tone: "error" },
};

export function NodeStateChip({ state }: { state: NodeState }) {
  const known = STATE[state];
  return <Chip testId="node-state" tone={known?.tone ?? "muted"} label={known?.label ?? humanize(String(state))} />;
}

/** server-scan's own state for a server no Machine has (`INSTALLED`, ...), in words and quiet. */
export function ServerStateText({ state }: { state: string }) {
  return (
    <span data-testid="node-state" className="text-xs text-muted-foreground whitespace-nowrap" title={`server-scan: ${state}`}>
      {humanize(state)}
    </span>
  );
}

interface Flag {
  key: "maintenance" | "stale" | "unreachable" | "contested" | "outdated";
  label: string;
  icon: LucideIcon;
  tone: "warning" | "error" | "quiet";
  hint: string;
}

/** What server-scan says about a server beyond its health, and a Replace pool's outdated Machine. Shown only. */
function flagsOf(server: ServerRecord | null, outdated: boolean | null): Flag[] {
  const flags: Flag[] = [];
  if (outdated) {
    flags.push({
      key: "outdated",
      label: "Will be replaced",
      icon: Replace,
      tone: "quiet",
      hint: "A Machine of an older revision of this NodePool: the rollout replaces it with a new one.",
    });
  }
  if (!server) return flags;
  if (server.maintenance) {
    flags.push({ key: "maintenance", label: "Maintenance", icon: Wrench, tone: "warning", hint: "server-scan has this server in maintenance." });
  }
  if (server.stale) {
    flags.push({
      key: "stale",
      label: "Stale",
      icon: ClockAlert,
      tone: "warning",
      hint: `server-scan's facts about this server are out of date${server.last_seen_at ? `; last seen ${formatDateTime(server.last_seen_at)}` : ""}.`,
    });
  }
  if (!server.reachable) {
    flags.push({ key: "unreachable", label: "Unreachable", icon: WifiOff, tone: "error", hint: "server-scan could not reach this server." });
  }
  if (server.contested) {
    flags.push({ key: "contested", label: "Contested", icon: Split, tone: "warning", hint: "Two clusters' jobs claim this server in server-scan." });
  }
  return flags;
}

const FLAG_TONE: Record<Flag["tone"], string> = {
  quiet: "bg-muted text-muted-foreground",
  warning: "bg-status-warning/10 text-status-warning-fg",
  error: "bg-status-error/10 text-status-error-fg",
};

export function NodeFlags({ server, outdated = null }: { server: ServerRecord | null; outdated?: boolean | null }) {
  const flags = flagsOf(server, outdated);
  if (flags.length === 0) return null;
  return (
    <TooltipProvider>
      {flags.map(({ key, label, icon: Icon, tone, hint }) => (
        <Tooltip key={key}>
          <TooltipTrigger
            data-testid={`node-flag-${key}`}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium cursor-default outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              FLAG_TONE[tone]
            )}
          >
            <Icon className="h-3 w-3" aria-hidden />
            {label}
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{hint}</TooltipContent>
        </Tooltip>
      ))}
    </TooltipProvider>
  );
}

/**
 * A server's newest uninstall run, in the orchestrator's words: a running
 * run names its phase (the workflow's own string, humanized), a failed one
 * its error. Wingman keeps no list of phases.
 */
export function RunStatus({ run }: { run: WorkflowRun }) {
  const running = isRunning(run);
  const completed = run.status === "completed";
  return (
    <div
      data-testid="node-uninstall-run"
      role={running ? "status" : undefined}
      className={cn(
        "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
        running && "border-status-provisioning/25 bg-status-provisioning/5",
        completed && "border-status-ready/25 bg-status-ready/5",
        !running && !completed && "border-status-error/25 bg-status-error/5"
      )}
    >
      {running ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 mt-px animate-spin text-status-provisioning-fg motion-reduce:animate-none" aria-hidden />
      ) : completed ? (
        <CircleCheck className="h-3.5 w-3.5 shrink-0 mt-px text-status-ready-fg" aria-hidden />
      ) : (
        <CircleX className="h-3.5 w-3.5 shrink-0 mt-px text-status-error-fg" aria-hidden />
      )}
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="flex flex-wrap items-baseline gap-x-1.5">
          <span
            className={cn(
              "font-medium",
              running ? "text-status-provisioning-fg" : completed ? "text-status-ready-fg" : "text-status-error-fg"
            )}
          >
            {running ? "Uninstalling" : completed ? "Uninstall completed" : `Uninstall ${humanize(run.status).toLowerCase()}`}
          </span>
          {running && (
            <span className="text-foreground" data-testid="node-uninstall-phase">
              {run.phase ? humanize(run.phase) : "Starting"}
            </span>
          )}
          <span className="font-mono text-[11px] text-muted-foreground break-all">{run.workflow_id}</span>
        </p>
        {run.error && <p className="text-status-error-fg break-words">{run.error}</p>}
      </div>
    </div>
  );
}
