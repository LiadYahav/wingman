"use client";

import { AlertTriangle, Gauge, Info, Lock, Plus, X } from "lucide-react";
import { Combobox } from "@/components/ui/combobox";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/common/hint";
import { useIsAdmin } from "@/stores/auth-store";
import {
  TUNING_HINT,
  addTuning,
  missingPerformanceProfiles,
  tuningOptions,
  tuningProblems,
  useTuningProfiles,
} from "@/lib/tuning-profiles";
import { cn } from "@/lib/utils";
import type { TuningProfile, TuningProfiles } from "@/types";

/** Why the picker has nothing to offer, or `null` when it has. */
function emptyReason(catalog: TuningProfiles | undefined): string | null {
  if (!catalog) return null;
  if (!catalog.found) return `The day1 repo has no ${catalog.folder}/ folder: no tuning profile to choose.`;
  if (catalog.profiles.length === 0) return `${catalog.folder}/ in the day1 repo has no usable tuning profile.`;
  return null;
}

/** The files of `tuning/` that are not offered, for admins (they fix the day1 repo). */
export function TuningCatalogProblems() {
  const admin = useIsAdmin();
  const { data: catalog } = useTuningProfiles();
  if (!admin || !catalog || catalog.problems.length === 0) return null;
  return (
    <div
      role="status"
      data-testid="tuning-catalog-problems"
      className="flex items-start gap-2 rounded-lg border border-status-warning/30 bg-status-warning/10 px-3 py-2.5 text-xs text-status-warning-fg"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <p className="font-medium">
          {catalog.problems.length === 1 ? "A file" : `${catalog.problems.length} files`} in {catalog.folder}/ {catalog.problems.length === 1 ? "is" : "are"} not offered:
        </p>
        <ul className="list-disc pl-4">
          {catalog.problems.map((p) => (
            <li key={p.path} className="break-words">
              <span className="font-mono">{p.path}</span>: {p.detail}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Chip({ name, profile, onRemove }: { name: string; profile: TuningProfile | undefined; onRemove?: () => void }) {
  return (
    <li
      className="flex min-w-0 items-start gap-2 rounded-lg border bg-muted/30 px-2.5 py-1.5"
      data-testid={`tuning-profile-${name}`}
    >
      <Gauge className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-2 text-sm">
          <span className="font-mono break-all">{name}</span>
          {profile && <span className="text-[11px] text-muted-foreground">{profile.kind}</span>}
        </p>
        {profile?.summary && <p className="text-xs text-muted-foreground">{profile.summary}</p>}
      </div>
      {onRemove && (
        <Button type="button" variant="ghost" size="icon" onClick={onRemove} aria-label={`Remove tuning profile ${name}`}>
          <X />
        </Button>
      )}
    </li>
  );
}

/**
 * A Tuned that builds on a PerformanceProfile the nodepool does not have
 * (`include=openshift-node-performance-<pp>`): a warning, never a refusal,
 * with the one click that adds it (replacing another PerformanceProfile).
 */
function PairingWarnings({
  names,
  catalog,
  onAdd,
  testId,
}: {
  names: string[];
  catalog: TuningProfiles | undefined;
  onAdd?: (performanceProfile: string) => void;
  testId: string;
}) {
  const missing = missingPerformanceProfiles(names, catalog);
  if (missing.length === 0) return null;
  return (
    <ul className="space-y-1" data-testid={`${testId}-pairing`}>
      {missing.map(({ tuned, requires }) => (
        <li key={tuned} role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-status-warning-fg">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">
            <span className="font-mono">{tuned}</span> builds on <span className="font-mono">{requires}</span>, which this
            nodepool does not have.
          </span>
          {onAdd && (
            <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => onAdd(requires)}>
              <Plus /> Add {requires}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * A nodepool's tuning profiles, picked from the catalogue (ADR-0061): a list
 * of names in the order chosen, with any number of Tuned and at most one
 * PerformanceProfile (picking another replaces it). Read-only when a flavor
 * locks them. `problems` are day1's for this list; the catalogue's own
 * checks show beside them, so an unknown name is caught before the request.
 */
export function TuningProfilesPicker({
  names,
  onChange,
  readOnly = false,
  lockedNote,
  label,
  testId,
  problems = [],
  localChecks = true,
}: {
  names: string[];
  onChange: (names: string[]) => void;
  readOnly?: boolean;
  /** Shown beside a read-only list: why it cannot change here. */
  lockedNote?: string;
  label: string;
  testId: string;
  problems?: string[];
  /** `false` where the page already shows the catalogue's checks (the flavor editor's issues). */
  localChecks?: boolean;
}) {
  const { data: catalog, isLoading, error } = useTuningProfiles();
  const byName = new Map((catalog?.profiles ?? []).map((p) => [p.name, p]));
  const shown = [...new Set([...(localChecks ? tuningProblems(names, catalog) : []), ...problems])];
  const empty = emptyReason(catalog);

  return (
    <div className="space-y-2" data-testid={testId}>
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <span>{readOnly && lockedNote ? lockedNote : "Applied to every node of the nodepool."}</span>
        <Hint hint={TUNING_HINT} label="What tuning profiles are" testId={`${testId}-hint`}>
          <Info className="h-3.5 w-3.5" aria-hidden />
        </Hint>
      </p>
      {names.length === 0 ? (
        <p className="text-xs text-muted-foreground">No tuning profiles.</p>
      ) : (
        <ul className="space-y-1.5" aria-label={label}>
          {names.map((name, index) => (
            <Chip
              key={name}
              name={name}
              profile={byName.get(name)}
              onRemove={readOnly ? undefined : () => onChange(names.filter((_, i) => i !== index))}
            />
          ))}
        </ul>
      )}
      {readOnly ? (
        <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <Lock className="h-3 w-3" aria-hidden /> Locked by the flavor
        </p>
      ) : (
        <div className={cn("flex items-center gap-2", names.length > 0 && "pt-1")}>
          <Plus className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
          <Combobox
            className="max-w-sm flex-1"
            size="sm"
            options={tuningOptions(catalog, names)}
            value={null}
            onValueChange={(name) => name && !names.includes(name) && onChange(addTuning(names, name, catalog))}
            placeholder={isLoading ? "Loading tuning profiles…" : empty ? "No tuning profiles to choose" : "Add a tuning profile…"}
            searchPlaceholder="Search tuning profiles…"
            emptyMessage="No tuning profile matches."
            disabled={isLoading || Boolean(empty) || Boolean(error)}
            aria-label={`${label}: add a profile`}
            data-testid={`${testId}-add`}
          />
        </div>
      )}
      <PairingWarnings names={names} catalog={catalog} onAdd={readOnly ? undefined : (pp) => onChange(addTuning(names, pp, catalog))} testId={testId} />
      {empty && !readOnly && <p className="text-xs text-muted-foreground" data-testid={`${testId}-empty`}>{empty}</p>}
      {error && (
        <p role="alert" className="text-xs text-destructive" data-testid={`${testId}-error`}>
          The tuning profiles could not be read: {error instanceof Error ? error.message : String(error)}
        </p>
      )}
      {shown.length > 0 && (
        <ul role="alert" className="space-y-0.5 text-xs text-destructive">
          {shown.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
