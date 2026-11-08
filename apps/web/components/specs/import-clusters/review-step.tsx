"use client";

import Link from "next/link";
import { ArrowRight, Ban, CheckCircle2, FileText, Link2, Shuffle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { WarningPanel } from "@/components/specs/flavor-inputs";
import { CheckToggle } from "@/components/specs/import-clusters/check-toggle";
import { DriftOnceLinked, driftSummary } from "@/components/specs/import-clusters/drift-preview";
import { pickKey } from "@/components/specs/import-clusters/pick-step";
import { clusterHref } from "@/lib/clusters";
import { cn } from "@/lib/utils";
import type { ImportCandidate, ImportPreview, ImportStatus } from "@/types";

const STATUS: Record<ImportStatus, { label: string; Icon: typeof CheckCircle2; className: string }> = {
  ready: { label: "Ready", Icon: CheckCircle2, className: "bg-status-ready/10 text-status-ready-fg" },
  relink: { label: "On another flavor", Icon: Shuffle, className: "bg-status-warning/10 text-status-warning-fg" },
  linked: { label: "Already on this flavor", Icon: Link2, className: "bg-muted text-muted-foreground" },
  refused: { label: "Can't be imported", Icon: Ban, className: "bg-destructive/10 text-destructive" },
};

/** What needs a decision first, then what is imported, then what is left out. */
const STATUS_ORDER: ImportStatus[] = ["relink", "ready", "refused", "linked"];

/** day1 starts each problem with the cluster's name; inside its card that is said already. */
const withoutName = (problem: string, name: string) =>
  problem.startsWith(`${name}: `) ? problem.slice(name.length + 2) : problem;

function StatusBadge({ status }: { status: ImportStatus }) {
  const { label, Icon, className } = STATUS[status];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}>
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </span>
  );
}

/** A candidate counts in the import when it is ready, or follows another flavor and is moved. */
export function isImported(c: ImportCandidate, moved: ReadonlySet<string>): boolean {
  return c.status === "ready" || (c.status === "relink" && moved.has(pickKey(c)));
}

function Candidate({
  candidate: c,
  flavor,
  moved,
  onMovedChange,
}: {
  candidate: ImportCandidate;
  flavor: string;
  moved: boolean;
  onMovedChange: (moved: boolean) => void;
}) {
  const summary = driftSummary(c.drift);
  return (
    <article
      data-testid={`import-candidate-${c.name}`}
      data-status={c.status}
      className={cn(
        "space-y-2.5 rounded-lg border p-3",
        c.status === "refused" && "border-destructive/30",
        c.status === "linked" && "bg-muted/20"
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold break-all">{c.name}</p>
          <p className="text-xs text-muted-foreground break-all">
            {c.site} / {c.mce}
            {(c.status === "ready" || c.status === "relink") && summary && <> · {summary}</>}
          </p>
        </div>
        <StatusBadge status={c.status} />
      </header>

      {c.status === "relink" && (
        <div className="space-y-1.5 rounded-md bg-status-warning/5 p-2.5">
          <p className="text-xs text-status-warning-fg">
            Follows flavor <strong className="font-semibold">{c.linked_spec?.name ?? "another flavor"}</strong>
            {c.linked_spec?.version && <> v{c.linked_spec.version}</>}. Moving it to {flavor} holds it to this
            flavor&apos;s locks instead.
          </p>
          <CheckToggle checked={moved} onCheckedChange={onMovedChange} className="items-center text-xs font-medium">
            Move to {flavor}
          </CheckToggle>
        </div>
      )}

      {c.status === "linked" && (
        <p className="text-xs text-muted-foreground">
          Nothing to import.{" "}
          <Link href={clusterHref(c)} className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
            Sync it from its page<ArrowRight className="h-3 w-3" aria-hidden />
          </Link>
        </p>
      )}

      {c.status === "refused" && (
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-destructive">
          {(c.problems.length > 0 ? c.problems : ["Its file cannot be edited safely."]).map((p, i) => (
            <li key={i} className="break-words">{withoutName(p, c.name)}</li>
          ))}
        </ul>
      )}

      {(c.status === "ready" || c.status === "relink") && <DriftOnceLinked drift={c.drift} />}
    </article>
  );
}

/** While the preview compares the picks with the flavor: the summary, then a card per pick. */
export function ReviewSkeleton({ count }: { count: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Comparing the clusters with the flavor">
      <p className="text-sm text-muted-foreground">
        Comparing {count} cluster{count !== 1 ? "s" : ""} with the flavor…
      </p>
      {Array.from({ length: Math.min(count, 4) }).map((_, i) => (
        <div key={i} className="space-y-2 rounded-lg border p-3">
          <div className="flex justify-between gap-3">
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-56" />
              <Skeleton className="h-3 w-40" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-10 w-full" />
        </div>
      ))}
    </div>
  );
}

/**
 * Step two: each pick against the flavor (`POST /specs/{name}/import/preview`)
 * — whether it can join and what will show as drift once it does.
 */
export function ReviewStep({
  flavor,
  preview,
  moved,
  onMovedChange,
}: {
  flavor: string;
  preview: ImportPreview;
  moved: ReadonlySet<string>;
  onMovedChange: (key: string, moved: boolean) => void;
}) {
  const counts = STATUS_ORDER.map((status) => ({
    status,
    count: preview.clusters.filter((c) => c.status === status).length,
  })).filter((c) => c.count > 0);
  const ordered = [...preview.clusters].sort(
    (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.name.localeCompare(b.name)
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2.5 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground" data-testid="import-explainer">
        <FileText className="h-4 w-4 shrink-0 text-foreground/70" aria-hidden />
        <p>
          The import opens one day1 MR that writes only the flavor link (<code className="font-mono">specName</code>,{" "}
          <code className="font-mono">specVersion</code>) into each cluster file&apos;s header. Nothing on the clusters
          changes. Once the MR merges, the differences below show as drift, and Sync on each cluster&apos;s page fixes
          them.
        </p>
      </div>

      <WarningPanel
        title="About this flavor"
        description="Worth knowing before these clusters follow it."
        lines={preview.warnings}
        data-testid="import-preview-warnings"
      />

      <div className="space-y-1.5" data-testid="import-preview-counts">
        <p className="text-sm font-medium">
          {preview.clusters.length} cluster{preview.clusters.length !== 1 ? "s" : ""} against {flavor} v{preview.spec_version}
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {counts.map(({ status, count }) => (
            <span key={status} className="inline-flex items-center gap-1 text-xs">
              <StatusBadge status={status} />
              <span className="font-medium tabular-nums">{count}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-2.5">
        {ordered.map((c) => (
          <Candidate
            key={pickKey(c)}
            candidate={c}
            flavor={flavor}
            moved={moved.has(pickKey(c))}
            onMovedChange={(on) => onMovedChange(pickKey(c), on)}
          />
        ))}
      </div>
    </div>
  );
}
