"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { staleRun, useUpgradeDecision } from "@/lib/api/upgrades";
import { DECISION_TEXT, decisionsFor, needsReason, nodePoolsLeft, takesNodePool, takesReason } from "@/lib/upgrade";
import type { UpgradeDecision, UpgradeDecisionRequest, UpgradeRun } from "@/types";

const QUIET: ReadonlySet<UpgradeDecision> = new Set(["pause", "resume"]);

/** The heading of a refused decision, by its `code`; the run's own words are listed under it. */
function refusalTitle(error: unknown): string {
  if (isApiError(error, "UPGRADE_DECISION_REFUSED")) return "The run refused it";
  if (isApiError(error, "AMBIGUOUS_WRITE")) return "Sent but not confirmed: it may have landed. The page reads the run again.";
  if (isApiError(error, "NOT_FOUND")) return "The run is no longer open.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Not sent: the workflows orchestrator did not answer.";
  return "The decision was not taken.";
}

/**
 * The decisions an admin can send now (`decisionsFor`): each opens a small
 * confirmation, and the run's validators judge it.
 */
export function DecisionBar({ name, where, run }: { name: string; where: string; run: UpgradeRun }) {
  const [chosen, setChosen] = useState<UpgradeDecision | null>(null);
  const decisions = decisionsFor(run);
  if (decisions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2" data-testid="upgrade-decisions">
      {decisions.map((decision) => (
        <button
          key={decision}
          type="button"
          data-testid={`upgrade-decision-${decision}`}
          title={DECISION_TEXT[decision].explain}
          onClick={() => setChosen(decision)}
          className={buttonVariants({
            size: "sm",
            variant: decision === "abort" ? "destructive" : QUIET.has(decision) ? "outline" : "default",
          })}
        >
          {DECISION_TEXT[decision].label}
        </button>
      ))}
      {chosen && (
        <DecisionDialog name={name} where={where} run={run} decision={chosen} onClose={() => setChosen(null)} />
      )}
    </div>
  );
}

function DecisionDialog({
  name,
  where,
  run,
  decision,
  onClose,
}: {
  name: string;
  where: string;
  run: UpgradeRun;
  decision: UpgradeDecision;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [nodepool, setNodepool] = useState("");
  const decide = useUpgradeDecision(name, where);
  const text = DECISION_TEXT[decision];
  const required = needsReason(decision);
  const settled = staleRun(decide.error);
  const canSend = !decide.isPending && !settled && (!required || reason.trim() !== "");
  const left = takesNodePool(decision) ? nodePoolsLeft(run) : [];

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    const body: UpgradeDecisionRequest = {};
    if (takesReason(decision) && reason.trim()) body.reason = reason.trim();
    if (nodepool) body.nodepool = nodepool;
    decide.mutate(
      { decision, body },
      {
        onSuccess: () => {
          toast.success(`${text.label}: sent`);
          onClose();
        },
      }
    );
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !decide.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-md" showCloseButton={false} data-testid="upgrade-decision-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{text.label}?</DialogTitle>
            <DialogDescription>{text.explain}</DialogDescription>
          </DialogHeader>
          {left.length > 0 && (
            <label className="grid gap-1 text-xs text-muted-foreground">
              NodePool
              <select
                value={nodepool}
                onChange={(e) => setNodepool(e.target.value)}
                disabled={decide.isPending}
                data-testid="upgrade-decision-nodepool"
                className="rounded-md border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
              >
                <option value="">Next in the run&apos;s order ({left[0]})</option>
                {left.map((pool) => <option key={pool} value={pool}>{pool}</option>)}
              </select>
            </label>
          )}
          {takesReason(decision) && (
            <label className="grid gap-1 text-xs text-muted-foreground">
              {required ? "Reason (required)" : "Reason (optional)"}
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                maxLength={500}
                disabled={decide.isPending}
                data-testid="upgrade-decision-reason"
                className="rounded-md border bg-background px-2.5 py-1.5 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </label>
          )}
          {Boolean(decide.error) && (
            <div data-testid="upgrade-decision-error">
              <ProblemList error={decide.error} title={refusalTitle(decide.error)} />
            </div>
          )}
          <DialogFooter>
            <button type="button" onClick={onClose} disabled={decide.isPending} className={buttonVariants({ variant: "outline" })}>
              {settled ? "Close" : "Cancel"}
            </button>
            <button
              type="submit"
              disabled={!canSend}
              data-testid="upgrade-decision-submit"
              className={buttonVariants({ variant: decision === "abort" ? "destructive" : "default" })}
            >
              {decide.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {text.label}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
