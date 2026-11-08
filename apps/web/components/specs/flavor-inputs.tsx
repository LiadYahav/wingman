import { AlertTriangle, Lock, SlidersHorizontal } from "lucide-react";
import { ConfigEntryList } from "@/components/specs/config-entries";
import { formatPreset, structureSummary } from "@/lib/specs";
import { isMapping } from "@/lib/values";
import { cn } from "@/lib/utils";
import type { ClusterSpec } from "@/types";

/**
 * A warning panel: rules a stored flavor breaks (`warnings` of a spec), or
 * what an import preview says about the flavor. Amber, above what it is about.
 */
export function WarningPanel({
  title,
  description,
  lines,
  className,
  ...props
}: {
  title: string;
  description?: React.ReactNode;
  lines: string[];
  className?: string;
  "data-testid"?: string;
}) {
  if (lines.length === 0) return null;
  return (
    <section
      className={cn("rounded-xl border border-status-warning/40 bg-status-warning/5 p-4 text-sm", className)}
      {...props}
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-status-warning" aria-hidden />
        <div className="min-w-0 space-y-1.5">
          <h2 className="font-semibold text-status-warning-fg">{title}</h2>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
          <ul className="list-disc pl-4 space-y-0.5 text-status-warning-fg">
            {lines.map((line, i) => (
              <li key={i} className="break-words">{line}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/** One value of `spec.day1.values`, at its template-input path (`owner_anaf`, `nodepools[0].configs`). */
interface InputRow {
  path: string;
  field: string;
  value: unknown;
}

/** The top-level inputs, then one group per item of a list of mappings (each nodepool). */
interface InputGroup {
  key: string;
  title: string | null;
  rows: InputRow[];
}

function itemTitle(list: string, index: number): string {
  return list === "nodepools" ? `Nodepool ${index + 1}` : `${list.replace(/_/g, " ")} ${index + 1}`;
}

function inputGroups(values: Record<string, unknown>): InputGroup[] {
  const top: InputRow[] = [];
  const items: InputGroup[] = [];
  for (const [key, value] of Object.entries(values)) {
    if (Array.isArray(value) && value.length > 0 && value.every(isMapping)) {
      value.forEach((item, i) => {
        items.push({
          key: `${key}[${i}]`,
          title: itemTitle(key, i),
          rows: Object.entries(item).map(([field, v]) => ({ path: `${key}[${i}].${field}`, field, value: v })),
        });
      });
    } else {
      top.push({ path: key, field: key, value });
    }
  }
  return [...(top.length > 0 ? [{ key: "", title: null, rows: top }] : []), ...items];
}

const isRule = (lock: string) => lock.includes("[*]");

/** `nodepools[*].configs` → matches `nodepools[3].configs`; a lock also covers what is under it. */
function lockPattern(lock: string): RegExp {
  const escaped = lock.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\[\\\*\\\]/g, "\\[\\d+\\]");
  return new RegExp(`^${escaped}(?=$|[.[])`);
}

/** The lock that fixes the value at `path`, the rule first (a rule beside a position enforces the rule). */
export function lockOf(path: string, locks: readonly string[]): string | null {
  const ordered = [...locks].sort((a, b) => Number(isRule(b)) - Number(isRule(a)));
  return ordered.find((lock) => lockPattern(lock).test(path)) ?? null;
}

function InputValue({ field, value }: { field: string; value: unknown }) {
  if (field === "configs" && Array.isArray(value)) return <ConfigEntryList value={value} />;
  if (isMapping(value)) {
    const pairs = Object.entries(value);
    if (pairs.length === 0) return <span className="text-xs text-muted-foreground">None</span>;
    return (
      <span className="flex flex-wrap justify-end gap-1">
        {pairs.map(([k, v]) => (
          <span key={k} className="rounded-md border bg-muted/40 px-1.5 py-0.5 font-mono text-xs break-all">
            {k}={formatPreset(v)}
          </span>
        ))}
      </span>
    );
  }
  if (value === "") return <span className="text-xs text-muted-foreground">Empty</span>;
  return <span className="text-xs font-mono text-foreground/80 break-all">{formatPreset(value)}</span>;
}

/** Preset (prefilled, overridable) or Locked (fixed by the flavor). */
function ValueKind({ lock }: { lock: string | null }) {
  if (!lock) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
        <SlidersHorizontal className="h-3 w-3" aria-hidden />Preset
      </span>
    );
  }
  return (
    <span
      title={`Locked by ${lock}`}
      className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
    >
      <Lock className="h-3 w-3" aria-hidden />Locked{isRule(lock) && <> · every nodepool</>}
    </span>
  );
}

/** Lists and maps go under their name, scalars beside it. */
const isWide = (value: unknown) => Array.isArray(value) || (isMapping(value) && Object.keys(value).length > 0);

function InputRowView({ row, lock }: { row: InputRow; lock: string | null }) {
  const wide = isWide(row.value);
  return (
    <div
      data-testid={`flavor-input-${row.path}`}
      data-kind={lock ? "locked" : "preset"}
      className={cn("px-3 py-2", wide ? "space-y-1.5" : "flex items-center justify-between gap-3")}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-mono break-all">{row.field}</span>
        <ValueKind lock={lock} />
      </div>
      <div className={cn("min-w-0", wide ? "[&>span]:justify-start" : "text-right")}>
        <InputValue field={row.field} value={row.value} />
      </div>
    </div>
  );
}

/**
 * What a cluster of this flavor starts from (ADR-0026): every value in
 * `spec.day1.values` is a preset, prefilled at create and overridable, unless
 * a path in `locked_paths` fixes it. A locked value can't be changed at
 * create, and a later edit of the cluster file shows as drift (ADR-0036).
 */
export function FlavorInputsCard({ spec }: { spec: ClusterSpec }) {
  const { values = {}, structure, locked_paths: locks = [], variables } = spec.spec.day1;
  const groups = inputGroups(values);
  const rows = groups.flatMap((g) => g.rows);
  const lockFor = new Map(rows.map((r) => [r.path, lockOf(r.path, locks)]));
  const lockedCount = rows.filter((r) => lockFor.get(r.path)).length;
  const presetCount = rows.length - lockedCount;
  // A lock with no value fixes nothing (the flavor's warnings say so too)
  const withoutValue = locks.filter((lock) => !rows.some((r) => lockPattern(lock).test(r.path)));
  const shape = structureSummary(structure);

  return (
    <div className="bg-card rounded-xl border shadow-sm p-5 space-y-4" data-testid="flavor-inputs">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="text-sm font-semibold">Cluster inputs</h2>
        <p className="text-xs text-muted-foreground" data-testid="flavor-input-counts">
          {presetCount} preset{presetCount !== 1 ? "s" : ""} · {lockedCount} locked
        </p>
      </div>

      <dl className="grid gap-1.5 text-xs text-muted-foreground">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 font-medium text-foreground">Preset</dt>
          <dd>Prefilled when a cluster is created; the person creating it can change it.</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 font-medium text-primary">Locked</dt>
          <dd>Fixed by the flavor: a create can&apos;t change it, and a later edit of the cluster file shows as drift.</dd>
        </div>
      </dl>

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No values — every template input is filled in when a cluster is created.
        </p>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.key} className="space-y-1.5">
              {group.title && (
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {group.title}
                  <span className="ml-1.5 normal-case tracking-normal font-mono">{group.key}</span>
                </p>
              )}
              <div className="rounded-lg border divide-y divide-border/50">
                {group.rows.map((row) => (
                  <InputRowView key={row.path} row={row} lock={lockFor.get(row.path) ?? null} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {locks.some(isRule) && (
        <p className="text-xs text-muted-foreground" data-testid="flavor-configs-rule">
          <span className="font-mono">nodepools[*].configs</span> is a rule: every nodepool of a cluster has exactly
          these configs, in any order, and <span className="font-mono">nm-conf</span> is each nodepool&apos;s own network
          config for its own hardware. The hardware shown is only the create form&apos;s preset.
        </p>
      )}

      {withoutValue.length > 0 && (
        <div className="space-y-1.5" data-testid="flavor-locks-without-value">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Locked without a value</p>
          <p className="text-xs text-muted-foreground">These locks fix nothing, so they are not enforced.</p>
          <div className="flex flex-wrap gap-1.5">
            {withoutValue.map((lock) => (
              <span key={lock} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-mono break-all text-muted-foreground">
                <Lock className="h-3 w-3 shrink-0" aria-hidden />{lock}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Structure</p>
        <p className="text-sm">
          {shape.length > 0 ? shape.join(", ") : <span className="text-xs text-muted-foreground">No list counts fixed by this flavor.</span>}
        </p>
      </div>

      {variables.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Declared variables (legacy)</p>
          <div className="space-y-1">
            {variables.map((v) => (
              <div key={v.name} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                <div>
                  <span className="text-sm font-mono">{v.name}</span>
                  {v.required && <span className="ml-1 text-xs text-destructive">*</span>}
                </div>
                <span className="text-xs text-muted-foreground">{v.type}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
