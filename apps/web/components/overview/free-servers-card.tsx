"use client";

import Link from "next/link";
import { Boxes } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { useInventory } from "@/lib/api/inventory";
import { serverCapacity, type MceCapacity } from "@/lib/overview/capacity";
import { plural } from "@/lib/utils";
import { CapacityRow, CapacityTotal } from "./capacity-row";
import { CardNote, OverviewCard, RowsSkeleton } from "./overview-card";

/** MCEs shown, and pools named per MCE; the rest are summed. */
const MCES_SHOWN = 6;
const POOLS_SHOWN = 3;

function Pools({ mce }: { mce: MceCapacity }) {
  if (mce.pools.length === 0) return null;
  const hidden = mce.pools.length - POOLS_SHOWN;
  return (
    <span className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground" data-testid="overview-pools">
      {mce.pools.slice(0, POOLS_SHOWN).map((pool) => (
        <span key={pool.infraEnv ?? ""} className="inline-flex min-w-0 items-baseline gap-1">
          <span className={pool.infraEnv ? "truncate font-mono" : "italic"}>{pool.infraEnv ?? "no InfraEnv"}</span>
          <span className="tabular-nums text-foreground">{pool.free}</span>
        </span>
      ))}
      {hidden > 0 && <span>+{plural(hidden, "pool")}</span>}
      {mce.unusable > 0 && <span className="text-status-warning-fg">{mce.unusable} not usable</span>}
    </span>
  );
}

function ServersBody() {
  const inventory = useInventory();
  if (inventory.isLoading) return <RowsSkeleton className="h-14" />;
  if (isApiError(inventory.error, "FEATURE_DISABLED")) {
    return <CardNote data-testid="overview-servers-off">Not set up here: Inventory Management counts server-scan&apos;s servers (SERVER_SCAN_URL).</CardNote>;
  }
  if (!inventory.data) return <ProblemList error={inventory.error} title="server-scan's servers could not be read" />;
  const capacity = serverCapacity(inventory.data.mces);
  if (capacity.mces.length === 0) {
    return <EmptyState icon={Boxes} title="No servers yet" description="server-scan names no server on any MCE of the day1 repo." data-testid="overview-servers-empty" />;
  }
  const hidden = capacity.mces.slice(MCES_SHOWN);
  return (
    <>
      <CapacityTotal free={capacity.free} what={`free across ${plural(capacity.mces.length, "MCE")}`} data-testid="overview-servers-total" />
      <div className="-mx-3 space-y-0.5">
        {capacity.mces.slice(0, MCES_SHOWN).map((mce) => (
          <CapacityRow key={mce.mce} href="/inventory" name={mce.mce} mono context={mce.site} free={mce.free} usedPercent={mce.usedPercent}
            label={`${mce.mce}: ${mce.free} free of ${plural(mce.servers, "server")}`} data-testid="overview-mce">
            <Pools mce={mce} />
          </CapacityRow>
        ))}
      </div>
      {(hidden.length > 0 || capacity.unknown.length > 0) && (
        <Link href="/inventory" className="mt-1 block text-xs text-muted-foreground hover:text-foreground" data-testid="overview-servers-more">
          {[
            hidden.length > 0 && `${plural(hidden.length, "more MCE")} · ${hidden.reduce((n, m) => n + m.free, 0)} free`,
            capacity.unknown.length > 0 && `${plural(capacity.unknown.length, "MCE")} not in server-scan`,
          ].filter(Boolean).join(" · ")}
        </Link>
      )}
    </>
  );
}

/** Inventory Management's numbers: each MCE's free servers, by InfraEnv pool. */
export function FreeServersCard() {
  return (
    <OverviewCard
      title="Free Servers"
      hint="Agents in each MCE's inventory and in no cluster, by InfraEnv pool, as server-scan counts them: a short NodePool on that InfraEnv takes one. The bar is the share of the MCE's servers already in a cluster."
      href="/inventory"
      linkLabel="Inventory"
      data-testid="overview-servers"
    >
      <ServersBody />
    </OverviewCard>
  );
}
