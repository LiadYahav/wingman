"use client";

import type { ReactNode } from "react";
import type { FieldInputContext, FormValues } from "@/components/clusters/dynamic-variable-form";
import { infraEnvNames, isInfraEnvsPath } from "@/lib/infra-envs";
import { AlsoDrawsFrom } from "./also-draws-from";

/** The nodepool's own InfraEnv in the form, the one that names its NodePool. */
function ownOf(form: FormValues, index: number): string | undefined {
  const pools = form.nodepools;
  const pool = Array.isArray(pools) ? pools[index] : undefined;
  const own = pool && typeof pool === "object" && !Array.isArray(pool) ? pool.infra_env : undefined;
  return typeof own === "string" && own ? own : undefined;
}

/**
 * The create form's "Also draws from" for one nodepool (ADR-0064): the
 * InfraEnvs it draws Agents from beside its own, picked from the MCE's list
 * the single picker offers (typed when there is none). Day1 offers the input
 * only with `DAY1_MULTI_INFRAENV_NODEPOOLS`. `undefined` for any other field.
 */
export function infraEnvsCreateInput(
  { path, value, onChange, locked }: FieldInputContext,
  form: FormValues,
  options: string[] | null | undefined,
  loading: boolean
): ReactNode | undefined {
  if (!isInfraEnvsPath(path)) return undefined;
  const index = Number(/\[(\d+)\]/.exec(path)?.[1] ?? 0);
  const own = ownOf(form, index);
  return (
    <AlsoDrawsFrom
      value={infraEnvNames(value)}
      onChange={onChange}
      own={own}
      options={options ?? undefined}
      loading={loading}
      readOnly={locked}
      label={`Nodepool ${index + 1} also draws from`}
      note={
        <>
          Beside {own ? <span className="font-mono">{own}</span> : "its own InfraEnv"}, which names the NodePool. A new
          node takes the first free Agent of any of them.
        </>
      }
      testId={`nodepool-${index}-infra-envs`}
    />
  );
}
