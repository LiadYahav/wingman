"use client";

import { useState } from "react";
import { Plus, Sprout, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import type { SeedWithClusters } from "@/lib/infrastructure";
import { noStandbyWarning, zoneChains, type ZoneChain } from "@/lib/kv-clusters";
import type { LiveStatuses } from "@/lib/live-status";
import { plural } from "@/lib/utils";
import { KvClusterDialog, type KvDialogStart } from "./kv-cluster-dialog";
import { KvClusterRow } from "./kv-cluster-row";
import { Chip, OffConvention } from "./page-parts";

/** A standby KV cluster's size: acceptance P1's 3, in the capacity policy's 1 to 5 (day1's default too). */
const STANDBY_WORKERS = 3;

/** A zone with no KV cluster next in line: when the filling one is full, create-vm has nowhere to go. */
function NoStandby({ chain, onCreate }: { chain: ZoneChain; onCreate: (start: KvDialogStart) => void }) {
  const warning = noStandbyWarning(chain);
  if (warning === null) return null;
  return (
    <div role="status" className="flex flex-wrap items-center gap-2 border-t bg-status-warning/5 px-4 py-2.5 text-xs" data-testid="kv-no-standby" data-zone={chain.zone ?? ""}>
      <TriangleAlert aria-hidden className="h-3.5 w-3.5 shrink-0 text-status-warning-fg" />
      <span className="min-w-0 flex-1 text-status-warning-fg">{warning}</span>
      <button
        type="button"
        onClick={() => onCreate({ zone: chain.zone, workers: STANDBY_WORKERS })}
        className={buttonVariants({ variant: "outline", size: "xs" })}
        title="A standby KV cluster: 3 workers by default, the capacity policy's 1 to 5"
        data-testid="kv-no-standby-create"
      >
        <Plus aria-hidden />Create the next one
      </button>
    </div>
  );
}

/** One zone's KV clusters in their fill order, then those never offered to placement. */
function Zone({ chain, many, status, onCreate }: { chain: ZoneChain; many: boolean; status: LiveStatuses | undefined; onCreate: (start: KvDialogStart) => void }) {
  const count = chain.entries.length + chain.apart.length;
  return (
    <div data-testid="kv-zone" data-zone={chain.zone ?? ""}>
      {many && <p className="border-b bg-muted/20 px-4 py-1.5 font-mono text-[11px] text-muted-foreground">{chain.zone ?? "no zone"}</p>}
      {count === 0 ? (
        <p className="px-4 py-3 text-xs text-muted-foreground" data-testid="seed-empty">No KV cluster in its folder yet.</p>
      ) : (
        <ul className="divide-y" aria-label={`${chain.zone ?? "No zone"}: ${plural(count, "KV cluster")}, oldest first`}>
          {chain.entries.map((entry) => <KvClusterRow key={entry.cluster.name} cluster={entry.cluster} status={status} entry={entry} />)}
          {chain.apart.map((cluster) => <KvClusterRow key={cluster.name} cluster={cluster} status={status} />)}
        </ul>
      )}
      <NoStandby chain={chain} onCreate={onCreate} />
    </div>
  );
}

/**
 * A seed: its zone and hub, its KV clusters by zone in the order create-vm
 * fills them (ADR-0069), and Create KV cluster, which opens the draft.
 */
export function SeedCard({ entry, status }: { entry: SeedWithClusters; status: LiveStatuses | undefined }) {
  const { seed, clusters } = entry;
  const [creating, setCreating] = useState<KvDialogStart | null>(null);
  const chains = zoneChains(clusters, seed.zone ?? null);
  return (
    <article className="overflow-hidden rounded-xl border bg-card shadow-sm" data-testid="seed" data-seed={seed.name}>
      <header className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-3">
        <Sprout aria-hidden className="h-4 w-4 shrink-0 text-status-ready" />
        <h3 className="min-w-0 font-mono text-[13px] font-semibold break-all">{seed.name}</h3>
        {seed.zone && <Chip title="Availability zone">{seed.zone}</Chip>}
        {seed.env && <Chip title="Lifecycle">{seed.env}</Chip>}
        <OffConvention problems={seed.naming_problems} testId="seed-off-convention" />
        <span className="ml-auto text-xs text-muted-foreground">
          Hub <span className="font-mono">{seed.hub_version ?? "—"}</span>
        </span>
        <button
          type="button"
          onClick={() => setCreating({ zone: seed.zone ?? null, workers: STANDBY_WORKERS })}
          className={buttonVariants({ variant: "outline", size: "sm" })}
          data-testid="seed-create-kv"
        >
          <Plus aria-hidden />Create KV cluster
        </button>
      </header>
      {chains.map((chain) => (
        <Zone key={chain.zone ?? ""} chain={chain} many={chains.length > 1} status={status} onCreate={setCreating} />
      ))}
      {creating && <KvClusterDialog seed={seed.name} start={creating} onClose={() => setCreating(null)} />}
    </article>
  );
}
