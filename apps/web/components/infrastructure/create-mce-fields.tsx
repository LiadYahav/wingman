"use client";

import { useId, type ReactNode } from "react";
import { Minus, Plus } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Segmented } from "@/components/specs/flavor-editor/controls";
import { LIFECYCLES, WORKERS_PER_ZONE, versionProblem, workersPerZone, type Lifecycle } from "@/lib/mce-preview";
import { cn } from "@/lib/utils";

/** What the preview asks for: the form's state. */
export interface PreviewInputs {
  site: string | null;
  lifecycle: Lifecycle;
  version: string;
  workersPerZone: number;
}

const LIFECYCLE_OPTIONS = LIFECYCLES.map((value) => ({ value, label: value }));

const inputClass =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 font-mono text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 placeholder:text-muted-foreground/60 aria-invalid:border-status-error dark:bg-input/30";

const stepClass =
  "flex size-8 shrink-0 items-center justify-center text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground active:bg-muted-foreground/15 focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-35 pointer-coarse:size-10";

/** One field: its label, the control, and a line under it (help, or what is wrong). */
function Field({ id, label, note, problem, children }: { id: string; label: string; note?: ReactNode; problem?: string | null; children: ReactNode }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {problem ? (
        <p id={`${id}-note`} className="text-xs text-status-error-fg" data-testid="mce-preview-problem">{problem}</p>
      ) : (
        note && <p id={`${id}-note`} className="text-xs text-muted-foreground text-pretty">{note}</p>
      )}
    </div>
  );
}

/** − n +: the workers in each zone, by a button, the arrow keys or typed. */
function WorkersStepper({ id, value, onValue }: { id: string; value: number; onValue: (n: number) => void }) {
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    onValue(workersPerZone(value + (e.key === "ArrowUp" ? 1 : -1)));
  };
  return (
    <div className="inline-flex w-fit items-stretch overflow-hidden rounded-lg border bg-background shadow-xs dark:bg-input/30" role="group" aria-label="Workers per zone">
      <button type="button" className={stepClass} onClick={() => onValue(workersPerZone(value - 1))} disabled={value <= WORKERS_PER_ZONE.min} aria-label="One worker fewer per zone">
        <Minus aria-hidden className="size-4" />
      </button>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        role="spinbutton"
        aria-valuemin={WORKERS_PER_ZONE.min}
        aria-valuemax={WORKERS_PER_ZONE.max}
        aria-valuenow={value}
        aria-describedby={`${id}-note`}
        autoComplete="off"
        value={String(value)}
        onChange={(e) => onValue(workersPerZone(Number.parseInt(e.target.value, 10)))}
        onKeyDown={onKeyDown}
        onFocus={(e) => e.currentTarget.select()}
        data-testid="mce-preview-workers"
        className="w-11 min-w-0 border-x bg-transparent text-center text-sm font-semibold tabular-nums outline-none focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      />
      <button type="button" className={stepClass} onClick={() => onValue(workersPerZone(value + 1))} disabled={value >= WORKERS_PER_ZONE.max} aria-label="One worker more per zone">
        <Plus aria-hidden className="size-4" />
      </button>
    </div>
  );
}

/**
 * The preview's four inputs: the site (the day1 repo's), the lifecycle, the
 * OpenShift version band it will serve and the workers in each zone. They
 * work, so the name, the zones and the steps follow them; nothing is sent.
 */
export function PreviewFields({ sites, inputs, onChange }: { sites: string[]; inputs: PreviewInputs; onChange: (next: PreviewInputs) => void }) {
  const siteId = useId();
  const versionId = useId();
  const workersId = useId();
  const set = (patch: Partial<PreviewInputs>) => onChange({ ...inputs, ...patch });
  const problem = versionProblem(inputs.version);
  const items = sites.map((site) => ({ value: site, label: site }));
  return (
    <div className="grid content-start gap-4" data-testid="mce-preview-fields">
      <Field id={siteId} label="Site" note={sites.length === 0 ? "The day1 repo has no site yet." : "Where its VMs run: the site's zones."}>
        <Select value={inputs.site} onValueChange={(site) => site && set({ site })} items={items} disabled={sites.length === 0}>
          <SelectTrigger id={siteId} className="w-full" aria-label="Site" data-testid="mce-preview-site">
            <SelectValue placeholder="No site" />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {items.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
      <div className="grid min-w-0 gap-1.5">
        <span className="text-xs font-medium text-muted-foreground" aria-hidden>Lifecycle</span>
        <Segmented options={LIFECYCLE_OPTIONS} value={inputs.lifecycle} onChange={(lifecycle) => set({ lifecycle })} label="Lifecycle" testId="mce-preview-lifecycle" className="w-fit" />
      </div>
      <Field
        id={versionId}
        label="OpenShift version"
        problem={problem}
        note="The band it serves: a tenant's cluster may not run newer than its MCE supports."
      >
        <input
          id={versionId}
          value={inputs.version}
          onChange={(e) => set({ version: e.target.value })}
          placeholder="4.20"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={problem !== null}
          aria-describedby={`${versionId}-note`}
          data-testid="mce-preview-version"
          className={inputClass}
        />
      </Field>
      <Field id={workersId} label="Workers per zone" note={`${WORKERS_PER_ZONE.min} to ${WORKERS_PER_ZONE.max}; acceptance test P11 builds one in each of three zones.`}>
        <WorkersStepper id={workersId} value={inputs.workersPerZone} onValue={(n) => set({ workersPerZone: n })} />
      </Field>
    </div>
  );
}

/** A small mono chip: a label, a path, a file. */
export function Code({ children, className }: { children: ReactNode; className?: string }) {
  return <code className={cn("rounded bg-muted px-1 py-px font-mono text-[11px] text-foreground [overflow-wrap:anywhere]", className)}>{children}</code>;
}
