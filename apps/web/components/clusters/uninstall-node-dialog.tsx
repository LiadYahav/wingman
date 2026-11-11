"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2, PowerOff, Replace, Undo2, Unplug, type LucideIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { STALE_LIST_CODES, useUninstallNode } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { ClusterNode, WorkflowRun } from "@/types";

/**
 * What the workflow does, in short (the API note's §2). The workflow's own
 * documentation is the authority; Wingman starts it and shows its run.
 */
const SUMMARY: { icon: LucideIcon; text: string; emphasis?: boolean }[] = [
  { icon: Unplug, text: "Drains the node and deletes its Machine." },
  {
    icon: PowerOff,
    text: "Takes the server out of the hosted cluster, then out of the MCE: it is powered off, its BareMetalHost and Agent are removed, and server-scan shows it free afterwards.",
  },
  {
    icon: Replace,
    text: "Leaves the NodePool's size as it is, so the NodePool binds a replacement node. This is a replacement, not a shrink.",
    emphasis: true,
  },
  { icon: Undo2, text: "Undoes nothing if it fails. Running it again resumes." },
];

/** The heading of a refused start, by its `code`; the problem's detail is listed under it. */
function refusalTitle(error: unknown): string {
  if (isApiError(error, "NODE_NOT_IN_CLUSTER")) return "server-scan no longer lists this server in this cluster; refresh the list.";
  if (isApiError(error, "UNINSTALL_ALREADY_RUNNING")) return "An uninstall of this server is already running; the list shows its run.";
  if (isApiError(error, "AMBIGUOUS_WRITE")) {
    return "The start was sent but not confirmed, so it may have started: check the node's status before trying again.";
  }
  if (isApiError(error, "VALIDATION_ERROR")) return "The name typed is not the server's name.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: server-scan or the workflows orchestrator did not answer.";
  if (isApiError(error, "FEATURE_DISABLED")) return "Uninstall is not available in this deployment.";
  return "The uninstall did not start.";
}

/**
 * The confirmation for `uninstall-server-from-hc` on one node: a summary of
 * what the workflow does, then the server's name typed again (it cannot be
 * undone). Mount it while open: its state is one start's.
 */
export function UninstallNodeDialog({
  cluster,
  where,
  node,
  onClose,
  onStarted,
}: {
  cluster: string;
  /** `?site=&mce=`, as the cluster's other calls send it. */
  where: string;
  node: ClusterNode;
  onClose: () => void;
  /** The 202's run, so the list shows it at once. */
  onStarted: (node: ClusterNode, run: WorkflowRun) => void;
}) {
  const [typed, setTyped] = useState("");
  const uninstall = useUninstallNode(cluster, where);
  const matches = typed.trim() === node.name;
  // After these the list is read again and a second start would not help (ADR-0006: never retried)
  const settled = STALE_LIST_CODES.some((code) => isApiError(uninstall.error, code));
  const canSubmit = matches && !uninstall.isPending && !settled;
  const hardware = [node.vendor, node.model].filter(Boolean).join(" ");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    uninstall.mutate(
      { node, typed: typed.trim() },
      {
        onSuccess: (run) => {
          toast.success("Uninstall started", { description: node.name });
          onStarted(node, run);
          onClose();
        },
      }
    );
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !uninstall.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="uninstall-node-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle className="leading-snug">Uninstall this server?</DialogTitle>
            <DialogDescription>
              Wingman starts the platform&apos;s <span className="font-mono text-foreground">uninstall-server-from-hc</span>{" "}
              workflow on it, and shows its run with the node. In short, the workflow:
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg border bg-muted/30 px-3.5 py-3 space-y-0.5" data-testid="uninstall-node-identity">
            <p className="font-mono text-xs font-medium text-foreground break-all">{node.name}</p>
            <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
              {node.serial && <span className="font-mono">{node.serial}</span>}
              {node.serial && hardware && <span aria-hidden>·</span>}
              {hardware && <span>{hardware}</span>}
              {(node.serial || hardware) && <span aria-hidden>·</span>}
              <span>
                in <span className="font-mono break-all">{cluster}</span>
              </span>
            </p>
          </div>

          <ul className="space-y-2" aria-label="What the workflow does">
            {SUMMARY.map(({ icon: Icon, text, emphasis }) => (
              <li key={text} className="flex items-start gap-2.5 text-sm">
                <Icon
                  className={cn("h-4 w-4 shrink-0 mt-0.5", emphasis ? "text-status-warning-fg" : "text-muted-foreground")}
                  aria-hidden
                />
                <span className={emphasis ? "font-medium text-foreground" : "text-muted-foreground"}>{text}</span>
              </li>
            ))}
          </ul>

          <label className="block text-xs text-muted-foreground">
            Type <span className="font-mono text-foreground break-all">{node.name}</span> to confirm; it cannot be undone.
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              aria-label="Server name, to confirm the uninstall"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              disabled={uninstall.isPending}
              className="mt-1.5 w-full rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs outline-none transition-shadow focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
            />
          </label>

          {Boolean(uninstall.error) && (
            <div data-testid="uninstall-node-error">
              <ProblemList error={uninstall.error} title={refusalTitle(uninstall.error)} />
            </div>
          )}

          <DialogFooter>
            <button type="button" onClick={onClose} disabled={uninstall.isPending} className={buttonVariants({ variant: "outline" })}>
              {settled ? "Close" : "Cancel"}
            </button>
            <button type="submit" disabled={!canSubmit} className={buttonVariants({ variant: "destructive" })}>
              {uninstall.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {uninstall.isPending ? "Starting…" : "Uninstall server"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
