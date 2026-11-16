"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { useAddServers, useCandidates } from "@/lib/api/inventory";
import { chosenInfraEnv, poolIn, type InstallTarget } from "@/lib/inventory/install";
import { addRequest, isSettled, refusalTitle, startSummary, type AddMode } from "@/lib/inventory/start";
import { needsFixChosen, withWaiver } from "@/lib/inventory/waiver";
import type { Candidate, InventoryRun, MceInventory } from "@/types/inventory";
import { InstallServerChoice, InstallTruths } from "./install-server-choice";
import { InstallTargetFields } from "./install-target-fields";
import { InstallWaiverConfirm } from "./install-waiver-confirm";

type Step = "choose" | "confirm";

const HEADINGS: Record<Step, { title: string; description: string }> = {
  choose: {
    title: "Install servers",
    description: "Into an MCE's InfraEnv pool, through the platform's add-server-to-mce workflow.",
  },
  confirm: {
    title: "Install with health checks waived?",
    description: "These servers fail a health check in server-scan. The workflow installs them anyway only when asked.",
  },
};

/** The submit's words: `Install 2`, `Install 2…` when a confirmation comes next, the waiver's own on that step. */
function submitLabel(step: Step, pending: boolean, size: number, confirmNext: boolean): string {
  if (pending) return "Starting…";
  if (step === "confirm") return "Install with checks waived";
  const label = `Install ${size > 0 ? size : ""}`.trim();
  return confirmNext ? `${label}…` : label;
}

/**
 * Install servers into an MCE's InfraEnv pool through the platform's
 * add-server-to-mce workflow (ADR-0057 and its amendments), as the
 * orchestrator's own form does: pick the MCE and the pool (or type an
 * InfraEnv), then let the pool pick N or name them. It needs no live status:
 * the workflow first checks the MCE has the InfraEnv. Naming a server that
 * needs a fix leads to a confirmation step; only its confirm sends the
 * workflow's `allow_unhealthy`, and a pool draw never does. Sent once and
 * never retried; after an unanswered start it sends nothing more. Mount it
 * while open: its state is one start's. `initial` preselects a pool (its
 * row's Install).
 */
export function InstallServersDialog({
  mces,
  runs,
  initial,
  onClose,
}: {
  mces: MceInventory[];
  runs: InventoryRun[];
  initial: InstallTarget;
  onClose: () => void;
}) {
  const [mce, setMce] = useState<string | null>(initial.mce);
  const [picked, setPicked] = useState<string | null>(initial.infraEnv);
  const [typed, setTyped] = useState("");
  const [mode, setMode] = useState<AddMode>("count");
  const [count, setCount] = useState(1);
  const [names, setNames] = useState<string[]>([]);
  // The servers that need a fix as the person confirms them: a refresh of the list does not change what is confirmed
  const [confirming, setConfirming] = useState<Candidate[] | null>(null);
  const step: Step = confirming ? "confirm" : "choose";
  const add = useAddServers();
  const infraEnv = chosenInfraEnv(picked, typed);
  const pool = mce && infraEnv ? { mce, infraEnv } : null;
  // The picker's read (one cache entry): which of the chosen servers need a fix
  const candidates = useCandidates(pool?.mce ?? "", pool?.infraEnv ?? "", { enabled: mode === "named" && pool !== null });
  const fix = mode === "named" ? needsFixChosen(names, candidates.data?.candidates) : [];
  const body = addRequest(mode, count, names);
  const settled = isSettled(add.error);
  const pending = add.isPending;
  const canSubmit = pool !== null && body !== null && !pending && !settled;
  const size = mode === "count" ? (Number.isInteger(count) ? count : 0) : names.length;

  const chooseMce = (next: string | null) => {
    setMce(next);
    setPicked(null);
    setTyped("");
    setNames([]);
  };
  const choosePool = (next: string | null) => {
    setPicked(next);
    setNames([]);
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || pool === null || body === null) return;
    if (confirming === null && fix.length > 0) {
      setConfirming(fix);
      return;
    }
    add.mutate(
      { ...pool, body: confirming ? withWaiver(body) : body },
      {
        onSuccess: (result) => {
          toast.success(startSummary(result), { description: `${pool.infraEnv} on ${pool.mce}` });
          onClose();
        },
      }
    );
  };
  const back = () => {
    add.reset();
    setConfirming(null);
  };
  const heading = HEADINGS[step];

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="add-servers-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{heading.title}</DialogTitle>
            <DialogDescription>{heading.description}</DialogDescription>
          </DialogHeader>
          {confirming ? (
            <InstallWaiverConfirm servers={confirming} total={names.length} />
          ) : (
            <>
              <InstallTargetFields
                mces={mces}
                runs={runs}
                mce={mce}
                picked={picked}
                typed={typed}
                onMce={chooseMce}
                onPicked={choosePool}
                onTyped={(name) => { setTyped(name); setNames([]); }}
                disabled={pending || settled}
              />
              <InstallTruths />
              <InstallServerChoice
                pool={pool}
                counts={poolIn(mces.find((m) => m.mce === mce), infraEnv)}
                needsFix={fix.length}
                mode={mode}
                count={count}
                names={names}
                onMode={setMode}
                onCount={setCount}
                onNames={setNames}
                disabled={pending}
              />
            </>
          )}
          {Boolean(add.error) && (
            <div data-testid="add-servers-error">
              <ProblemList error={add.error} title={refusalTitle(add.error)} />
            </div>
          )}
          <DialogFooter>
            {step === "confirm" && !settled ? (
              <button type="button" onClick={back} disabled={pending} className={buttonVariants({ variant: "outline" })}>
                Back
              </button>
            ) : (
              <button type="button" onClick={onClose} disabled={pending} className={buttonVariants({ variant: "outline" })}>
                {settled ? "Close" : "Cancel"}
              </button>
            )}
            <button
              type="submit"
              disabled={!canSubmit}
              className={buttonVariants({ variant: step === "confirm" ? "destructive" : "default" })}
            >
              {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {submitLabel(step, pending, size, fix.length > 0)}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
