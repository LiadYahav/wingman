"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { staleRun, useStartUpgrade, useUpgradeTargets } from "@/lib/api/upgrades";
import { changedMaxUnavailable } from "@/lib/upgrade";
import { NodePoolOrder, OptionsFields, TargetList, type Options } from "@/components/clusters/upgrade/upgrade-fields";
import type { StartUpgradeRequest, UpgradeTargets } from "@/types";

/** The heading of a targets read that failed, by its `code`; the workflow's detail is listed under it. */
function targetsErrorTitle(error: unknown): string {
  if (isApiError(error, "UPGRADE_TARGETS_REFUSED")) return "The workflow cannot plan an upgrade of this cluster.";
  if (isApiError(error, "NOT_FOUND")) return "The workflow's day1 repo has no file for this cluster.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "The workflow did not answer.";
  return "The targets could not be read.";
}

/** The heading of a refused start, by its `code`. */
function startErrorTitle(error: unknown): string {
  if (isApiError(error, "UPGRADE_ALREADY_RUNNING")) return "This cluster already has an upgrade run; the page shows it.";
  if (isApiError(error, "AMBIGUOUS_WRITE")) {
    return "The start was sent but not confirmed, so it may have started: the page reads the run again.";
  }
  if (isApiError(error, "VALIDATION_ERROR")) return "The workflow refused the request.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: the workflows orchestrator did not answer.";
  return "The upgrade did not start.";
}

/** The NodePools in the workflow's default roll order, then any it did not order. */
function inOrder(targets: UpgradeTargets): string[] {
  const names = targets.nodepools.map((p) => p.name);
  return [...targets.nodepool_order.filter((n) => names.includes(n)), ...names.filter((n) => !targets.nodepool_order.includes(n))];
}

/**
 * Start the platform's upgrade-cluster workflow on one cluster, toward a
 * target the workflow offers. Starting is its dry run: it plans and checks,
 * then waits for approval with nothing committed. Mount it while open: its
 * state is one start's.
 */
export function UpgradeDialog({ name, where, onClose }: { name: string; where: string; onClose: () => void }) {
  const targets = useUpgradeTargets(name, where, true);
  const start = useStartUpgrade(name, where);
  const pending = start.isPending;
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="upgrade-dialog">
        <DialogHeader>
          <DialogTitle>Upgrade <span className="font-mono break-all">{name}</span></DialogTitle>
          <DialogDescription>
            Start plans and checks, then waits for your approval. Nothing is committed before you approve.
          </DialogDescription>
        </DialogHeader>
        {targets.isLoading ? (
          <p data-testid="upgrade-targets-loading" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
            Asking the workflow for targets. This can take up to a minute.
          </p>
        ) : targets.error || !targets.data ? (
          <>
            <div data-testid="upgrade-targets-error">
              <ProblemList error={targets.error} title={targetsErrorTitle(targets.error)} />
            </div>
            <DialogFooter>
              <button type="button" onClick={onClose} className={buttonVariants({ variant: "outline" })}>Close</button>
            </DialogFooter>
          </>
        ) : (
          <UpgradeForm targets={targets.data} start={start} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** The start request: the target, and only what was changed from the workflow's defaults. */
function startRequest(
  target: string,
  order: string[],
  defaultOrder: string[],
  limits: Record<string, string>,
  targets: UpgradeTargets,
  options: Options
): StartUpgradeRequest {
  const body: StartUpgradeRequest = { target_version: target };
  if (order.join("\n") !== defaultOrder.join("\n")) body.nodepool_order = order;
  const fileLimits = Object.fromEntries(targets.nodepools.map((p) => [p.name, p.max_unavailable]));
  const maxUnavailable = changedMaxUnavailable(limits, fileLimits);
  if (maxUnavailable) body.max_unavailable = maxUnavailable;
  if (options.controlPlaneOnly) body.workers_to_target = false;
  if (options.auto) body.nodepool_mode = "auto";
  if (options.autoApprove) body.auto_approve = true;
  return body;
}

function UpgradeForm({
  targets,
  start,
  onClose,
}: {
  targets: UpgradeTargets;
  start: ReturnType<typeof useStartUpgrade>;
  onClose: () => void;
}) {
  const defaultOrder = inOrder(targets);
  const [target, setTarget] = useState<string | null>(null);
  const [order, setOrder] = useState(defaultOrder);
  const [limits, setLimits] = useState<Record<string, string>>(
    Object.fromEntries(targets.nodepools.map((p) => [p.name, p.max_unavailable ?? ""]))
  );
  const [options, setOptions] = useState<Options>({ controlPlaneOnly: false, auto: false, autoApprove: false });
  const pending = start.isPending;
  const settled = staleRun(start.error);
  const canStart = target !== null && !pending && !settled;
  const offered = targets.targets.length > 0;

  const move = (index: number, by: number) =>
    setOrder((current) => {
      const next = [...current];
      [next[index], next[index + by]] = [next[index + by], next[index]];
      return next;
    });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canStart || target === null) return;
    start.mutate(startRequest(target, order, defaultOrder, limits, targets, options), {
      onSuccess: () => {
        toast.success("Upgrade started", { description: "It plans and checks, then waits for approval." });
        onClose();
      },
    });
  };

  return (
    <form onSubmit={submit} className="grid gap-4">
      <p className="text-xs text-muted-foreground" data-testid="upgrade-targets-facts">
        Runs <span className="font-mono text-foreground">{targets.control_plane_version ?? "—"}</span>. MCE{" "}
        <span className="font-mono">{targets.mce}</span> ({targets.mce_version}) supports{" "}
        {targets.supported_minors.join(", ") || "none"}.
        {targets.verified_against_graph && <> Ladder checked {targets.verified_against_graph}.</>}
      </p>
      <TargetList targets={targets} target={target} onChoose={setTarget} disabled={pending} />
      {offered && order.length > 0 && !options.controlPlaneOnly && (
        <NodePoolOrder
          order={order}
          zones={Object.fromEntries(targets.nodepools.map((p) => [p.name, p.zone]))}
          limits={limits}
          onMove={move}
          onLimit={(pool, value) => setLimits((current) => ({ ...current, [pool]: value }))}
          disabled={pending}
        />
      )}
      {offered && <OptionsFields options={options} onChange={setOptions} disabled={pending} />}
      {Boolean(start.error) && (
        <div data-testid="upgrade-start-error">
          <ProblemList error={start.error} title={startErrorTitle(start.error)} />
        </div>
      )}
      <DialogFooter>
        <button type="button" onClick={onClose} disabled={pending} className={buttonVariants({ variant: "outline" })}>
          {settled ? "Close" : "Cancel"}
        </button>
        {offered && (
          <button type="submit" disabled={!canStart} data-testid="upgrade-start" className={buttonVariants()}>
            {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {pending ? "Starting…" : "Start"}
          </button>
        )}
      </DialogFooter>
    </form>
  );
}
