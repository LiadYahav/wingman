"use client";

import { Info, Lock, Wrench } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { ServerLink } from "@/components/server-scan/server-link";
import { useServerScanArea } from "@/lib/api/server-scan";
import { hardwareLabel } from "@/lib/inventory/pools";
import { groupCandidates, type GroupInfo } from "@/lib/inventory/waiver";
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

/**
 * The name, its pool's shared prefix muted and cut first, so the part that
 * differs stays whole. With `link`, a link to the server's page in the Server
 * Scan area (in a new tab from the install dialog's picker, `newTab`).
 */
function ServerName({ candidate, prefix, link, newTab }: { candidate: Candidate; prefix: string; link: boolean; newTab: boolean }) {
  const { name } = candidate;
  const shared = name.startsWith(prefix) ? prefix : "";
  const text = (
    <>
      {shared && <span className="truncate text-muted-foreground">{shared}</span>}
      <span className="shrink-0">{name.slice(shared.length)}</span>
    </>
  );
  if (!link) {
    return (
      <span className="flex min-w-0 flex-1 font-mono" title={name}>
        {text}
      </span>
    );
  }
  return (
    <span className="flex min-w-0 flex-1" title={name}>
      <ServerLink id={candidate.id} newTab={newTab} className="flex min-w-0 font-mono">
        {text}
      </ServerLink>
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
  infraEnv,
  linked,
  selected,
  onToggle,
}: {
  candidate: Candidate;
  infraEnv: string;
  linked: boolean;
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
      <ServerName candidate={c} prefix={`ocp-${infraEnv}`} link={linked} newTab={Boolean(selected)} />
      <span className="hidden shrink-0 sm:inline">{hardwareLabel(c)}</span>
      <Problems candidate={c} />
      <Why candidate={c} />
    </li>
  );
}

/**
 * A pool's servers in no MCE, as server-scan reports them, in three groups:
 * ready (a pool draw could pick them), needing a fix (with why) and not
 * offered (locked, in maintenance, contested; with why). With `selected`, a
 * picker: a server that is not offered cannot be picked, one that needs a fix
 * can (the dialog then asks to waive its health checks).
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
  // A server's page is in the Server Scan area: a link for whoever has it, text for anyone else
  const linked = useServerScanArea() === true;
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  if (error) return <ProblemList error={error} title="The pool's servers could not be read" />;
  if (!candidates || candidates.length === 0) {
    return <p className="px-1 py-2 text-xs text-muted-foreground">No free server in server-scan is named for this pool.</p>;
  }
  return (
    <div className="max-h-64 overflow-auto rounded-lg border" role="group" aria-label="Servers in no MCE">
      {groupCandidates(candidates).map(({ group, candidates: members }) => (
        <section key={group.group} aria-label={group.label}>
          <GroupHeading group={group} count={members.length} />
          <ul className="divide-y divide-border/60">
            {members.map((c) => (
              <CandidateRow key={c.id} candidate={c} infraEnv={infraEnv} linked={linked} selected={selected} onToggle={onToggle} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
