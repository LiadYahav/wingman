"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { useAddServers } from "@/lib/api/inventory";
import { chosenInfraEnv, drawableIn, type InstallTarget } from "@/lib/inventory/install";
import { addRequest, isSettled, refusalTitle, startSummary, type AddMode } from "@/lib/inventory/start";
import type { InventoryRun, MceInventory } from "@/types/inventory";
import { InstallServerChoice, InstallTruths } from "./install-server-choice";
import { InstallTargetFields } from "./install-target-fields";

/**
 * Install servers into an MCE's InfraEnv pool through the platform's
 * add-server-to-mce workflow (ADR-0057 and its amendment), as the
 * orchestrator's own form does: pick the MCE and the pool (or type an
 * InfraEnv), then let the pool pick N or name them. It needs no live status:
 * the workflow first checks the MCE has the InfraEnv. Sent once and never
 * retried; after an unanswered start it sends nothing more. Mount it while
 * open: its state is one start's. `initial` preselects a pool (its row's
 * Install).
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
  const add = useAddServers();
  const infraEnv = chosenInfraEnv(picked, typed);
  const pool = mce && infraEnv ? { mce, infraEnv } : null;
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
    add.mutate(
      { ...pool, body },
      {
        onSuccess: (result) => {
          toast.success(startSummary(result), { description: `${pool.infraEnv} on ${pool.mce}` });
          onClose();
        },
      }
    );
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="add-servers-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Install servers</DialogTitle>
            <DialogDescription>Into an MCE&apos;s InfraEnv pool, through the platform&apos;s add-server-to-mce workflow.</DialogDescription>
          </DialogHeader>
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
            drawable={drawableIn(mces.find((m) => m.mce === mce), infraEnv)}
            mode={mode}
            count={count}
            names={names}
            onMode={setMode}
            onCount={setCount}
            onNames={setNames}
            disabled={pending}
          />
          {Boolean(add.error) && (
            <div data-testid="add-servers-error">
              <ProblemList error={add.error} title={refusalTitle(add.error)} />
            </div>
          )}
          <DialogFooter>
            <button type="button" onClick={onClose} disabled={pending} className={buttonVariants({ variant: "outline" })}>
              {settled ? "Close" : "Cancel"}
            </button>
            <button type="submit" disabled={!canSubmit} className={buttonVariants()}>
              {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {pending ? "Starting…" : `Install ${size > 0 ? size : ""}`.trim()}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
