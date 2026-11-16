"use client";

import { ReviewDialog } from "@/components/common/review-dialog";
import type { AddonDrift } from "@/types";

/** One row of what the fix installs. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="text-muted-foreground w-24 shrink-0">{label}</span>
      {children}
    </div>
  );
}

/**
 * The drift tab's Fix of a missing spec add-on: what it installs (at the
 * add-on's revision, with the values requested at create) before the day2
 * merge request is opened. Mount it while open.
 */
export function FixAddonDialog({ entry, onClose, onConfirm, pending }: {
  entry: AddonDrift;
  onClose: () => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  const requested = Object.keys(entry.override_values).length;
  return (
    <ReviewDialog
      open
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={`Fix: Install ${entry.addon_name}`}
      description={`Install ${entry.addon_name} of ${entry.team} at the add-on's revision, with the values requested at create. Opens a GitLab MR for approval.`}
      onConfirm={onConfirm}
      isPending={pending}
      confirmLabel="Confirm — Create Install MR"
    >
      <div className="rounded-lg border bg-muted/30 p-4 text-sm space-y-2">
        <Fact label="Addon">
          <span className="font-semibold font-mono break-all">{entry.addon_name}</span>
        </Fact>
        <Fact label="Team">
          <span className="font-medium">{entry.team}</span>
        </Fact>
        <Fact label="Version">
          <span className="font-medium">the add-on&apos;s revision</span>
        </Fact>
        <Fact label="Values">
          <span className="font-medium">{requested > 0 ? `${requested} requested at create` : "chart and Sig values"}</span>
        </Fact>
      </div>
    </ReviewDialog>
  );
}
