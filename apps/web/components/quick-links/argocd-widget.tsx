import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ArgoReading } from "@/types";

type Tone = "plain" | "warning" | "error";

const TONE: Record<Tone, string> = {
  plain: "text-foreground",
  warning: "text-status-warning-fg",
  error: "text-status-error-fg",
};

function Stat({ id, label, value, tone = "plain" }: { id: string; label: string; value: number; tone?: Tone }) {
  return (
    <div className="flex items-baseline justify-between gap-2" data-testid={`argocd-${id}`}>
      <dt className="whitespace-nowrap text-[11px] text-muted-foreground">{label}</dt>
      <dd className={cn("text-xs font-semibold tabular-nums", TONE[value > 0 ? tone : "plain"])}>{value}</dd>
    </div>
  );
}

/**
 * An ArgoCD's applications by sync and health, as day1 read them with the
 * instance's read-only token (the token never reaches the browser). Out of
 * sync is a warning; degraded and missing are errors. While day1's first
 * answer is on its way, a skeleton; when the read failed, why, in one line.
 */
export function ArgoCdWidget({ reading, loading }: { reading: ArgoReading | undefined; loading: boolean }) {
  if (!reading) {
    if (!loading) return null;
    return <Skeleton className="h-[86px] w-full" data-testid="argocd-widget-loading" />;
  }
  if (!reading.counts) {
    return (
      <p className="truncate text-xs text-muted-foreground" data-testid="argocd-widget-error" title={reading.error ?? undefined}>
        Counts unavailable{reading.error ? `: ${reading.error}` : ""}
      </p>
    );
  }
  const { applications, sync, health } = reading.counts;
  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2" data-testid="argocd-widget">
      <p className="text-[11px] font-medium text-muted-foreground">
        <span className="tabular-nums text-foreground" data-testid="argocd-applications">{applications}</span>{" "}
        application{applications === 1 ? "" : "s"}
      </p>
      <dl className="mt-1 grid grid-cols-2 gap-x-4">
        <Stat id="synced" label="Synced" value={sync.synced} />
        <Stat id="out-of-sync" label="OutOfSync" value={sync.out_of_sync} tone="warning" />
      </dl>
      <dl className="mt-1 grid grid-cols-2 gap-x-4 border-t pt-1">
        <Stat id="healthy" label="Healthy" value={health.healthy} />
        <Stat id="progressing" label="Progressing" value={health.progressing} />
        <Stat id="degraded" label="Degraded" value={health.degraded} tone="error" />
        <Stat id="missing" label="Missing" value={health.missing} tone="error" />
      </dl>
    </div>
  );
}
