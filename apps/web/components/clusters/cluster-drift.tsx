import { AlertTriangle, CheckCircle2, CircleHelp, Unlink, Wrench } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import type { AddonDrift, ClusterDrift } from "@/types";

function Notice({ icon: Icon, tone, children }: { icon: typeof CheckCircle2; tone: string; children: React.ReactNode }) {
  return (
    <div className={`flex items-start gap-2 text-sm py-4 ${tone}`}>
      <Icon className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/**
 * Drift is the spec's day2 addons against what day2 has installed (the file
 * itself is never re-rendered: nothing is stored to re-render from).
 */
export function ClusterDriftPanel({
  drift,
  isLoading,
  error,
  isAdmin,
  onFix,
  onFixAll,
  fixAllPending,
}: {
  drift: ClusterDrift | undefined;
  isLoading: boolean;
  error: unknown;
  isAdmin: boolean;
  onFix: (entry: AddonDrift) => void;
  onFixAll: () => void;
  fixAllPending: boolean;
}) {
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (error) return <ProblemList error={error} title="Drift could not be loaded" />;
  if (!drift) return null;

  const specLabel = (
    <>
      <strong>{drift.spec_name}</strong>{drift.spec_version && <> v{drift.spec_version}</>}
    </>
  );
  const newerSpec =
    drift.current_spec_version && drift.spec_version && drift.current_spec_version !== drift.spec_version ? (
      <p className="text-xs text-muted-foreground mt-1">
        The spec is now at v{drift.current_spec_version}; this cluster was created from v{drift.spec_version}.
        Drift compares against the version it was created from.
      </p>
    ) : null;

  switch (drift.state) {
    case "not_linked":
      return (
        <Notice icon={Unlink} tone="text-muted-foreground">
          Drift tracking is not active — this cluster is not linked to a cluster spec.
        </Notice>
      );
    case "unknown":
      return (
        <Notice icon={CircleHelp} tone="text-status-deleting-fg">
          <p>Drift against {specLabel} could not be determined.</p>
          {drift.error && <p className="text-xs text-muted-foreground mt-1 break-words">{drift.error}</p>}
        </Notice>
      );
    case "in_sync":
      return (
        <Notice icon={CheckCircle2} tone="text-status-ready-fg">
          <p>Every addon of {specLabel} is installed at the spec&apos;s version.</p>
          {newerSpec}
        </Notice>
      );
    case "drifted":
      return (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-2 text-sm text-status-warning-fg">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p>The cluster has drifted from {specLabel}.</p>
                {newerSpec}
              </div>
            </div>
            {isAdmin && drift.addon_drift.length > 1 && (
              <button onClick={onFixAll} disabled={fixAllPending} className={buttonVariants({ size: "sm" })}>
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                Fix all ({drift.addon_drift.length})
              </button>
            )}
          </div>

          <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-4 space-y-2">
            <p className="text-xs font-semibold text-status-warning-fg uppercase tracking-wide">Addon compliance issues</p>
            <div className="divide-y divide-status-warning/20">
              {drift.addon_drift.map((entry) => (
                <div key={`${entry.team}/${entry.addon_name}`} className="flex items-center justify-between gap-3 py-2 text-sm flex-wrap">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono font-medium truncate">{entry.addon_name}</span>
                    <span className="text-muted-foreground text-xs">{entry.team}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    {entry.reason === "missing" ? (
                      <span className="text-status-error-fg">Not installed — spec requires {entry.expected_version}</span>
                    ) : (
                      <span className="text-status-warning-fg">
                        {entry.installed_version} installed → spec requires {entry.expected_version}
                      </span>
                    )}
                    {isAdmin && (
                      <button onClick={() => onFix(entry)} className={buttonVariants({ size: "sm", variant: "outline" })}>
                        <Wrench className="h-3 w-3 mr-1" />
                        {entry.reason === "missing" ? "Install" : "Update"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
  }
}
