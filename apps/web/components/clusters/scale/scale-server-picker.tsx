"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { humanize, useClusterNodes } from "@/lib/nodes";
import { pickedWords, serversOf, type PickableServer } from "@/lib/scale-servers";
import { cn } from "@/lib/utils";
import type { ScaleTabValue } from "./scale-tab";

/** The NodePool's servers a scale-down could pick, from the Nodes tab's own read of the MCE (`GET .../nodes`). */
export function usePickable(tab: ScaleTabValue): PickableServer[] {
  const { data } = useClusterNodes(tab.cluster.name, tab.cluster.where);
  const nodepool = tab.state.change?.nodepool;
  const pool = data && !data.off ? data.data.node_pools.find((p) => p.name === nodepool) : undefined;
  return serversOf(pool);
}

/**
 * Under "Pick the servers" in a scale-down's confirmation (ADR-0062's
 * 2026-11-18 amendments): the NodePool's servers, to tick exactly the ones
 * that leave. Once as many are ticked as leave, the rest wait; Yes waits
 * until then. Without live status there is nothing to pick from: the choice
 * says so and is not offered (`scale-leave-choice.tsx`).
 */
export function ServerPicker({ tab, offered }: { tab: ScaleTabValue; offered: PickableServer[] }) {
  const { change, leaving, servers, toggleServer, start } = tab.state;
  if (!change || leaving <= 0 || offered.length === 0) return null;
  const full = servers.length >= leaving;
  return (
    <div className="space-y-1.5" data-testid="scale-pick">
      <ul className="max-h-48 space-y-1 overflow-y-auto" aria-label={`Servers of ${change.nodepool}`}>
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
    </div>
  );
}
