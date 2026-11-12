"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, GitPullRequest, Network } from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { inlineYaml } from "@/lib/values";
import { Checkbox } from "@/components/ui/checkbox";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ReviewDialog } from "@/components/common/review-dialog";
import { FindingsList } from "@/components/addons/findings";
import { FilePreview, MessageField, WriteError, type PlannedFile } from "@/components/addons/file-preview";
import { ReadOnlyNote } from "@/components/addons/team-access";
import type { Adoption, AuthoringChange, AuthoringPlan, PlannedFileChange } from "@/types/day2";

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

function AdoptionCard({
  adoption,
  needsConfirmation,
  confirmed,
  onConfirmedChange,
}: {
  adoption: Adoption;
  needsConfirmation: boolean;
  confirmed: boolean;
  onConfirmedChange: (on: boolean) => void;
}) {
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
      {adoption.changes.length === 0 ? (
        <p className="text-status-ready-fg">Unchanged: the same Application, with the same config and values.</p>
      ) : (
        <div className="space-y-1.5">
          <p className="font-medium text-status-warning-fg">This changes the cluster&apos;s app:</p>
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
              {adoption.changes.map((c) => (
                <tr key={`${c.stack}|${c.key}`} className="border-t border-border/50 font-mono text-[11px]">
                  <td className="py-0.5 pr-2 font-sans">{c.stack === "deploy" ? "deploy config" : c.stack}</td>
                  <td className="break-all py-0.5 pr-2">{c.key}</td>
                  <td className="break-all py-0.5 pr-2">{c.before === null || c.before === undefined ? "—" : inlineYaml(c.before)}</td>
                  <td className="break-all py-0.5">{c.after === null || c.after === undefined ? "—" : inlineYaml(c.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {needsConfirmation && (
            <label className="flex items-start gap-2 font-medium">
              <Checkbox checked={confirmed} onCheckedChange={onConfirmedChange} className="mt-px" />
              <span>I understand {adoption.name} changes as listed</span>
            </label>
          )}
        </div>
      )}
    </li>
  );
}

/** What an authoring write would do, from its dry run (ADR-0043). */
export function PlanView({
  plan,
  confirmed,
  onConfirmedChange,
}: {
  plan: AuthoringPlan;
  confirmed: ReadonlySet<string>;
  onConfirmedChange: (cluster: string, on: boolean) => void;
}) {
  return (
    <div className="space-y-4" data-testid="authoring-plan">
      <p className="flex items-start gap-2 text-xs">
        <GitPullRequest className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
        <span className="min-w-0 break-words font-medium">{plan.title}</span>
      </p>
      <FindingsList findings={plan.warnings} showContext />
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
              <AdoptionCard
                key={a.cluster}
                adoption={a}
                needsConfirmation={plan.needs_confirmation.includes(a.cluster)}
                confirmed={confirmed.has(a.cluster)}
                onConfirmedChange={(on) => onConfirmedChange(a.cluster, on)}
              />
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

/**
 * An authoring write in two steps (ADR-0043): the form, then its dry run
 * (`?dry_run=true`, every check, nothing opened) for review, then the same
 * body for real. What was reviewed is what is sent; clusters the dry run says
 * would change must each be confirmed, and go in `confirm_changes`.
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
  withConfirmations = false,
  confirmLabel = "Confirm — Create MR",
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
  /** Make default: the body carries `confirm_changes`. */
  withConfirmations?: boolean;
  confirmLabel?: string;
  onOpened: (change: AuthoringChange) => void;
}) {
  const [reviewing, setReviewing] = useState(false);
  const [plan, setPlan] = useState<AuthoringPlan | null>(null);
  const [sent, setSent] = useState<B | null>(null);
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);

  const send = <T,>(path: string, payload: unknown) => (method === "post" ? api.post<T>(path, payload) : api.put<T>(path, payload));

  const preview = useMutation({
    mutationFn: (payload: B) => send<AuthoringPlan>(url(true), payload),
    onMutate: () => setPreviewError(null),
    onSuccess: (result, payload) => {
      setPlan(result);
      setSent(payload);
      setConfirmed(new Set());
      setSubmitError(null);
      setReviewing(true);
    },
    onError: (error) => setPreviewError(error),
  });

  const submit = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = { ...((sent ?? body()) as Record<string, unknown>) };
      if (message.trim()) payload.message = message.trim();
      if (withConfirmations) payload.confirm_changes = (plan?.needs_confirmation ?? []).filter((id) => confirmed.has(id));
      return send<AuthoringChange>(url(false), payload);
    },
    onMutate: () => setSubmitError(null),
    onSuccess: (change) => {
      onOpened(change);
      setReviewing(false);
      setPlan(null);
      setMessage("");
      onOpenChange(false);
    },
    onError: (error) => setSubmitError(error),
  });

  const unconfirmed = (plan?.needs_confirmation ?? []).filter((id) => !confirmed.has(id));
  const blocked = readOnlyReason ? "This team is read-only in Wingman" : blocker;

  return (
    <>
      <Dialog
        open={open && !reviewing}
        onOpenChange={(next) => {
          if (!next) {
            setPreviewError(null);
            onOpenChange(false);
          }
        }}
      >
        <DialogContent className="max-h-[92vh] w-[95vw] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="break-words pr-8">{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {readOnlyReason && <ReadOnlyNote reason={readOnlyReason} />}
          <div className="space-y-4">{children}</div>
          <WriteError error={previewError} />
          <DialogFooter>
            <button type="button" onClick={() => onOpenChange(false)} className={buttonVariants({ variant: "outline" })}>
              Cancel
            </button>
            <button
              type="button"
              onClick={() => preview.mutate(body())}
              disabled={Boolean(blocked) || preview.isPending}
              title={blocked ?? undefined}
              className={buttonVariants()}
            >
              {preview.isPending ? "Checking…" : "Preview changes"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReviewDialog
        open={open && reviewing}
        onOpenChange={(next) => {
          if (!next) {
            setReviewing(false);
            setSubmitError(null);
          }
        }}
        title={title}
        description="What the merge request will do, checked by the service with every rule it applies. Nothing is opened until you confirm."
        onConfirm={() => submit.mutate()}
        isPending={submit.isPending}
        confirmDisabled={unconfirmed.length > 0 || !plan}
        confirmLabel={confirmLabel}
        size="lg"
      >
        <div className="space-y-4">
          {plan && (
            <PlanView
              plan={plan}
              confirmed={confirmed}
              onConfirmedChange={(cluster, on) =>
                setConfirmed((prev) => {
                  const next = new Set(prev);
                  if (on) next.add(cluster);
                  else next.delete(cluster);
                  return next;
                })
              }
            />
          )}
          {unconfirmed.length > 0 && (
            <p className="text-xs text-status-warning-fg" role="status">
              Confirm each cluster whose app changes ({unconfirmed.length} left) to open the merge request.
            </p>
          )}
          <MessageField value={message} onChange={setMessage} />
          <WriteError error={submitError} />
        </div>
      </ReviewDialog>
    </>
  );
}
