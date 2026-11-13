"use client";

import { useState } from "react";
import { Info, Unplug } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { useInventory, useInventoryRuns } from "@/lib/api/inventory";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { InstallTarget } from "@/lib/inventory/install";
import { bySite, totalAvailable } from "@/lib/inventory/pools";
import { runningCount } from "@/lib/inventory/runs";
import type { Availability } from "@/types/inventory";
import { InstallServersButton } from "./install-servers-button";
import { InstallServersDialog } from "./install-servers-dialog";
import { MceCard } from "./mce-card";
import { RunsTable } from "./runs-table";

/** Why the page cannot show anything: no server-scan. */
function Blocked() {
  return (
    <EmptyState
      icon={Unplug}
      bordered
      title="Inventory Management is not set up"
      description="It counts server-scan's servers: set serverScan.url in the chart (SERVER_SCAN_URL)."
      data-testid="inventory-off"
    />
  );
}

function SectionTitle({ title, hint, children }: { title: string; hint: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <Hint hint={hint} label={`About ${title}`}>
        <Info aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />
      </Hint>
      {children}
    </div>
  );
}

function RunsSection({ availability }: { availability: Availability }) {
  const runs = useInventoryRuns({ enabled: availability.available });
  const list = runs.data?.runs ?? [];
  const running = runningCount(list);
  return (
    <section className="space-y-2" aria-label="Add-server runs">
      <SectionTitle
        title="Runs"
        hint="The platform's add-server-to-mce runs, herzi's and people's. A named install is a person's; a pool draw is herzi's or a person's, which the orchestrator does not record."
      >
        {running > 0 && <span className="text-xs text-muted-foreground" data-testid="runs-running">{running} running</span>}
      </SectionTitle>
      {!availability.available ? (
        <p className="text-xs text-muted-foreground" data-testid="runs-off">{availability.detail}</p>
      ) : runs.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : runs.error ? (
        <ProblemList error={runs.error} title="The runs could not be read" />
      ) : (
        <RunsTable runs={list} />
      )}
    </section>
  );
}

/**
 * Inventory Management (ADR-0057): each MCE's available Agents by InfraEnv
 * pool, as server-scan counts them; installing servers into a pool through
 * the platform's add-server-to-mce workflow, from the header or a pool's row;
 * and its runs, herzi's included. Not a fleet view: a server's record is
 * server-scan's. Everyone signed in reads it; only an admin sees Install
 * servers (day1 refuses anyone else's start), disabled with the reason where
 * installing is off.
 */
export function InventoryPage() {
  const overview = useInventory();
  const admin = useIsAdmin();
  const mounted = useMounted();
  const [target, setTarget] = useState<InstallTarget | null>(null);
  const data = overview.data;
  const runs = useInventoryRuns({ enabled: data?.runs.available ?? false });

  if (overview.isLoading) {
    return (
      <div className="mx-auto max-w-[1600px] space-y-4 p-6 lg:p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-[1600px] p-6 lg:p-8">
        {isApiError(overview.error, "FEATURE_DISABLED") ? (
          <Blocked />
        ) : (
          <ProblemList error={overview.error} title="server-scan's servers could not be read" />
        )}
      </div>
    );
  }

  const isAdmin = admin && mounted;
  const canAdd = isAdmin && data.add_servers.available;
  return (
    <div className="mx-auto max-w-[1600px] space-y-6 p-6 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <h1 className="text-xl font-semibold tracking-tight">Inventory Management</h1>
          <Hint
            hint="Agents available in each MCE's InfraEnv pools, as server-scan counts them: in the MCE's inventory and in no cluster. A short NodePool on that InfraEnv takes one."
            label="About Inventory Management"
          >
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <div className="flex items-center gap-4">
          <p className="text-sm text-muted-foreground" data-testid="inventory-total">
            <span className="font-semibold tabular-nums text-foreground">{totalAvailable(data.mces)}</span> available
          </p>
          {isAdmin && (
            <InstallServersButton availability={data.add_servers} onOpen={() => setTarget({ mce: null, infraEnv: null })} />
          )}
        </div>
      </header>

      {bySite(data.mces).map((group) => (
        <section key={group.site} className="space-y-2" aria-label={`Site ${group.site}`}>
          <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{group.site}</h2>
          <div className="grid gap-3">
            {group.mces.map((mce) => (
              <MceCard key={mce.mce} mce={mce} canAdd={canAdd} onAdd={setTarget} />
            ))}
          </div>
          {group.quiet.length > 0 && (
            <p className="text-xs text-muted-foreground" data-testid="quiet-mces">
              Not in server-scan: <span className="font-mono">{group.quiet.map((m) => m.mce).join(", ")}</span>
            </p>
          )}
        </section>
      ))}

      <RunsSection availability={data.runs} />

      {target && (
        <InstallServersDialog mces={data.mces} runs={runs.data?.runs ?? []} initial={target} onClose={() => setTarget(null)} />
      )}
    </div>
  );
}
