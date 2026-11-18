"use client";

import { AlsoDrawsFrom } from "@/components/clusters/also-draws-from";
import { infraEnvNames, INFRA_ENVS_INPUT } from "@/lib/infra-envs";
import { ValueField } from "./controls";
import { nodepoolPath } from "./model";

/**
 * A flavor nodepool's "Also draws from" preset (ADR-0064): InfraEnvs beside
 * its own, typed (a flavor is not tied to an MCE, so there is no list to pick
 * from, as for its own InfraEnv). None is no key: the input is left out.
 */
export function InfraEnvsPreset({
  index,
  own,
  value,
  onChange,
  problems,
}: {
  index: number;
  own: unknown;
  value: unknown;
  onChange: (value: unknown) => void;
  problems: string[];
}) {
  const names = infraEnvNames(value);
  return (
    <ValueField
      path={nodepoolPath(index, INFRA_ENVS_INPUT)}
      label="Also draws from"
      empty={names.length === 0}
      problems={problems}
      hint="A preset: beside its own InfraEnv, which names the NodePool; a cluster may change it."
      labelsInput={false}
      className="sm:col-span-2"
    >
      {() => (
        <AlsoDrawsFrom
          value={names}
          onChange={(next) => onChange(next.length > 0 ? next : undefined)}
          own={typeof own === "string" && own ? own : undefined}
          label={`Nodepool ${index + 1} also draws from`}
          testId={`nodepool-${index}-infra-envs`}
        />
      )}
    </ValueField>
  );
}
