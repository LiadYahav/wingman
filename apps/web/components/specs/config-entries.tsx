import { Network } from "lucide-react";
import { asEntries, isNetworkEntry, networkConfigName } from "@/lib/machine-configs";
import { cn } from "@/lib/utils";
import type { ConfigEntry } from "@/types";

/**
 * One nodepool config entry as a person reads it: a static config by its
 * name, or `{name: nm-conf, hardware: dell}` as the cluster's own network
 * config for dell hardware (the file gets `nm-conf-<clusterName>-dell`).
 */
function ConfigEntryChip({ entry, className }: { entry: ConfigEntry; className?: string }) {
  if (isNetworkEntry(entry)) {
    const hardware = entry.hardware;
    return (
      <span
        title={
          hardware
            ? `The cluster's own network config for ${hardware} hardware: the file gets ${networkConfigName("<cluster>", hardware)}`
            : "The cluster's own network config, for each nodepool's own hardware"
        }
        className={cn(
          "inline-flex max-w-full items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-1.5 py-0.5 text-xs",
          className
        )}
      >
        <Network className="h-3 w-3 shrink-0 text-primary" aria-hidden />
        <span className="font-mono">nm-conf</span>
        <span className="text-muted-foreground">
          {hardware ? <>network config · {hardware} hardware</> : <>network config · its own hardware</>}
        </span>
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center rounded-md border bg-muted/40 px-1.5 py-0.5 font-mono text-xs break-all",
        className
      )}
    >
      {entry.name}
    </span>
  );
}

/** A `configs` value as chips, in its order; anything that is not an entry is left out. */
export function ConfigEntryList({ value }: { value: unknown }) {
  const entries = asEntries(value);
  if (entries.length === 0) return <span className="text-xs text-muted-foreground">No configs</span>;
  return (
    <span className="flex flex-wrap justify-end gap-1">
      {entries.map((entry, i) => (
        <ConfigEntryChip key={`${entry.name}-${entry.hardware ?? ""}-${i}`} entry={entry} />
      ))}
    </span>
  );
}
