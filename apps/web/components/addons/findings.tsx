"use client";

import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import { bySeverity, uniqueFindings, worstSeverity } from "@/lib/day2";
import { cn } from "@/lib/utils";
import type { Finding } from "@/types/day2";

const TONE: Record<string, { icon: typeof Info; box: string; text: string; label: string }> = {
  error: {
    icon: OctagonAlert,
    box: "border-status-error/30 bg-status-error/8",
    text: "text-status-error-fg",
    label: "Error",
  },
  warning: {
    icon: AlertTriangle,
    box: "border-status-warning/30 bg-status-warning/8",
    text: "text-status-warning-fg",
    label: "Warning",
  },
  info: {
    icon: Info,
    box: "border-border bg-muted/40",
    text: "text-muted-foreground",
    label: "Info",
  },
};

export function severityTone(severity: string) {
  return TONE[severity] ?? TONE.info;
}

/** Findings as a compact list, worst first; nothing when there are none. */
export function FindingsList({
  findings,
  className,
  showContext = false,
}: {
  findings: readonly Finding[];
  className?: string;
  /** Show each finding's file path (off where the path is the card's own). */
  showContext?: boolean;
}) {
  const items = uniqueFindings(findings).sort(bySeverity);
  if (items.length === 0) return null;
  return (
    <ul className={cn("space-y-1.5", className)} aria-label="Findings">
      {items.map((f) => {
        const tone = severityTone(f.severity);
        const Icon = tone.icon;
        return (
          <li
            key={`${f.rule}|${f.path}|${f.message}`}
            className={cn("flex gap-2 rounded-lg border px-3 py-2 text-xs", tone.box)}
          >
            <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", tone.text)} aria-label={tone.label} />
            <div className="min-w-0 space-y-0.5">
              <p className="text-foreground break-words">{f.message}</p>
              <p className="flex flex-wrap gap-x-2 font-mono text-[11px] text-muted-foreground">
                <span>{f.rule}</span>
                {showContext && f.path && <span className="break-all">{f.path}</span>}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** A count badge in the worst finding's color; nothing when there are none. */
export function FindingsBadge({ findings }: { findings: readonly Finding[] }) {
  const items = uniqueFindings(findings);
  const worst = worstSeverity(items);
  if (!worst) return null;
  const tone = severityTone(worst);
  const Icon = tone.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
        worst === "info" ? "bg-muted text-muted-foreground" : worst === "error" ? "bg-status-error/12" : "bg-status-warning/12",
        tone.text,
      )}
      title={`${items.length} finding${items.length === 1 ? "" : "s"}`}
    >
      <Icon className="h-3 w-3" />
      {items.length}
    </span>
  );
}
