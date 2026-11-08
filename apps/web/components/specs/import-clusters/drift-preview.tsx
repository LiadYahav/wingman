import { AlertTriangle, CheckCircle2, CircleHelp, Minus, Package, Plus, RefreshCcw } from "lucide-react";
import { formatPreset } from "@/lib/specs";
import type { ClusterDrift, ValueDrift } from "@/types";

const isConfigs = (item: ValueDrift) => item.file_key.endsWith(".configs");

/** `3 locked values differ · 1 add-on missing`: one line for a candidate's drift. */
export function driftSummary(drift: ClusterDrift): string {
  const parts: string[] = [];
  const values = drift.value_drift.length;
  if (values > 0) parts.push(`${values} locked value${values !== 1 ? "s" : ""} differ${values === 1 ? "s" : ""}`);
  const decide = drift.value_drift.filter((d) => d.needs_decision).length;
  if (decide > 0) parts.push(`${decide} need${decide === 1 ? "s" : ""} a person to decide`);
  const addons = drift.addon_drift.length;
  if (addons > 0) parts.push(`${addons} add-on${addons !== 1 ? "s" : ""} missing`);
  if (drift.error) parts.push("add-ons not checked");
  return parts.join(" · ");
}

/** One locked value the file does not hold (ADR-0036), as a sync would change it. */
function ValueDriftItem({ item }: { item: ValueDrift }) {
  return (
    <li className="space-y-1 py-2 first:pt-0 last:pb-0" data-testid={`value-drift-${item.file_key}`}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-mono text-xs font-medium break-all">{item.file_key}</span>
        {item.nodepool && <span className="text-xs text-muted-foreground break-all">{item.nodepool.name}</span>}
        {item.reboots && !item.needs_decision && (item.added.length > 0 || item.removed.length > 0) && (
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <RefreshCcw className="h-3 w-3" aria-hidden />a sync rolls this nodepool&apos;s nodes
          </span>
        )}
      </div>
      {isConfigs(item) ? (
        (item.added.length > 0 || item.removed.length > 0) && (
          <div className="flex flex-wrap gap-1">
            {item.added.map((name) => (
              <span key={`+${name}`} className="inline-flex items-center gap-0.5 rounded-md bg-status-ready/10 px-1.5 py-0.5 font-mono text-xs text-status-ready-fg break-all">
                <Plus className="h-3 w-3 shrink-0" aria-label="added" />{name}
              </span>
            ))}
            {item.removed.map((name) => (
              <span key={`-${name}`} className="inline-flex items-center gap-0.5 rounded-md bg-status-error/10 px-1.5 py-0.5 font-mono text-xs text-status-error-fg break-all">
                <Minus className="h-3 w-3 shrink-0" aria-label="removed" />{name}
              </span>
            ))}
          </div>
        )
      ) : (
        <p className="text-xs text-muted-foreground break-all">
          flavor <span className="font-mono text-foreground">{formatPreset(item.flavor_value)}</span>
          {" · "}file{" "}
          {item.in_file ? (
            <span className="font-mono text-foreground">{formatPreset(item.cluster_value)}</span>
          ) : (
            <span className="italic">not set</span>
          )}
        </p>
      )}
      {item.needs_decision && (
        <p className="flex items-start gap-1.5 text-xs text-status-warning-fg">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span className="break-words">{item.needs_decision}</span>
        </p>
      )}
    </li>
  );
}

/**
 * What will show as drift once the cluster follows the flavor: each locked
 * value its file does not hold, and each add-on of the flavor it lacks.
 */
export function DriftOnceLinked({ drift }: { drift: ClusterDrift }) {
  const nothing = drift.value_drift.length === 0 && drift.addon_drift.length === 0;
  if (drift.state === "in_sync" || (nothing && !drift.error)) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-status-ready-fg">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Matches the flavor: nothing will show as drift.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">Will show as drift once linked</p>
      {drift.value_drift.length > 0 && (
        <ul className="divide-y divide-border/50 rounded-md border px-3 py-2">
          {drift.value_drift.map((item, i) => (
            <ValueDriftItem key={`${item.file_key}-${i}`} item={item} />
          ))}
        </ul>
      )}
      {drift.addon_drift.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Missing add-ons:</span>
          {drift.addon_drift.map((a) => (
            <span key={`${a.team}/${a.addon_name}`} className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5">
              <Package className="h-3 w-3 text-muted-foreground" aria-hidden />
              <span className="font-medium">{a.addon_name}</span>
              <span className="text-muted-foreground">{a.team}</span>
            </span>
          ))}
        </div>
      )}
      {drift.error && (
        <p className="flex items-start gap-1.5 text-xs text-status-deleting-fg">
          <CircleHelp className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span className="break-words">
            {drift.state === "unknown" && drift.value_drift.length === 0
              ? "Drift could not be determined"
              : "Missing add-ons could not be checked"}
            : {drift.error}
          </span>
        </p>
      )}
    </div>
  );
}
