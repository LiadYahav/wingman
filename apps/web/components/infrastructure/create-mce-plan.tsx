"use client";

import { useId, type ReactNode } from "react";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { MCE_VM, type VmPlan } from "@/lib/mce-preview";
import { cn, plural } from "@/lib/utils";
import { Code } from "./create-mce-fields";

/** Where the name, zones and steps come from: the form's choices worked out. */
export interface PlanFacts {
  site: string | null;
  name: string | null;
  letter: string | null;
  version: string;
  zones: string[];
  workersPerZone: number;
  plan: VmPlan;
}

/** The zones the design spreads an MCE over (AD19). */
const DESIGN_ZONES = 3;

function Note({ tone = "muted", children, ...props }: { tone?: "muted" | "warning"; children: ReactNode; "data-testid"?: string }) {
  return (
    <p
      className={cn(
        "flex items-start gap-1.5 text-xs text-pretty",
        tone === "warning" ? "rounded-lg bg-status-warning/12 px-2.5 py-2 text-status-warning-fg" : "text-muted-foreground"
      )}
      {...props}
    >
      {tone === "warning" && <TriangleAlert aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
      <span>{children}</span>
    </p>
  );
}

function Vm({ role }: { role: "master" | "worker" }) {
  return (
    <li className="flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-[11px] dark:bg-input/30">
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", role === "master" ? "bg-primary" : "bg-muted-foreground/50")} />
      <span className={role === "master" ? "font-medium" : "text-muted-foreground"}>{role}</span>
      <span className="ml-auto hidden font-mono text-[10px] text-muted-foreground sm:inline">{MCE_VM.size}</span>
    </li>
  );
}

/** Each zone's VMs: its master, then its workers. */
function ZoneColumns({ zones, workersPerZone }: { zones: string[]; workersPerZone: number }) {
  return (
    <ul className="grid grid-cols-[repeat(auto-fit,minmax(5rem,1fr))] gap-2" aria-label="VMs by zone">
      {zones.map((zone) => (
        <li key={zone} className="min-w-0 rounded-lg bg-muted/60 p-2" data-testid="mce-preview-zone" data-zone={zone}>
          <p className="mb-1.5 font-mono text-xs font-medium">{zone}</p>
          <ul className="space-y-1" aria-label={`${zone}: 1 master, ${plural(workersPerZone, "worker")}`}>
            <Vm role="master" />
            {Array.from({ length: workersPerZone }, (_, i) => <Vm key={i} role="worker" />)}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function ZonesBody({ facts }: { facts: PlanFacts }) {
  const { site, zones, plan } = facts;
  if (site === null) return null;
  if (zones.length === 0) {
    return (
      <Note tone="warning" data-testid="mce-preview-no-zones">
        {site} has no seed yet. The site needs a seed in each zone first: the MCE&apos;s VMs run on the zones&apos; KV clusters.
      </Note>
    );
  }
  return (
    <>
      <ZoneColumns zones={zones} workersPerZone={facts.workersPerZone} />
      <p className="text-xs text-muted-foreground tabular-nums" data-testid="mce-preview-totals">
        <span className="font-semibold text-foreground">{plural(plan.vms, "VM")}</span>
        {` · ${plural(plan.masters, "master")}, ${plural(plan.workers, "worker")} · ${plan.vcpu} vCPU · ${plan.memoryGiB} GiB`}
      </p>
      {zones.length < DESIGN_ZONES && (
        <Note data-testid="mce-preview-few-zones">
          The design spreads an MCE over three zones, a master in each; {site} has a seed in {plural(zones.length, "zone")} so far.
        </Note>
      )}
    </>
  );
}

/** What the choices make: the name, and each zone's VMs. */
export function PlanSummary({ facts }: { facts: PlanFacts }) {
  const { site, name, letter } = facts;
  return (
    <section className="grid content-start gap-3 self-start rounded-xl border bg-card p-3.5 shadow-xs" aria-label="What it will be" data-testid="mce-preview-summary">
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Name</p>
        <p className="mt-0.5 font-mono text-[15px] font-semibold break-all" data-testid="mce-preview-name">{name ?? "—"}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {site === null
            ? "No site in the day1 repo yet."
            : letter
              ? <>Its <Code>{"<id>"}</Code> is <Code>{letter}</Code>, the first letter no Customer MCE at {site} has.</>
              : <>Every letter, a to z, is taken at {site}.</>}
        </p>
      </div>
      <ZonesBody facts={facts} />
    </section>
  );
}

/** The steps a create will take, in order; each says what it does with the choices. */
function steps({ site, name, version, plan }: PlanFacts): { title: string; detail: ReactNode }[] {
  const mce = name ?? "<name>";
  return [
    {
      title: "Create the VMs",
      detail: (
        <>
          create-vm builds {plan.vms > 0 ? `${plural(plan.masters, "master")} and ${plural(plan.workers, "worker")}` : "a master in each zone and the workers"},
          each a {MCE_VM.size} ({MCE_VM.vcpu} vCPU, {MCE_VM.memoryGiB} GiB), labelled <Code>redbull.io/role=mce</Code> and{" "}
          <Code>redbull.io/mce={mce}</Code>, no two on one hypervisor.
        </>
      ),
    },
    {
      title: "Install the cluster",
      detail: (
        <>
          A standalone OpenShift {version.trim() || "cluster"} on those VMs, every Node labelled with its zone
          (<Code>topology.kubernetes.io/zone</Code>).
        </>
      ),
    },
    { title: "Install MCE with HyperShift", detail: "The multicluster engine, HyperShift and the Agent installer: what hosts the tenants' control planes." },
    {
      title: "Add its day1 folder",
      detail: (
        <>
          <Code>{`sites/${site ?? "<site>"}/mces/${mce}/`}</Code> with <Code>values.yaml</Code> and <Code>version.yaml</Code>; this page then lists it.
        </>
      ),
    },
    { title: "Fill its pools", detail: "herzi fills its InfraEnv pools, and placement may pick it for a new tenant's cluster." },
  ];
}

/** What creating it will do, as numbered steps that follow the choices. */
export function PlanSteps({ facts }: { facts: PlanFacts }) {
  const titleId = useId();
  const list = steps(facts);
  return (
    <section aria-labelledby={titleId}>
      <h3 id={titleId} className="mb-2.5 text-sm font-semibold">What it will do</h3>
      <ol className="space-y-0" data-testid="mce-preview-steps">
        {list.map((step, index) => (
          <li key={step.title} className="relative flex gap-3 pb-3.5 last:pb-0">
            {index < list.length - 1 && <span aria-hidden className="absolute top-6 bottom-0 left-[11px] w-px bg-border" />}
            <span aria-hidden className="relative flex size-6 shrink-0 items-center justify-center rounded-full border bg-background text-[11px] font-semibold tabular-nums text-muted-foreground">
              {index + 1}
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-sm font-medium">{step.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground text-pretty">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** The platform's acceptance test P11: what a created Customer MCE must hold. */
const ACCEPTANCE = [
  "One master VM in each zone",
  "Three worker VMs",
  <>Every VM labelled <Code>redbull.io/role=mce</Code> and <Code>redbull.io/mce=&lt;name&gt;</Code></>,
  "No two of its VMs on one hypervisor",
  "Every Node labelled with its zone",
];

export function PlanAcceptance() {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="rounded-xl bg-muted/50 p-3.5">
      <h3 id={titleId} className="mb-2 text-sm font-semibold">
        Done when <span className="font-normal text-muted-foreground">· the platform&apos;s acceptance test P11</span>
      </h3>
      <ul className="grid gap-1.5 sm:grid-cols-2" data-testid="mce-preview-acceptance">
        {ACCEPTANCE.map((line, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs">
            <CircleCheck aria-hidden className="mt-px h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0">{line}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
