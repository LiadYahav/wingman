"use client";

import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CopyPlus, Info, Loader2, Network, Rows3 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { useAddServers, useCandidates } from "@/lib/api/inventory";
import { MAX_SERVERS, addRequest, isSettled, refusalTitle, startSummary, toggled, type AddMode } from "@/lib/inventory/start";
import { CandidateList } from "./candidate-list";

/** One true sentence, its detail in a tooltip. */
function Truth({ icon: Icon, children, hint }: { icon: typeof Info; children: ReactNode; hint: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <Icon aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span>{children}</span>
      <Hint hint={hint} label="More">
        <Info aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />
      </Hint>
    </li>
  );
}

/**
 * Add servers to one InfraEnv pool through the platform's add-server-to-mce
 * workflow (ADR-0057): let the pool pick N, or name them. Sent once and never
 * retried; after an unanswered start it sends nothing more. Mount it while
 * open: its state is one start's.
 */
export function AddServersDialog({
  mce,
  infraEnv,
  drawable,
  onClose,
}: {
  mce: string;
  infraEnv: string;
  /** What a pool draw could pick, as server-scan counts it. */
  drawable: number | null;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<AddMode>("count");
  const [count, setCount] = useState(1);
  const [names, setNames] = useState<string[]>([]);
  const add = useAddServers(mce, infraEnv);
  const candidates = useCandidates(mce, infraEnv, { enabled: mode === "named" });
  const body = addRequest(mode, count, names);
  const settled = isSettled(add.error);
  const canSubmit = body !== null && !add.isPending && !settled;
  const size = mode === "count" ? (Number.isInteger(count) ? count : 0) : names.length;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || body === null) return;
    add.mutate(body, {
      onSuccess: (result) => {
        toast.success(startSummary(result), { description: `${infraEnv} on ${mce}` });
        onClose();
      },
    });
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !add.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="add-servers-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add servers</DialogTitle>
            <DialogDescription>
              <span className="font-mono text-foreground">{infraEnv}</span> on <span className="font-mono text-foreground">{mce}</span>
            </DialogDescription>
          </DialogHeader>

          <ul className="space-y-1.5" aria-label="What it does">
            <Truth icon={Network} hint="Any NodePool on this InfraEnv that is short of nodes takes it, whatever its cluster. A cluster grows by raising its NodePool's replicas.">
              Joins the MCE&apos;s pool, not one cluster.
            </Truth>
            <Truth icon={Rows3} hint="add-server-to-mce runs once per server, each up to an hour. The runs below show them.">
              One run per server.
            </Truth>
            <Truth icon={CopyPlus} hint="Not retry-safe. Where herzi runs, it counts a pool draw as its own supply, and a named server only once its Agent appears.">
              Sending again installs more.
            </Truth>
          </ul>

          <Tabs value={mode} onValueChange={(value) => setMode(value as AddMode)}>
            <TabsList>
              <TabsTrigger value="count" disabled={add.isPending}>Let the pool pick</TabsTrigger>
              <TabsTrigger value="named" disabled={add.isPending}>Choose servers</TabsTrigger>
            </TabsList>
          </Tabs>

          {mode === "count" ? (
            <label className="flex items-center gap-3 text-sm">
              <span className="text-muted-foreground">Servers</span>
              <input
                type="number"
                min={1}
                max={MAX_SERVERS}
                value={Number.isNaN(count) ? "" : count}
                onChange={(e) => setCount(e.target.valueAsNumber)}
                aria-label="How many servers"
                disabled={add.isPending}
                className="w-20 rounded-md border bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              {drawable !== null && (
                <span className="text-xs text-muted-foreground" data-testid="add-servers-drawable">
                  {drawable} free in server-scan
                </span>
              )}
            </label>
          ) : (
            <div className="grid gap-1.5">
              <CandidateList
                infraEnv={infraEnv}
                candidates={candidates.data?.candidates}
                isLoading={candidates.isLoading}
                error={candidates.error}
                selected={names}
                onToggle={(name) => setNames((now) => toggled(now, name))}
              />
              <p className="text-xs text-muted-foreground">
                {names.length} of {MAX_SERVERS} at most
              </p>
            </div>
          )}

          {Boolean(add.error) && (
            <div data-testid="add-servers-error">
              <ProblemList error={add.error} title={refusalTitle(add.error)} />
            </div>
          )}

          <DialogFooter>
            <button type="button" onClick={onClose} disabled={add.isPending} className={buttonVariants({ variant: "outline" })}>
              {settled ? "Close" : "Cancel"}
            </button>
            <button type="submit" disabled={!canSubmit} className={buttonVariants()}>
              {add.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {add.isPending ? "Starting…" : `Add ${size > 0 ? size : ""}`.trim()}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
