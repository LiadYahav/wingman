"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2, Edit2, Server, CheckCircle2, ExternalLink, GitCommitHorizontal, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, isApiError, errorMessages } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, formatDate } from "@/lib/utils";
import { ReviewDialog } from "@/components/common/review-dialog";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, EmptyStateLink } from "@/components/common/empty-state";
import { DriftBadge } from "@/components/clusters/drift-badge";
import { FlavorInputsCard, WarningPanel } from "@/components/specs/flavor-inputs";
import { clusterHref } from "@/lib/clusters";
import { specApiPath } from "@/lib/specs";
import { toastMrOpened } from "@/lib/mr-toast";
import { writeErrorTitle } from "@/lib/write-errors";
import type { DriftState, MRDetail, SpecCluster, SpecCommit, SpecDetail, SpecDrift } from "@/types";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground shrink-0 w-32">{label}</span>
      <span className="text-sm font-medium text-right min-w-0 break-words">{value}</span>
    </div>
  );
}

const DRIFT_ORDER: DriftState[] = ["drifted", "unknown", "in_sync", "not_linked"];

/** A 409 REVISION_CONFLICT: the flavor's file moved since this page read it. */
const STALE_SPEC =
  "The flavor changed since you opened it, so the delete was refused and nothing was changed. Reload to see the current flavor, then delete it again if you still want to.";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The header's Delete: refused while clusters follow the flavor, with the reason on hover and for screen readers. */
function DeleteButton({ blocked, pending, onClick }: { blocked: string | null; pending: boolean; onClick: () => void }) {
  const button = (
    <button
      className={buttonVariants({ variant: "destructive", size: "sm" })}
      onClick={onClick}
      disabled={pending || !!blocked}
      aria-describedby={blocked ? "flavor-delete-blocked" : undefined}
    >
      <Trash2 className="h-3.5 w-3.5 mr-1.5" />Delete
    </button>
  );
  if (!blocked) return button;
  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger render={<span className="inline-flex" tabIndex={0} />}>{button}</TooltipTrigger>
          <TooltipContent className="max-w-xs">{blocked}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <span id="flavor-delete-blocked" className="sr-only">{blocked}</span>
    </>
  );
}

