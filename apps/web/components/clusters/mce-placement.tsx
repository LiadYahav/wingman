"use client";

import { useId } from "react";
import { AlertTriangle, CircleCheck, CircleHelp, CircleMinus, CircleX, Info, RotateCcw, Server, Sparkles } from "lucide-react";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { BEHIND_ON, CHECK_NAMES, REASON_MAX, notCheckedChecks, unmetChecks } from "@/lib/placement";
import { cn } from "@/lib/utils";
import type { Placement, PlacementCandidate, PlacementNodeType, PlacementPods } from "@/types";

/** The candidates' columns: the label shown above a number on a phone, and in the header row from `sm` up. */
const COLUMNS = [
  { key: "owner", label: "Owner", title: "This owner's clusters on the MCE (fewest first)" },
  { key: "clusters", label: "Clusters", title: "Cluster files, plus open merge requests that create one there" },
  { key: "spare", label: "Spare", title: "Usable spare servers server-scan registers to the MCE (most first), of all its spare" },
  { key: "pods", label: "Free pods", title: "Allocatable pods less the pods running, on the workers: Ready, schedulable, untainted, neither control-plane nor infra" },
] as const;

const ROW = "grid grid-cols-[1.25rem_minmax(0,1fr)] sm:grid-cols-[1.25rem_minmax(0,1fr)_repeat(4,4.75rem)] gap-x-3";

/**
 * Wingman's MCE pick for a new cluster, and every candidate's numbers and
 * checks (ADR-0050). The pick comes first, with day1's reason; below it the
 * candidates as one radio group: an admin may choose another MCE that passes
 * every check, and then must say why. An MCE that fails a check, or that
 * Wingman could not read, cannot be chosen; its row says why.
 */
