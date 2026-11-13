"use client";

import { Lock, Wrench } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { hardwareLabel } from "@/lib/inventory/pools";
import { cn } from "@/lib/utils";
import type { Candidate } from "@/types/inventory";

const HEALTH_TONE: Record<string, string> = {
  HEALTHY: "bg-status-ready",
  WARNING: "bg-status-warning",
  MAJOR: "bg-status-warning",
  CRITICAL: "bg-status-error",
};

function Why({ candidate }: { candidate: Candidate }) {
  if (!candidate.why_not) return null;
  const Icon = candidate.lock ? Lock : Wrench;
  return (
    <Hint hint={candidate.why_not} label={`Not offered: ${candidate.why_not}`} testId="candidate-why-not">
      <Icon aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />
    </Hint>
  );
}

/** The name, its pool's shared prefix muted and cut first, so the part that differs stays whole. */
function ServerName({ name, prefix }: { name: string; prefix: string }) {
  const shared = name.startsWith(prefix) ? prefix : "";
  return (
    <span className="flex min-w-0 flex-1 font-mono" title={name}>
      {shared && <span className="truncate text-muted-foreground">{shared}</span>}
      <span className="shrink-0">{name.slice(shared.length)}</span>
    </span>
  );
}

/**
 * A pool's servers in no MCE, as server-scan reports them: name, hardware,
 * health and lock. With `selected`, a picker: a server a named install would
 * fail on (locked, in maintenance, contested) cannot be picked.
 */
export function CandidateList({
  infraEnv,
  candidates,
  isLoading,
  error,
  selected,
  onToggle,
}: {
  infraEnv: string;
  candidates: Candidate[] | undefined;
  isLoading: boolean;
  error: unknown;
  selected?: string[];
  onToggle?: (name: string) => void;
}) {
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  if (error) return <ProblemList error={error} title="The pool's servers could not be read" />;
  if (!candidates || candidates.length === 0) {
    return <p className="px-1 py-2 text-xs text-muted-foreground">No free server in server-scan is named for this pool.</p>;
  }
  return (
    <ul className="max-h-64 divide-y divide-border/60 overflow-auto rounded-lg border" aria-label="Servers in no MCE">
      {candidates.map((c) => {
        const picked = selected?.includes(c.name) ?? false;
        return (
          <li
            key={c.id}
            data-testid="candidate"
            data-server={c.name}
            data-offered={c.offered}
            className={cn("flex items-center gap-2.5 px-2.5 py-1.5 text-xs", !c.offered && "text-muted-foreground")}
          >
            {selected && onToggle && (
              <Checkbox
                checked={picked}
                disabled={!c.offered}
                onCheckedChange={() => onToggle(c.name)}
                aria-label={`Install ${c.name}`}
              />
            )}
            <span
              role="img"
              aria-label={`health ${c.health}`}
              className={cn("h-1.5 w-1.5 shrink-0 rounded-full", HEALTH_TONE[c.health] ?? "bg-muted-foreground/50")}
              title={c.health}
            />
            <ServerName name={c.name} prefix={`ocp-${infraEnv}`} />
            <span className="hidden shrink-0 sm:inline">{hardwareLabel(c)}</span>
            <Why candidate={c} />
          </li>
        );
      })}
    </ul>
  );
}
