"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2, Package, Edit2, Eye, X, ExternalLink, GitCommitHorizontal, RotateCcw, Lock } from "lucide-react";
import { toast } from "sonner";
import { api, getToken, isApiError } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReviewDialog } from "@/components/common/review-dialog";
import { ProblemList } from "@/components/common/problem-list";
import { DriftBadge } from "@/components/clusters/drift-badge";
import { ClusterDriftPanel } from "@/components/clusters/cluster-drift";
import { LiveStatusCard } from "@/components/clusters/live-status-card";
import {
  ClusterInfoCard, FileProblems, HostedClusterCard, NamingNotice, NodePoolsCard, SpecCard,
} from "@/components/clusters/cluster-facts";
import { computeFullFileDiff } from "@/lib/diff";
import { clusterQuery } from "@/lib/clusters";
import { fetchLiveStatus } from "@/lib/live-status";
import { toastMrOpened } from "@/lib/mr-toast";
import type {
  AddonCatalogEntry, AddonDrift, ClusterDetail, ClusterDrift, ClusterLiveStatus, InstalledAddon, MRDetail,
} from "@/types";

interface CommitEntry {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  web_url: string;
  team?: string;
}

function CommitList({ commits, isLoading, teamColumn }: { commits?: CommitEntry[]; isLoading: boolean; teamColumn?: boolean }) {
  if (isLoading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>;
  if (!commits?.length) return <p className="text-sm text-muted-foreground py-4">No history available.</p>;
  return (
    <div className="rounded-xl border bg-card overflow-hidden divide-y divide-border">
      {commits.map((c) => (
        <div key={c.sha} className="flex items-start gap-3 px-4 py-3">
          <GitCommitHorizontal className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium line-clamp-1">{c.message}</p>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
              <span className="font-mono">{c.short_sha}</span>
              <span>·</span>
              <span>{c.author}</span>
              <span>·</span>
              <span>{new Date(c.date).toLocaleDateString()}</span>
              {teamColumn && c.team && <><span>·</span><span className="text-primary/70">{c.team}</span></>}
            </div>
          </div>
          {c.web_url && (
            <a href={c.web_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary transition-colors shrink-0">
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

/** A 409 REVISION_CONFLICT: the file moved since this page read it. */
const STALE_FILE =
  "The cluster file changed since you opened it (CI or the allocate-segment workflow may have committed to it). Reload to see the current file, then make your change again.";

function ClusterDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const name = params.name as string;
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();

  // site/mce are optional (cluster names are unique); the detail answers both.
  const { data: cluster, isLoading, error: detailError, refetch: refetchDetail } = useQuery<ClusterDetail>({
    queryKey: ["clusters", name, "detail"],
    queryFn: () =>
      api.get<ClusterDetail>(
        `/api/day1/clusters/${encodeURIComponent(name)}${clusterQuery(searchParams.get("site") ?? "", searchParams.get("mce") ?? "")}`
      ),
    staleTime: 30_000,
    // Edits and deletes send this read's last_commit_id: re-read on every visit
    // (a cached or prefetched copy renders meanwhile), so a merge since is seen.
    refetchOnMount: "always",
    retry: (count, error) => !isApiError(error, 404) && !isApiError(error, 422) && count < 2,
  });

  const site = cluster?.site ?? searchParams.get("site") ?? "";
  const mce = cluster?.mce ?? searchParams.get("mce") ?? "";
  const where = clusterQuery(site, mce);
  const path = `/api/day1/clusters/${encodeURIComponent(name)}`;

  const { data: liveStatus, isLoading: liveStatusLoading } = useQuery<ClusterLiveStatus | null>({
    queryKey: ["clusters", name, "live-status", mce],
    queryFn: () => fetchLiveStatus(name, mce),
    enabled: Boolean(mce),
    staleTime: 30_000,
    retry: false,
  });
  const statusOn = liveStatus !== null && liveStatus !== undefined;

  const { data: drift, isLoading: driftLoading, error: driftError } = useQuery<ClusterDrift>({
    queryKey: ["clusters", name, "drift"],
    queryFn: () => api.get<ClusterDrift>(`${path}/drift${where}`),
    enabled: Boolean(cluster),
    staleTime: 60_000,
  });

  // Prefetch the addons page's data (keys match it)
  useEffect(() => {
    if (!mce) return;
    queryClient.prefetchQuery({
      queryKey: ["clusters", name, "addons"],
      queryFn: () => api.get<{ installed: InstalledAddon[] }>(`/api/day2/clusters/${encodeURIComponent(name)}/addons?mce=${encodeURIComponent(mce)}`),
      staleTime: 30_000,
    });
    queryClient.prefetchQuery({
      queryKey: ["addons", "catalog"],
      queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
      staleTime: 60_000,
    });
  }, [queryClient, name, mce]);

  // Server-sent status updates, once the first read shows status is on. fetch()
  // instead of EventSource so the Authorization header can be sent.
  useEffect(() => {
    if (!mce || !statusOn) return;
    const controller = new AbortController();
    const key = ["clusters", name, "live-status", mce];
    const MAX_RETRIES = 5;
    let retries = 0;
    const startStream = async () => {
      try {
        const token = getToken();
        const res = await fetch(`${path}/status/stream?mce=${encodeURIComponent(mce)}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const dataLine = chunk.split("\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            try {
              const frame = JSON.parse(dataLine.slice(6)) as Partial<ClusterLiveStatus>;
              if (frame.cluster_name) {
                queryClient.setQueryData(key, frame as ClusterLiveStatus);
              } else if (frame.error) {
                // An error frame ends the stream; keep the last status and say why.
                queryClient.setQueryData<ClusterLiveStatus | null>(key, (prev) => prev && { ...prev, error: frame.error ?? null });
              }
            } catch { /* ignore malformed frames */ }
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError" && retries < MAX_RETRIES) {
          retries++;
          setTimeout(startStream, Math.min(5_000 * retries, 30_000));
        }
      }
    };
    startStream();
    return () => controller.abort();
  }, [name, mce, path, statusOn, queryClient]);

  const [activeTab, setActiveTab] = useState("overview");
  const [editYaml, setEditYaml] = useState("");
  const [editBase, setEditBase] = useState<{ yaml: string; lastCommitId: string } | null>(null);
  const isEditing = editBase !== null;
  const [writeError, setWriteError] = useState<unknown>(null);

  const { data: clusterHistory, isLoading: clusterHistoryLoading } = useQuery<CommitEntry[]>({
    queryKey: ["clusters", name, "history", "day1"],
    queryFn: () => api.get(`${path}/history${where}`),
    enabled: Boolean(cluster) && activeTab === "history",
    staleTime: 60_000,
  });

  const { data: addonHistory, isLoading: addonHistoryLoading } = useQuery<CommitEntry[]>({
    queryKey: ["clusters", name, "history", "day2"],
    queryFn: () => api.get(`/api/day2/clusters/${encodeURIComponent(name)}/history?mce=${encodeURIComponent(mce)}`),
    enabled: Boolean(mce) && activeTab === "history",
    staleTime: 60_000,
  });
  const [reviewOpen, setReviewOpen] = useState(false);
  const [deleteReviewOpen, setDeleteReviewOpen] = useState(false);
  const [fixingAddon, setFixingAddon] = useState<AddonDrift | null>(null);

  /** Install or update a spec addon on day2 with the values requested at create. */
  const fixAddon = (entry: AddonDrift) => {
    const base = `/api/day2/clusters/${encodeURIComponent(name)}/addons/${encodeURIComponent(entry.team)}/${encodeURIComponent(entry.addon_name)}?mce=${encodeURIComponent(mce)}`;
    const payload = { version: entry.expected_version, override_values: entry.override_values };
    return entry.reason === "missing" ? api.post<MRDetail>(base, payload) : api.put<MRDetail>(base, payload);
  };

  const addonFixMutation = useMutation({
    mutationFn: fixAddon,
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Fix MR");
      setFixingAddon(null);
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
    onError: (e) => toast.error(`Fix failed: ${e.message}`),
  });

  const fixAllMutation = useMutation({
    mutationFn: async () => {
      const opened: MRDetail[] = [];
      for (const entry of drift?.addon_drift ?? []) opened.push(await fixAddon(entry));
      return opened;
    },
    onSuccess: (mrs) => {
      toast.success(`${mrs.length} fix MR${mrs.length !== 1 ? "s" : ""} opened`, {
        action: { label: "Approvals", onClick: () => router.push("/approvals") },
      });
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
    onError: (e) => {
      toast.error(`A fix failed: ${e.message}`);
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
  });

  const handleStartEdit = () => {
    if (!cluster) return;
    setEditYaml(cluster.yaml);
    setEditBase({ yaml: cluster.yaml, lastCommitId: cluster.last_commit_id });
    setWriteError(null);
    setActiveTab("yaml");
  };

  const handleCancelEdit = () => {
    setEditBase(null);
    setWriteError(null);
  };

  /** After a 409: drop the stale edit and read the file again. */
  const reloadAfterConflict = async () => {
    setEditBase(null);
    setWriteError(null);
    await refetchDetail();
    queryClient.invalidateQueries({ queryKey: ["clusters", name, "history"] });
  };

  const onWriteError = (e: unknown, what: string) => {
    setReviewOpen(false);
    setDeleteReviewOpen(false);
    setWriteError(e);
    if (!isApiError(e, "REVISION_CONFLICT") && !isApiError(e, "VALIDATION_ERROR")) {
      toast.error(`${what} failed: ${(e as Error).message}`);
    }
  };

  const deleteMutation = useMutation({
    mutationFn: () => {
      const lastCommit = `last_commit_id=${encodeURIComponent(cluster!.last_commit_id)}`;
      return api.del<MRDetail>(`${path}${where ? `${where}&` : "?"}${lastCommit}`);
    },
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Delete MR");
      setDeleteReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: (e) => onWriteError(e, "Delete"),
  });

  const modifyMutation = useMutation({
    mutationFn: () =>
      api.patch<MRDetail>(`${path}${where}`, {
        updated_yaml: editYaml,
        change_summary: `Modify cluster ${name} via Wingman`,
        last_commit_id: editBase!.lastCommitId,
      }),
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Modify MR");
      setReviewOpen(false);
      setEditBase(null);
      queryClient.invalidateQueries({ queryKey: ["clusters", name] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: (e) => onWriteError(e, "Modify"),
  });

  const unchanged = editBase !== null && editYaml.trim() === editBase.yaml.trim();
  const automationKeys = cluster?.values?.automation_keys ?? [];

  if (detailError) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-4">
        <div className="flex items-center gap-3">
          <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold tracking-tight break-all">{name}</h1>
        </div>
        <ProblemList
          error={detailError}
          title={isApiError(detailError, 404) ? "This cluster does not exist (an MR may have deleted it)" : "The cluster could not be loaded"}
        />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3 flex-wrap">
        <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1 min-w-0">
          {isLoading ? (
            <Skeleton className="h-7 w-48" />
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight break-all">{name}</h1>
              {drift && drift.state !== "not_linked" && <DriftBadge state={drift.state} error={drift.error} />}
            </div>
          )}
        </div>
        {!isLoading && cluster && (
          <div className="flex items-center gap-2 flex-wrap">
            {cluster.gitlab_url && (
              <a
                href={cluster.gitlab_url}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
                title="View in GitLab"
              >
                <ExternalLink className="h-4 w-4 mr-1.5" />GitLab
              </a>
            )}
            <Link
              href={`/clusters/${encodeURIComponent(name)}/addons${where}`}
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              <Package className="h-4 w-4 mr-1.5" />Addons
            </Link>

            {isAdmin && isEditing ? (
              <>
                <button onClick={handleCancelEdit} className={buttonVariants({ variant: "outline", size: "sm" })}>
                  <X className="h-4 w-4 mr-1.5" />Cancel
                </button>
                <button
                  onClick={() => { setWriteError(null); setReviewOpen(true); }}
                  disabled={unchanged}
                  title={unchanged ? "No changes to submit" : undefined}
                  className={buttonVariants({ size: "sm" })}
                >
                  <Eye className="h-4 w-4 mr-1.5" />
                  {unchanged ? "No Changes" : "Review & Submit"}
                </button>
              </>
            ) : isAdmin ? (
              <>
                <button className={buttonVariants({ variant: "outline", size: "sm" })} onClick={handleStartEdit}>
                  <Edit2 className="h-4 w-4 mr-1.5" />Edit
                </button>
                <button
                  className={buttonVariants({ variant: "destructive", size: "sm" })}
                  onClick={() => { setWriteError(null); setDeleteReviewOpen(true); }}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />Delete
                </button>
              </>
            ) : null}
          </div>
        )}
      </div>

      {Boolean(writeError) && (
        isApiError(writeError, "REVISION_CONFLICT") ? (
          <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
            <p className="text-status-warning-fg">{STALE_FILE}</p>
            <button onClick={reloadAfterConflict} className={buttonVariants({ variant: "outline", size: "sm" })}>
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Reload
            </button>
          </div>
        ) : (
          <ProblemList error={writeError} title="The change was refused" />
        )
      )}

      {isEditing && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-2.5 text-xs text-primary space-y-1">
          <p className="flex items-center gap-2">
            <Edit2 className="h-3.5 w-3.5 shrink-0" />
            Editing the cluster file — use <strong>Review &amp; Submit</strong> to open a merge request.
          </p>
          {automationKeys.length > 0 && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Lock className="h-3.5 w-3.5 shrink-0" />
              Automation owns <span className="font-mono">{automationKeys.join(", ")}</span>; keep them as they are.
            </p>
          )}
        </div>
      )}

      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          // Tabs stay on the file while editing, so Cancel/Submit keep their context
          if (!isEditing) setActiveTab(v as string);
        }}
      >
        <TabsList>
          <TabsTrigger value="overview" disabled={isEditing}>Overview</TabsTrigger>
          <TabsTrigger value="yaml">YAML</TabsTrigger>
          <TabsTrigger value="drift" disabled={isEditing}>
            Drift
            {drift?.state === "drifted" && <span className="ml-1.5 inline-flex h-2 w-2 rounded-full bg-status-warning" />}
          </TabsTrigger>
          <TabsTrigger value="history" disabled={isEditing}>History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          {isLoading || !cluster ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-xl" />)}
            </div>
          ) : (
            <>
              <FileProblems problems={cluster.problems} />
              <NamingNotice cluster={cluster} />
              <div className="grid gap-4 sm:grid-cols-2">
                <ClusterInfoCard cluster={cluster} />
                <HostedClusterCard cluster={cluster} />
              </div>
              {cluster.values && <NodePoolsCard values={cluster.values} />}
              <SpecCard cluster={cluster} />
              {/* Only when the deployment reads HostedClusters from the hubs */}
              {(liveStatusLoading || statusOn) && (
                <LiveStatusCard status={liveStatus ?? undefined} isLoading={liveStatusLoading} />
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="yaml" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-4 space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
                </div>
              ) : isEditing ? (
                <textarea
                  aria-label="Cluster file"
                  className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[500px] focus:outline-none resize-y leading-5 rounded-md"
                  value={editYaml}
                  onChange={(e) => setEditYaml(e.target.value)}
                  spellCheck={false}
                />
              ) : (
                <pre className="overflow-auto p-4 text-xs font-mono bg-zinc-950 text-zinc-200 rounded-md leading-5 max-h-[600px]">
                  {cluster?.yaml}
                </pre>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="drift" className="mt-4 space-y-4">
          <ClusterDriftPanel
            drift={drift}
            isLoading={isLoading || driftLoading}
            error={driftError}
            isAdmin={isAdmin}
            onFix={setFixingAddon}
            onFixAll={() => fixAllMutation.mutate()}
            fixAllPending={fixAllMutation.isPending}
          />
        </TabsContent>

        <TabsContent value="history" className="mt-4 space-y-6">
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Cluster file (day1 repo)
            </h3>
            <CommitList commits={clusterHistory} isLoading={clusterHistoryLoading} />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Addon values (day2 team repos)
            </h3>
            <CommitList commits={addonHistory} isLoading={addonHistoryLoading} teamColumn />
          </div>
        </TabsContent>
      </Tabs>

      {/* Modify review: the edit against the file it started from */}
      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Modify Cluster "${name}"`}
        description="Full file shown — green lines added, red lines removed. If the file changed since you started editing, the MR is refused and nothing is overwritten."
        diff={editBase ? computeFullFileDiff(editBase.yaml, editYaml) : undefined}
        onConfirm={() => modifyMutation.mutate()}
        isPending={modifyMutation.isPending}
        confirmLabel="Confirm — Create MR"
        size="xl"
      />

      <ReviewDialog
        open={deleteReviewOpen}
        onOpenChange={setDeleteReviewOpen}
        title={`Review: Delete Cluster "${name}"`}
        description="This opens a GitLab MR that removes the cluster file. The change requires approval before merging."
        onConfirm={() => deleteMutation.mutate()}
        isPending={deleteMutation.isPending}
        confirmLabel="Confirm — Delete Cluster MR"
        confirmVariant="destructive"
      >
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-1">
          <p className="break-words">Deleting cluster <strong>{name}</strong> from site <strong>{site}</strong> / MCE <strong>{mce}</strong>.</p>
          {cluster && <p className="font-mono text-xs text-muted-foreground break-all">{cluster.path}</p>}
          <p className="text-muted-foreground text-xs">Once merged, ArgoCD removes the HostedCluster.</p>
        </div>
      </ReviewDialog>

      {fixingAddon && (
        <ReviewDialog
          open
          onOpenChange={(open) => { if (!open) setFixingAddon(null); }}
          title={fixingAddon.reason === "missing" ? `Fix: Install ${fixingAddon.addon_name}` : `Fix: Update ${fixingAddon.addon_name}`}
          description={fixingAddon.reason === "missing"
            ? `Install ${fixingAddon.addon_name} ${fixingAddon.expected_version} as the spec requires, with the values requested at create. Opens a GitLab MR for approval.`
            : `Update ${fixingAddon.addon_name} from ${fixingAddon.installed_version} to ${fixingAddon.expected_version} as the spec requires. Opens a GitLab MR for approval.`}
          onConfirm={() => addonFixMutation.mutate(fixingAddon)}
          isPending={addonFixMutation.isPending}
          confirmLabel={fixingAddon.reason === "missing" ? "Confirm — Create Install MR" : "Confirm — Create Update MR"}
        >
          <div className="rounded-lg border bg-muted/30 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Addon</span>
              <span className="font-semibold font-mono break-all">{fixingAddon.addon_name}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Team</span>
              <span className="font-medium">{fixingAddon.team}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">
                {fixingAddon.reason === "missing" ? "Version" : "New version"}
              </span>
              <span className="font-medium">{fixingAddon.expected_version}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Values</span>
              <span className="font-medium">
                {Object.keys(fixingAddon.override_values).length > 0
                  ? `${Object.keys(fixingAddon.override_values).length} requested at create`
                  : "chart and team defaults"}
              </span>
            </div>
            {fixingAddon.reason === "version_mismatch" && (
              <p className="text-xs text-muted-foreground pt-1">
                The cluster&apos;s values file is replaced with the values requested at create. To keep later edits, update the addon from the Addons page instead.
              </p>
            )}
          </div>
        </ReviewDialog>
      )}
    </div>
  );
}

export default function ClusterDetailPage() {
  return (
    <Suspense>
      <ClusterDetailContent />
    </Suspense>
  );
}
