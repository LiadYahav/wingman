import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleHelp, Info, RefreshCcw, Unlink, Wrench } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { ValueDriftList } from "@/components/clusters/value-drift";
import type { AddonDrift, ClusterDrift, ValueDrift, VersionDifference } from "@/types";

function Notice({ icon: Icon, tone, children }: { icon: typeof CheckCircle2; tone: string; children: React.ReactNode }) {
  return (
    <div className={`flex items-start gap-2 text-sm py-4 ${tone}`}>
      <Icon className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/**
 * Spec addons installed at another version than the spec names. Information
 * only (ADR-0025): day2 keeps a cluster on its team's default unless someone
 * pins it on purpose, so there is nothing here to fix.
 */
function VersionDifferences({ differences }: { differences: VersionDifference[] }) {
  if (differences.length === 0) return null;
  return (
    <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        <Info className="h-3.5 w-3.5" />
        Other versions than the flavor names
      </div>
      <p className="text-xs text-muted-foreground">
        Not drift. These charts follow their team&apos;s default version or a deliberate pin in day2.
      </p>
      <div className="divide-y">
        {differences.map((d) => (
          <div key={`${d.team}/${d.addon_name}`} className="flex items-center justify-between gap-3 py-2 text-sm flex-wrap">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono font-medium truncate">{d.addon_name}</span>
              <span className="text-muted-foreground text-xs">{d.team}</span>
            </div>
            <span className="text-xs text-muted-foreground">
              {d.installed_version} installed · flavor names {d.spec_version}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** What the panel looks like while drift is read: the notice line, then a few addon rows. */
function DriftSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 py-4">
        <Skeleton className="h-4 w-4 shrink-0 rounded-full" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <div className="rounded-lg border p-4 space-y-2">
        <Skeleton className="h-3 w-28" />
        <div className="divide-y">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3 py-2">
              <div className="flex items-center gap-2 min-w-0">
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** `value_drift`, which a day1 that predates it does not send. */
export function valueDriftOf(drift: ClusterDrift): ValueDrift[] {
  return drift.value_drift ?? [];
}

/** The file's header names an older version of its flavor than the flavor's current one. */
function olderHeader(drift: ClusterDrift): boolean {
  return Boolean(drift.current_spec_version && drift.spec_version && drift.current_spec_version !== drift.spec_version);
}

/**
 * Whether "Sync to flavor" has something to do: the cluster follows a flavor
 * and holds a locked value it should not, or its header names an older
 * version (the sync moves `specVersion`).
 */
export function syncOffered(drift: ClusterDrift | undefined): boolean {
  if (!drift || drift.state === "not_linked" || !drift.spec_name) return false;
  return valueDriftOf(drift).length > 0 || olderHeader(drift);
}

function MissingAddons({
  entries,
  isAdmin,
  onFix,
}: {
  entries: AddonDrift[];
  isAdmin: boolean;
  onFix: (entry: AddonDrift) => void;
}) {
  return (
    <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-4 space-y-2">
      <p className="text-xs font-semibold text-status-warning-fg uppercase tracking-wide">Missing addons</p>
      <p className="text-xs text-muted-foreground">Installed through day2, one MR each, with the values requested at create.</p>
      <div className="divide-y divide-status-warning/20">
        {entries.map((entry) => (
          <div key={`${entry.team}/${entry.addon_name}`} className="flex items-center justify-between gap-3 py-2 text-sm flex-wrap">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono font-medium truncate">{entry.addon_name}</span>
              <span className="text-muted-foreground text-xs">{entry.team}</span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-status-error-fg">Not installed</span>
              {isAdmin && (
                <button onClick={() => onFix(entry)} className={buttonVariants({ size: "sm", variant: "outline" })}>
                  <Wrench className="h-3 w-3 mr-1" />
                  Install
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Drift is two things (ADR-0036): the flavor's locked values the cluster file
 * does not hold (compared with the file itself, never a re-render), and the
 * flavor's day2 add-ons the cluster does not have. A sync to the flavor fixes
 * the first in one day1 MR; day2 installs the second. Another add-on version
 * is listed as information, never drift.
 */
export function ClusterDriftPanel({
  drift,
  isLoading,
  error,
  isAdmin,
  onFix,
  onFixAll,
  fixAllPending,
  onSync,
}: {
  drift: ClusterDrift | undefined;
  isLoading: boolean;
  error: unknown;
  isAdmin: boolean;
  onFix: (entry: AddonDrift) => void;
  onFixAll: () => void;
  fixAllPending: boolean;
  /** Opens "Sync to flavor"; offered to admins when `syncOffered(drift)`, and not at all without it. */
  onSync?: () => void;
}) {
  if (isLoading) return <DriftSkeleton />;
  if (error) return <ProblemList error={error} title="Drift could not be loaded" />;
  if (!drift) return null;

  const values = valueDriftOf(drift);
  const addons = drift.addon_drift ?? [];
  // The version compared against: the flavor's current one, else (it is gone) the one the header names
  const comparedVersion = drift.current_spec_version ?? drift.spec_version;
  const flavorLabel = (
    <>
      <strong>{drift.spec_name}</strong>{comparedVersion && <> v{comparedVersion}</>}
    </>
  );
  const newerFlavor = olderHeader(drift) ? (
    <p className="text-xs text-muted-foreground mt-1">
      The file&apos;s header names v{drift.spec_version}; drift compares against the flavor as it is now,
      v{drift.current_spec_version}. A sync moves the header to v{drift.current_spec_version}.
    </p>
  ) : null;

  const syncButton = isAdmin && onSync && syncOffered(drift) && (
    <button onClick={onSync} className={buttonVariants({ size: "sm" })}>
      <RefreshCcw className="h-3.5 w-3.5 mr-1.5" />
      Sync to flavor
    </button>
  );
  const fixAllButton = isAdmin && addons.length > 1 && (
    <button
      onClick={onFixAll}
      disabled={fixAllPending}
      className={buttonVariants({ size: "sm", variant: values.length > 0 ? "outline" : "default" })}
    >
      <Wrench className="h-3.5 w-3.5 mr-1.5" />
      Fix all ({addons.length})
    </button>
  );

  const lockedValues = values.length > 0 && (
    <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-4 space-y-1" data-testid="value-drift">
      <p className="text-xs font-semibold text-status-warning-fg uppercase tracking-wide">Locked values that differ</p>
      <p className="text-xs text-muted-foreground">
        The flavor fixes these values, and the cluster file holds others. Sync to flavor sets them in one day1 MR.
      </p>
      <ValueDriftList items={values} />
    </div>
  );

  switch (drift.state) {
    case "not_linked":
      return (
        <Notice icon={Unlink} tone="text-muted-foreground">
          <p>This cluster follows no flavor, so there is nothing to drift from.</p>
          <p className="text-xs mt-1">
            It can join one from that flavor&apos;s page, with <strong>Add existing clusters</strong>.{" "}
            <Link href="/specs" className="text-primary hover:underline">Choose a flavor</Link>
          </p>
        </Notice>
      );
    case "unknown":
      return (
        <div className="space-y-4">
          <Notice icon={CircleHelp} tone="text-status-deleting-fg">
            <p>Drift against {flavorLabel} could not be determined.</p>
            {drift.error && <p className="text-xs text-muted-foreground mt-1 break-words">{drift.error}</p>}
          </Notice>
          {lockedValues}
        </div>
      );
    case "in_sync":
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <Notice icon={CheckCircle2} tone="text-status-ready-fg">
              <p>The cluster holds every value {flavorLabel} locks and has every add-on it lists.</p>
              {newerFlavor}
            </Notice>
            {syncButton}
          </div>
          <VersionDifferences differences={drift.version_differences ?? []} />
        </div>
      );
    case "drifted": {
      const parts = [
        values.length > 0 && `${values.length} locked value${values.length !== 1 ? "s" : ""} differ${values.length === 1 ? "s" : ""}`,
        addons.length > 0 && `${addons.length} add-on${addons.length !== 1 ? "s are" : " is"} missing`,
      ].filter(Boolean);
      return (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-2 text-sm text-status-warning-fg">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p>
                  The cluster has drifted from {flavorLabel}
                  {parts.length > 0 && <>: {parts.join(", and ")}</>}.
                </p>
                {drift.error && <p className="text-xs text-muted-foreground mt-1 break-words">{drift.error}</p>}
                {newerFlavor}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {syncButton}
              {fixAllButton}
            </div>
          </div>

          {lockedValues}
          {addons.length > 0 && <MissingAddons entries={addons} isAdmin={isAdmin} onFix={onFix} />}
          <VersionDifferences differences={drift.version_differences ?? []} />
        </div>
      );
    }
  }
}
