"use client";

import type { ReactNode } from "react";
import { CopyPlus, Info, Network, Rows3, TriangleAlert } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Hint } from "@/components/common/hint";
import { useCandidates } from "@/lib/api/inventory";
import { unnamedReason } from "@/lib/inventory/pools";
import { MAX_SERVERS, toggled, type AddMode } from "@/lib/inventory/start";
import type { PoolCount } from "@/types/inventory";
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

/** What an install does, said before anything is sent. */
export function InstallTruths() {
  return (
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
  );
}

const inputClass =
  "w-20 rounded-md border bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/** What a pool draw could pick here, and what it never picks, as server-scan counts them. */
function PoolFree({ counts }: { counts: PoolCount }) {
  const fix = counts.needs_fix ?? 0;
  return (
    <span className="text-xs text-muted-foreground" data-testid="add-servers-ready">
      {counts.ready ?? 0} ready in server-scan
      {fix > 0 && (
        <span className="text-status-warning-fg">
          {" · "}
          {fix} {fix === 1 ? "needs" : "need"} a fix: choose by name
        </span>
      )}
    </span>
  );
}

/** A pool draw into an InfraEnv whose agentLabels name no servers: the workflow refuses it. */
function DrawRefused({ counts }: { counts: PoolCount | null }) {
  if (counts === null || counts.label_problems.length === 0) return null;
  return (
    <p className="flex items-start gap-1.5 text-xs text-status-warning-fg" role="status" data-testid="add-servers-labels-missing">
      <TriangleAlert aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>The workflow would refuse a pool draw here. {unnamedReason(counts)}</span>
    </p>
  );
}

/**
 * Which servers: let the pool pick N, or name them from the pool's servers in
 * server-scan (a locked, maintenance or contested one cannot be picked; one
 * that needs a fix can, and the dialog then asks to waive its health checks).
 * `pool` is `null` until a pool is chosen; a pool draw never waives anything.
 */
export function InstallServerChoice({
  pool,
  counts,
  needsFix,
  mode,
  count,
  names,
  onMode,
  onCount,
  onNames,
  disabled,
}: {
  pool: { mce: string; infraEnv: string } | null;
  /** The pool's counts, when the page knows the pool. */
  counts: PoolCount | null;
  /** How many of the chosen servers need a fix. */
  needsFix: number;
  mode: AddMode;
  count: number;
  names: string[];
  onMode: (mode: AddMode) => void;
  onCount: (count: number) => void;
  onNames: (names: string[]) => void;
  disabled: boolean;
}) {
  const candidates = useCandidates(pool?.mce ?? "", pool?.infraEnv ?? "", { enabled: mode === "named" && pool !== null });
  return (
    <>
      <Tabs value={mode} onValueChange={(value) => onMode(value as AddMode)}>
        <TabsList>
          <TabsTrigger value="count" disabled={disabled}>Let the pool pick</TabsTrigger>
          <TabsTrigger value="named" disabled={disabled}>Choose servers</TabsTrigger>
        </TabsList>
      </Tabs>
      {mode === "count" && <DrawRefused counts={counts} />}
      {mode === "count" ? (
        <label className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">Servers</span>
          <input
            type="number"
            min={1}
            max={MAX_SERVERS}
            value={Number.isNaN(count) ? "" : count}
            onChange={(e) => onCount(e.target.valueAsNumber)}
            aria-label="How many servers"
            disabled={disabled}
            className={inputClass}
          />
          {counts !== null && counts.ready !== null && <PoolFree counts={counts} />}
        </label>
      ) : pool === null ? (
        <p className="text-xs text-muted-foreground">Choose the MCE and the pool to list its servers.</p>
      ) : (
        <div className="grid gap-1.5">
          <CandidateList
            found={candidates.data}
            isLoading={candidates.isLoading}
            error={candidates.error}
            selected={names}
            onToggle={(name) => onNames(toggled(names, name))}
          />
          <p className="text-xs text-muted-foreground">
            {names.length} of {MAX_SERVERS} at most
            {needsFix > 0 && (
              <span className="text-status-warning-fg" data-testid="add-servers-needs-fix">
                {" · "}
                {needsFix === 1
                  ? "1 needs a fix: you confirm its health checks are waived next"
                  : `${needsFix} need a fix: you confirm their health checks are waived next`}
              </span>
            )}
          </p>
        </div>
      )}
    </>
  );
}
