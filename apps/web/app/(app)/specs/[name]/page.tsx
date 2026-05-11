"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2, Edit2, Server, AlertTriangle, CheckCircle2, ExternalLink, GitCommitHorizontal } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ReviewDialog } from "@/components/common/review-dialog";
import type { ClusterSpec, MRDetail, SpecCommit } from "@/types";

interface SpecCluster {
  name: string;
  site: string;
  mce: string;
  phase: string;
  is_drifted: boolean;
}

interface SpecDriftResult {
  cluster: string;
  site: string;
  mce: string;
  is_drifted: boolean;
  spec_version: string;
  unified_diff: string;
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground shrink-0 w-32">{label}</span>
      <span className="text-sm font-medium text-right">{value}</span>
    </div>
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

  const { data: spec, isLoading } = useQuery<ClusterSpec>({
    queryKey: ["specs", specName],
    queryFn: () => api.get<ClusterSpec>(`/api/day1/specs/${specName}`),
    staleTime: 60_000,
  });

  const { data: clusters, isLoading: clustersLoading } = useQuery<SpecCluster[]>({
    queryKey: ["specs", specName, "clusters"],
    queryFn: () => api.get<SpecCluster[]>(`/api/day1/specs/${specName}/clusters`),
    enabled: activeTab === "clusters" || activeTab === "drift",
    staleTime: 30_000,  // Cache for 30 seconds
    gcTime: 2 * 60_000, // Keep in cache for 2 minutes
  });

  const { data: driftResults, isLoading: driftLoading } = useQuery<SpecDriftResult[]>({
    queryKey: ["specs", specName, "drift"],
    queryFn: () => api.get<SpecDriftResult[]>(`/api/day1/specs/${specName}/drift`),
    enabled: activeTab === "drift",
    staleTime: 60_000,
  });

  const { data: history, isLoading: historyLoading } = useQuery<SpecCommit[]>({
    queryKey: ["spec-history", specName],
    queryFn: () => api.get<SpecCommit[]>(`/api/day1/specs/${specName}/history`),
    enabled: activeTab === "history",
    staleTime: 60_000,
  });

