"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleArrowUp, Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Hint } from "@/components/common/hint";
import { UpgradeDialog } from "@/components/clusters/upgrade/upgrade-dialog";
import { clusterHref, clusterQuery } from "@/lib/clusters";
import { stateWord, type RowUpgrade } from "@/lib/fleet-upgrades";
import { humanize } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { ClusterStatus, FleetUpgrade } from "@/types";

const CHIP = "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 font-sans text-[11px] font-medium whitespace-nowrap";

/** "Upgrading · <phase>", linked to the cluster's page, where the panel has the plan and the decisions. */
function Upgrading({ cluster, run }: { cluster: ClusterStatus; run: FleetUpgrade }) {
  const word = stateWord(run);
  return (
    <Tooltip>
      <TooltipTrigger
        render={<Link href={clusterHref(cluster)} />}
        data-testid="cluster-upgrading"
        className={cn(CHIP, "bg-status-provisioning/12 text-status-provisioning-fg hover:bg-status-provisioning/20")}
      >
        <Loader2 aria-hidden className="h-3 w-3 animate-spin motion-reduce:animate-none" />
        {word ? `Upgrading · ${humanize(word)}` : "Upgrading"}
      </TooltipTrigger>
      <TooltipContent className="block max-w-sm text-left">
        {run.waiting_for && <span className="block" data-testid="cluster-upgrading-waiting">{run.waiting_for}</span>}
        <span className="mt-0.5 block opacity-80">Open the cluster for the plan, the log and the decisions.</span>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * "Upgrade available → <version>", and for an admin the Upgrade that opens
 * the cluster page's dialog right here. Only a suggestion: the dialog asks the
 * workflow for its targets, and says so when it offers none.
 */
function Available({ cluster, version, isAdmin }: { cluster: ClusterStatus; version: string; isAdmin: boolean }) {
  const [open, setOpen] = useState(false);
  const hint =
    `MCE ${cluster.mce} offers OpenShift ${version}, newer than this cluster's ${cluster.mastertag}. ` +
    "Only a suggestion: the upgrade workflow plans the path, and may offer other targets, or none.";
  return (
    <span className="inline-flex items-center gap-1.5">
      <Hint
        hint={hint}
        testId="cluster-upgrade-available"
        className={cn(CHIP, "min-h-0 cursor-default bg-primary/8 text-primary")}
      >
        <CircleArrowUp aria-hidden className="h-3 w-3" />
        Upgrade available → {version}
      </Hint>
      {isAdmin && (
        <button
          type="button"
          data-testid="row-upgrade-action"
          onClick={() => setOpen(true)}
          title="Start the platform's upgrade-cluster workflow"
          className={buttonVariants({ variant: "outline", size: "xs" })}
        >
          Upgrade
        </button>
      )}
      {open && (
        <UpgradeDialog name={cluster.name} where={clusterQuery(cluster.site, cluster.mce)} onClose={() => setOpen(false)} />
      )}
    </span>
  );
}

/**
 * A clusters list row's upgrade, under its mastertag: upgrading, or an
 * upgrade available; nothing when up to date or while upgrades are off.
 * A viewer sees the state and the suggestion, with no Upgrade: starting is
 * an admin's (ADR-0055).
 */
export function UpgradeState({
  cluster,
  upgrade,
  isAdmin,
}: {
  cluster: ClusterStatus;
  upgrade: RowUpgrade;
  isAdmin: boolean;
}) {
  if (!upgrade) return null;
  return (
    <div className="mt-1">
      {upgrade.kind === "upgrading" ? (
        <Upgrading cluster={cluster} run={upgrade.run} />
      ) : (
        <Available cluster={cluster} version={upgrade.version} isAdmin={isAdmin} />
      )}
    </div>
  );
}
