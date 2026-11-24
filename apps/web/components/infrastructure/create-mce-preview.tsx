"use client";

import { useId, useState } from "react";
import { Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { firstSite, nextMceLetter, previewMceName, previewSites, siteZones, vmPlan } from "@/lib/mce-preview";
import type { Mce } from "@/types";
import { PreviewFields, type PreviewInputs } from "./create-mce-fields";
import { PlanAcceptance, PlanSteps, PlanSummary, type PlanFacts } from "./create-mce-plan";

/** Why Create does nothing yet: the one dead part of the preview. */
const NOT_YET =
  "Not available yet: a Customer MCE is installed by hand today (the platform's procedure 12); no workflow creates one.";

function PreviewTag() {
  return (
    <span className="rounded-full bg-primary/12 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-primary ring-1 ring-inset ring-primary/20">
      Preview
    </span>
  );
}

/** The choices worked out against the MCE list: the name, the site's zones and the VMs. */
function factsOf(mces: readonly Mce[], inputs: PreviewInputs): PlanFacts {
  const zones = inputs.site ? siteZones(mces, inputs.site) : [];
  return {
    site: inputs.site,
    name: inputs.site ? previewMceName(mces, inputs.site, inputs.lifecycle) : null,
    letter: inputs.site ? nextMceLetter(mces, inputs.site) : null,
    version: inputs.version,
    zones,
    workersPerZone: inputs.workersPerZone,
    plan: vmPlan(zones.length, inputs.workersPerZone),
  };
}

/**
 * What creating a Customer MCE will ask for and do, on the platform's design
 * (ADR-0018's 2026-11-24 amendment): a tenants' hub for one OpenShift version
 * band, a standalone cluster on KubeVirt VMs, one master per zone and the
 * workers spread over the zones. The inputs work and the name, zones and
 * steps follow them; Create stays disabled with its reason, and nothing here
 * calls an API or writes anything. Mount it while open: its state is one look.
 */
function CreateMceDialog({ mces, onClose }: { mces: readonly Mce[]; onClose: () => void }) {
  const reasonId = useId();
  const [chosen, setInputs] = useState<PreviewInputs>({ site: null, lifecycle: "prod", version: "", workersPerZone: 1 });
  // Until a site is chosen, the first with a seed: also once the list arrives after the dialog opened
  const inputs = { ...chosen, site: chosen.site ?? firstSite(mces) };
  const facts = factsOf(mces, inputs);
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-3xl"
        data-testid="mce-preview-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            Create a Customer MCE <PreviewTag />
          </DialogTitle>
          <DialogDescription className="text-pretty">
            The tenants&apos; hub for one OpenShift version band, on KubeVirt VMs. A preview of what creating one will
            ask for and do: nothing here is sent or written.
          </DialogDescription>
        </DialogHeader>
        <div className="-mx-4 grid content-start gap-5 overflow-y-auto overscroll-contain px-4 pb-1">
          <div className="grid gap-4 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
            <PreviewFields sites={previewSites(mces)} inputs={inputs} onChange={setInputs} />
            <PlanSummary facts={facts} />
          </div>
          <PlanSteps facts={facts} />
          <PlanAcceptance />
        </div>
        <DialogFooter className="flex-col sm:items-center">
          <p id={reasonId} className="text-xs text-muted-foreground text-pretty sm:mr-auto sm:max-w-md" data-testid="mce-preview-reason">
            {NOT_YET}
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className={buttonVariants({ variant: "outline" })}>Close</button>
            <button type="button" disabled aria-describedby={reasonId} className={buttonVariants()} data-testid="mce-preview-create">
              Create MCE
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Customer MCEs' Create MCE: it opens the preview of the vision, marked so on
 * the button itself. Admins only, as the whole Infrastructure workspace is.
 */
export function CreateMcePreview({ mces }: { mces: readonly Mce[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={buttonVariants({ variant: "outline", size: "sm" })} data-testid="create-mce">
        <Plus aria-hidden />
        Create MCE
        <PreviewTag />
      </button>
      {open && <CreateMceDialog mces={mces} onClose={() => setOpen(false)} />}
    </>
  );
}
