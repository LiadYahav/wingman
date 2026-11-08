"use client";

import { useMemo } from "react";
import { Lock, Network, Plus, X } from "lucide-react";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  NETWORK_CONFIG,
  entryProblems,
  fileName,
  folderLabel,
  isNetworkEntry,
} from "@/lib/machine-configs";
import type { ConfigEntry, MachineConfigs } from "@/types";

const NETWORK_GROUP = "Network (one per nodepool)";

/** The picker's choices: the network entry first, then every static config grouped by folder. */
function nameOptions(catalog: MachineConfigs | undefined, entries: ConfigEntry[]): ComboboxOption[] {
  const used = new Set(entries.map((e) => e.name));
  const network: ComboboxOption = {
    value: NETWORK_CONFIG,
    label: NETWORK_CONFIG,
    description: "The cluster's own network config, for the nodepool's hardware type",
    group: NETWORK_GROUP,
    disabled: used.has(NETWORK_CONFIG),
  };
  const statics = (catalog?.static_configs ?? []).map((c) => ({
    value: c.name,
    label: c.name,
    description: c.path,
    group: folderLabel(c.folder),
    disabled: used.has(c.name),
  }));
  return [network, ...statics];
}

/**
 * A nodepool's `configs`, edited from the machine-config catalogue (ADR-0027):
 * static configs by name, and `nm-conf` with a hardware type, which day1
 * writes as `nm-conf-<clusterName>-<hw>`. Read-only when a flavor locks it.
 *
 * `problems` are day1's, by entry index; the catalogue's own checks show
 * beside them so a typo is caught before the request.
 */
export function ConfigListEditor({
  entries,
  onChange,
  catalog,
  loading = false,
  readOnly = false,
  clusterName,
  problems = {},
  label = "Machine configs",
  testId = "config-list",
}: {
  entries: ConfigEntry[];
  onChange: (entries: ConfigEntry[]) => void;
  catalog: MachineConfigs | undefined;
  loading?: boolean;
  /** Locked by the flavor: shown, not editable. */
  readOnly?: boolean;
  /** The chart's clusterName (no `ocp4-`), to show the network config's file name. */
  clusterName?: string;
  /** Day1's problems by entry index (`nodepools[i].configs[j]: ...`). */
  problems?: Record<number, string[]>;
  label?: string;
  testId?: string;
}) {
  const local = useMemo(() => entryProblems(entries, catalog), [entries, catalog]);
  const options = useMemo(() => nameOptions(catalog, entries), [catalog, entries]);
  const hardwareOptions = useMemo<ComboboxOption[]>(
    () => (catalog?.hardware_types ?? []).map((h) => ({ value: h.name, label: h.name, description: h.template })),
    [catalog]
  );

  const set = (index: number, entry: ConfigEntry) => onChange(entries.map((e, i) => (i === index ? entry : e)));
  const remove = (index: number) => onChange(entries.filter((_, i) => i !== index));
  const add = (name: string | null) => {
    if (!name) return;
    onChange([...entries, name === NETWORK_CONFIG ? { name, hardware: null } : { name }]);
  };

  if (readOnly) {
    return (
      <div className="space-y-1.5" data-testid={testId}>
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Lock className="h-3 w-3" aria-hidden /> {label} · locked by the flavor
        </p>
        {entries.length === 0 ? (
          <p className="text-xs text-muted-foreground">None.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5" aria-label={label}>
            {entries.map((entry, i) => (
              <li
                key={`${entry.name}-${i}`}
                className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-0.5 font-mono text-xs"
              >
                {isNetworkEntry(entry) && <Network className="h-3 w-3 text-muted-foreground" aria-hidden />}
                {fileName(entry, clusterName) ?? `${NETWORK_CONFIG} (hardware to choose)`}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid={testId}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {entries.length === 0 && <p className="text-xs text-muted-foreground">No machine configs.</p>}
      <ul className="space-y-2" aria-label={label}>
        {entries.map((entry, index) => {
          const shown = [...(local[index] ?? []), ...(problems[index] ?? [])];
          const network = isNetworkEntry(entry);
          const name = fileName(entry, clusterName);
          return (
            <li key={index} className="space-y-1" data-testid={`${testId}-entry-${index}`}>
              <div className="flex items-start gap-2">
                <Combobox
                  className="min-w-0 flex-1"
                  options={options.map((o) => (o.value === entry.name ? { ...o, disabled: false } : o))}
                  value={entry.name || null}
                  onValueChange={(value) =>
                    value && set(index, value === NETWORK_CONFIG ? { name: value, hardware: entry.hardware ?? null } : { name: value })
                  }
                  placeholder={loading ? "Loading machine configs…" : "Choose a machine config…"}
                  searchPlaceholder="Search machine configs…"
                  emptyMessage="No machine config matches."
                  disabled={loading}
                  aria-label={`${label}: entry ${index + 1}`}
                  aria-invalid={shown.length > 0}
                />
                {network && (
                  <Combobox
                    className="w-40 shrink-0"
                    options={hardwareOptions}
                    value={entry.hardware ?? null}
                    onValueChange={(hardware) => set(index, { name: NETWORK_CONFIG, hardware })}
                    placeholder="Hardware…"
                    searchPlaceholder="Search hardware types…"
                    emptyMessage="No hardware type matches."
                    disabled={loading}
                    aria-label={`${label}: entry ${index + 1} hardware type`}
                    aria-invalid={!entry.hardware}
                  />
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(index)}
                  aria-label={`Remove ${entry.name || "entry"} (entry ${index + 1})`}
                >
                  <X />
                </Button>
              </div>
              {network && name && (
                <p className="pl-1 font-mono text-[11px] text-muted-foreground">Written as {name}</p>
              )}
              {shown.length > 0 && (
                <ul className="pl-1 text-xs text-destructive" role="alert">
                  {shown.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      <div className={cn("flex items-center gap-2", entries.length > 0 && "pt-1")}>
        <Plus className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <Combobox
          className="max-w-sm flex-1"
          size="sm"
          options={options}
          value={null}
          onValueChange={add}
          placeholder={loading ? "Loading machine configs…" : "Add a machine config…"}
          searchPlaceholder="Search machine configs…"
          emptyMessage="No machine config matches."
          disabled={loading}
          aria-label={`${label}: add a config`}
          data-testid={`${testId}-add`}
        />
      </div>
    </div>
  );
}

/** Day1's problems for one config list, by entry index: `<base>[j]: message`. */
export function configProblems(problems: string[], base: string): Record<number, string[]> {
  const found: Record<number, string[]> = {};
  const prefix = `${base}[`;
  for (const problem of problems) {
    if (!problem.startsWith(prefix)) continue;
    const match = /^\[(\d+)\]:\s*(.*)$/.exec(problem.slice(base.length));
    if (!match) continue;
    const index = Number(match[1]);
    (found[index] ??= []).push(match[2]);
  }
  return found;
}
