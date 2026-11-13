"use client";

import { useId, type ReactNode } from "react";
import {
  AlertTriangle, Check, CircleCheck, CircleDashed, CircleHelp, CircleMinus, CircleX, Info, RotateCcw, Server, Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { BEHIND_ON, CHECK_NAMES, REASON_MAX, notCheckedChecks, shortReason, unmetChecks } from "@/lib/placement";
import { cn } from "@/lib/utils";
import type { Placement, PlacementCandidate, PlacementPods } from "@/types";

/** The candidates' columns: the label shown above a number on a phone, and in the header row from `sm` up. */
const COLUMNS = [
  { key: "owner", label: "Owner", title: "This owner's clusters on the MCE (fewest first)" },
  { key: "clusters", label: "Clusters", title: "Cluster files, plus open merge requests that create one there" },
  { key: "spare", label: "Spare", title: "Usable spare servers server-scan registers to the MCE (most first), of all its spare" },
  { key: "pods", label: "Free pods", title: "Allocatable pods less the pods running, on the workers: Ready, schedulable, untainted, neither control-plane nor infra" },
] as const;

const ROW = "grid grid-cols-[1.25rem_minmax(0,1fr)] sm:grid-cols-[1.25rem_minmax(0,1fr)_repeat(4,4.75rem)] gap-x-3";

/**
 * How Wingman picks, behind the ⓘ beside the section's label: who it ranks
 * for, the checks, the ranking, and the servers it counted.
 */
export function PlacementRule({
  placement,
  owner,
  ranked,
}: {
  placement: Placement | undefined;
  /** The owner's mador as the form has it; `undefined` until it is a number. */
  owner: string | undefined;
  /** The placement shown was ranked for `owner` (not still asking). */
  ranked: boolean;
}) {
  const needs = placement?.live_reads ? placement.needs : [];
  return (
    <Hint
      label="How Wingman picks the MCE"
      testId="placement-rule"
      descriptionTestId="placement-rule-text"
      className="text-muted-foreground hover:text-foreground"
      hint={
        <>
          <span className="block" data-testid="placement-owner">
            {!owner
              ? "Not ranked by owner yet: the owner's mador spreads this owner's clusters."
              : ranked
              ? `Ranked for owner ${owner}.`
              : `Ranking for owner ${owner}…`}
          </span>
          <span className="mt-1 block">
            An MCE must host the version, have{" "}
            {placement ? `at least ${placement.min_free_pods}` : "enough"} free pods on its workers and enough healthy
            free servers of each node type the nodepools use, and answer Wingman.
          </span>
          <span className="mt-1 block">
            Among those: fewest clusters of this owner, then fewest clusters, then most usable spare servers. The owner
            and the nodepools refine the pick; neither is needed to see one.
          </span>
          {needs.length > 0 && (
            <span className="mt-1 block [overflow-wrap:anywhere]" data-testid="placement-needs">
              Servers counted for the nodepools: {needs.map((need) => `${need.replicas} × ${need.infra_env}`).join(", ")}.
            </span>
          )}
        </>
      }
    >
      <Info className="h-3.5 w-3.5" aria-hidden />
    </Hint>
  );
}

/**
 * Wingman's MCE pick for a new cluster, and every candidate (ADR-0050), as one
 * radio group: a row per MCE, its numbers, and one mark for its checks whose
 * reasons wait in a tooltip. The pick's row says so; an admin may choose
 * another row that passes, and then must say why. An MCE that fails a check,
 * or that Wingman could not read, cannot be chosen; its row says why in a
 * few words.
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
        <Skeleton className="h-9 rounded-lg" />
        <Skeleton className="h-20 rounded-lg" />
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
          className="inline-flex min-h-6 items-center gap-1.5 text-xs font-medium text-primary hover:underline"
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
  // At most one quiet line on what was not checked, or not known, for every MCE
  const note = !placement.live_reads
    ? { testId: "placement-live-reads-off", text: "Free pods and servers not checked (live status off)." }
    : placement.needs.length === 0
    ? { testId: "placement-no-needs", text: "Servers not checked until a nodepool names its node type; the pick may change then." }
    : scanError
    ? { testId: "placement-server-scan", text: scanError }
    : null;

  return (
    <div data-testid="placement" className="space-y-2">
      {!pick && (
        <div
          data-testid="placement-none"
          role="status"
          className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-4 py-3 text-sm text-status-warning-fg"
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
          <div className={cn(ROW, "hidden sm:grid items-end border-b bg-muted/30 px-3 py-1.5 text-[11px] font-medium text-muted-foreground")}>
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
                why={placement.why}
                version={placement.version}
                liveReads={placement.live_reads}
                scanError={scanError}
              />
            ))}
          </div>
        </div>
      )}

      {placement.candidates.length > 0 && note && (
        <p data-testid={note.testId} className="text-[11px] text-muted-foreground break-words">{note.text}</p>
      )}
      {pick && placement.problems.length > 0 && (
        <ul data-testid="placement-problems" className="list-disc pl-5 space-y-0.5 text-[11px] text-muted-foreground">
          {placement.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
        </ul>
      )}

      {override && pick && (
        <div
          data-testid="placement-override"
          className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-4 py-3 space-y-2 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150"
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
              className="inline-flex min-h-6 shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
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
    </div>
  );
}

/** A candidate's checks, as one mark: all pass, pass with some not checked, one fails, or one is unknown. */
type RowState = "pass" | "partly" | "fail" | "unknown";

const STATE_LABEL: Record<RowState, string> = {
  pass: "Passes every check",
  partly: "Passes the checks made",
  fail: "Fails a check",
  unknown: "A check is unknown",
};

function rowState(candidate: PlacementCandidate): RowState {
  if (!candidate.eligible) return unmetChecks(candidate).some((check) => check.status === "fail") ? "fail" : "unknown";
  return notCheckedChecks(candidate).length > 0 ? "partly" : "pass";
}

function StateIcon({ state }: { state: RowState }) {
  if (state === "pass") return <CircleCheck className="h-4 w-4 text-status-ready-fg" aria-hidden />;
  if (state === "fail") return <CircleX className="h-4 w-4 text-destructive" aria-hidden />;
  if (state === "unknown") return <CircleHelp className="h-4 w-4 text-muted-foreground" aria-hidden />;
  // Passed what was checked: a check in a dashed ring
  return (
    <span className="relative inline-flex h-4 w-4 text-status-ready-fg" aria-hidden>
      <CircleDashed className="h-4 w-4" />
      <Check className="absolute inset-0 m-auto h-2.5 w-2.5" strokeWidth={3} />
    </span>
  );
}

function CandidateRow({
  candidate,
  chosen,
  onChoose,
  why,
  version,
  liveReads,
  scanError,
}: {
  candidate: PlacementCandidate;
  chosen: boolean;
  onChoose: (mce: string) => void;
  why: string | null;
  version: string | null;
  /** `false`: the MCE was not read live; its free pods and servers are "not checked", not a problem. */
  liveReads: boolean;
  /** Why every MCE's spare servers are unknown, when they are. */
  scanError: string | null;
}) {
  const radioId = useId();
  const detailId = useId();
  const whyId = useId();
  const state = rowState(candidate);
  const short = shortReason(candidate, version);
  const pods = candidate.pods;
  return (
    <div
      data-testid={`placement-candidate-${candidate.mce}`}
      data-eligible={candidate.eligible}
      data-chosen={chosen}
      data-state={state}
      onClick={(event) => {
        // The whole row chooses, as before; the radio and its label already do
        if (!candidate.eligible || (event.target as HTMLElement).closest("input, label")) return;
        onChoose(candidate.mce);
      }}
      className={cn(
        ROW,
        "items-center px-3 py-1.5 text-sm transition-colors",
        candidate.eligible ? "cursor-pointer hover:bg-muted/40" : "cursor-not-allowed",
        chosen && "bg-primary/5 hover:bg-primary/5"
      )}
    >
      <input
        id={radioId}
        type="radio"
        name="placement-mce"
        value={candidate.mce}
        checked={chosen}
        disabled={!candidate.eligible}
        onChange={() => onChoose(candidate.mce)}
        aria-label={candidate.mce}
        aria-describedby={candidate.picked ? `${whyId} ${detailId}` : detailId}
        className="h-4 w-4 accent-primary disabled:opacity-40"
      />
      <div className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5">
        <label
          htmlFor={radioId}
          data-testid={candidate.picked ? "placement-pick-name" : undefined}
          className={cn(
            "font-mono font-medium break-all",
            candidate.eligible ? "cursor-pointer" : "cursor-not-allowed text-muted-foreground"
          )}
        >
          {candidate.mce}
        </label>
        <Hint
          label={STATE_LABEL[state]}
          testId="placement-state"
          className="-ml-1"
          descriptionId={detailId}
          hint={<RowDetail candidate={candidate} state={state} liveReads={liveReads} />}
        >
          <StateIcon state={state} />
        </Hint>
        {short && (
          <span data-testid="placement-short" className="text-xs text-muted-foreground">{short}</span>
        )}
        {candidate.picked && (
          <Hint
            testId="placement-pick"
            descriptionId={whyId}
            descriptionTestId="placement-why"
            hint={why ?? "Wingman's pick"}
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
              <Sparkles className="h-3 w-3" aria-hidden />
              Wingman&apos;s pick
            </span>
          </Hint>
        )}
      </div>
      <div className="col-start-2 mt-1 grid grid-cols-4 gap-x-2 sm:mt-0 sm:contents">
        <Cell label="Owner" testId="owner">
          {candidate.owner_clusters ?? <Dash label="No owner" hint="No owner given: enter the owner's mador to rank by it." />}
        </Cell>
        <Cell
          label="Clusters"
          testId="clusters"
          title={candidate.open_creates > 0 ? openCreates(candidate) : undefined}
        >
          {candidate.clusters}
        </Cell>
        <Cell
          label="Spare"
          testId="spare"
          title={candidate.spare ? `${candidate.spare.usable} usable of ${candidate.spare.total} spare` : undefined}
        >
          {candidate.spare ? (
            candidate.spare.usable
          ) : (
            <Dash label="Spare servers unknown" hint={scanError ?? candidate.spare_detail ?? "Unknown."} />
          )}
        </Cell>
        <Cell label="Free pods" testId="pods" title={pods ? podsBreakdown(pods) : undefined}>
          {pods ? (
            pods.free
          ) : liveReads ? (
            <Dash label="Free pods unknown" hint="Unknown: Wingman could not read the MCE." />
          ) : (
            <Dash label="Free pods not checked" hint="Not checked: live status is off, so Wingman does not read the MCEs." />
          )}
        </Cell>
      </div>
    </div>
  );
}

/**
 * Everything a row's mark stands for: its checks (each failing or unknown
 * one in day1's words, each node type's servers, what was not checked), where
 * it ranks behind the pick, and what its numbers are made of.
 */
function RowDetail({ candidate, state, liveReads }: { candidate: PlacementCandidate; state: RowState; liveReads: boolean }) {
  // Readability is implied by the rest: name only the checks a person cares about
  const notChecked = notCheckedChecks(candidate).filter((check) => check.check !== "readable");
  const numbers = [
    candidate.open_creates > 0 && openCreates(candidate),
    candidate.spare && `${candidate.spare.usable} usable of ${candidate.spare.total} spare servers.`,
    candidate.pods && `Free pods: ${podsBreakdown(candidate.pods)}.`,
  ].filter((line): line is string => Boolean(line));
  return (
    <>
      <span className="block font-medium">
        {STATE_LABEL[state]}
        {candidate.eligible && candidate.behind_on && (
          <span data-testid="placement-behind" className="font-normal"> · behind the pick: {BEHIND_ON[candidate.behind_on]}</span>
        )}
      </span>
      {!candidate.eligible &&
        // The servers check is told per node type, below
        unmetChecks(candidate)
          .filter((check) => check.check !== "servers" || candidate.node_types.length === 0)
          .map((check) => (
            <Line
              key={check.check}
              testId={`placement-check-${check.check}`}
              icon={check.status === "fail" ? CircleX : CircleHelp}
            >
              {check.status === "unknown" && "Unknown: "}
              {check.detail}
            </Line>
          ))}
      {candidate.node_types.length > 0 && (
        <span data-testid="placement-node-types" className="block">
          {candidate.node_types.map((type) => (
            <Line
              key={type.infra_env}
              testId={`placement-node-type-${type.infra_env}`}
              status={type.status}
              icon={type.status === "fail" ? CircleX : type.status === "unknown" ? CircleHelp : Server}
            >
              {type.status === "unknown" && "Unknown: "}
              {type.detail}
            </Line>
          ))}
        </span>
      )}
      {notChecked.length > 0 && (
        <Line testId="placement-not-checked" icon={CircleMinus}>
          {upperFirst(notChecked.map((check) => CHECK_NAMES[check.check]).join(" and "))}: not checked
          {liveReads ? "." : " (live status off)."}
        </Line>
      )}
      {numbers.length > 0 && (
        <span className="mt-1 block opacity-80">
          {numbers.map((line) => <span key={line} className="block">{line}</span>)}
        </span>
      )}
    </>
  );
}

/** One reason in a row's tooltip: a small icon, then the words. */
function Line({ icon: Icon, testId, status, children }: { icon: LucideIcon; testId?: string; status?: string; children: ReactNode }) {
  return (
    <span data-testid={testId} data-status={status} className="flex items-start gap-1.5">
      <Icon className="mt-[3px] h-3 w-3 shrink-0" aria-hidden />
      <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </span>
  );
}

/** A number Wingman does not have: a dash, and why in its tooltip. */
function Dash({ label, hint }: { label: string; hint: string }) {
  return (
    <Hint label={label} hint={hint} className="-my-1 font-normal text-muted-foreground">
      —
    </Hint>
  );
}

function openCreates(candidate: PlacementCandidate): string {
  return `${candidate.open_creates} of its ${candidate.clusters} clusters in an open merge request.`;
}

function podsBreakdown(pods: PlacementPods): string {
  return (
    `${pods.allocatable} allocatable less ${pods.used} in use, on ${pods.nodes_counted} worker${pods.nodes_counted === 1 ? "" : "s"}; ` +
    leftOut(pods.nodes_excluded)
  );
}

function upperFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
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

/** One number of a candidate: right-aligned, tabular; on a phone, labelled above. */
function Cell({ label, testId, title, children }: { label: string; testId: string; title?: string; children: ReactNode }) {
  return (
    <span className="min-w-0 text-left sm:text-right" title={title} data-testid={`placement-cell-${testId}`}>
      <span className="block text-[10px] text-muted-foreground sm:hidden">{label}</span>
      <span className="block font-medium tabular-nums">{children}</span>
    </span>
  );
}
