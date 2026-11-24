"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Edit2, Lock } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessages, isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReviewDialog } from "@/components/common/review-dialog";
import { ProblemList } from "@/components/common/problem-list";
import { StaleAlert } from "@/components/common/stale-alert";
import { ClusterDriftPanel } from "@/components/clusters/cluster-drift";
import { ClusterHeader } from "@/components/clusters/cluster-header";
import { FixAddonDialog } from "@/components/clusters/fix-addon-dialog";
import { SyncDialog } from "@/components/clusters/sync-dialog";
import { DeleteClusterDialog } from "@/components/clusters/delete-cluster-dialog";
import { ClusterNodes } from "@/components/clusters/cluster-nodes";
import { CommitList, type CommitEntry } from "@/components/clusters/commit-list";
import { LiveStatusCard } from "@/components/clusters/live-status-card";
import { UpgradeAction } from "@/components/clusters/upgrade/upgrade-action";
import { UpgradePanel } from "@/components/clusters/upgrade/upgrade-panel";
import { ClusterInfoCard, HostedClusterCard, NodePoolsCard, SpecCard } from "@/components/clusters/cluster-facts";
import { FileProblems, NamingNotice } from "@/components/clusters/cluster-notices";
import { ClusterFileEditor } from "@/components/clusters/cluster-file-editor";
import { computeFullFileDiff } from "@/lib/diff";
import { clusterQuery } from "@/lib/clusters";
import { offersNodesTab, requestedTab, shownTab } from "@/lib/cluster-tabs";
import { day2Api, day2Keys } from "@/lib/day2";
import { useClusterLiveStatus } from "@/lib/live-status";
import { toastMrOpened } from "@/lib/mr-toast";
import { writeErrorTitle } from "@/lib/write-errors";
import type {
  AddonDrift, CatalogEntry, ChangeResult, ClusterDetail, ClusterDrift, DestinationCharts,
  ModifyClusterRequest,
} from "@/types";

/** A 409 REVISION_CONFLICT: the file moved since this page read it. */
const STALE_FILE =
  "The cluster file changed since you opened it (CI, a platform workflow or another person may have committed to it). Reload to see the current file, then make your change again.";

