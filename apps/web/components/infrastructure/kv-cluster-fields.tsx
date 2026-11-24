"use client";

import { useId } from "react";
import { Info } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { Combobox } from "@/components/ui/combobox";
import type { KvDraft } from "@/types";

export type Owner = { merkaz: string; anaf: string; mador: string };
export const OWNER_KEYS = ["merkaz", "anaf", "mador"] as const;

const INPUT =
  "w-full rounded-md border bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-status-error";

function Label({ htmlFor, children, hint }: { htmlFor?: string; children: string; hint?: string }) {
  return (
    <span className="flex min-h-6 items-center gap-1 text-xs font-medium text-muted-foreground">
      {htmlFor ? <label htmlFor={htmlFor}>{children}</label> : <span>{children}</span>}
      {hint && (
        <Hint hint={hint} label={`About ${children}`}>
          <Info aria-hidden className="h-3 w-3" />
        </Hint>
      )}
    </span>
  );
}

/** A choice among the draft's options: a combobox, or the one option as text when there is no other. */
function Choice({
  label, hint, options, value, onChange, disabled, testId, mono = true,
}: {
  label: string; hint: string; options: string[]; value: string | null; onChange: (value: string | null) => void;
  disabled: boolean; testId: string; mono?: boolean;
}) {
  const id = useId();
  return (
    <div className="grid min-w-0 grid-cols-1 gap-1">
      <Label htmlFor={options.length > 1 ? id : undefined} hint={hint}>{label}</Label>
      {options.length > 1 ? (
        <Combobox
          id={id}
          options={options.map((o) => ({ value: o, label: o }))}
          value={value}
          onValueChange={onChange}
          placeholder={`Choose the ${label.toLowerCase()}`}
          searchPlaceholder={`Search…`}
          emptyMessage="None matches."
          disabled={disabled}
          aria-label={label}
          data-testid={testId}
        />
      ) : (
        <span data-testid={testId} className={`min-h-8 py-1.5 text-sm ${mono ? "font-mono" : ""} ${value ? "" : "text-muted-foreground"}`}>
          {value ?? "None found"}
        </span>
      )}
    </div>
  );
}

/**
 * What a KV cluster's dialog shows and lets an admin choose (ADR-0069): the
 * derived name, the zone, the version, the InfraEnv, the workers, and the
 * owner only when no KV cluster exists to copy it from.
 */
export function KvClusterFields({
  draft, zone, mastertag, infraEnv, workers, owner, onZone, onMastertag, onInfraEnv, onWorkers, onOwner, disabled,
}: {
  draft: KvDraft;
  zone: string | null;
  mastertag: string | null;
  infraEnv: string | null;
  workers: string;
  owner: Owner;
  onZone: (zone: string | null) => void;
  onMastertag: (mastertag: string | null) => void;
  onInfraEnv: (infraEnv: string | null) => void;
  onWorkers: (workers: string) => void;
  onOwner: (owner: Owner) => void;
  disabled: boolean;
}) {
  const workersId = useId();
  const [low, high] = draft.standby_workers;
  const from = draft.infra_envs_from === "hub" ? "read from the seed's hub" : "named by the seed's KV cluster files (live status is off)";
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="grid min-w-0 gap-1 sm:col-span-2">
        <Label hint="The lowest free id letter on the convention's ocp4-<lc>-kv-<site>-<zone>-<id>: no cluster file and no open provision-cluster merge request has it.">
          Name
        </Label>
        <span data-testid="kv-draft-name" className="font-mono text-sm font-semibold break-all">{draft.name ?? "—"}</span>
      </div>
      <Choice
        label="Zone" testId="kv-draft-zone" options={draft.zones} value={zone ?? draft.zone} onChange={onZone} disabled={disabled}
        hint="The zone in the seed's name; a seed whose name gives none offers the zones of its bare-metal InfraEnvs."
      />
      <Choice
        label="OpenShift" testId="kv-draft-version" options={draft.versions} value={mastertag ?? draft.mastertag} onChange={onMastertag}
        disabled={disabled} hint="The releases the seed offers (the day1 repo's upgrade ladder); its own default first when it offers it."
      />
      <Choice
        label="InfraEnv" testId="kv-draft-infra-env" options={draft.infra_envs} value={infraEnv ?? draft.infra_env} onChange={onInfraEnv}
        disabled={disabled} hint={`The zone's bare-metal pool, <flavor>-mtl-<zone>, ${from}.`}
      />
      <div className="grid min-w-0 gap-1">
        <Label htmlFor={workersId} hint={`1 to ${draft.max_workers} (the capacity policy's maxNodes). A standby KV cluster is built with ${low} to ${high}.`}>
          Workers
        </Label>
        <input
          id={workersId} type="number" min={1} max={draft.max_workers} value={workers} disabled={disabled}
          onChange={(e) => onWorkers(e.target.value)} data-testid="kv-draft-workers" className={INPUT}
        />
      </div>
      {draft.model === null && (
        <fieldset className="grid gap-2 sm:col-span-2" data-testid="kv-draft-owner">
          <legend className="text-xs font-medium text-muted-foreground">Owner: no KV cluster exists to copy it from</legend>
          <div className="grid grid-cols-3 gap-2">
            {OWNER_KEYS.map((key) => (
              <input
                key={key} aria-label={`Owner ${key}`} placeholder={key} inputMode="numeric" value={owner[key]} disabled={disabled}
                onChange={(e) => onOwner({ ...owner, [key]: e.target.value.trim() })} className={`${INPUT} font-mono`}
              />
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}
