"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, GitPullRequest, Network, RefreshCw, Unplug } from "lucide-react";
import { api } from "@/lib/api-client";
import { isPlanChanged, problemOf } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { inlineYaml } from "@/lib/values";
import { Checkbox } from "@/components/ui/checkbox";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ReviewDialog } from "@/components/common/review-dialog";
import { FindingsList } from "@/components/addons/findings";
import { FilePreview, MessageField, WriteError, type PlannedFile } from "@/components/addons/file-preview";
import { ReadOnlyNote } from "@/components/addons/team-access";
import type { Adoption, AdoptionChange, AuthoringChange, AuthoringPlan, DestinationImpact, PlannedFileChange } from "@/types/day2";

function plannedFile(file: PlannedFileChange): PlannedFile {
  const action: PlannedFile["action"] = file.action === "create" ? "create" : file.action === "delete" ? "delete" : "update";
  return { action, path: file.path, before: file.previous ?? undefined, after: file.content ?? undefined };
}

/** A clusters list, folded when it is long. */
function DestinationList({ ids, label }: { ids: string[]; label: string }) {
  if (ids.length === 0) return null;
  return (
    <details className="rounded-lg border bg-muted/20 px-3 py-2 text-xs" open={ids.length <= 4}>
      <summary className="cursor-pointer font-medium">
        <Network className="mr-1.5 inline h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        {label}
      </summary>
      <ul className="mt-1.5 space-y-0.5">
        {ids.map((id) => (
          <li key={id} className="break-all font-mono text-[11px] text-muted-foreground">
            {id}
          </li>
        ))}
      </ul>
    </details>
  );
}

function shown(value: unknown): string {
  return value === null || value === undefined ? "—" : inlineYaml(value);
}

/**
 * Each key a change moves, before and after, chart defaults aside. A key
 * set to a Helm null (`after_null`) deletes the chart's own default for that
 * key, which the table says; one that is simply no longer set shows "—".
 */
