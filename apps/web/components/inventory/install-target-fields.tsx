"use client";

import { useId } from "react";
import { Info } from "lucide-react";
import { Combobox } from "@/components/ui/combobox";
import { Hint } from "@/components/common/hint";
import { OTHER_INFRA_ENV, infraEnvOptions, infraEnvProblem, knownInfraEnvs, mceOptions } from "@/lib/inventory/install";
import type { InventoryRun, MceInventory } from "@/types/inventory";

const INFRA_ENV_HINT =
  "The InfraEnv's name states the hardware, so it is also the pool: the healthy, unclaimed servers server-scan lists under ocp-<InfraEnv>. The workflow first checks the MCE has it.";

function Label({ htmlFor, children, hint }: { htmlFor: string; children: string; hint?: string }) {
  return (
    <span className="flex min-h-6 items-center gap-1 text-xs font-medium text-muted-foreground">
      <label htmlFor={htmlFor}>{children}</label>
      {hint && (
        <Hint hint={hint} label={`About ${children}`}>
          <Info aria-hidden className="h-3 w-3" />
        </Hint>
      )}
    </span>
  );
}

/** The typed InfraEnv, with why it is not a name yet. */
function TypedInfraEnv({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled: boolean }) {
  const id = useId();
  const problem = value ? infraEnvProblem(value.trim()) : null;
  return (
    <div className="grid gap-1">
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        autoComplete="off"
        spellCheck={false}
        placeholder="cisco-m6-site1-64c-512gb"
        aria-label="InfraEnv name"
        aria-invalid={problem !== null}
        aria-describedby={problem ? `${id}-problem` : undefined}
        className="w-full rounded-md border bg-background px-2.5 py-1.5 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-status-error"
      />
      {problem && (
        <p id={`${id}-problem`} className="text-xs text-status-error" data-testid="infra-env-problem">
          {problem}
        </p>
      )}
    </div>
  );
}

/**
 * Where to install: a day1 MCE, then one of the InfraEnvs the page knows on
 * it (its pools, and those its runs filled), or another one typed.
 */
export function InstallTargetFields({
  mces,
  runs,
  mce,
  picked,
  typed,
  onMce,
  onPicked,
  onTyped,
  disabled,
}: {
  mces: MceInventory[];
  runs: InventoryRun[];
  mce: string | null;
  /** The chosen InfraEnv, or `OTHER_INFRA_ENV` while one is typed. */
  picked: string | null;
  typed: string;
  onMce: (mce: string | null) => void;
  onPicked: (infraEnv: string | null) => void;
  onTyped: (name: string) => void;
  disabled: boolean;
}) {
  const mceId = useId();
  const poolId = useId();
  const chosen = mces.find((m) => m.mce === mce);
  const known = knownInfraEnvs(chosen, runs);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="grid min-w-0 grid-cols-1 gap-1">
        <Label htmlFor={mceId}>MCE</Label>
        <Combobox
          id={mceId}
          options={mceOptions(mces)}
          value={mce}
          onValueChange={onMce}
          placeholder="Choose an MCE"
          searchPlaceholder="Search MCEs…"
          emptyMessage="No MCE matches."
          disabled={disabled}
          aria-label="MCE"
          data-testid="install-mce"
        />
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-1">
        <Label htmlFor={poolId} hint={INFRA_ENV_HINT}>InfraEnv</Label>
        <Combobox
          id={poolId}
          options={infraEnvOptions(known, chosen)}
          value={picked}
          onValueChange={onPicked}
          placeholder={mce ? "Choose a pool" : "Choose an MCE first"}
          searchPlaceholder="Search InfraEnvs…"
          emptyMessage="No InfraEnv matches."
          disabled={disabled || !mce}
          aria-label="InfraEnv"
          data-testid="install-infra-env"
        />
      </div>
      {picked === OTHER_INFRA_ENV && (
        <div className="sm:col-span-2">
          <TypedInfraEnv value={typed} onChange={onTyped} disabled={disabled} />
        </div>
      )}
    </div>
  );
}
