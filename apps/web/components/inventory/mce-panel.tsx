"use client";

import { useMemo, useState } from "react";
import { SearchX, Server } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import type { InstallTarget } from "@/lib/inventory/install";
import {
  NO_FILTER,
  facetsOf,
  narrows,
  poolNames,
  shownPools,
  splitSelection,
  withinFacets,
  type PoolFilter,
} from "@/lib/inventory/pool-filter";
import type { MceInventory, UsedLabels } from "@/types/inventory";
import { InfraEnvPicker } from "./infra-env-picker";
import { Counts, McePicker, PoolsFromDay1 } from "./mce-summary";
import { PickedInfraEnvs } from "./picked-infra-envs";
import { PoolFilters } from "./pool-filters";
import { PoolTable } from "./pool-table";
import { UnguardedNotice, UsedUnread } from "./used-agents";
import type { InventoryViewState } from "./use-inventory-view";

interface PoolsProps {
  mce: MceInventory;
  selection: string[];
  onSelect: (next: readonly string[]) => void;
  usedLabels: UsedLabels;
  canAdd: boolean;
  onAdd: (t: InstallTarget) => void;
}

/** Nothing to filter: the MCE names no pool (server-scan names nothing on it, and its InfraEnvs are unknown). */
function NoPools({ mce }: { mce: MceInventory }) {
  return (
    <EmptyState
      icon={Server}
      bordered
      title="No pools on this MCE"
      description={
        mce.known
          ? "server-scan names no available server here, and no InfraEnv is known."
          : "server-scan names no server on this MCE, and its InfraEnvs are unknown: Install servers still takes an InfraEnv you type."
      }
      data-testid="mce-no-pools"
    />
  );
}

/** The filters hide every pool: say which, and offer to clear them. */
function NoneShown({ onlyAbsent, onClear }: { onlyAbsent: boolean; onClear: () => void }) {
  return (
    <div className="rounded-xl border bg-card">
      <EmptyState
        icon={SearchX}
        title="No InfraEnvs match"
        description={onlyAbsent ? "This MCE has none of the InfraEnvs picked." : "Nothing on this MCE matches the InfraEnvs picked, the search and the filters."}
        action={
          <button type="button" onClick={onClear} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Clear filters
          </button>
        }
        data-testid="pools-none-shown"
      />
    </div>
  );
}

/**
 * The selected MCE's pools: the InfraEnvs picked (kept across MCEs), the
 * table's filters, then the rows. The filters stay while the MCE changes; a
 * zone or size the new MCE lacks is dropped.
 */
function Pools({ mce, selection, onSelect, usedLabels, canAdd, onAdd }: PoolsProps) {
  const [filter, setFilter] = useState<PoolFilter>(NO_FILTER);
  const names = useMemo(() => poolNames(mce.pools), [mce.pools]);
  const facets = useMemo(() => facetsOf(names), [names]);
  if (mce.pools.length === 0) return <NoPools mce={mce} />;

  const effective = withinFacets(filter, facets);
  const { present, missing } = splitSelection(names, selection);
  const rows = shownPools(mce.pools, selection, effective);
  const shown = rows.filter((pool) => pool.infra_env !== null).length;
  const clear = () => {
    setFilter({ ...NO_FILTER, sort: filter.sort });
    onSelect([]);
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={`Filter the pools on ${mce.mce}`}>
        <InfraEnvPicker mce={mce.mce} pools={mce.pools} selection={selection} onChange={onSelect} />
        <PoolFilters
          facets={facets}
          filter={effective}
          onChange={setFilter}
          shown={shown}
          total={names.length}
          filtering={narrows(effective, selection)}
        />
      </div>
      <PickedInfraEnvs mce={mce.mce} present={present} missing={missing} onChange={onSelect} />
      {rows.length === 0 ? (
        <NoneShown onlyAbsent={selection.length > 0 && present.length === 0} onClear={clear} />
      ) : (
        <PoolTable
          mce={mce.mce}
          pools={rows}
          usedLabels={usedLabels}
          canAdd={canAdd}
          onAdd={onAdd}
          sort={effective.sort}
          onSort={(sort) => setFilter({ ...filter, sort })}
        />
      )}
    </div>
  );
}

/**
 * One MCE at a time (ADR-0057's 2026-11-24 amendment): the picker, its
 * counts and notes, then its pools. Which one, and the InfraEnvs picked, are
 * the page's view (`?mce=`, `&infraEnv=`, kept per viewer).
 */
export function McePanel({
  mces,
  view,
  usedLabels,
  canAdd,
  onAdd,
}: {
  mces: MceInventory[];
  view: InventoryViewState;
  usedLabels: UsedLabels;
  canAdd: boolean;
  onAdd: (t: InstallTarget) => void;
}) {
  const mce = view.mce;
  if (!mce) {
    return <EmptyState icon={Server} bordered title="No MCEs" description="The day1 repo names no MCE." data-testid="inventory-no-mces" />;
  }
  return (
    <section data-testid="mce-panel" data-mce={mce.mce} aria-label={mce.mce} className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <McePicker mces={mces} value={mce.mce} onChange={view.setMce} />
        <Counts mce={mce} usedLabels={usedLabels} />
      </div>
      {view.unknownMce && (
        <p className="text-xs text-muted-foreground" data-testid="mce-unknown">
          The day1 repo has no MCE named <span className="font-mono">{view.unknownMce}</span>: showing{" "}
          <span className="font-mono">{mce.mce}</span>.
        </p>
      )}
      <PoolsFromDay1 mce={mce} />
      <UsedUnread mce={mce} />
      <UnguardedNotice mce={mce} labels={usedLabels} />
      <Pools mce={mce} selection={view.infraEnvs} onSelect={view.setInfraEnvs} usedLabels={usedLabels} canAdd={canAdd} onAdd={onAdd} />
    </section>
  );
}
