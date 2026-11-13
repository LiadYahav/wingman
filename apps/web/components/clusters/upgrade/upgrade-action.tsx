"use client";

import { useState } from "react";
import { CircleArrowUp } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Hint } from "@/components/common/hint";
import { UpgradeDialog } from "@/components/clusters/upgrade/upgrade-dialog";
import { useUpgradeRun } from "@/lib/api/upgrades";
import { isOpen } from "@/lib/upgrade";
import { cn } from "@/lib/utils";

/** Why an admin sees Upgrade greyed out: the setting that turns it on. */
const UPGRADES_OFF = "Upgrades are off on this Wingman (DAY1_UPGRADES=false).";

/** Upgrade, greyed out, with why in a tooltip: admins learn the feature exists. */
function UpgradeOff() {
  return (
    <Hint hint={UPGRADES_OFF} label="Upgrade is off: why" testId="upgrade-action-off">
      <span aria-hidden className={cn(buttonVariants({ variant: "outline", size: "xs" }), "pointer-events-none opacity-50")}>
        <CircleArrowUp aria-hidden />Upgrade
      </span>
    </Hint>
  );
}

/**
 * The Mastertag row's Upgrade, for admins: only while upgrades are on and
 * the cluster has no open run (the panel shows that one). Versions change
 * this way while upgrades are on (ADR-0055). Off, admins see it greyed out
 * with why; viewers see nothing.
 */
export function UpgradeAction({ name, where, isAdmin }: { name: string; where: string; isAdmin: boolean }) {
  const { data } = useUpgradeRun(name, where);
  const [open, setOpen] = useState(false);
  if (!isAdmin || !data || (data.state === "run" && isOpen(data.run))) return null;
  if (data.state === "off") return <UpgradeOff />;
  return (
    <>
      <button
        type="button"
        data-testid="upgrade-action"
        onClick={() => setOpen(true)}
        title="Start the platform's upgrade-cluster workflow"
        className={buttonVariants({ variant: "outline", size: "xs" })}
      >
        <CircleArrowUp aria-hidden />Upgrade
      </button>
      {open && <UpgradeDialog name={name} where={where} onClose={() => setOpen(false)} />}
    </>
  );
}
