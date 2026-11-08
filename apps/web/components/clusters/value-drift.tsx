import { Lock, RotateCw, TriangleAlert } from "lucide-react";
import { NETWORK_CONFIG } from "@/lib/machine-configs";
import { cn } from "@/lib/utils";
import type { ValueDrift } from "@/types";

/** A configs value in the file's form (`[{name}]`) as names; `null` for any other value. */
function configNames(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  return value.map((entry) => {
    if (typeof entry === "string") return entry;
    if (entry && typeof entry === "object" && typeof (entry as { name?: unknown }).name === "string") {
      return (entry as { name: string }).name;
    }
    return JSON.stringify(entry);
  });
}

/** A locked scalar or mapping as the file holds it. */
function valueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value === "" ? '""' : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "none";
    return entries.map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
  }
  return JSON.stringify(value);
}

/**
 * Config names as chips. `marked` are the ones a sync changes: added to the
 * flavor's side, removed from the cluster's. An unexpanded `nm-conf` is a
 * network config whose hardware is not known yet.
 */
function ConfigChips({ names, marked, mark }: { names: string[]; marked: string[]; mark: "added" | "removed" }) {
  if (names.length === 0) return <span className="text-muted-foreground">none</span>;
  return (
    <ul className="flex flex-wrap gap-1">
      {names.map((name, i) => {
        const changed = marked.includes(name);
        return (
          <li
            key={`${name}-${i}`}
            className={cn(
              "rounded-md border px-1.5 py-0.5 font-mono text-[11px] break-all",
              !changed && "bg-muted/40",
              changed && mark === "added" && "border-status-ready/40 bg-status-ready/10 text-status-ready-fg",
              changed && mark === "removed" && "border-status-error/40 bg-status-error/10 text-status-error-fg line-through"
            )}
          >
            {name === NETWORK_CONFIG ? `${NETWORK_CONFIG} (hardware to choose)` : name}
          </li>
        );
      })}
    </ul>
  );
}

function Value({ value, marked, mark }: { value: unknown; marked: string[]; mark: "added" | "removed" }) {
  const names = configNames(value);
  if (names) return <ConfigChips names={names} marked={marked} mark={mark} />;
  return <span className="font-mono break-all">{valueText(value)}</span>;
}

/** One locked value the cluster file does not hold (ADR-0036). */
function ValueDriftItem({ item }: { item: ValueDrift }) {
  const added = item.added ?? [];
  const removed = item.removed ?? [];
  return (
    <li className="py-3 space-y-2 text-sm" data-testid={`value-drift-${item.file_key}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono font-medium">{item.file_key}</span>
        {item.nodepool && (
          <span className="text-xs text-muted-foreground break-all">nodepool {item.nodepool.name}</span>
        )}
        {item.reboots && (
          <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-status-warning-fg">
            <RotateCw className="h-3 w-3" aria-hidden />Changing it rolls the nodes
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground" title="The flavor's lock">
          <Lock className="h-3 w-3" aria-hidden />
          <span className="font-mono">{item.path}</span>
        </span>
      </div>
      <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground pt-0.5">Flavor</dt>
        <dd><Value value={item.flavor_value} marked={added} mark="added" /></dd>
        <dt className="text-muted-foreground pt-0.5">Cluster</dt>
        <dd>
          {item.in_file ? (
            <Value value={item.cluster_value} marked={removed} mark="removed" />
          ) : (
            <span className="italic text-muted-foreground">absent from the file</span>
          )}
        </dd>
      </dl>
      {(added.length > 0 || removed.length > 0) && (
        <p className="text-xs text-muted-foreground">
          {added.length > 0 && <>A sync adds <span className="font-mono text-status-ready-fg">{added.join(", ")}</span></>}
          {added.length > 0 && removed.length > 0 && " and removes "}
          {added.length === 0 && removed.length > 0 && "A sync removes "}
          {removed.length > 0 && <span className="font-mono text-status-error-fg">{removed.join(", ")}</span>}
          .
        </p>
      )}
      {item.needs_decision && (
        <p className="flex items-start gap-1.5 text-xs text-status-warning-fg" data-testid="needs-decision">
          <TriangleAlert className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span className="break-words">
            {item.needs_decision}.{" "}
            {item.needs_hardware
              ? "Sync to flavor asks for it."
              : "A sync cannot set it: a person edits the cluster file."}
          </span>
        </p>
      )}
    </li>
  );
}

/** The flavor's locked values the cluster file does not hold, one row each. */
export function ValueDriftList({ items }: { items: ValueDrift[] }) {
  return (
    <ul className="divide-y divide-status-warning/20" aria-label="Locked values that differ">
      {items.map((item) => <ValueDriftItem key={`${item.path}|${item.file_key}`} item={item} />)}
    </ul>
  );
}
