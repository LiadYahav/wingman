"use client";

import { TriangleAlert } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { errorMessages } from "@/lib/api-client";
import { UPGRADE_FILTERS, type UpgradeFilter } from "@/lib/fleet-upgrades";
import { FilterPills } from "./filter-pills";
import type { ListUpgrades } from "./use-list-upgrades";

/** Why no row says "Upgrading": the fleet's runs could not be read. */
function RunsUnknown({ error }: { error: unknown }) {
  const why = errorMessages(error).join(" ") || "The workflows orchestrator did not answer.";
  return (
    <Hint
      hint={`The upgrade runs could not be read, so no cluster shows Upgrading: ${why}`}
      label="Upgrade runs unknown"
      testId="upgrade-runs-unknown"
      className="text-status-warning"
    >
      <TriangleAlert aria-hidden className="h-3.5 w-3.5" />
    </Hint>
  );
}

/**
 * The clusters list's Upgrades filter, in the style of its other filters:
 * All, Upgrade available, Upgrading, each with its count. Shown only while
 * upgrades are on.
 */
export function UpgradeFilterGroup({
  upgrades,
  onFilter,
}: {
  upgrades: ListUpgrades;
  onFilter: (next: UpgradeFilter) => void;
}) {
  if (!upgrades.on) return null;
  return (
    <FilterPills
      label="Upgrades"
      pills={UPGRADE_FILTERS.map((f) => ({ ...f, count: f.value === "all" ? undefined : upgrades.counts[f.value] }))}
      value={upgrades.filter}
      onChange={onFilter}
      testId="upgrade-filter"
    >
      {upgrades.error !== null && <RunsUnknown error={upgrades.error} />}
    </FilterPills>
  );
}
