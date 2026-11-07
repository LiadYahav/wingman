"use client";

import { AlertTriangle } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import type { ValueLayer } from "@/types/day2";

/**
 * The revision a cluster folder inherits: the last deploy-config layer below
 * the folder's own `<chart>.yaml` that sets `targetRevision`, else `HEAD`.
 * A scalar is last-wins, so this is the platform's answer too.
 */
export function inheritedRevision(deployLayers: readonly ValueLayer[]): string {
  let revision = "HEAD";
  for (const layer of deployLayers) {
    if (layer.role === "cluster") continue;
    const value = layer.values.targetRevision;
    if (typeof value === "string" && value) revision = value;
  }
  return revision;
}

/**
 * Pick the chart revision. Anything but the inherited one is an emergency
 * pin (ADR-0022): it detaches this cluster from the team default and its
 * OCP-version pins until removed, so it has to be asked for explicitly.
 */
export function VersionField({
  versions,
  inherited,
  pinned,
  value,
  onChange,
  emergencyPin,
  onEmergencyPinChange,
  clusterName,
}: {
  /** The chart repo's branches, default branch first. */
  versions: readonly string[];
  inherited: string;
  /** The cluster folder pins a revision today. */
  pinned: boolean;
  value: string;
  onChange: (version: string) => void;
  emergencyPin: boolean;
  onEmergencyPinChange: (pin: boolean) => void;
  clusterName: string;
}) {
  const options = [...new Set([inherited, value, ...versions])];
  const pins = value !== inherited;
  return (
    <div className="space-y-2">
      <label className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted-foreground">Revision</span>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 min-w-32 rounded-md border bg-background px-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
        >
          {options.map((v) => (
            <option key={v} value={v}>
              {v === inherited ? `${v} (inherited${v === "HEAD" && versions[0] ? `: ${versions[0]}` : ""})` : v}
            </option>
          ))}
        </select>
      </label>
      {pins ? (
        <div className="rounded-lg border border-status-warning/30 bg-status-warning/8 p-3 text-xs">
          <p className="flex items-start gap-2 text-status-warning-fg">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {value} is an <strong>emergency pin</strong>: {clusterName} stops following the team default ({inherited}) and
              its OCP-version pins until someone removes it.
            </span>
          </p>
          <label className="mt-2 flex items-center gap-2 pl-5.5 text-foreground">
            <Checkbox checked={emergencyPin} onCheckedChange={(checked) => onEmergencyPinChange(checked === true)} />
            Pin {clusterName} to {value} anyway
          </label>
        </div>
      ) : (
        pinned && (
          <p className="text-xs text-muted-foreground">
            Choosing the inherited revision removes this cluster&apos;s emergency pin.
          </p>
        )
      )}
    </div>
  );
}
