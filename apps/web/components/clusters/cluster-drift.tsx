import Link from "next/link";
import {
  AlertTriangle, ArrowRight, ArrowUpCircle, CheckCircle2, CircleHelp, ExternalLink, GitPullRequest, Info, RefreshCcw, Unlink, Wrench,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { ValueDriftList } from "@/components/clusters/value-drift";
import { approvalHref } from "@/lib/approvals";
import type { AddonDrift, ClusterDrift, FlavorUpdate, ValueDrift, VersionDifference } from "@/types";

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
 * only (ADR-0025): day2 keeps a cluster on the add-on's revision unless someone
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

/** The file's header names another version of its flavor than the flavor's newest. */
function olderHeader(drift: ClusterDrift): boolean {
  return Boolean(drift.current_spec_version && drift.spec_version && drift.current_spec_version !== drift.spec_version);
}

/**
 * The cluster's update (ADR-0044): a newer version of its flavor, and the
 * open MR that moves the cluster to it. A day1 that predates `update` sends
 * none: an older header is then an update whose MR is not known.
 */
export function updateOf(drift: ClusterDrift): FlavorUpdate | null {
  if (drift.update !== undefined) return drift.update;
  return olderHeader(drift) ? { version: drift.current_spec_version!, merge_request: null } : null;
}

/**
 * Whether "Sync to flavor" has something to do: the cluster follows a flavor
 * and holds a locked value it should not, or a newer version is out (the sync
 * moves `specVersion` to it). Not while an update MR is open: that MR is the
 * sync, and the panel links it instead (a second one is refused, 409).
 */
export function syncOffered(drift: ClusterDrift | undefined): boolean {
  if (!drift || drift.state === "not_linked" || !drift.spec_name) return false;
  const update = updateOf(drift);
  if (update?.merge_request) return false;
  return valueDriftOf(drift).length > 0 || update !== null;
}

/**
 * A newer version of the flavor: its open update MR, or (none open) a sync.
 * A new version opens one MR per cluster on its own; one that is not open
 * waits for the next run, needs a person, or was declined (the flavor's page
 * says which).
 */
function UpdateNotice({ flavor, update, syncButton }: { flavor: string; update: FlavorUpdate; syncButton: React.ReactNode }) {
  const mr = update.merge_request;
  return (
    <div
      data-testid="flavor-update"
      data-state={mr ? "merge_request_open" : "available"}
      className="flex items-start justify-between gap-3 flex-wrap rounded-lg border border-status-provisioning/30 bg-status-provisioning/5 p-4"
    >
      <div className="flex items-start gap-2 text-sm min-w-0">
        {mr ? (
          <GitPullRequest className="h-4 w-4 shrink-0 mt-0.5 text-status-provisioning-fg" aria-hidden />
        ) : (
          <ArrowUpCircle className="h-4 w-4 shrink-0 mt-0.5 text-status-provisioning-fg" aria-hidden />
        )}
        <div className="min-w-0 space-y-1">
          <p>
            <strong>{flavor} v{update.version}</strong> is out.
            {mr ? (
              <> Merge request !{mr.iid} moves this cluster to it, and nothing changes on the cluster until it merges.</>
            ) : (
              <> No merge request moves this cluster to it yet.</>
            )}
          </p>
          <p className="text-xs text-muted-foreground">
            {mr
              ? "Its customer merges it when ready. It sets every value the new version locks, and moves the header to it."
              : "A new version opens one merge request per cluster on its own; none is open for this one (the flavor's page says why). Sync to flavor opens it now."}
          </p>
        </div>
      </div>
      {mr ? (
        <div className="flex items-center gap-3 text-xs font-medium shrink-0">
          <Link href={approvalHref(mr)} className={buttonVariants({ size: "sm" })}>
            Review the update MR !{mr.iid}
            <ArrowRight className="h-3.5 w-3.5 ml-1" aria-hidden />
          </Link>
          <a
            href={mr.web_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
            aria-label={`Open !${mr.iid} in GitLab`}
          >
            GitLab
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        </div>
      ) : (
        syncButton
      )}
    </div>
  );
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
 * flavor's day2 add-ons the cluster does not have, both against the version
 * of the flavor the cluster's header names (ADR-0044). A newer version is an
 * update, never drift: its MR opens on its own and is linked here, or a sync
 * moves the cluster to it. A sync fixes the values in one day1 MR; day2
 * installs the add-ons. Another add-on version is information, never drift.
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
  const update = updateOf(drift);
  // Drift compares with the version the header names (ADR-0044), never the newest
  const flavorLabel = (
    <>
      <strong>{drift.spec_name}</strong>{drift.spec_version && <> v{drift.spec_version}</>}
    </>
  );
  const newest = !update && drift.current_spec_version === drift.spec_version;
  const comparedWith = drift.spec_version && (
    <p className="text-xs text-muted-foreground mt-1" data-testid="drift-compared-with">
      Compared with {drift.spec_name} v{drift.spec_version}, the version this cluster is on
      {newest ? " and the flavor's newest" : ""}.
    </p>
  );

  const syncButton = isAdmin && onSync && syncOffered(drift) && (
    <button onClick={onSync} className={buttonVariants({ size: "sm" })}>
      <RefreshCcw className="h-3.5 w-3.5 mr-1.5" />
      Sync to flavor
    </button>
  );
  // With an update, the sync is offered beside it: it moves the cluster to that version
  const updateNotice = update && drift.spec_name && (
    <UpdateNotice flavor={drift.spec_name} update={update} syncButton={syncButton} />
  );
  const stateSync = update ? null : syncButton;
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
        The version of the flavor it is on fixes these values, and the cluster file holds others.{" "}
        {update?.merge_request
          ? `Its update MR !${update.merge_request.iid} sets the values v${update.version} locks.`
          : "Sync to flavor sets them in one day1 MR."}
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
          {updateNotice}
          {lockedValues}
        </div>
      );
    case "in_sync":
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <Notice icon={CheckCircle2} tone="text-status-ready-fg">
              <p>The cluster holds every value {flavorLabel} locks and has every add-on it lists.</p>
              {comparedWith}
            </Notice>
            {stateSync}
          </div>
          {updateNotice}
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
                {comparedWith}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {stateSync}
              {fixAllButton}
            </div>
          </div>

          {updateNotice}
          {lockedValues}
          {addons.length > 0 && <MissingAddons entries={addons} isAdmin={isAdmin} onFix={onFix} />}
          <VersionDifferences differences={drift.version_differences ?? []} />
        </div>
      );
    }
  }
}
