"use client";

import { useId } from "react";
import { AlertTriangle } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
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
 * pin (ADR-0022): it detaches this cluster from the add-on's revision and its
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
  const labelId = useId();
  // The chart repo's branches: a list that grows, so it is searchable
  const options: ComboboxOption[] = [...new Set([inherited, value, ...versions])].map((v) => ({
    value: v,
    label: v === inherited ? `${v} (inherited${v === "HEAD" && versions[0] ? `: ${versions[0]}` : ""})` : v,
  }));
  const pins = value !== inherited;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span id={labelId} className="font-semibold uppercase tracking-wide text-muted-foreground">Revision</span>
        <Combobox
          size="sm"
          options={options}
          value={value}
          onValueChange={(v) => v && onChange(v)}
          searchPlaceholder="Search branches…"
          emptyMessage="No branch matches."
          aria-labelledby={labelId}
          className="w-auto min-w-40 max-w-72 font-mono text-xs"
        />
      </div>
      {pins ? (
        <div className="rounded-lg border border-status-warning/30 bg-status-warning/8 p-3 text-xs">
          <p className="flex items-start gap-2 text-status-warning-fg">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {value} is an <strong>emergency pin</strong>: {clusterName} stops following the add-on&apos;s revision ({inherited}) and
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
