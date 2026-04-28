"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, AlertTriangle, RefreshCw, Trash2, Package, Edit2, Eye, X, Wrench, Activity, CheckCircle2, XCircle, HelpCircle, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { ReviewDialog } from "@/components/common/review-dialog";
import { computeLineDiff } from "@/lib/diff";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { MRDetail, ClusterLiveStatus, AddonCatalogEntry, InstalledAddon } from "@/types";

const NO_SPEC_SENTINEL = "(not linked to a cluster spec)";
const hasSpec = (specName: string | undefined) =>
  !!specName && specName !== NO_SPEC_SENTINEL && specName !== "—";

interface AddonSyncEntry {
  addon_name: string;
  team: string;
  reason: "missing" | "version_mismatch";
  expected_version: string;
  installed_version: string;
}

interface ClusterDetail {
  name: string;
  site: string;
  mce: string;
  yaml: string;
  gitlab_url?: string;
  metadata: {
    spec_name: string;
    spec_version: string;
    created_by: string;
    created_at: string;
    variables: Record<string, unknown>;
  };
}

interface DriftResult {
  cluster: string;
  is_drifted: boolean;
  spec_name: string;
  spec_version: string;
  unified_diff: string;
  addon_drift?: AddonSyncEntry[];
}

function ClusterDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const name = params.name as string;
  const site = searchParams.get("site") ?? "";
  const mce = searchParams.get("mce") ?? "";
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();

  const { data: cluster, isLoading } = useQuery<ClusterDetail>({
    queryKey: ["clusters", name, "detail"],
    queryFn: () => api.get<ClusterDetail>(`/api/day1/clusters/${name}?site=${site}&mce=${mce}`),
    enabled: Boolean(site && mce),
    staleTime: 30_000,
  });

  const { data: liveStatus, isLoading: liveStatusLoading } = useQuery<ClusterLiveStatus | null>({
    queryKey: ["clusters", name, "live-status", mce],
    queryFn: async () => {
      try {
        return await api.get<ClusterLiveStatus>(`/api/day1/clusters/${name}/status?mce=${mce}`);
      } catch (err) {
        // 501 = feature disabled (no CLUSTER_STATUS_ENABLED) — silently skip
        if (err instanceof Error && err.message.startsWith("API error 501")) return null;
        throw err;
      }
    },
    enabled: Boolean(mce),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  });

  const { data: drift, isLoading: driftLoading } = useQuery<DriftResult>({
    queryKey: ["clusters", name, "drift"],
    queryFn: () => api.get<DriftResult>(`/api/day1/clusters/${name}/drift?site=${site}&mce=${mce}`),
    enabled: Boolean(site && mce),
    staleTime: 60_000,
  });

  // Prefetch addons data immediately when cluster page loads
  useEffect(() => {
    if (!mce) return;
    // Prefetch installed addons for this cluster (key matches addons page)
    queryClient.prefetchQuery({
      queryKey: ["clusters", name, "addons"],
      queryFn: () => api.get<{ installed: InstalledAddon[] }>(`/api/day2/clusters/${name}/addons?mce=${mce}`),
      staleTime: 30_000,
    });
    // Prefetch addon catalog (key matches addons page)
    queryClient.prefetchQuery({
      queryKey: ["addons", "catalog"],
      queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
      staleTime: 60_000,
    });
  }, [queryClient, name, mce]);

  const [activeTab, setActiveTab] = useState("overview");
  const [editYaml, setEditYaml] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [deleteReviewOpen, setDeleteReviewOpen] = useState(false);
  const [fixingAddon, setFixingAddon] = useState<AddonSyncEntry | null>(null);
  const [yamlSyncOpen, setYamlSyncOpen] = useState(false);

  const addonFixMutation = useMutation({
    mutationFn: (entry: AddonSyncEntry) => {
      const base = `/api/day2/clusters/${name}/addons/${entry.team}/${entry.addon_name}?mce=${mce}`;
      const payload = { version: entry.expected_version, override_values: {} };
      return entry.reason === "missing"
        ? api.post<MRDetail>(base, payload)
        : api.put<MRDetail>(base, payload);
    },
    onSuccess: (mr) => {
      toast.success(`Fix MR #${mr.iid} created: ${mr.title}`);
      setFixingAddon(null);
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
    onError: () => toast.error("Failed to create fix MR"),
  });

  const yamlSyncMutation = useMutation({
    mutationFn: () =>
      api.post<MRDetail>(`/api/day1/clusters/${name}/sync-yaml?site=${site}&mce=${mce}`, {}),
    onSuccess: (mr) => {
      toast.success(`Sync MR #${mr.iid} created: ${mr.title}`);
      setYamlSyncOpen(false);
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
    onError: () => toast.error("Failed to create YAML sync MR"),
  });

  const fixAllMutation = useMutation({
    mutationFn: async () => {
      const results: MRDetail[] = [];
      const addonEntries = drift?.addon_drift ?? [];
      for (const entry of addonEntries) {
        const base = `/api/day2/clusters/${name}/addons/${entry.team}/${entry.addon_name}?mce=${mce}`;
        const payload = { version: entry.expected_version, override_values: {} };
        const mr = entry.reason === "missing"
          ? await api.post<MRDetail>(base, payload)
          : await api.put<MRDetail>(base, payload);
        results.push(mr);
      }
      if (drift?.unified_diff) {
        const mr = await api.post<MRDetail>(`/api/day1/clusters/${name}/sync-yaml?site=${site}&mce=${mce}`, {});
        results.push(mr);
      }
      return results;
    },
    onSuccess: (mrs) => {
      toast.success(`${mrs.length} fix MR${mrs.length !== 1 ? "s" : ""} created`);
      queryClient.invalidateQueries({ queryKey: ["clusters", name, "drift"] });
    },
    onError: () => toast.error("One or more fixes failed — check individual items"),
  });

  const handleStartEdit = () => {
    setEditYaml(cluster?.yaml ?? "");
    setIsEditing(true);
    setActiveTab("yaml");
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    // Stay on yaml tab so user can see the current state
  };

  const deleteMutation = useMutation({
    mutationFn: () => api.del<MRDetail>(`/api/day1/clusters/${name}?site=${site}&mce=${mce}`),
    onSuccess: (mr) => {
      toast.success(`Delete MR #${mr.iid} created: ${mr.title}`);
      setDeleteReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
    },
    onError: () => toast.error("Failed to create delete MR"),
  });

  const modifyMutation = useMutation({
    mutationFn: () =>
      api.patch<MRDetail>(`/api/day1/clusters/${name}?site=${site}&mce=${mce}`, {
        updated_yaml: editYaml,
        change_summary: `Modify cluster ${name} via Wingman`,
      }),
    onSuccess: (mr) => {
      toast.success(`Modify MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      setIsEditing(false);
      queryClient.invalidateQueries({ queryKey: ["clusters", name] });
    },
    onError: () => toast.error("Failed to create modify MR"),
  });

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          {isLoading ? (
            <Skeleton className="h-7 w-48" />
          ) : (
            <h1 className="text-2xl font-bold tracking-tight">{name}</h1>
          )}
        </div>
        {!isLoading && cluster && (
          <div className="flex items-center gap-2">
            {drift?.is_drifted && (
              <Badge variant="outline" className="text-amber-600 border-amber-300 gap-1">
                <AlertTriangle className="h-3 w-3" />
                Drifted
              </Badge>
            )}
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
              href={`/clusters/${name}/addons?site=${site}&mce=${mce}`}
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              <Package className="h-4 w-4 mr-1.5" />Addons
            </Link>

            {/* Edit mode controls — always visible in header when editing */}
            {isAdmin && isEditing ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  <X className="h-4 w-4 mr-1.5" />Cancel
                </button>
                <button
                  onClick={() => setReviewOpen(true)}
                  disabled={editYaml.trim() === (cluster?.yaml ?? "").trim()}
                  title={editYaml.trim() === (cluster?.yaml ?? "").trim() ? "No changes to submit" : undefined}
                  className={buttonVariants({ size: "sm" })}
                >
                  <Eye className="h-4 w-4 mr-1.5" />
                  {editYaml.trim() === (cluster?.yaml ?? "").trim() ? "No Changes" : "Review & Submit"}
                </button>
              </>
            ) : isAdmin ? (
              <>
                <button
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                  onClick={handleStartEdit}
                >
                  <Edit2 className="h-4 w-4 mr-1.5" />Edit
                </button>
                <button
                  className={buttonVariants({ variant: "destructive", size: "sm" })}
                  onClick={() => setDeleteReviewOpen(true)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />Delete
                </button>
              </>
            ) : null}
          </div>
        )}
      </div>

      {isEditing && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-2 text-xs text-primary flex items-center gap-2">
          <Edit2 className="h-3.5 w-3.5 shrink-0" />
          Editing cluster YAML — use <strong>Review &amp; Submit</strong> in the header to create a GitLab MR for approval.
        </div>
      )}

      {!site || !mce ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          Missing site or mce URL parameters. Navigate here from the cluster list.
        </div>
      ) : (
        <Tabs
          value={activeTab}
          onValueChange={(v) => {
            // Block tab switching while editing so Cancel/Submit stays context-appropriate
            if (!isEditing) setActiveTab(v as string);
          }}
        >
          <TabsList>
            <TabsTrigger value="overview" disabled={isEditing}>Overview</TabsTrigger>
            <TabsTrigger value="yaml">YAML</TabsTrigger>
            <TabsTrigger value="drift" disabled={isEditing}>
              Drift
              {drift?.is_drifted && (
                <span className="ml-1.5 inline-flex h-2 w-2 rounded-full bg-amber-500" />
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-4 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-muted-foreground">Cluster Info</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {isLoading ? (
                    Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)
                  ) : (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Site</span>
                        <span className="font-medium">{cluster?.site}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">MCE</span>
                        <span className="font-medium">{cluster?.mce}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Created by</span>
                        <span className="font-medium">{cluster?.metadata.created_by}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Created at</span>
                        <span className="font-medium">
                          {cluster?.metadata.created_at
                            ? new Date(cluster.metadata.created_at).toLocaleDateString("en-GB")
                            : "—"}
                        </span>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-muted-foreground">Spec</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {isLoading ? (
                    Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)
                  ) : cluster?.metadata.spec_name ? (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Name</span>
                        <Link
                          href={`/specs/${cluster.metadata.spec_name}`}
                          className="font-medium hover:underline"
                        >
                          {cluster.metadata.spec_name}
                        </Link>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Version</span>
                        <Badge variant="outline">v{cluster.metadata.spec_version}</Badge>
                      </div>
                    </>
                  ) : (
                    <p className="text-muted-foreground italic">No spec associated</p>
                  )}
                </CardContent>
              </Card>
            </div>

            {cluster?.metadata.variables && Object.keys(cluster.metadata.variables).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-muted-foreground">Variables</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-1.5 text-sm">
                    {Object.entries(cluster.metadata.variables).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="text-muted-foreground min-w-32 shrink-0">{k}</span>
                        <span className="font-mono font-medium break-all">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
            {/* Live cluster status — only shown when CLUSTER_STATUS_ENABLED=true on the backend */}
            {(liveStatusLoading || liveStatus !== undefined) && liveStatus !== null && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-muted-foreground flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5" />
                    Live Status
                    <span className="ml-auto text-[10px] font-normal text-muted-foreground/60">auto-refreshes 60s</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {liveStatusLoading ? (
                    Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)
                  ) : liveStatus?.error ? (
                    <div className="flex items-center gap-2 text-red-600 text-xs">
                      <XCircle className="h-4 w-4 shrink-0" />
                      {liveStatus.error}
                    </div>
                  ) : (
                    <>
                      {/* HostedCluster health */}
                      <div className="flex items-start gap-2">
                        <span className="text-muted-foreground min-w-28 shrink-0">HostedCluster</span>
                        {liveStatus?.hc_problems && liveStatus.hc_problems.length > 0 ? (
                          <div className="space-y-1">
                            {liveStatus.hc_problems.map((p, i) => (
                              <div key={i} className="flex items-start gap-1.5 text-red-600">
                                <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                                <span className="text-xs">{p}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-green-600">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>Healthy</span>
                          </div>
                        )}
                      </div>

                      {/* NodePools */}
                      {liveStatus?.node_pools && liveStatus.node_pools.length > 0 && (
                        <div>
                          <p className="text-muted-foreground mb-1.5">Node Pools</p>
                          <div className="divide-y divide-border rounded-md border overflow-hidden">
                            {liveStatus.node_pools.map((np) => (
                              <div key={np.name} className="flex items-center justify-between px-3 py-2">
                                <span className="font-mono text-xs">{np.name}</span>
                                <div className="flex items-center gap-3 text-xs">
                                  <span className="text-muted-foreground">
                                    {np.ready_replicas}/{np.desired_replicas} ready
                                  </span>
                                  {np.problems.length > 0 ? (
                                    <div className="flex items-center gap-1 text-red-600">
                                      <XCircle className="h-3.5 w-3.5" />
                                      <span>{np.problems[0]}</span>
                                    </div>
                                  ) : (
                                    <div className="flex items-center gap-1 text-green-600">
                                      <CheckCircle2 className="h-3.5 w-3.5" />
                                      <span>OK</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
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
            {!hasSpec(cluster?.metadata.spec_name) ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <HelpCircle className="h-4 w-4 cursor-default" />
                    </TooltipTrigger>
                    <TooltipContent>Drift is not active — cluster is not linked to a spec</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                Drift tracking not active — cluster is not linked to a cluster spec
              </div>
            ) : driftLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : drift?.is_drifted ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm text-amber-600">
                    <AlertTriangle className="h-4 w-4" />
                    Cluster has drifted from spec{" "}
                    <strong>{drift.spec_name}</strong> v{drift.spec_version}
                  </div>
                  {isAdmin && (
                    <button
                      onClick={() => fixAllMutation.mutate()}
                      disabled={fixAllMutation.isPending}
                      className={buttonVariants({ size: "sm" })}
                    >
                      <Wrench className="h-3.5 w-3.5 mr-1.5" />
                      Fix All ({(drift.addon_drift?.length ?? 0) + (drift.unified_diff ? 1 : 0)} issues)
                    </button>
                  )}
                </div>

                {/* Day 2 addon drift */}
                {drift.addon_drift && drift.addon_drift.length > 0 && (
                  <div className="rounded-lg border border-amber-300/50 bg-amber-50/50 dark:bg-amber-950/20 p-4 space-y-2">
                    <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide">
                      Addon Compliance Issues
                    </p>
                    <div className="divide-y divide-amber-200/50 dark:divide-amber-800/30">
                      {drift.addon_drift.map((entry) => (
                        <div key={`${entry.team}/${entry.addon_name}`} className="flex items-center justify-between py-2 text-sm">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-medium">{entry.addon_name}</span>
                            <span className="text-muted-foreground text-xs">{entry.team}</span>
                          </div>
                          <div className="flex items-center gap-3 text-xs">
                            {entry.reason === "missing" ? (
                              <span className="text-red-600 dark:text-red-400">
                                Not installed — spec requires v{entry.expected_version}
                              </span>
                            ) : (
                              <span className="text-amber-700 dark:text-amber-400">
                                v{entry.installed_version} installed → spec requires v{entry.expected_version}
                              </span>
                            )}
                            {isAdmin && (
                              <button
                                onClick={() => setFixingAddon(entry)}
                                className={buttonVariants({ size: "sm", variant: "outline" })}
                              >
                                <Wrench className="h-3 w-3 mr-1" />
                                {entry.reason === "missing" ? "Install" : "Update"}
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Day 1 YAML drift */}
                {drift.unified_diff && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        YAML Drift from Spec
                      </p>
                      {isAdmin && (
                        <button
                          onClick={() => setYamlSyncOpen(true)}
                          className={buttonVariants({ size: "sm", variant: "outline" })}
                        >
                          <Wrench className="h-3.5 w-3.5 mr-1.5" />
                          Sync YAML to Spec
                        </button>
                      )}
                    </div>
                    <YamlDiffViewer diff={drift.unified_diff} />
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-green-600 py-4">
                <RefreshCw className="h-4 w-4" />
                Cluster is in sync with its spec
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}

      {/* Modify review dialog — shows actual diff between original and edited YAML */}
      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Modify Cluster "${name}"`}
        description="Changed lines are highlighted. Green = added, red = removed. Confirming creates a GitLab MR for approval."
        diff={computeLineDiff(cluster?.yaml ?? "", editYaml)}
        onConfirm={() => modifyMutation.mutate()}
        isPending={modifyMutation.isPending}
        confirmLabel="Confirm — Create MR"
      />

      {/* Delete review dialog */}
      <ReviewDialog
        open={deleteReviewOpen}
        onOpenChange={setDeleteReviewOpen}
        title={`Review: Delete Cluster "${name}"`}
        description="This will create a GitLab MR to delete the cluster. The change requires approval before merging."
        onConfirm={() => deleteMutation.mutate()}
        isPending={deleteMutation.isPending}
        confirmLabel="Confirm — Delete Cluster MR"
        confirmVariant="destructive"
      >
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-1">
          <p>Deleting cluster <strong>{name}</strong> from site <strong>{site}</strong> / MCE <strong>{mce}</strong>.</p>
          <p className="text-muted-foreground text-xs">This action is irreversible once the MR is merged.</p>
        </div>
      </ReviewDialog>

      {/* Addon fix dialog */}
      {fixingAddon && (
        <ReviewDialog
          open
          onOpenChange={(open) => { if (!open) setFixingAddon(null); }}
          title={fixingAddon.reason === "missing"
            ? `Fix: Install ${fixingAddon.addon_name}`
            : `Fix: Update ${fixingAddon.addon_name}`}
          description={fixingAddon.reason === "missing"
            ? `Install ${fixingAddon.addon_name} v${fixingAddon.expected_version} as required by the spec. Creates a GitLab MR for approval.`
            : `Update ${fixingAddon.addon_name} from v${fixingAddon.installed_version} to v${fixingAddon.expected_version} as required by the spec. Creates a GitLab MR for approval.`}
          onConfirm={() => addonFixMutation.mutate(fixingAddon)}
          isPending={addonFixMutation.isPending}
          confirmLabel={fixingAddon.reason === "missing" ? "Confirm — Create Install MR" : "Confirm — Create Update MR"}
        >
          <div className="rounded-lg border bg-muted/30 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Addon</span>
              <span className="font-semibold font-mono">{fixingAddon.addon_name}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">Team</span>
              <span className="font-medium">{fixingAddon.team}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-24 shrink-0">
                {fixingAddon.reason === "missing" ? "Version" : "New version"}
              </span>
              <span className="font-medium">v{fixingAddon.expected_version}</span>
            </div>
            {fixingAddon.reason === "version_mismatch" && (
              <p className="text-xs text-muted-foreground pt-1">
                Note: Existing cluster override values will be reset. To preserve them, update via the Addons page instead.
              </p>
            )}
          </div>
        </ReviewDialog>
      )}

      {/* YAML sync dialog */}
      <ReviewDialog
        open={yamlSyncOpen}
        onOpenChange={setYamlSyncOpen}
        title={`Sync "${name}" to Spec`}
        description={`Re-renders the cluster YAML from spec ${drift?.spec_name ?? ""} v${drift?.spec_version ?? ""} using stored variables. Green lines = what spec expects, red lines = what needs to be removed. Creates a GitLab MR for approval.`}
        diff={drift?.unified_diff || undefined}
        onConfirm={() => yamlSyncMutation.mutate()}
        isPending={yamlSyncMutation.isPending}
        confirmLabel="Confirm — Create Sync MR"
      />
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
