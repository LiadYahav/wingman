"use client";

import { toast } from "sonner";
import { Bot } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { useUpgradeActionDecision } from "@/lib/api/upgrades";
import { humanize } from "@/lib/nodes";
import { proposalsOpen } from "@/lib/upgrade";
import type { UpgradeRun } from "@/types";

/**
 * The upgrade agent's last verdict and its proposals. It is asked only when
 * a gate fails or a watch stalls; it proposes, a person decides. An approved
 * action runs with the workflow's identity, then the run waits for Retry.
 */
export function AgentProposals({ name, where, run, isAdmin }: { name: string; where: string; run: UpgradeRun; isAdmin: boolean }) {
  const decide = useUpgradeActionDecision(name, where);
  const verdict = run.last_verdict;
  if (!verdict && run.pending_actions.length === 0) return null;
  const open = isAdmin && proposalsOpen(run);
  const send = (actionId: string, approve: boolean) =>
    decide.mutate(
      { actionId, approve },
      { onSuccess: () => toast.success(approve ? "Proposal approved" : "Proposal rejected") }
    );
  return (
    <div className="space-y-2 rounded-lg border bg-muted/20 px-3 py-2.5 text-sm" data-testid="upgrade-agent">
      {verdict && (
        <p className="flex items-start gap-2">
          <Bot className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="min-w-0 break-words">
            {verdict.diagnosis}{" "}
            <span className="text-xs text-muted-foreground">
              ({humanize(verdict.confidence).toLowerCase()}; {humanize(verdict.verdict).toLowerCase()})
            </span>
          </span>
        </p>
      )}
      {run.pending_actions.length > 0 && (
        <ul className="space-y-1.5">
          {run.pending_actions.map((p) => (
            <li key={p.action_id} data-testid="upgrade-proposal" className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 space-y-0.5">
                <p className="break-words">
                  <span className="font-medium">{humanize(p.kind)}</span>{" "}
                  <span className="font-mono text-xs">{p.target}</span>
                </p>
                {p.rationale && <p className="text-xs text-muted-foreground break-words">{p.rationale}</p>}
                {Object.keys(p.args).length > 0 && (
                  <p className="font-mono text-xs text-muted-foreground break-all">
                    {Object.entries(p.args).map(([k, v]) => `${k}=${v}`).join(" ")}
                  </p>
                )}
              </div>
              {p.decision === "pending" && open ? (
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => send(p.action_id, true)}
                    title="Run this action with the workflow's identity; then Retry"
                    className={buttonVariants({ size: "xs" })}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => send(p.action_id, false)}
                    title="Record it and never run it; then Retry or Abort"
                    className={buttonVariants({ size: "xs", variant: "outline" })}
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {humanize(p.decision)}
                  {p.decided_by && ` by ${p.decided_by}`}
                  {p.executed && ", ran"}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {Boolean(decide.error) && <ProblemList error={decide.error} title="The proposal was not decided" />}
    </div>
  );
}