export function ChangesTable({ changes }: { changes: AdoptionChange[] }) {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
          <th className="py-0.5 pr-2 font-semibold">Stack</th>
          <th className="py-0.5 pr-2 font-semibold">Key</th>
          <th className="py-0.5 pr-2 font-semibold">Before</th>
          <th className="py-0.5 font-semibold">After</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((c) => {
          const helmNull = c.after_null === true;
          return (
            <tr key={`${c.stack}|${c.key}`} className="border-t border-border/50 font-mono text-[11px]">
              <td className="py-0.5 pr-2 font-sans">{c.stack === "deploy" ? "deploy config" : c.stack}</td>
              <td className="break-all py-0.5 pr-2">{c.key}</td>
              <td className="break-all py-0.5 pr-2">{shown(c.before)}</td>
              <td className="break-all py-0.5">
                {helmNull ? (
                  <span className="text-status-warning-fg" data-testid="helm-null">
                    null <span className="font-sans">— deletes the chart&apos;s own default for this key</span>
                  </span>
                ) : (
                  shown(c.after)
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AdoptionCard({ adoption, needsConfirmation }: { adoption: Adoption; needsConfirmation: boolean }) {
  return (
    <li
      className={cn("space-y-2 rounded-lg border p-3 text-xs", needsConfirmation && "border-status-warning/40 bg-status-warning/5")}
      data-testid={`adopted-${adoption.name}`}
    >
      <p className="font-semibold">
        {adoption.name} <span className="break-all font-mono text-[11px] font-normal text-muted-foreground">{adoption.cluster}</span>
      </p>
      {adoption.moved.length > 0 && (
        <ul className="space-y-0.5">
          {adoption.moved.map((m) => (
            <li key={m.from} className="flex flex-wrap items-center gap-1 font-mono text-[11px]">
              <span className="break-all">{m.from}</span>
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="moves to" />
              <span className="break-all">{m.to}</span>
            </li>
          ))}
        </ul>
      )}
      {adoption.deleted.length > 0 && (
        <p className="text-muted-foreground">
          Deletes <span className="break-all font-mono text-[11px]">{adoption.deleted.join(", ")}</span>
        </p>
      )}
      {adoption.gitkeep && (
        <p className="text-muted-foreground">
          It was the cluster&apos;s last folder: <code className="break-all">{adoption.gitkeep}</code> keeps it registered.
        </p>
      )}
      {adoption.exclusion_removed && (
        <p className="text-status-warning-fg">
          An old <code>exclusions.yaml</code> entry named it for this chart: the entry goes in the same commit, or the cluster
          would lose its app.
        </p>
      )}
      {adoption.changes.length === 0 ? (
        <p className="text-status-ready-fg">Unchanged: the same Application, with the same config and values.</p>
      ) : (
        <div className="space-y-1.5">
          <p className="font-medium text-status-warning-fg">This changes the cluster&apos;s app:</p>
          <ChangesTable changes={adoption.changes} />
        </div>
      )}
    </li>
  );
}

const EFFECT_TONE: Record<string, string> = {
  changed: "bg-primary/12 text-primary",
  added: "bg-status-ready/12 text-status-ready-fg",
  removed: "bg-status-error/12 text-status-error-fg",
};

function ImpactRow({ impact }: { impact: DestinationImpact }) {
  return (
    <li className="space-y-1.5 rounded-lg border p-3 text-xs" data-testid={`impact-${impact.name}`}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className={cn(
            "rounded px-1.5 py-px text-[10px] font-semibold uppercase",
            EFFECT_TONE[impact.effect] ?? "bg-muted text-muted-foreground",
          )}
        >
          {impact.effect}
        </span>
        <span className="font-semibold">{impact.name}</span>
        {impact.app_name && <code className="break-all font-mono text-[11px] text-muted-foreground">{impact.app_name}</code>}
      </p>
      {impact.changes.length > 0 ? (
        <ChangesTable changes={impact.changes} />
      ) : impact.effect === "added" ? (
        <p className="text-muted-foreground">
          ArgoCD generates the Application again; it adopts what is still running there.
        </p>
      ) : null}
    </li>
  );
}

/** The destinations whose Application goes: what that leaves running, said as loudly as a remove. */
function OrphanWarning({ removed }: { removed: DestinationImpact[] }) {
  return (
    <div
      className="space-y-2 rounded-lg border border-status-error/40 bg-status-error/8 p-3 text-sm"
      role="note"
      data-testid="orphan-warning"
    >
      <p className="flex items-start gap-2 font-semibold text-status-error-fg">
        <Unplug className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        {removed.length === 1
          ? `The Application on ${removed[0].name} is deleted, and its workload keeps running.`
          : `The Applications on ${removed.length} destinations are deleted, and their workloads keep running.`}
      </p>
      <p className="text-xs text-foreground/90">
        Leaf apps have <code>prune: false</code>, so ArgoCD orphans what each one deployed: it stays on the cluster,
        unmanaged, and nothing updates it. To tear it down, run{" "}
        <code className="rounded bg-muted px-1">argocd app delete &lt;app&gt; --cascade</code> on that cluster&apos;s ArgoCD
        after the merge (runbook R8). Wingman has no ArgoCD access.
      </p>
      <ul className="space-y-0.5 text-xs" aria-label="Applications deleted">
        {removed.map((r) => (
          <li key={r.cluster} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold">{r.name}</span>
            <code className="break-all font-mono text-[11px] text-muted-foreground">{r.app_name ?? r.cluster}</code>
            {r.orphaned && <span className="text-status-error-fg">orphaned</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** What an authoring write would do, from its dry run (ADR-0043, ADR-0053). */
export function PlanView({ plan }: { plan: AuthoringPlan }) {
  const impact = plan.impact ?? [];
  const removed = impact.filter((i) => i.effect === "removed");
  const others = impact.filter((i) => i.effect !== "removed");
  return (
    <div className="space-y-4" data-testid="authoring-plan">
      <p className="flex items-start gap-2 text-xs">
        <GitPullRequest className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
        <span className="min-w-0 break-words font-medium" data-testid="plan-title">
          {plan.title}
        </span>
      </p>
      <FindingsList findings={plan.warnings} showContext />
      {removed.length > 0 && <OrphanWarning removed={removed} />}
      {others.length > 0 && (
        <section className="space-y-2" aria-label="What changes on the destinations">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            On the destinations ({others.length})
          </p>
          <ul className="space-y-2">
            {others.map((i) => (
              <ImpactRow key={i.cluster} impact={i} />
            ))}
          </ul>
        </section>
      )}
      <div className="space-y-3">
        {plan.files.map((file) => (
          <FilePreview key={`${file.action}|${file.path}`} file={plannedFile(file)} />
        ))}
      </div>
      <DestinationList
        ids={plan.reach}
        label={`Reaches ${plan.reach.length} destination${plan.reach.length === 1 ? "" : "s"}`}
      />
      {plan.adopted.length > 0 && (
        <section className="space-y-2" aria-label="Clusters moving into the default">
          <p className="text-xs">
            <strong>
              {plan.adopted.length} cluster{plan.adopted.length === 1 ? " has" : "s have"} {plan.chart} in {plan.adopted.length === 1 ? "its" : "their"} own folder.
            </strong>{" "}
            The folder moves into the default in this merge request. The app keeps its name, so ArgoCD keeps the same
            Application: nothing is deleted, re-created or orphaned.
          </p>
          <ul className="space-y-2">
            {plan.adopted.map((a) => (
              <AdoptionCard key={a.cluster} adoption={a} needsConfirmation={plan.needs_confirmation.includes(a.cluster)} />
            ))}
          </ul>
        </section>
      )}
      {plan.notes.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-foreground/90 marker:text-muted-foreground">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A name for a destination id in a plan: its impact's or adoption's name, else the id. */
function nameIn(plan: AuthoringPlan, id: string): string {
  return plan.impact?.find((i) => i.cluster === id)?.name ?? plan.adopted.find((a) => a.cluster === id)?.name ?? id;
}

/** What the user has to acknowledge before the MR opens: the orphans, and every other app that changes. */
export interface Acknowledgements {
  /** Ids whose Application goes (impact `removed`). */
  removed: string[];
  /** Every other id of `needs_confirmation`. */
  changed: string[];
}

export function acknowledgementsOf(plan: AuthoringPlan): Acknowledgements {
  const removedIds = new Set((plan.impact ?? []).filter((i) => i.effect === "removed").map((i) => i.cluster));
  return {
    removed: plan.needs_confirmation.filter((id) => removedIds.has(id)),
    changed: plan.needs_confirmation.filter((id) => !removedIds.has(id)),
  };
}

/** The checkboxes that stand between a plan and its MR: one for the orphans, one for the changed apps. */
function Confirmations({
  plan,
  orphans,
  onOrphansChange,
  changes,
  onChangesChange,
}: {
  plan: AuthoringPlan;
  orphans: boolean;
  onOrphansChange: (on: boolean) => void;
  changes: boolean;
  onChangesChange: (on: boolean) => void;
}) {
  const ack = acknowledgementsOf(plan);
  if (ack.removed.length === 0 && ack.changed.length === 0) return null;
  // A name two destinations share is given as their ids, so the user sees which is which.
  const names = (ids: string[]) => {
    const given = ids.map((id) => nameIn(plan, id));
    return ids.map((id, i) => (given.indexOf(given[i]) !== given.lastIndexOf(given[i]) ? id : given[i])).join(", ");
  };
  return (
    <div className="space-y-2" data-testid="plan-confirmations">
      {ack.removed.length > 0 && (
        <label className="flex items-start gap-2 rounded-lg border border-status-error/40 bg-status-error/5 p-3 text-xs font-medium">
          <Checkbox checked={orphans} onCheckedChange={onOrphansChange} className="mt-px" />
          <span>
            {ack.removed.length === 1
              ? `Delete the Application on ${names(ack.removed)} and leave its workload running, unmanaged`
              : `Delete the Applications on ${names(ack.removed)} and leave their workloads running, unmanaged`}
          </span>
        </label>
      )}
      {ack.changed.length > 0 && (
        <label className="flex items-start gap-2 rounded-lg border border-status-warning/40 bg-status-warning/5 p-3 text-xs font-medium">
          <Checkbox checked={changes} onCheckedChange={onChangesChange} className="mt-px" />
          <span>
            {ack.changed.length === 1
              ? `I understand the app on ${names(ack.changed)} changes as listed`
              : `I understand the apps on these ${ack.changed.length} destinations change as listed: ${names(ack.changed)}`}
          </span>
        </label>
      )}
    </div>
  );
}

/**
 * An authoring write in two steps (ADR-0043, ADR-0053): the body's dry run
 * (`?dry_run=true`: every check, nothing opened), shown for review, then the
 * same body for real with `confirm_changes` (the dry run's
 * `needs_confirmation`, once the user ticked it) and `expected_digest` (the
 * dry run's `digest`). When the repo moved since the preview, the service
 * refuses with `plan-changed`: the hook previews again and shows the new plan,
 * never submitting one the user has not seen.
 */
export function useAuthoringWrite<B extends object>({
  method,
  url,
  onOpened,
}: {
  method: "post" | "put";
  url: (dryRun: boolean) => string;
  onOpened: (change: AuthoringChange) => void;
}) {
  const [reviewing, setReviewing] = useState(false);
  const [plan, setPlan] = useState<AuthoringPlan | null>(null);
  const [sent, setSent] = useState<B | null>(null);
  const [orphans, setOrphans] = useState(false);
  const [changes, setChanges] = useState(false);
  const [message, setMessage] = useState("");
  const [replanned, setReplanned] = useState(false);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);

  const send = <T,>(path: string, payload: unknown) => (method === "post" ? api.post<T>(path, payload) : api.put<T>(path, payload));

  function show(next: AuthoringPlan, body: B, again: boolean) {
    setPlan(next);
    setSent(body);
    setOrphans(false);
    setChanges(false);
    setReplanned(again);
    setSubmitError(null);
    setReviewing(true);
  }

  const preview = useMutation({
    mutationFn: (payload: B) => send<AuthoringPlan>(url(true), payload),
    onMutate: () => setPreviewError(null),
    onSuccess: (result, payload) => show(result, payload, false),
    onError: (error) => setPreviewError(error),
  });

  // The repo moved since the preview: the same body, previewed again.
  const replan = useMutation({
    mutationFn: (payload: B) => send<AuthoringPlan>(url(true), payload),
    onSuccess: (result, payload) => show(result, payload, true),
    onError: (error) => {
      setPlan(null);
      setSubmitError(error);
    },
  });

  const submit = useMutation({
    mutationFn: () => {
      if (!plan || !sent) throw new Error("Preview the change first.");
      const payload: Record<string, unknown> = {
        ...(sent as Record<string, unknown>),
        confirm_changes: plan.needs_confirmation,
        expected_digest: plan.digest ?? null,
      };
      if (message.trim()) payload.message = message.trim();
      return send<AuthoringChange>(url(false), payload);
    },
    onMutate: () => setSubmitError(null),
    onSuccess: (change) => {
      onOpened(change);
      setReviewing(false);
      setPlan(null);
      setSent(null);
      setMessage("");
      setReplanned(false);
    },
    onError: (error) => {
      if (isPlanChanged(problemOf(error)) && sent) replan.mutate(sent);
      else setSubmitError(error);
    },
  });

  const ack = plan ? acknowledgementsOf(plan) : { removed: [], changed: [] };
  const unconfirmed = (ack.removed.length > 0 && !orphans ? 1 : 0) + (ack.changed.length > 0 && !changes ? 1 : 0);

  return {
    plan,
    reviewing,
    replanned,
    replanning: replan.isPending,
    /** Run the dry run of `body` and open the review. */
    preview: (body: B) => preview.mutate(body),
    previewing: preview.isPending,
    previewError,
    clearPreviewError: () => setPreviewError(null),
    submit: () => submit.mutate(),
    submitting: submit.isPending || replan.isPending,
    submitError,
    /** Back to the form: the plan is dropped. */
    closeReview: () => {
      setReviewing(false);
      setSubmitError(null);
      setReplanned(false);
    },
    confirmations: { orphans, setOrphans, changes, setChanges },
    /** How many checkboxes are still to tick. */
    unconfirmed,
    message,
    setMessage,
  };
}

/** A write's review state, whatever its body. */
export type AuthoringWrite = Omit<ReturnType<typeof useAuthoringWrite<object>>, "preview">;

/** The review of an authoring write's plan, and the button that opens its MR. */
export function AuthoringReview({
  write,
  title,
  confirmLabel = "Confirm — Create MR",
  destructive = false,
}: {
  write: AuthoringWrite;
  title: string;
  confirmLabel?: string;
  /** The plan deletes Applications: a red button. */
  destructive?: boolean;
}) {
  const { plan, confirmations: c } = write;
  const removes = Boolean(plan?.impact?.some((i) => i.effect === "removed"));
  return (
    <ReviewDialog
      open={write.reviewing}
      onOpenChange={(next) => {
        if (!next) write.closeReview();
      }}
      title={title}
      description="What the merge request will do, checked by the service with every rule it applies. Nothing is opened until you confirm."
      onConfirm={write.submit}
      isPending={write.submitting}
      confirmDisabled={write.unconfirmed > 0 || !plan}
      confirmLabel={confirmLabel}
      confirmVariant={destructive || removes ? "destructive" : "default"}
      pendingLabel={write.replanning ? "The repo changed since your preview: previewing again…" : undefined}
      size="lg"
    >
      <div className="space-y-4">
        {write.replanned && (
          <p
            role="alert"
            data-testid="plan-changed"
            className="flex items-start gap-2 rounded-lg border border-status-warning/40 bg-status-warning/10 p-3 text-xs font-medium text-status-warning-fg"
          >
            <RefreshCw className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>
              The repo changed since your preview, so nothing was opened. This is the new plan: review it and confirm again.
            </span>
          </p>
        )}
        {plan && <PlanView plan={plan} />}
        {plan && (
          <Confirmations
            plan={plan}
            orphans={c.orphans}
            onOrphansChange={c.setOrphans}
            changes={c.changes}
            onChangesChange={c.setChanges}
          />
        )}
        {plan && write.unconfirmed > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-status-warning-fg" role="status">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
            Tick {write.unconfirmed === 1 ? "the confirmation" : "both confirmations"} to open the merge request.
          </p>
        )}
        <MessageField value={write.message} onChange={write.setMessage} />
        <WriteError error={write.submitError} />
      </div>
    </ReviewDialog>
  );
}

/**
 * An authoring write from a dialog: the form, then its plan for review, then
 * the MR (`useAuthoringWrite`). What was reviewed is what is sent.
 */
export function AuthoringDialogs<B extends object>({
  open,
  onOpenChange,
  title,
  description,
  children,
  blocker,
  readOnlyReason,
  body,
  method,
  url,
  confirmLabel = "Confirm — Create MR",
  wide = false,
  onOpened,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** The form's fields. */
  children: React.ReactNode;
  /** Why the form cannot be previewed yet, or `null`. */
  blocker: string | null;
  /** The team is read-only: the form shows why and cannot be sent. */
  readOnlyReason?: string | null;
  /** The request body, built when Preview is pressed. */
  body: () => B;
  method: "post" | "put";
  url: (dryRun: boolean) => string;
  confirmLabel?: string;
  /** A wider form (a values editor with its previews). */
  wide?: boolean;
  onOpened: (change: AuthoringChange) => void;
}) {
  const write = useAuthoringWrite<B>({
    method,
    url,
    onOpened: (change) => {
      onOpened(change);
      onOpenChange(false);
    },
  });
  const blocked = readOnlyReason ? "This team is read-only in Wingman" : blocker;

  return (
    <>
      <Dialog
        open={open && !write.reviewing}
        onOpenChange={(next) => {
          if (!next) {
            write.clearPreviewError();
            onOpenChange(false);
          }
        }}
      >
        <DialogContent className={cn("max-h-[92vh] w-[95vw] overflow-y-auto", wide ? "sm:max-w-5xl" : "sm:max-w-3xl")}>
          <DialogHeader>
            <DialogTitle className="break-words pr-8">{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {readOnlyReason && <ReadOnlyNote reason={readOnlyReason} />}
          <div className="space-y-4">{children}</div>
          <WriteError error={write.previewError} />
          <DialogFooter>
            <button type="button" onClick={() => onOpenChange(false)} className={buttonVariants({ variant: "outline" })}>
              Cancel
            </button>
            <button
              type="button"
              onClick={() => write.preview(body())}
              disabled={Boolean(blocked) || write.previewing}
              title={blocked ?? undefined}
              className={buttonVariants()}
            >
              {write.previewing ? "Checking…" : "Preview changes"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {open && <AuthoringReview write={write} title={title} confirmLabel={confirmLabel} />}
    </>
  );
}