// eslint-disable-next-line max-lines-per-function, complexity -- size baseline (ADR-0056)
function ClusterDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const name = params.name as string;
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  // The server has no cache, and providers.tsx restores one from localStorage that can land before this
  // Suspense boundary hydrates (React hydrates it after the shell): until mounted, every read below is
  // drawn as the server drew it, loading, so the first render is the server's.
  const mounted = useMounted();

  // site/mce are optional (cluster names are unique); the detail answers both.
  const detail = useQuery<ClusterDetail>({
    queryKey: day1Keys.clusters.detail(name),
    queryFn: () =>
      day1Api.clusters.detail(name, clusterQuery(searchParams.get("site") ?? "", searchParams.get("mce") ?? "")),
    staleTime: 30_000,
    // Edits and deletes send this read's last_commit_id: re-read on every visit
    // (a cached or prefetched copy renders meanwhile), so a merge since is seen.
    refetchOnMount: "always",
    retry: (count, error) => !isApiError(error, 404) && !isApiError(error, 422) && count < 2,
  });
  const cluster = mounted ? detail.data : undefined;
  const isLoading = !mounted || detail.isLoading;
  const { error: detailError, refetch: refetchDetail } = detail;

  const site = cluster?.site ?? searchParams.get("site") ?? "";
  const mce = cluster?.mce ?? searchParams.get("mce") ?? "";
  const where = clusterQuery(site, mce);

  // `null` is status off (501 FEATURE_DISABLED); any other failure is an error to show.
  const { data: liveStatus, isLoading: liveStatusLoading, error: liveStatusError } = useClusterLiveStatus(name, mce);
  const statusOn = liveStatus !== null && liveStatus !== undefined;

  const driftRead = useQuery<ClusterDrift>({
    queryKey: day1Keys.clusters.drift(name),
    queryFn: () => day1Api.clusters.drift(name, where),
    enabled: Boolean(cluster),
    // A sync or install merged by someone else changes it: ask again on every visit,
    // showing the last answer (from the stored cache, too) meanwhile. Not
    // refetchOnMount: the query is still disabled when the page mounts.
    staleTime: 0,
  });
  const drift = mounted ? driftRead.data : undefined;

  // The cluster's charts as day2 lists them (a bare name, narrowed by its MCE):
  // the entry its charts page reads, and what a drift fix writes against.
  const chartsQuery = useMemo(
    () => ({
      queryKey: day2Keys.charts(name, mce),
      queryFn: () => api.get<DestinationCharts>(day2Api.charts(name, mce)),
      staleTime: 30_000,
    }),
    [name, mce]
  );

  // Prefetch the charts page's data
  useEffect(() => {
    if (!mce) return;
    queryClient.prefetchQuery(chartsQuery);
    queryClient.prefetchQuery({
      queryKey: day2Keys.catalog,
      queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
      staleTime: 120_000,
    });
  }, [queryClient, chartsQuery, mce]);

  // `?tab=drift` opens a tab. A viewer never sees the cluster's nodes (ADR-0038): no Nodes tab once the role is known.
  const [requested, setActiveTab] = useState(() => requestedTab(searchParams.get("tab")));
  const nodesTab = offersNodesTab({ mounted, isAdmin });
  const activeTab = shownTab(requested, nodesTab);
  const [editYaml, setEditYaml] = useState("");
  const [editBase, setEditBase] = useState<{ yaml: string; lastCommitId: string } | null>(null);
  const isEditing = editBase !== null;
  const [writeError, setWriteError] = useState<unknown>(null);

  const day1History = useQuery<CommitEntry[]>({
    queryKey: day1Keys.clusters.history(name),
    queryFn: () => day1Api.clusters.history(name, where),
    enabled: Boolean(cluster) && activeTab === "history",
    staleTime: 60_000,
  });

  const day2History = useQuery<CommitEntry[]>({
    queryKey: day2Keys.history(name, mce),
    queryFn: () => api.get(day2Api.history(name, mce)),
    enabled: Boolean(mce) && activeTab === "history",
    staleTime: 60_000,
  });
  const [reviewOpen, setReviewOpen] = useState(false);
  const [deleteReviewOpen, setDeleteReviewOpen] = useState(false);
  const [fixingAddon, setFixingAddon] = useState<AddonDrift | null>(null);
  const [syncOpen, setSyncOpen] = useState(false);

  /**
   * Install a missing spec addon on day2 with the values requested at create,
   * at the add-on's revision (ADR-0025: day2 refuses another version
   * unless it is an emergency pin). A write names the destination by the id
   * day2 resolved the name to.
   */
  const fixAddon = async (entry: AddonDrift): Promise<ChangeResult> => {
    const charts = await queryClient.fetchQuery(chartsQuery);
    const path = day2Api.chart(charts.id, entry.team, entry.addon_name);
    return api.post<ChangeResult>(path, { override_values: entry.override_values });
  };

  const addonFixMutation = useMutation({
    mutationFn: fixAddon,
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Fix MR");
      setFixingAddon(null);
      queryClient.invalidateQueries({ queryKey: day1Keys.clusters.drift(name) });
    },
    onError: (e) => toast.error(writeErrorTitle(e, "Fix failed"), { description: errorMessages(e).join(" · ") }),
  });

  /** One day2 MR per missing addon: the drift tab's Fix all, and what a sync leaves to day2. */
  const fixAllMutation = useMutation({
    mutationFn: async (entries: AddonDrift[]) => {
      const opened: ChangeResult[] = [];
      for (const entry of entries) opened.push(await fixAddon(entry));
      return opened;
    },
    onSuccess: (mrs) => {
      toast.success(`${mrs.length} fix MR${mrs.length !== 1 ? "s" : ""} opened`, {
        action: { label: "Approvals", onClick: () => router.push("/approvals") },
      });
      queryClient.invalidateQueries({ queryKey: day1Keys.clusters.drift(name) });
    },
    onError: (e) => {
      toast.error(writeErrorTitle(e, "A fix failed"), { description: errorMessages(e).join(" · ") });
      queryClient.invalidateQueries({ queryKey: day1Keys.clusters.drift(name) });
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
    queryClient.invalidateQueries({ queryKey: day1Keys.clusters.histories(name) });
  };

  const onWriteError = (e: unknown, what: string) => {
    setReviewOpen(false);
    setDeleteReviewOpen(false);
    setWriteError(e);
    // The page shows the problem itself (below the header); the toast only points at it.
    if (!isApiError(e, "REVISION_CONFLICT") && !isApiError(e, "VALIDATION_ERROR")) {
      toast.error(writeErrorTitle(e, `${what} failed`), { description: "The problem is shown on the page." });
    }
  };

  const deleteMutation = useMutation({
    mutationFn: (confirm: string) => day1Api.clusters.remove(name, where, cluster!.last_commit_id, confirm),
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Delete MR");
      setDeleteReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: day1Keys.clusters.all });
      queryClient.invalidateQueries({ queryKey: day1Keys.approvals.all });
    },
    onError: (e) => onWriteError(e, "Delete"),
  });

  const modifyMutation = useMutation({
    mutationFn: () =>
      day1Api.clusters.modify(name, where, {
        updated_yaml: editYaml,
        change_summary: `Modify cluster ${name} via Wingman`,
        last_commit_id: editBase!.lastCommitId,
      } satisfies ModifyClusterRequest),
    onSuccess: (mr) => {
      toastMrOpened(mr, router.push, "Modify MR");
      setReviewOpen(false);
      setEditBase(null);
      queryClient.invalidateQueries({ queryKey: day1Keys.clusters.one(name) });
      queryClient.invalidateQueries({ queryKey: day1Keys.approvals.all });
    },
    onError: (e) => onWriteError(e, "Modify"),
  });

  const unchanged = editBase !== null && editYaml.trim() === editBase.yaml.trim();
  const automationKeys = cluster?.values?.automation_keys ?? [];

  if (detailError) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-4">
        <ClusterHeader name={name} />
        <ProblemList
          error={detailError}
          title={isApiError(detailError, 404) ? "This cluster does not exist (an MR may have deleted it)" : "The cluster could not be loaded"}
        />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <ClusterHeader
        name={name}
        mce={mce}
        loading={isLoading}
        cluster={cluster}
        drift={drift}
        isAdmin={isAdmin}
        actions={{
          editing: isEditing,
          unchanged,
          onEdit: handleStartEdit,
          onCancelEdit: handleCancelEdit,
          onReview: () => { setWriteError(null); setReviewOpen(true); },
          onDelete: () => { setWriteError(null); setDeleteReviewOpen(true); },
          deleting: deleteMutation.isPending,
        }}
      />

      {Boolean(writeError) && (
        isApiError(writeError, "REVISION_CONFLICT") ? (
          <StaleAlert message={STALE_FILE} onReload={reloadAfterConflict} />
        ) : (
          <ProblemList error={writeError} title={writeErrorTitle(writeError)} />
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
          if (!isEditing) setActiveTab(requestedTab(v as string));
        }}
      >
        <TabsList>
          <TabsTrigger value="overview" disabled={isEditing}>Overview</TabsTrigger>
          {nodesTab && <TabsTrigger value="nodes" disabled={isEditing}>Nodes</TabsTrigger>}
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
              <UpgradePanel name={name} where={where} isAdmin={isAdmin} onOpenNodesTab={isAdmin ? () => setActiveTab("nodes") : undefined} />
              <div className="grid gap-4 sm:grid-cols-2">
                <ClusterInfoCard cluster={cluster} mastertagAction={<UpgradeAction name={name} where={where} isAdmin={isAdmin} />} />
                <HostedClusterCard cluster={cluster} where={where} />
              </div>
              {/* Only when the deployment reads HostedClusters from the hubs; then its nodepools, then its flavor */}
              {liveStatusError ? (
                <div data-testid="live-status-error">
                  <ProblemList error={liveStatusError} title="Live status could not be read from the MCE hub" />
                </div>
              ) : (liveStatusLoading || statusOn) && (
                <LiveStatusCard status={liveStatus ?? undefined} isLoading={liveStatusLoading} />
              )}
              {cluster.values && (
                <NodePoolsCard
                  values={cluster.values}
                  nodes={isAdmin ? {
                    name,
                    where,
                    clusterName: cluster.hosted_cluster.cluster_name,
                    onOpenNodesTab: () => setActiveTab("nodes"),
                  } : undefined}
                />
              )}
              <SpecCard cluster={cluster} />
            </>
          )}
        </TabsContent>

        {/* The servers server-scan places in the cluster, an admin's; read when the tab opens (inactive panels unmount) */}
        {nodesTab && (
          <TabsContent value="nodes" className="mt-4">
            {mounted ? (
              <ClusterNodes name={name} where={where} isAdmin={isAdmin} enabled={activeTab === "nodes"} />
            ) : (
              <Skeleton className="h-40 w-full rounded-xl" />
            )}
          </TabsContent>
        )}

        <TabsContent value="yaml" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-4 space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
                </div>
              ) : isEditing ? (
                <ClusterFileEditor value={editYaml} onChange={setEditYaml} mce={mce} />
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
            isLoading={isLoading || driftRead.isLoading}
            error={driftRead.error}
            isAdmin={isAdmin}
            onFix={setFixingAddon}
            onFixAll={() => fixAllMutation.mutate(drift?.addon_drift ?? [])}
            fixAllPending={fixAllMutation.isPending}
            onSync={() => setSyncOpen(true)}
          />
        </TabsContent>

        <TabsContent value="history" className="mt-4 space-y-6">
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Cluster file (day1 repo)
            </h3>
            <CommitList
              commits={mounted ? day1History.data : undefined}
              isLoading={!mounted || day1History.isLoading}
              error={day1History.error}
              errorTitle="The cluster file's history could not be loaded"
              empty={{
                title: "No history yet",
                description: "No commit to this cluster file was found in the day1 repo.",
                testId: "history-day1-empty",
              }}
            />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Addon values (day2 team repos)
            </h3>
            <CommitList
              commits={mounted ? day2History.data : undefined}
              isLoading={!mounted || day2History.isLoading}
              error={day2History.error}
              errorTitle="The addon values' history could not be loaded"
              empty={{
                title: "No addon value changes yet",
                description: "No team repo has a commit to this cluster's addon values.",
                testId: "history-day2-empty",
              }}
              teamColumn
            />
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

      <DeleteClusterDialog
        open={deleteReviewOpen}
        onOpenChange={setDeleteReviewOpen}
        name={name}
        site={site}
        mce={mce}
        where={where}
        cluster={cluster}
        isAdmin={isAdmin}
        isPending={deleteMutation.isPending}
        onConfirm={(confirm) => deleteMutation.mutate(confirm)}
      />

      {syncOpen && (
        <SyncDialog
          name={name}
          where={where}
          onClose={() => setSyncOpen(false)}
          onInstallAddons={(entries) => fixAllMutation.mutateAsync(entries)}
        />
      )}

      {fixingAddon && (
        <FixAddonDialog
          entry={fixingAddon}
          onClose={() => setFixingAddon(null)}
          onConfirm={() => addonFixMutation.mutate(fixingAddon)}
          pending={addonFixMutation.isPending}
        />
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
