"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useFleetUpgrades } from "@/lib/api/upgrades";
import { openByCluster, stateWord, upgradeHref } from "@/lib/fleet-upgrades";
import { humanize } from "@/lib/nodes";

/**
 * "Upgrading" beside a cluster on the clusters list while its upgrade run is
 * open; the tooltip says where it is, and a click opens the cluster's page.
 * Nothing while upgrades are off or the cluster has no open run. Every row
 * shares the one fleet query.
 */
export function UpgradingBadge({ name }: { name: string }) {
  const { data } = useFleetUpgrades();
  const run = data?.state === "on" ? openByCluster(data.runs).get(name) : undefined;
  if (!run) return null;
  const word = stateWord(run);
  return (
    <Tooltip>
      <TooltipTrigger
        render={<Link href={upgradeHref(run)} />}
        data-testid="cluster-upgrading"
        className="ml-2 inline-flex items-center gap-1 rounded-full bg-status-provisioning/12 px-1.5 py-0.5 font-sans text-[11px] font-medium text-status-provisioning-fg hover:bg-status-provisioning/20"
      >
        <Loader2 aria-hidden className="h-3 w-3 animate-spin motion-reduce:animate-none" />
        Upgrading
      </TooltipTrigger>
      <TooltipContent className="block max-w-sm text-left">
        <span className="font-medium">{word ? humanize(word) : "Upgrade running"}</span>
        {run.waiting_for && <span className="mt-0.5 block">{run.waiting_for}</span>}
      </TooltipContent>
    </Tooltip>
  );
}
