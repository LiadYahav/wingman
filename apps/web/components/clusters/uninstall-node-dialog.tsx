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
import type { ServerRecord, WorkflowRun } from "@/types";

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
  if (isApiError(error, "NODE_NOT_IN_CLUSTER")) {
    return "Neither the MCE nor server-scan places this server in this cluster any more; refresh the list.";
  }
  if (isApiError(error, "UNINSTALL_ALREADY_RUNNING")) return "An uninstall of this server is already running; the list shows its run.";
  if (isApiError(error, "AMBIGUOUS_WRITE")) {
    return "The start was sent but not confirmed, so it may have started: check the node's status before trying again.";
  }
  if (isApiError(error, "VALIDATION_ERROR")) return "The name typed is not the server's name.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: server-scan or the workflows orchestrator did not answer.";
  if (isApiError(error, "FEATURE_DISABLED")) return "Uninstall is not available in this deployment.";
  return "The uninstall did not start.";
}

/** Where the server is: its Machine and NodePool, or only the cluster for a server no Machine has. */
export interface UninstallTarget {
  server: ServerRecord;
  pool: string | null;
  machine: string | null;
}

/**
 * The confirmation for `uninstall-server-from-hc` on one server: a summary of
 * what the workflow does, then the server's name typed again (it cannot be
 * undone). Mount it while open: its state is one start's.
 */
export function UninstallNodeDialog({
  cluster,
  where,
  target,
  onClose,
  onStarted,
}: {
  cluster: string;
  /** `?site=&mce=`, as the cluster's other calls send it. */
  where: string;
  target: UninstallTarget;
  onClose: () => void;
  /** The 202's run, so the page shows it at once. */
  onStarted: (server: ServerRecord, run: WorkflowRun) => void;
}) {
  const { server, pool, machine } = target;
  const [typed, setTyped] = useState("");
  const uninstall = useUninstallNode(cluster, where);
  const matches = typed.trim() === server.name;
  // After these the page is read again and a second start would not help (ADR-0006: never retried)
  const settled = STALE_LIST_CODES.some((code) => isApiError(uninstall.error, code));
  const canSubmit = matches && !uninstall.isPending && !settled;
  const hardware = [server.vendor, server.model].filter(Boolean).join(" ");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    uninstall.mutate(
      { server, typed: typed.trim() },
      {
        onSuccess: (run) => {
          toast.success("Uninstall started", { description: server.name });
          onStarted(server, run);
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
            <p className="font-mono text-xs font-medium text-foreground break-all">{server.name}</p>
            <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
              {server.serial && <span className="font-mono">{server.serial}</span>}
              {server.serial && hardware && <span aria-hidden>·</span>}
              {hardware && <span>{hardware}</span>}
            </p>
            {machine ? (
              <>
                <p className="text-xs text-muted-foreground break-words">
                  Machine <span className="font-mono">{machine}</span>
                </p>
                {pool && (
                  <p className="text-xs text-muted-foreground break-words">
                    NodePool <span className="font-mono">{pool}</span>
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground break-words">
                In <span className="font-mono">{cluster}</span>, in no NodePool
              </p>
            )}
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
            Type <span className="font-mono text-foreground break-all">{server.name}</span> to confirm; it cannot be undone.
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
