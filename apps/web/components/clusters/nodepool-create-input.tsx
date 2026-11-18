"use client";

import type { ReactNode } from "react";
import type { FieldInputContext, FormValues } from "@/components/clusters/dynamic-variable-form";
import { isPolicyPath } from "@/lib/nodepool-policy";
import { infraEnvsCreateInput } from "./infra-envs-create-input";
import { PolicySelect } from "./policy-select";

/**
 * The create form's nodepool inputs that have a control of their own: the
 * InfraEnvs a nodepool also draws from (ADR-0064) and its scale-down policy
 * (ADR-0062), a select whose platform default sends nothing. Each shows only
 * when day1's template schema offers it; `undefined` for any other field.
 */
export function nodepoolCreateInput(
  context: FieldInputContext,
  form: FormValues,
  infraEnvs: string[] | null | undefined,
  loading: boolean
): ReactNode | undefined {
  if (!isPolicyPath(context.path)) return infraEnvsCreateInput(context, form, infraEnvs, loading);
  const index = Number(/\[(\d+)\]/.exec(context.path)?.[1] ?? 0);
  return (
    <PolicySelect
      value={context.value}
      onChange={(policy) => context.onChange(policy ?? "")}
      readOnly={context.locked}
      label={`Nodepool ${index + 1} scale-down policy`}
      testId={`nodepool-${index}-scale-down-policy`}
    />
  );
}
