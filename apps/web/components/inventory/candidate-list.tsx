"use client";

import { Info, Lock, Wrench } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { hardwareLabel, unnamedReason } from "@/lib/inventory/pools";
import { groupCandidates, type GroupInfo } from "@/lib/inventory/waiver";
import { cn } from "@/lib/utils";
import type { Candidate, Candidates } from "@/types/inventory";

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
function ServerName({ candidate, prefix }: { candidate: Candidate; prefix: string | null }) {
  const { name } = candidate;
  const shared = prefix && name.startsWith(prefix) ? prefix : "";
  return (
    <span className="flex min-w-0 flex-1 font-mono" title={name}>
      {shared && <span className="truncate text-muted-foreground">{shared}</span>}
      <span className="shrink-0">{name.slice(shared.length)}</span>
    </span>
  );
}

/** Why a server needs a fix, from server-scan's row: shown, as it decides what an install waives. */
function Problems({ candidate }: { candidate: Candidate }) {
  if (!candidate.offered || candidate.ready || candidate.health_problems.length === 0) return null;
  return (
    <span className="shrink-0 text-status-warning-fg" data-testid="candidate-problems">
      {candidate.health_problems.join(" · ")}
    </span>
  );
}

function GroupHeading({ group, count }: { group: GroupInfo; count: number }) {
  return (
    <div
      className="sticky top-0 z-10 flex items-center gap-1 border-b bg-muted px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
      data-testid="candidate-group"
      data-group={group.group}
    >
      <span>
        {group.label} <span className="tabular-nums">· {count}</span>
      </span>
      <Hint hint={group.hint} label={`About ${group.label}`}>
        <Info aria-hidden className="h-3 w-3" />
      </Hint>
    </div>
  );
}

function CandidateRow({
  candidate: c,
  prefix,
  selected,
  onToggle,
}: {
  candidate: Candidate;
  prefix: string | null;
  selected?: string[];
  onToggle?: (name: string) => void;
}) {
  const picked = selected?.includes(c.name) ?? false;
  return (
    <li
      data-testid="candidate"
      data-server={c.name}
      data-offered={c.offered}
      data-ready={c.ready}
      className={cn("flex items-center gap-2.5 px-2.5 py-1.5 text-xs", !c.offered && "text-muted-foreground")}
    >
      {selected && onToggle && (
        <Checkbox checked={picked} disabled={!c.offered} onCheckedChange={() => onToggle(c.name)} aria-label={`Install ${c.name}`} />
      )}
      <span
        role="img"
        aria-label={`health ${c.health}`}
        className={cn("h-1.5 w-1.5 shrink-0 rounded-full", HEALTH_TONE[c.health] ?? "bg-muted-foreground/50")}
        title={c.health}
      />
      <ServerName candidate={c} prefix={prefix} />
      <span className="hidden shrink-0 sm:inline">{hardwareLabel(c)}</span>
      <Problems candidate={c} />
      <Why candidate={c} />
    </li>
  );
}

/** Why the list is every free server: the pool's agentLabels name none, or were not read. */
function Unfiltered({ found }: { found: Candidates }) {
  const why = unnamedReason(found);
  if (why === null) return null;
  return (
    <p className="flex items-start gap-1 px-1 py-1 text-xs text-muted-foreground" data-testid="candidates-unfiltered">
      <Info aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>Every free server in server-scan, not filtered by name. {why}</span>
    </p>
  );
}

/**
 * A pool's servers in no MCE, as server-scan reports them, in three groups:
 * ready (a pool draw could pick them), needing a fix (with why) and not
 * offered (locked, in maintenance, contested; with why). They are the free
 * servers its InfraEnv's agentLabels name, or every free server, said so,
 * when those name none. With `selected`, a picker: a server that is not
 * offered cannot be picked, one that needs a fix can (the dialog then asks to
 * waive its health checks).
 */
export function CandidateList({
  found,
  isLoading,
  error,
  selected,
  onToggle,
}: {
  found: Candidates | undefined;
  isLoading: boolean;
  error: unknown;
  selected?: string[];
  onToggle?: (name: string) => void;
}) {
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  if (error) return <ProblemList error={error} title="The pool's servers could not be read" />;
  if (!found || found.candidates.length === 0) {
    const named = found?.server_prefix ? "is named for this pool" : "is in no MCE";
    return <p className="px-1 py-2 text-xs text-muted-foreground">No free server in server-scan {named}.</p>;
  }
  return (
    <div className="grid gap-1">
      <Unfiltered found={found} />
      <CandidateGroups found={found} selected={selected} onToggle={onToggle} />
    </div>
  );
}

function CandidateGroups({
  found,
  selected,
  onToggle,
}: {
  found: Candidates;
  selected?: string[];
  onToggle?: (name: string) => void;
}) {
  return (
    <div className="max-h-64 overflow-auto rounded-lg border" role="group" aria-label="Servers in no MCE">
      {groupCandidates(found.candidates).map(({ group, candidates: members }) => (
        <section key={group.group} aria-label={group.label}>
          <GroupHeading group={group} count={members.length} />
          <ul className="divide-y divide-border/60">
            {members.map((c) => (
              <CandidateRow key={c.id} candidate={c} prefix={found.server_prefix} selected={selected} onToggle={onToggle} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
