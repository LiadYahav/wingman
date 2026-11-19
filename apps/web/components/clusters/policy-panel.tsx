"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ServerOff } from "lucide-react";
import { filePolicies, withPolicy } from "@/lib/nodepool-policy";
import { PolicySelect } from "./policy-select";

/** Whether the file sets a policy on any nodepool: the panel shows then, whatever the template reads. */
export function hasPolicies(text: string): boolean {
  return Boolean(filePolicies(text)?.some((pool) => pool.policy !== null));
}

/**
 * Each nodepool's scale-down policy, above the file while it is edited
 * (ADR-0062): its `redbull.io/scale-down-policy` annotation, which
 * update-nodepool reads to choose the servers a scale-down removes. A change
 * edits only that line of the file's text, as the shared template writes it,
 * every other line kept; a layout it cannot edit is left to the person, who
 * sees the change in the review either way. An annotation rolls no node.
 */
export function PolicyPanel({ text, onChange }: { text: string; onChange: (text: string) => void }) {
  const pools = useMemo(() => filePolicies(text), [text]);
  const [refused, setRefused] = useState<number | null>(null);
  if (!pools || pools.length === 0) return null;
  const set = (index: number, policy: string | null) => {
    const edited = withPolicy(text, index, policy);
    setRefused(edited === null ? index : null);
    if (edited !== null) onChange(edited);
  };
  return (
    <section className="border-b border-zinc-800 bg-card text-card-foreground" aria-label="Scale-down policy per nodepool" data-testid="edit-policies">
      <p className="flex flex-wrap items-center gap-x-1.5 px-3 pt-2.5 text-xs font-medium">
        <ServerOff className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        Scale-down policy per nodepool
        <span className="font-normal text-muted-foreground">· which nodes leave first; a change edits the file below and rolls no node</span>
      </p>
      <ul className="divide-y divide-border">
        {pools.map((pool) => (
          <li key={pool.index} className="grid gap-x-4 gap-y-1.5 px-3 py-2.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]" data-testid={`edit-policy-${pool.index}`}>
            <p className="min-w-0 pt-1.5 font-mono text-xs font-medium break-all">{pool.label}</p>
            <PolicySelect
              value={pool.policy}
              onChange={(policy) => set(pool.index, policy)}
              label={`${pool.label} scale-down policy`}
              testId={`edit-policy-${pool.index}-select`}
            />
          </li>
        ))}
      </ul>
      {refused !== null && (
        <p role="alert" className="flex items-start gap-1.5 px-3 pb-2.5 text-xs text-status-warning-fg" data-testid="edit-policies-refused">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          This nodepool&apos;s annotations are not in a layout this can edit: change its redbull.io/scale-down-policy in the file below.
        </p>
      )}
    </section>
  );
}
