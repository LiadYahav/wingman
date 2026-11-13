"use client";

import type { ReactNode } from "react";
import { CopyPlus, Info, Network, Rows3 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Hint } from "@/components/common/hint";
import { useCandidates } from "@/lib/api/inventory";
import { MAX_SERVERS, toggled, type AddMode } from "@/lib/inventory/start";
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

/**
 * Which servers: let the pool pick N, or name them from the pool's servers in
 * server-scan (a locked, maintenance or contested one cannot be picked).
 * `pool` is `null` until a pool is chosen.
 */
export function InstallServerChoice({
  pool,
  drawable,
  mode,
  count,
  names,
  onMode,
  onCount,
  onNames,
  disabled,
}: {
  pool: { mce: string; infraEnv: string } | null;
  /** What a pool draw could pick, as server-scan counts it. */
  drawable: number | null;
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
          {drawable !== null && (
            <span className="text-xs text-muted-foreground" data-testid="add-servers-drawable">
              {drawable} free in server-scan
            </span>
          )}
        </label>
      ) : pool === null ? (
        <p className="text-xs text-muted-foreground">Choose the MCE and the pool to list its servers.</p>
      ) : (
        <div className="grid gap-1.5">
          <CandidateList
            infraEnv={pool.infraEnv}
            candidates={candidates.data?.candidates}
            isLoading={candidates.isLoading}
            error={candidates.error}
            selected={names}
            onToggle={(name) => onNames(toggled(names, name))}
          />
          <p className="text-xs text-muted-foreground">
            {names.length} of {MAX_SERVERS} at most
          </p>
        </div>
      )}
    </>
  );
}