  const { data: specAtSha, isLoading: specAtShaLoading } = useQuery<string>({
    queryKey: ["spec-at-sha", specName, selectedSha],
    queryFn: () => api.getText(`/api/day1/specs/${specName}/at/${selectedSha}`),
    enabled: !!selectedSha && activeTab === "history",
    staleTime: Infinity,
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.del<MRDetail>(`/api/day1/specs/${specName}`),
    onSuccess: (mr) => {
      toast.success(`Delete MR #${mr.iid} created: ${mr.title}`);
      setDeleteReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["specs"] });
      router.push("/specs");
    },
    onError: () => toast.error("Failed to create delete MR"),
  });

  const tabs = [
    { id: "overview" as const, label: "Overview" },
    { id: "clusters" as const, label: `Clusters${clusters ? ` (${clusters.length})` : ""}` },
    { id: "drift" as const, label: "Drift" },
    { id: "history" as const, label: "History" },
  ];

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/specs" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          {isLoading ? <Skeleton className="h-7 w-48" /> : (
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
            >
              {spec?.metadata.name}
            </h1>
          )}
          {spec?.metadata.description && (
            <p className="text-sm text-muted-foreground mt-0.5">{spec.metadata.description}</p>
          )}
        </div>
        {!isLoading && spec && isAdmin && (
          <div className="flex items-center gap-2">
            <Link
              href={`/specs/${specName}/edit`}
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              <Edit2 className="h-3.5 w-3.5 mr-1.5" />Edit
            </Link>
            <button
              className={buttonVariants({ variant: "destructive", size: "sm" })}
              onClick={() => setDeleteReviewOpen(true)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1.5" />Delete
            </button>
          </div>
        )}
      </div>

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
      {activeTab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="bg-card rounded-xl border shadow-sm p-5">
            <h2 className="text-sm font-semibold mb-3">Metadata</h2>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-full mb-2" />)
            ) : spec && (
              <>
                <InfoRow label="Name" value={spec.metadata.name} />
                <InfoRow label="Version" value={
                  <span className="rounded-full px-2 py-0.5 text-xs bg-primary/8 text-primary font-medium">
                    v{spec.metadata.version}
                  </span>
                } />
                {spec.metadata.labels && Object.entries(spec.metadata.labels).map(([k, v]) => (
                  <InfoRow key={k} label={k} value={v} />
                ))}
              </>
            )}
          </div>

          <div className="bg-card rounded-xl border shadow-sm p-5">
            <h2 className="text-sm font-semibold mb-3">Variables ({spec?.spec.day1.variables.length ?? "…"})</h2>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full mb-2" />)
            ) : (
              <div className="space-y-1">
                {spec?.spec.day1.variables.map((v) => (
                  <div key={v.name} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                    <div>
                      <span className="text-sm font-mono">{v.name}</span>
                      {v.required && <span className="ml-1 text-xs text-destructive">*</span>}
                    </div>
                    <span className="text-xs text-muted-foreground">{v.type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {spec && spec.spec.day2.addons.length > 0 && (
            <div className="bg-card rounded-xl border shadow-sm p-5 lg:col-span-2">
              <h2 className="text-sm font-semibold mb-3">Addons ({spec.spec.day2.addons.length})</h2>
              <div className="flex flex-wrap gap-2">
                {spec.spec.day2.addons.map((addon) => (
                  <div key={`${addon.team}/${addon.name}`} className="rounded-lg border px-3 py-2 text-sm">
                    <span className="font-medium">{addon.name}</span>
                    <span className="text-muted-foreground ml-1.5 text-xs">{addon.team} · v{addon.version}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Clusters tab */}
      {activeTab === "clusters" && (
        <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Cluster</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Site / MCE</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Drift</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {clustersLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>{Array.from({ length: 4 }).map((_, j) => (
                      <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                    ))}</tr>
                  ))
                : clusters?.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">
                        No clusters created from this spec yet.
                      </td>
                    </tr>
                  )
                : clusters?.map((c) => (
                    <tr key={c.name} className="hover:bg-primary/[0.03] transition-colors">
                      <td className="px-4 py-3">
                        <Link
                          href={`/clusters/${c.name}?site=${c.site}&mce=${c.mce}`}
                          className="font-semibold hover:text-primary transition-colors flex items-center gap-1"
                        >
                          {c.name}
                          <ExternalLink className="h-3 w-3 text-muted-foreground" />
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{c.site} / {c.mce}</td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-muted-foreground">{c.phase}</span>
                      </td>
                      <td className="px-4 py-3">
                        {c.is_drifted ? (
                          <span className="inline-flex items-center gap-1 text-xs text-[#fdab3d]">
                            <AlertTriangle className="h-3 w-3" />Drifted
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-[#00c875]">
                            <CheckCircle2 className="h-3 w-3" />In sync
                          </span>
                        )}
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
            <Skeleton className="h-32 w-full rounded-xl" />
          ) : driftResults?.length === 0 ? (
            <div className="bg-card rounded-xl border shadow-sm p-8 text-center">
              <CheckCircle2 className="h-8 w-8 text-[#00c875] mx-auto mb-2" />
              <p className="text-sm font-semibold">All clusters in sync</p>
              <p className="text-xs text-muted-foreground mt-1">No drift detected across any clusters using this spec</p>
            </div>
          ) : (
            driftResults?.map((r) => (
              <div key={r.cluster} className="bg-card rounded-xl border shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-muted-foreground" />
                    <Link
                      href={`/clusters/${r.cluster}?site=${r.site}&mce=${r.mce}`}
                      className="font-semibold hover:text-primary transition-colors"
                    >
                      {r.cluster}
                    </Link>
                  </div>
                  {r.is_drifted ? (
                    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-[#fdab3d]/10 text-[#c07800] dark:text-[#fdab3d]">
                      <AlertTriangle className="h-3 w-3" />Drifted
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-[#00c875]/10 text-[#007038] dark:text-[#00c875]">
                      <CheckCircle2 className="h-3 w-3" />In sync
                    </span>
                  )}
                </div>
                {r.is_drifted && r.unified_diff && (
                  <pre className="text-xs font-mono bg-muted/50 rounded-lg p-3 overflow-auto max-h-64 leading-5">
                    {r.unified_diff}
                  </pre>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* History tab */}
      {activeTab === "history" && (
        <div className="flex gap-4 min-h-[400px]">
          {/* Commit list */}
          <div className="w-80 shrink-0 bg-card rounded-xl border shadow-sm overflow-hidden flex flex-col">
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
              ) : history?.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8 px-4">No history available.</p>
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
                        <span>{new Date(commit.date).toLocaleDateString()}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* YAML viewer */}
          <div className="flex-1 bg-card rounded-xl border shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b bg-muted/30 flex items-center justify-between">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                {selectedSha
                  ? `Spec at ${history?.find((c) => c.sha === selectedSha)?.short_sha ?? selectedSha.slice(0, 8)}`
                  : "Spec content"}
              </h2>
              {selectedSha && (
                <span className="text-xs text-muted-foreground font-mono">{selectedSha.slice(0, 8)}</span>
              )}
            </div>
            <div className="flex-1 overflow-auto p-4">
              {!selectedSha ? (
                <p className="text-sm text-muted-foreground text-center py-12">
                  Select a commit to view the spec at that point in time.
                </p>
              ) : specAtShaLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <Skeleton key={i} className="h-4 w-full" />
                  ))}
                </div>
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
        title={`Review: Delete Spec "${specName}"`}
        description="This will create a GitLab MR to delete this spec. The change requires approval before merging."
        onConfirm={() => deleteMutation.mutate()}
        isPending={deleteMutation.isPending}
        confirmLabel="Confirm — Delete Spec MR"
        confirmVariant="destructive"
      >
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-2">
          <div className="flex gap-3">
            <span className="text-muted-foreground w-24 shrink-0">Spec</span>
            <span className="font-semibold">{spec?.metadata.name}</span>
          </div>
          <div className="flex gap-3">
            <span className="text-muted-foreground w-24 shrink-0">Version</span>
            <span className="font-medium">v{spec?.metadata.version}</span>
          </div>
          {clusters && clusters.length > 0 && (
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">⚠ Used by</span>
              <span className="font-medium text-amber-600">
                {clusters.length} cluster{clusters.length !== 1 ? "s" : ""} — they will lose their spec reference
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground pt-1">
            This action is irreversible once the MR is merged.
          </p>
        </div>
      </ReviewDialog>
    </div>
  );
}
