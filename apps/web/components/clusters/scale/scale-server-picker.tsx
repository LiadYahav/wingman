"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { humanize, useClusterNodes } from "@/lib/nodes";
import { pickedWords, serversOf } from "@/lib/scale-servers";
import { cn } from "@/lib/utils";
import type { ScaleTabValue } from "./scale-tab";

/**
 * In a scale-down's confirmation: the NodePool's servers, to tick exactly
 * the ones that leave (ADR-0062's 2026-11-18 amendment). Optional: none
 * ticked, the NodePool's scale-down policy picks, as before. The list is the
 * Nodes tab's own read of the MCE (`GET .../nodes`), so without live status
 * there is nothing to pick from, and it says so. Once as many are ticked as
 * leave, the rest wait; Yes waits until the count is none or all.
 */
export function ServerPicker({ tab }: { tab: ScaleTabValue }) {
  const { change, leaving, servers, toggleServer, start } = tab.state;
  const { data } = useClusterNodes(tab.cluster.name, tab.cluster.where);
  if (!change || leaving <= 0) return null;
  const pool = data && !data.off ? data.data.node_pools.find((p) => p.name === change.nodepool) : undefined;
  const offered = serversOf(pool);
  if (offered.length === 0) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="scale-pick-none">
        Picking which servers leave needs this NodePool&apos;s nodes from the MCE (live status); without them its scale-down
        policy picks.
      </p>
    );
  }
  const full = servers.length >= leaving;
  return (
    <fieldset className="space-y-2 rounded-lg border px-3 pb-2.5 pt-1.5" data-testid="scale-pick">
      <legend className="px-1 text-xs font-semibold">Which servers leave (optional)</legend>
      <ul className="max-h-56 space-y-1 overflow-y-auto" aria-label={`Servers of ${change.nodepool}`}>
        {offered.map((s) => {
          const ticked = s.name !== null && servers.includes(s.name);
          const held = s.name === null || s.why !== null || (full && !ticked);
          return (
            <li key={s.label} data-testid="scale-pick-server" data-server={s.name ?? ""}>
              <label className={cn("flex items-start gap-2.5 text-sm", held && !ticked && "text-muted-foreground")}>
                <Checkbox
                  checked={ticked}
                  onCheckedChange={() => s.name && toggleServer(s.name)}
                  disabled={held || start.isPending}
                  aria-label={s.label}
                  className="mt-0.5"
                />
                <span className="min-w-0 break-words">
                  <span className="block font-mono break-all">{s.label}</span>
                  <span className="block text-xs text-muted-foreground">
                    {s.node ?? "no Node yet"} · {humanize(s.state)}
                    {s.why && <> · {s.why}</>}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      <p role="status" className="text-xs text-muted-foreground" data-testid="scale-pick-count">
        {pickedWords(servers.length, leaving)}
      </p>
    </fieldset>
  );
}
