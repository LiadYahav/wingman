"use client";

import { useState } from "react";
import { CircleArrowUp } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { UpgradeDialog } from "@/components/clusters/upgrade/upgrade-dialog";
import { useUpgradeRun } from "@/lib/api/upgrades";
import { isOpen } from "@/lib/upgrade";

/**
 * The Mastertag row's Upgrade, for admins: only while upgrades are on and
 * the cluster has no open run (the panel shows that one). Versions change
 * this way while upgrades are on (ADR-0055).
 */
export function UpgradeAction({ name, where, isAdmin }: { name: string; where: string; isAdmin: boolean }) {
  const { data } = useUpgradeRun(name, where);
  const [open, setOpen] = useState(false);
  if (!isAdmin || !data || data.state === "off" || (data.state === "run" && isOpen(data.run))) return null;
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