export function MCEPlacementPanel({
  placement,
  loading,
  error,
  onRetry,
  chosen,
  onChoose,
  reason,
  onReason,
  reasonInvalid,
}: {
  placement: Placement | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  /** The MCE the cluster goes to: the pick, or the admin's other choice. */
  chosen: string | null;
  onChoose: (mce: string) => void;
  reason: string;
  onReason: (reason: string) => void;
  /** The form was sent without a reason for an override. */
  reasonInvalid: boolean;
}) {
  const reasonId = useId();
  const reasonHintId = useId();

  if (loading && !placement) {
    return (
      <div data-testid="placement-loading" className="space-y-2" aria-busy="true" aria-label="Wingman is picking the MCE">
        <Skeleton className="h-20 rounded-lg" />
        <Skeleton className="h-28 rounded-lg" />
      </div>
    );
  }
  if (error && !placement) {
    return (
      <div data-testid="placement-error" className="space-y-2">
        <ProblemList error={error} title="Wingman could not pick the MCE" />
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
        >
          <RotateCcw className="h-3 w-3" aria-hidden />
          Try again
        </button>
      </div>
    );
  }
  if (!placement) return null;

  const pick = placement.pick;
  const override = chosen && chosen !== pick ? chosen : null;
  const scanError = placement.server_scan_error;

  return (
    <div data-testid="placement" className="space-y-3">
      {pick ? (
        <div
          data-testid="placement-pick"
          className={cn(
            "rounded-lg border px-4 py-3.5",
            override ? "border-border bg-muted/30" : "border-primary/30 bg-primary/5"
          )}
        >
          <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-primary">
            <Sparkles className="h-3 w-3" aria-hidden />
            Wingman&apos;s pick
          </p>
          <p className="mt-1 font-mono text-base font-semibold break-all" data-testid="placement-pick-name">{pick}</p>
          {placement.why && (
            <p className="mt-1 text-sm text-muted-foreground break-words" data-testid="placement-why">{placement.why}</p>
          )}
        </div>
      ) : (
        <div
          data-testid="placement-none"
          role="status"
          className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-4 py-3.5 text-sm text-status-warning-fg"
        >
          <p className="flex items-center gap-1.5 font-medium">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            {placement.candidates.length === 0
              ? `No ${placement.env} MCE on ${placement.site}`
              : `No ${placement.env} MCE on ${placement.site} can take this cluster`}
          </p>
          {placement.problems.length > 0 && (
            <ul className="mt-1.5 list-disc pl-5 space-y-0.5 text-xs" data-testid="placement-problems">
              {placement.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
            </ul>
          )}
        </div>
      )}

      {placement.candidates.length > 0 && (
        <div className="rounded-lg border">
          <div className={cn(ROW, "hidden sm:grid items-end border-b bg-muted/30 px-3 py-2 text-[11px] font-medium text-muted-foreground")}>
            <span aria-hidden />
            <span>MCE</span>
            {COLUMNS.map((c) => (
              <span key={c.key} className="text-right" title={c.title}>{c.label}</span>
            ))}
          </div>
          <div role="radiogroup" aria-label="MCE for the new cluster" className="divide-y">
            {placement.candidates.map((candidate) => (
              <CandidateRow
                key={candidate.mce}
                candidate={candidate}
                chosen={candidate.mce === chosen}
                onChoose={onChoose}
                hideSpareDetail={scanError !== null}
                liveReads={placement.live_reads}
              />
            ))}
          </div>
        </div>
      )}

      {override && pick && (
        <div
          data-testid="placement-override"
          className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-4 py-3.5 space-y-2 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150"
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <label htmlFor={reasonId} className="text-sm font-medium min-w-0 break-words">
              Why <span className="font-mono">{override}</span> instead of Wingman&apos;s pick?{" "}
              <span className="text-destructive">*</span>
            </label>
            <button
              type="button"
              data-testid="placement-use-pick"
              onClick={() => onChoose(pick)}
              className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              <RotateCcw className="h-3 w-3" aria-hidden />
              Use the pick
            </button>
          </div>
          <textarea
            id={reasonId}
            data-testid="placement-reason"
            value={reason}
            onChange={(e) => onReason(e.target.value)}
            maxLength={REASON_MAX}
            rows={2}
            required
            aria-invalid={reasonInvalid}
            aria-describedby={reasonHintId}
            placeholder="e.g. next to this owner's storage cluster"
            className={cn(
              "w-full rounded-lg border bg-background px-3 py-2 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary/50",
              reasonInvalid && "border-destructive focus:ring-destructive/20"
            )}
          />
          <p id={reasonHintId} className="flex justify-between gap-3 text-[11px] text-muted-foreground">
            <span>Recorded in the merge request, next to the numbers.</span>
            <span className="tabular-nums shrink-0">{reason.length}/{REASON_MAX}</span>
          </p>
        </div>
      )}

      <div className="space-y-1 text-[11px] text-muted-foreground">
        <p className="flex items-start gap-1.5">
          <Info className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
          <span>
            An MCE must host the version, have at least {placement.min_free_pods} free pods on its workers and enough
            healthy free servers of each node type the nodepools use, and answer Wingman. Among those: fewest clusters
            of this owner, then fewest clusters, then most usable spare servers.
          </span>
        </p>
        {!placement.live_reads ? (
          // One quiet note for every MCE: what was not checked, and why
          <p data-testid="placement-live-reads-off" className="flex items-start gap-1.5">
            <Info className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
            <span>
              Free pods and servers were not checked: this deployment does not read the MCEs live (live status is off).
              The pick rests on the version, this owner&apos;s clusters, the clusters and the spare servers.
            </span>
          </p>
        ) : placement.needs.length > 0 ? (
          <p data-testid="placement-needs" className="flex items-start gap-1.5">
            <Server className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
            <span className="min-w-0 [overflow-wrap:anywhere]">
              Servers counted for the nodepools:{" "}
              {placement.needs.map((need) => `${need.replicas} × ${need.infra_env}`).join(", ")}.
            </span>
          </p>
        ) : (
          <p data-testid="placement-no-needs" className="flex items-start gap-1.5">
            <Server className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
            <span>
              No nodepool names a node type yet, so servers are not checked. Once the nodepools have their InfraEnvs,
              each MCE&apos;s free servers of those types are, and the pick may change.
            </span>
          </p>
        )}
        {scanError && (
          <p data-testid="placement-server-scan" className="flex items-start gap-1.5">
            <Info className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
            <span className="break-words">{scanError}</span>
          </p>
        )}
        {pick && placement.problems.length > 0 && (
          <ul data-testid="placement-problems" className="list-disc pl-5 space-y-0.5">
            {placement.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function CandidateRow({
  candidate,
  chosen,
  onChoose,
  hideSpareDetail,
  liveReads,
}: {
  candidate: PlacementCandidate;
  chosen: boolean;
  onChoose: (mce: string) => void;
  /** server-scan's error already says why every MCE's spare servers are unknown. */
  hideSpareDetail: boolean;
  /** `false`: the MCE was not read live; its free pods and servers are "not checked", not a problem. */
  liveReads: boolean;
}) {
  const detailId = useId();
  const unmet = unmetChecks(candidate);
  // Readability is implied by the rest: name only the checks a person cares about
  const notChecked = notCheckedChecks(candidate).filter((check) => check.check !== "readable");
  const pods = candidate.pods;
  const podsBreakdown = pods
    ? `${pods.allocatable} allocatable less ${pods.used} in use, on ${pods.nodes_counted} worker${pods.nodes_counted === 1 ? "" : "s"}; ` +
      leftOut(pods.nodes_excluded)
    : liveReads
    ? "Unknown: Wingman could not read the MCE"
    : "Not checked: live MCE reads are off";
  return (
    <label
      data-testid={`placement-candidate-${candidate.mce}`}
      data-eligible={candidate.eligible}
      data-chosen={chosen}
      className={cn(
        ROW,
        "items-start px-3 py-2.5 text-sm transition-colors",
        candidate.eligible ? "cursor-pointer hover:bg-muted/40" : "cursor-not-allowed",
        chosen && "bg-primary/5 hover:bg-primary/5"
      )}
    >
      <input
        type="radio"
        name="placement-mce"
        value={candidate.mce}
        checked={chosen}
        disabled={!candidate.eligible}
        onChange={() => onChoose(candidate.mce)}
        aria-label={candidate.mce}
        aria-describedby={detailId}
        className="mt-0.5 h-4 w-4 accent-primary disabled:opacity-40"
      />
      <div className="min-w-0">
        <p className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", !candidate.eligible && "text-muted-foreground")}>
          <span className="font-mono font-medium break-all">{candidate.mce}</span>
          {candidate.picked && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
              Wingman&apos;s pick
            </span>
          )}
        </p>
        <div id={detailId} className="mt-0.5 space-y-0.5 text-xs">
          {candidate.eligible ? (
            <p className="flex items-start gap-1 text-status-ready-fg">
              <CircleCheck className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
              <span className="break-words">
                {notChecked.length > 0 ? "Passes the checks made" : "Passes every check"}
                {candidate.behind_on && (
                  <span className="text-muted-foreground"> · behind the pick: {BEHIND_ON[candidate.behind_on]}</span>
                )}
              </span>
            </p>
          ) : (
            // The servers check is told per node type, below
            unmet.filter((check) => check.check !== "servers" || candidate.node_types.length === 0).map((check) => (
              <p
                key={check.check}
                data-testid={`placement-check-${check.check}`}
                className={cn("flex items-start gap-1", check.status === "fail" ? "text-destructive" : "text-muted-foreground")}
              >
                {check.status === "fail" ? (
                  <CircleX className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
                ) : (
                  <CircleHelp className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
                )}
                <span className="break-words">
                  {check.status === "unknown" && "Unknown: "}
                  {check.detail}
                </span>
              </p>
            ))
          )}
          {notChecked.length > 0 && (
            <p data-testid="placement-not-checked" className="flex items-start gap-1 text-muted-foreground">
              <CircleMinus className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
              <span className="break-words">
                {notChecked.map((check) => CHECK_NAMES[check.check]).join(" and ")}: not checked
              </span>
            </p>
          )}
          {candidate.node_types.length > 0 && <NodeTypes types={candidate.node_types} />}
          {!candidate.spare && candidate.spare_detail && !hideSpareDetail && (
            <p className="text-muted-foreground break-words">{candidate.spare_detail}</p>
          )}
        </div>
      </div>
      <div className="col-start-2 mt-2 grid grid-cols-4 gap-x-2 sm:contents">
        <Cell label="Owner" testId="owner">
          {candidate.owner_clusters ?? <span className="text-muted-foreground" title="No owner given">—</span>}
        </Cell>
        <Cell
          label="Clusters"
          testId="clusters"
          note={candidate.open_creates > 0 ? `${candidate.open_creates} in an open MR` : undefined}
        >
          {candidate.clusters}
        </Cell>
        <Cell
          label="Spare"
          testId="spare"
          note={candidate.spare ? `of ${candidate.spare.total}` : undefined}
          title={candidate.spare ? `${candidate.spare.usable} usable of ${candidate.spare.total} spare` : candidate.spare_detail ?? undefined}
        >
          {candidate.spare ? candidate.spare.usable : <span className="text-[11px] text-muted-foreground font-normal">unknown</span>}
        </Cell>
        <Cell
          label="Free pods"
          testId="pods"
          note={pods ? `${pods.nodes_counted} node${pods.nodes_counted === 1 ? "" : "s"}` : undefined}
          title={podsBreakdown}
          srNote={podsBreakdown}
        >
          {pods ? (
            pods.free
          ) : (
            <span className="text-[11px] text-muted-foreground font-normal">{liveReads ? "unknown" : "not checked"}</span>
          )}
        </Cell>
      </div>
    </label>
  );
}

/** Why nodes were left out of the free pods, in the API's order; only the reasons that apply. */
const LEFT_OUT: [keyof PlacementPods["nodes_excluded"], string][] = [
  ["control_plane", "control-plane"],
  ["infra", "infra"],
  ["not_ready", "not Ready"],
  ["unschedulable", "cordoned"],
  ["tainted", "tainted"],
];

function leftOut(excluded: PlacementPods["nodes_excluded"]): string {
  const parts = LEFT_OUT.filter(([key]) => excluded[key] > 0).map(([key, label]) => `${excluded[key]} ${label}`);
  return parts.length > 0 ? `left out: ${parts.join(", ")}` : "no node left out";
}

/**
 * A candidate's servers, one line per node type the nodepools use: the
 * healthy free servers of that type against what the new cluster needs. A
 * type that fails or is unknown says why the MCE is not offered.
 */
function NodeTypes({ types }: { types: PlacementNodeType[] }) {
  return (
    <ul data-testid="placement-node-types" aria-label="Servers of each node type" className="space-y-0.5">
      {types.map((type) => (
        <li
          key={type.infra_env}
          data-testid={`placement-node-type-${type.infra_env}`}
          data-status={type.status}
          className={cn("flex items-start gap-1", type.status === "fail" ? "text-destructive" : "text-muted-foreground")}
        >
          {type.status === "fail" ? (
            <CircleX className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
          ) : type.status === "unknown" ? (
            <CircleHelp className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
          ) : (
            <Server className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
          )}
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {type.status === "unknown" && "Unknown: "}
            {type.detail}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** One number of a candidate: right-aligned, tabular; on a phone, labelled above. */
function Cell({
  label,
  testId,
  note,
  title,
  srNote,
  children,
}: {
  label: string;
  testId: string;
  note?: string;
  title?: string;
  srNote?: string;
  children: React.ReactNode;
}) {
  return (
    <span className="min-w-0 text-left sm:text-right" title={title} data-testid={`placement-cell-${testId}`}>
      <span className="block text-[10px] text-muted-foreground sm:hidden">{label}</span>
      <span className="block font-medium tabular-nums">{children}</span>
      {note && <span className="block text-[10px] leading-tight text-muted-foreground">{note}</span>}
      {srNote && <span className="sr-only">{srNote}</span>}
    </span>
  );
}
