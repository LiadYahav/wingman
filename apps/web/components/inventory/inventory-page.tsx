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
import { totalAvailable } from "@/lib/inventory/pools";
import { runningCount } from "@/lib/inventory/runs";
import type { Availability } from "@/types/inventory";
import { InstallServersButton } from "./install-servers-button";
import { InstallServersDialog } from "./install-servers-dialog";
import { McePanel } from "./mce-panel";
import { RunsTable } from "./runs-table";
import { useInventoryView } from "./use-inventory-view";

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
    <div className="flex flex-wrap items-center gap-1.5">
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
        hint="The platform's add-server-to-mce runs on every MCE and into every InfraEnv, herzi's and people's, whichever MCE and InfraEnvs are picked above. A named install is a person's; a pool draw is herzi's or a person's, which the orchestrator does not record."
      >
        <span className="text-xs text-muted-foreground">
          <span aria-hidden>· </span>
          <span data-testid="runs-scope">every MCE and InfraEnv</span>
          {running > 0 && (
            <>
              <span aria-hidden> · </span>
              <span data-testid="runs-running">{running} running</span>
            </>
          )}
        </span>
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
 * Inventory Management (ADR-0057): one MCE at a time, picked by site, with its
 * available Agents by InfraEnv pool, as server-scan counts them, the free
 * servers ready to install and those that need a fix; the InfraEnvs shown
 * picked by name (kept across MCEs) and filtered (2026-11-24 amendment);
 * installing servers into a pool through the platform's add-server-to-mce
 * workflow, from the header (on the MCE shown) or a pool's row; and every
 * MCE's runs, herzi's included, whatever is picked. Not a fleet view: a
 * server's record is server-scan's. An admin's, in the Infrastructure
 * workspace (ADR-0067; the route mounts it under `AdminsOnly`, and day1
 * refuses a viewer's reads); Install servers is disabled with the reason
 * where installing is off.
 */
export function InventoryPage() {
  const overview = useInventory();
  const admin = useIsAdmin();
  const mounted = useMounted();
  const [target, setTarget] = useState<InstallTarget | null>(null);
  const data = overview.data;
  const view = useInventoryView(data?.mces);
  const runs = useInventoryRuns({ enabled: data?.runs.available ?? false });

  if (overview.isLoading) {
    return (
      <div className="mx-auto max-w-[1600px] space-y-4 px-4 py-6 sm:p-6 lg:p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 py-6 sm:p-6 lg:p-8">
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
    <div className="mx-auto max-w-[1600px] space-y-6 px-4 py-6 sm:p-6 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <h1 className="text-xl font-semibold tracking-tight">Inventory Management</h1>
          <Hint
            hint="Agents available in each MCE's InfraEnv pools, as server-scan counts them: in the MCE's inventory and in no cluster. A short NodePool on that InfraEnv takes one. The total is every MCE's; pick one MCE below to see its pools."
            label="About Inventory Management"
          >
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className="text-sm text-muted-foreground" data-testid="inventory-total">
            <span className="font-semibold tabular-nums text-foreground">{totalAvailable(data.mces)}</span> available across{" "}
            {data.mces.length} MCE{data.mces.length === 1 ? "" : "s"}
          </p>
          {isAdmin && (
            <InstallServersButton availability={data.add_servers} onOpen={() => setTarget({ mce: view.mce?.mce ?? null, infraEnv: null })} />
          )}
        </div>
      </header>

      <McePanel mces={data.mces} view={view} usedLabels={data.used_labels} canAdd={canAdd} onAdd={setTarget} />

      <RunsSection availability={data.runs} />

      {target && (
        <InstallServersDialog mces={data.mces} runs={runs.data?.runs ?? []} initial={target} onClose={() => setTarget(null)} />
      )}
    </div>
  );
}