export default function SpecDetailPage() {
  const params = useParams();
  const specName = params.name as string;
  const isAdmin = useIsAdmin();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"overview" | "clusters" | "drift" | "history">("overview");
  const [deleteReviewOpen, setDeleteReviewOpen] = useState(false);
  const [selectedSha, setSelectedSha] = useState<string | null>(null);

  const { data: spec, isLoading, error: specError, refetch: refetchSpec } = useQuery<SpecDetail>({
    queryKey: ["specs", specName],
    queryFn: () => api.get<SpecDetail>(specApiPath(specName)),
    staleTime: 60_000,
    // A delete sends this read's last_commit_id: re-read on every visit (a
    // cached copy renders meanwhile), so a change merged since is seen.
    refetchOnMount: "always",
    retry: (count, error) => !isApiError(error, "VALIDATION_ERROR") && !isApiError(error, "NOT_FOUND") && count < 2,
  });
  // A flavor file that does not parse answers 422 with every problem; it can still be deleted.
  const doesNotLoad = isApiError(specError, "VALIDATION_ERROR");

  // Read on every tab: the count is in the tab, and a flavor clusters follow can't be deleted.
  const { data: clusters, isLoading: clustersLoading, error: clustersError } = useQuery<SpecCluster[]>({
    queryKey: ["specs", specName, "clusters"],
    queryFn: () => api.get<SpecCluster[]>(`/api/day1/specs/${encodeURIComponent(specName)}/clusters`),
    staleTime: 30_000,
    gcTime: 2 * 60_000,
  });

  const { data: driftResults, isLoading: driftLoading, error: driftError } = useQuery<SpecDrift[]>({
    queryKey: ["specs", specName, "drift"],
    queryFn: () => api.get<SpecDrift[]>(`/api/day1/specs/${encodeURIComponent(specName)}/drift`),
    enabled: activeTab === "drift",
    staleTime: 60_000,
  });

  const { data: history, isLoading: historyLoading, error: historyError } = useQuery<SpecCommit[]>({
    queryKey: ["spec-history", specName],
    queryFn: () => api.get<SpecCommit[]>(`/api/day1/specs/${encodeURIComponent(specName)}/history`),
    enabled: activeTab === "history",
    staleTime: 60_000,
  });

  const { data: specAtSha, isLoading: specAtShaLoading, error: specAtShaError } = useQuery<string>({
    queryKey: ["spec-at-sha", specName, selectedSha],
    queryFn: () => api.getText(`/api/day1/specs/${encodeURIComponent(specName)}/at/${selectedSha}`),
    enabled: !!selectedSha && activeTab === "history",
    staleTime: Infinity,
  });

  const deleteMutation = useMutation({
    // Guarded by the commit the flavor was read at (a flavor that does not load has none)
    mutationFn: () => api.del<MRDetail>(specApiPath(specName, spec?.last_commit_id)),
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Delete MR");
      setDeleteReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["specs"] });
      router.push("/specs");
    },
    onError: (err) => {
      // A stale read is never retried: the page says so and offers a reload
      if (isApiError(err, "REVISION_CONFLICT")) {
        setDeleteReviewOpen(false);
        return;
      }
      toast.error(writeErrorTitle(err, "Could not open the delete MR"), { description: errorMessages(err).join(" · ") });
    },
  });
  const deleteConflict = isApiError(deleteMutation.error, "REVISION_CONFLICT");

  /** After a 409: read the flavor (and its history) again, then the delete can be reviewed anew. */
  const reloadAfterConflict = async () => {
    deleteMutation.reset();
    await refetchSpec();
    queryClient.invalidateQueries({ queryKey: ["spec-history", specName] });
  };

  const followers = clusters?.length ?? 0;
  // A flavor in use is not deleted: its clusters would follow a flavor that is gone. When the
  // check fails, the review says it could not be made.
  const deleteBlocked = clustersLoading
    ? "Checking which clusters follow this flavor…"
    : followers > 0
      ? `${plural(followers, "cluster")} follow${followers === 1 ? "s" : ""} this flavor, so it can't be deleted. ` +
        "Move them to another flavor or delete them first."
      : null;

  const driftCounts = DRIFT_ORDER
    .map((state) => ({ state, count: driftResults?.filter((r) => r.state === state).length ?? 0 }))
    .filter((c) => c.count > 0);
  const allInSync = (driftResults?.length ?? 0) > 0 && driftResults!.every((r) => r.state === "in_sync");
  const anyDrifted = driftResults?.some((r) => r.state === "drifted") ?? false;

  const tabs = [
    { id: "overview" as const, label: "Overview" },
    { id: "clusters" as const, label: `Clusters${clusters ? ` (${clusters.length})` : ""}` },
    { id: "drift" as const, label: "Drift" },
    { id: "history" as const, label: "History" },
  ];

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <Link href="/specs" className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="All flavors">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Flavor</p>
          <h1
            className="text-2xl font-bold tracking-tight break-all"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            {specName}
          </h1>
          {spec?.metadata.description && (
            <p className="text-sm text-muted-foreground mt-0.5">{spec.metadata.description}</p>
          )}
        </div>
        {!isLoading && isAdmin && (spec || doesNotLoad) && (
          <div className="flex items-center gap-2 shrink-0">
            {spec && (
              <Link
                href={`/specs/${encodeURIComponent(specName)}/edit`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Edit2 className="h-3.5 w-3.5 mr-1.5" />Edit
              </Link>
            )}
            <DeleteButton
              blocked={deleteBlocked}
              pending={deleteMutation.isPending}
              onClick={() => { deleteMutation.reset(); setDeleteReviewOpen(true); }}
            />
          </div>
        )}
      </div>

      {deleteConflict && (
        <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
          <p className="text-status-warning-fg">{STALE_SPEC}</p>
          <button onClick={reloadAfterConflict} className={buttonVariants({ variant: "outline", size: "sm" })}>
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Reload
          </button>
        </div>
      )}

      {specError && (
        <ProblemList
          error={specError}
          title={
            doesNotLoad
              ? "This flavor's file does not load. Fix it in GitLab, or delete the flavor."
              : isApiError(specError, "NOT_FOUND")
                ? "No flavor by this name."
                : undefined
          }
        />
      )}

      {spec && (
        <WarningPanel
          title={`This flavor breaks ${plural(spec.warnings?.length ?? 0, "rule")}`}
          description="It still loads and its clusters still follow it, but saving it unchanged is refused, and a lock that breaks a rule is not enforced. Edit the flavor to fix it."
          lines={spec.warnings ?? []}
          data-testid="flavor-warnings"
        />
      )}

      {/* Line tabs */}
      <div className="border-b border-border">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 transition-all",
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Overview tab */}
      {activeTab === "overview" && (isLoading || spec) && (
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          <div className="bg-card rounded-xl border shadow-sm p-5">
            <h2 className="text-sm font-semibold mb-3">Metadata</h2>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-full mb-2" />)
            ) : spec && (
              <>
                <InfoRow label="Name" value={<span className="break-all">{spec.metadata.name}</span>} />
                <InfoRow label="Version" value={
                  <span className="rounded-full px-2 py-0.5 text-xs bg-primary/8 text-primary font-medium break-all">
                    {spec.metadata.version}
                  </span>
                } />
                {spec.metadata.labels && Object.entries(spec.metadata.labels).map(([k, v]) => (
                  <InfoRow key={k} label={k} value={v} />
                ))}
                <InfoRow
                  label="Clusters"
                  value={
                    clustersLoading ? (
                      <Skeleton className="h-4 w-28 inline-block" />
                    ) : clustersError ? (
                      <span className="text-status-warning-fg font-normal">Could not be checked</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setActiveTab("clusters")}
                        className="hover:text-primary transition-colors"
                        data-testid="flavor-followers"
                      >
                        {followers === 0 ? "None follow it yet" : `${plural(followers, "cluster")} follow${followers === 1 ? "s" : ""} it`}
                      </button>
                    )
                  }
                />
              </>
            )}
          </div>

          {isLoading ? (
            <Skeleton className="h-48 rounded-xl" />
          ) : spec && <FlavorInputsCard spec={spec} />}

          {spec && spec.spec.day2.addons.length > 0 && (
            <div className="bg-card rounded-xl border shadow-sm p-5 lg:col-span-2">
              <h2 className="text-sm font-semibold mb-3">Addons ({spec.spec.day2.addons.length})</h2>
              <div className="flex flex-wrap gap-2">
                {spec.spec.day2.addons.map((addon) => (
                  <div key={`${addon.team}/${addon.name}`} className="rounded-lg border px-3 py-2 text-sm max-w-full">
                    <span className="font-medium break-all">{addon.name}</span>
                    <span className="text-muted-foreground ml-1.5 text-xs">{addon.team} · {addon.version}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Clusters tab */}
      {activeTab === "clusters" && clustersError && (
        <ProblemList error={clustersError} title="The clusters following this flavor could not be loaded" />
      )}
      {activeTab === "clusters" && !clustersError && (
        <div className="bg-card rounded-xl border shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Cluster</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Site / MCE</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Drift</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {clustersLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>{Array.from({ length: 3 }).map((_, j) => (
                      <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                    ))}</tr>
                  ))
                : clusters?.length === 0 ? (
                    <tr>
                      <td colSpan={3}>
                        <EmptyState
                          icon={Server}
                          title="No clusters follow this flavor yet"
                          description="A cluster created from this flavor, or an existing one added to it, is listed here with its drift state."
                          action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
                          data-testid="spec-clusters-empty"
                        />
                      </td>
                    </tr>
                  )
                : clusters?.map((c) => (
                    <tr key={`${c.site}/${c.mce}/${c.name}`} data-testid={`spec-cluster-${c.name}`} className="hover:bg-primary/[0.03] transition-colors">
                      <td className="px-4 py-3">
                        <Link
                          href={clusterHref(c)}
                          className="font-semibold hover:text-primary transition-colors inline-flex items-center gap-1 break-all"
                        >
                          {c.name}
                          <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0" />
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground break-all">{c.site} / {c.mce}</td>
                      <td className="px-4 py-3">
                        <DriftBadge state={c.state} error={c.error} />
                      </td>
                    </tr>
                  ))
              }
            </tbody>
          </table>
        </div>
      )}

      {/* Drift tab */}
      {activeTab === "drift" && (
        <div className="space-y-4">
          {driftLoading ? (
            <>
              {/* The summary bar, then one row per cluster */}
              <div className="bg-card rounded-xl border shadow-sm px-5 py-4 flex flex-wrap items-center gap-x-4 gap-y-2">
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-5 w-24 rounded-full" />
                <Skeleton className="h-5 w-24 rounded-full" />
              </div>
              <div className="bg-card rounded-xl border shadow-sm divide-y divide-border overflow-hidden">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-start gap-3 px-5 py-3.5">
                    <Skeleton className="h-4 w-4 shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0 space-y-1.5">
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-3 w-64 max-w-full" />
                    </div>
                    <Skeleton className="h-5 w-16 rounded-full shrink-0" />
                  </div>
                ))}
              </div>
            </>
          ) : driftError ? (
            <ProblemList error={driftError} title="Could not compute drift for this flavor's clusters." />
          ) : driftResults?.length === 0 ? (
            <EmptyState
              icon={Server}
              title="No clusters follow this flavor"
              description="There is nothing to drift until a cluster is created from it or added to it."
              action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
              bordered
              data-testid="spec-drift-empty"
            />
          ) : (
            <>
              <div className="bg-card rounded-xl border shadow-sm px-5 py-4 space-y-2" data-testid="spec-drift-summary">
                {allInSync ? (
                  <p className="flex items-center gap-2 text-sm font-medium text-status-ready-fg">
                    <CheckCircle2 className="h-4 w-4" />
                    {driftResults!.length === 1
                      ? "The cluster matches the flavor"
                      : `All ${driftResults!.length} clusters match the flavor`}
                  </p>
                ) : (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <p className="text-sm font-medium">{plural(driftResults!.length, "cluster")}</p>
                    {driftCounts.map(({ state, count }) => (
                      <span key={state} data-testid={`spec-drift-count-${state}`} className="inline-flex items-center gap-1.5 text-sm">
                        <DriftBadge state={state} />
                        <span className="tabular-nums font-medium">{count}</span>
                      </span>
                    ))}
                  </div>
                )}
                {anyDrifted && (
                  <p className="text-xs text-muted-foreground">
                    A cluster has drifted when a value the flavor locks differs in its file, or an add-on the flavor
                    lists is missing. Open it to see what differs and sync it.
                  </p>
                )}
              </div>
              <div className="bg-card rounded-xl border shadow-sm divide-y divide-border overflow-hidden">
                {[...driftResults!]
                  .sort((a, b) => DRIFT_ORDER.indexOf(a.state) - DRIFT_ORDER.indexOf(b.state) || a.cluster.localeCompare(b.cluster))
                  .map((r) => (
                    <div key={`${r.site}/${r.mce}/${r.cluster}`} data-testid={`spec-drift-${r.cluster}`} className="flex items-start gap-3 px-5 py-3.5">
                      <Server className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <Link
                          href={clusterHref({ name: r.cluster, site: r.site, mce: r.mce })}
                          className="text-sm font-semibold hover:text-primary transition-colors break-all"
                        >
                          {r.cluster}
                        </Link>
                        <p className="text-xs text-muted-foreground mt-0.5 break-all">
                          {r.site} / {r.mce}
                          {r.spec_version && spec && r.spec_version !== spec.metadata.version && (
                            <> · follows v{r.spec_version} (the flavor is v{spec.metadata.version})</>
                          )}
                        </p>
                        {r.state === "unknown" && r.error && (
                          <p className="text-xs text-status-deleting-fg mt-1 break-words">{r.error}</p>
                        )}
                      </div>
                      <DriftBadge state={r.state} error={r.error} className="shrink-0" />
                    </div>
                  ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* History tab */}
      {activeTab === "history" && (
        <div className="flex flex-col md:flex-row gap-4 min-h-[400px]">
          {/* Commit list */}
          <div className="md:w-80 shrink-0 bg-card rounded-xl border shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b bg-muted/30">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Commits</h2>
            </div>
            <div className="overflow-y-auto flex-1">
              {historyLoading ? (
                <div className="p-4 space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : historyError ? (
                <div className="p-4">
                  <ProblemList error={historyError} title="The flavor's history could not be loaded" />
                </div>
              ) : history?.length === 0 ? (
                <EmptyState
                  icon={GitCommitHorizontal}
                  title="No history yet"
                  description="No commit in the specs repo has changed this flavor's file."
                  data-testid="spec-history-empty"
                />
              ) : (
                <div className="divide-y divide-border">
                  {history?.map((commit) => (
                    <button
                      key={commit.sha}
                      onClick={() => setSelectedSha(commit.sha)}
                      className={cn(
                        "w-full text-left px-4 py-3 transition-colors hover:bg-primary/[0.03]",
                        selectedSha === commit.sha && "bg-primary/[0.06] border-l-2 border-l-primary"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
                          <GitCommitHorizontal className="h-3 w-3 shrink-0" />
                          <span>{commit.short_sha}</span>
                        </div>
                        <a
                          href={commit.web_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-muted-foreground hover:text-primary transition-colors shrink-0"
                          title="Open in GitLab"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                      <p className="text-xs font-medium mt-1 line-clamp-2 leading-snug">{commit.message}</p>
                      <div className="flex items-center gap-1 mt-1.5 text-xs text-muted-foreground">
                        <span>{commit.author}</span>
                        <span>·</span>
                        <span>{formatDate(commit.date)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* YAML viewer */}
          <div className="flex-1 min-w-0 bg-card rounded-xl border shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b bg-muted/30 flex items-center justify-between">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                {selectedSha
                  ? `Flavor at ${history?.find((c) => c.sha === selectedSha)?.short_sha ?? selectedSha.slice(0, 8)}`
                  : "Flavor file"}
              </h2>
              {selectedSha && (
                <span className="text-xs text-muted-foreground font-mono">{selectedSha.slice(0, 8)}</span>
              )}
            </div>
            <div className="flex-1 overflow-auto p-4">
              {!selectedSha ? (
                <p className="text-sm text-muted-foreground text-center py-12">
                  Select a commit to view the flavor at that point in time.
                </p>
              ) : specAtShaLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <Skeleton key={i} className="h-4 w-full" />
                  ))}
                </div>
              ) : specAtShaError ? (
                <ProblemList error={specAtShaError} title="The flavor at this commit could not be loaded" />
              ) : (
                <pre className="text-xs font-mono text-zinc-300 bg-zinc-950 rounded-lg p-4 overflow-auto leading-5 whitespace-pre-wrap">
                  {specAtSha}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete review dialog */}
      <ReviewDialog
        open={deleteReviewOpen}
        onOpenChange={setDeleteReviewOpen}
        title={`Review: Delete Flavor "${specName}"`}
        description="This will create a GitLab MR to delete this flavor. The change requires approval before merging."
        onConfirm={() => deleteMutation.mutate()}
        isPending={deleteMutation.isPending}
        confirmLabel="Confirm — Delete Flavor MR"
        confirmVariant="destructive"
      >
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-2">
          <div className="flex gap-3">
            <span className="text-muted-foreground w-24 shrink-0">Flavor</span>
            <span className="font-semibold break-all">{specName}</span>
          </div>
          <div className="flex gap-3">
            <span className="text-muted-foreground w-24 shrink-0">Version</span>
            <span className="font-medium">{spec?.metadata.version ?? "— (does not load)"}</span>
          </div>
          {clustersError ? (
            <div className="flex gap-3" data-testid="spec-delete-clusters-unknown">
              <span className="text-muted-foreground w-24 shrink-0">⚠ Used by</span>
              <span className="font-medium text-status-warning-fg">
                Could not be checked — any cluster that follows this flavor keeps its file, but follows a flavor that is gone
              </span>
            </div>
          ) : clusters && (
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Used by</span>
              <span className="font-medium">
                {followers === 0 ? "No cluster follows this flavor" : `${plural(followers, "cluster")} follow it`}
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground pt-1">
            This action is irreversible once the MR is merged.
          </p>
        </div>
        {clustersError && (
          <ProblemList error={clustersError} title="The clusters following this flavor could not be loaded" />
        )}
        {deleteMutation.error && <ProblemList error={deleteMutation.error} />}
      </ReviewDialog>
    </div>
  );
}
