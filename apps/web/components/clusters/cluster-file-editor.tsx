"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Layers } from "lucide-react";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { fileNodepools, offersInfraEnvs, withInfraEnvs, type FileNodepool } from "@/lib/infra-envs";
import { offersPolicy } from "@/lib/nodepool-policy";
import type { TemplateField } from "@/types";
import { AlsoDrawsFrom } from "./also-draws-from";
import { hasPolicies, PolicyPanel } from "./policy-panel";

/** The MCE's InfraEnvs, as the create form reads them; `null` when live status is off. */
function useMceInfraEnvs(mce: string) {
  return useQuery<string[] | null>({
    queryKey: day1Keys.fleet.infraEnvs(mce),
    queryFn: async () => {
      try {
        return await day1Api.fleet.infraEnvs(mce);
      } catch (error) {
        if (isApiError(error, "FEATURE_DISABLED")) return null;
        throw error;
      }
    },
    enabled: Boolean(mce),
    staleTime: 60_000,
    retry: false,
  });
}

function PoolRow({ pool, text, onChange, options, loading, onRefused }: {
  pool: FileNodepool;
  text: string;
  onChange: (text: string) => void;
  options: string[] | undefined;
  loading: boolean;
  onRefused: (index: number) => void;
}) {
  const set = (names: string[]) => {
    const edited = withInfraEnvs(text, pool.index, names);
    if (edited === null) onRefused(pool.index);
    else onChange(edited);
  };
  return (
    <li className="grid gap-x-4 gap-y-1.5 px-3 py-2.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]" data-testid={`edit-nodepool-${pool.index}`}>
      <div className="min-w-0 text-xs">
        <p className="font-mono font-medium text-foreground break-all">{pool.first}</p>
        <p className="text-[11px] text-muted-foreground">{pool.name ? `NodePool ${pool.name}` : "its own InfraEnv: names the NodePool"}</p>
      </div>
      <AlsoDrawsFrom
        value={pool.additional}
        onChange={set}
        own={pool.first}
        options={options}
        loading={loading}
        readOnly={pool.replace}
        label={`${pool.first} also draws from`}
        note={pool.replace ? "upgradeType Replace: a change of its InfraEnvs would replace every node, so they stay as they are." : undefined}
        testId={`edit-nodepool-${pool.index}-infra-envs`}
      />
    </li>
  );
}

/**
 * Each agent nodepool's InfraEnvs, above the file while it is edited
 * (ADR-0064): its own InfraEnv, which names the NodePool and is never changed
 * here, and those it also draws from, picked from the MCE's list. A change
 * edits the file's text, every other line kept; a layout it cannot edit is
 * left to the person, who sees the change in the review either way.
 */
function InfraEnvsPanel({ text, onChange, mce }: { text: string; onChange: (text: string) => void; mce: string }) {
  const pools = useMemo(() => fileNodepools(text), [text]);
  const { data: infraEnvs, isLoading } = useMceInfraEnvs(mce);
  const [refused, setRefused] = useState<number | null>(null);
  if (!pools || pools.length === 0) return null;
  return (
    <section className="border-b border-zinc-800 bg-card text-card-foreground" aria-label="InfraEnvs per nodepool" data-testid="edit-infra-envs">
      <p className="flex items-center gap-1.5 px-3 pt-2.5 text-xs font-medium">
        <Layers className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        InfraEnvs per nodepool
        <span className="font-normal text-muted-foreground">· a change edits the file below</span>
      </p>
      <ul className="divide-y divide-border">
        {pools.map((pool) => (
          <PoolRow key={pool.index} pool={pool} text={text} onChange={(t) => { setRefused(null); onChange(t); }} options={infraEnvs ?? undefined} loading={isLoading} onRefused={setRefused} />
        ))}
      </ul>
      {refused !== null && (
        <p role="alert" className="flex items-start gap-1.5 px-3 pb-2.5 text-xs text-status-warning-fg" data-testid="edit-infra-envs-refused">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          This nodepool&apos;s lines are not in a layout this can edit: change its additionalInfraEnvNames in the file below.
        </p>
      )}
    </section>
  );
}

/**
 * The cluster file while it is edited: its text, and with
 * `DAY1_MULTI_INFRAENV_NODEPOOLS` on (day1's template schema offers the
 * input) each nodepool's InfraEnvs above it; each nodepool's scale-down
 * policy when the template writes it or the file already sets one (ADR-0062).
 */
export function ClusterFileEditor({ value, onChange, mce }: { value: string; onChange: (text: string) => void; mce: string }) {
  const { data: schema } = useQuery<TemplateField[]>({
    queryKey: day1Keys.specs.templateSchema,
    queryFn: day1Api.specs.templateSchema,
    staleTime: 300_000,
  });
  return (
    <div>
      {offersInfraEnvs(schema) && <InfraEnvsPanel text={value} onChange={onChange} mce={mce} />}
      {(offersPolicy(schema) || hasPolicies(value)) && <PolicyPanel text={value} onChange={onChange} />}
      <textarea
        aria-label="Cluster file"
        className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[500px] focus:outline-none resize-y leading-5 rounded-md"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
    </div>
  );
}
