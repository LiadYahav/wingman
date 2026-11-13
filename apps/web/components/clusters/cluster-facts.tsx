"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { ChevronRight, Clock3, ExternalLink, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PoolLiveState, PoolNodesInline, matchPool } from "@/components/clusters/pool-nodes-inline";
import { ClusterSegmentsLink } from "@/components/clusters/segments-link";
import { Skeleton } from "@/components/ui/skeleton";
import { useClusterNetwork } from "@/lib/network";
import { useClusterNodes } from "@/lib/nodes";
import { cn, formatDate } from "@/lib/utils";
import type { ClusterDetail, ClusterNetworkRead, ClusterValues, NodePoolNodes } from "@/types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="font-medium text-right min-w-0 break-words">{children}</span>
    </div>
  );
}

/** Shown in place of a value automation has not written yet. */
function Pending({ what }: { what: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-status-provisioning/10 px-2 py-0.5 text-xs font-medium text-status-provisioning-fg" title={what}>
      <Clock3 className="h-3 w-3" />pending
    </span>
  );
}

function ownerText(owner: ClusterValues["owner"]): string | null {
  if (!owner) return null;
  const parts = ["merkaz", "anaf", "mador"].map((k) => owner[k]).filter((v) => v !== undefined && v !== null && v !== "");
  return parts.length > 0 ? parts.join(" / ") : null;
}

/** `mastertagAction` sits beside the mastertag: the Upgrade, when upgrades are on (ADR-0055). */
export function ClusterInfoCard({ cluster, mastertagAction }: { cluster: ClusterDetail; mastertagAction?: React.ReactNode }) {
  const values = cluster.values;
  const mastertag = values?.mastertag ?? null;
  const owner = ownerText(values?.owner ?? null);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">Cluster</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Site">{cluster.site}</Row>
        <Row label="MCE">{cluster.mce}</Row>
        <Row label="Mastertag">
          {mastertag ? (
            <span className="inline-flex flex-wrap items-center justify-end gap-1.5">
              <span className="font-mono text-xs">{mastertag}</span>
              {cluster.mce_default_mastertag && cluster.mce_default_mastertag !== mastertag && (
                <span className="text-xs text-muted-foreground font-normal">MCE default {cluster.mce_default_mastertag}</span>
              )}
              {mastertagAction}
            </span>
          ) : "—"}
        </Row>
        {values && <Row label="Platform">{values.platform}</Row>}
        <Row label="Owner">{owner ?? <span className="text-muted-foreground font-normal">—</span>}</Row>
        <Row label="Last change">
          {cluster.metadata.created_by || "—"}
          {cluster.metadata.created_at && (
            <span className="text-muted-foreground font-normal"> · {formatDate(cluster.metadata.created_at)}</span>
          )}
        </Row>
        <div className="pt-1 border-t border-border/50">
          <p className="text-xs text-muted-foreground mb-0.5">File</p>
          {cluster.gitlab_url ? (
            <a
              href={cluster.gitlab_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-start gap-1 font-mono text-xs break-all hover:text-primary transition-colors"
            >
              {cluster.path}
              <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 opacity-60 group-hover:opacity-100" />
            </a>
          ) : (
            <p className="font-mono text-xs break-all">{cluster.path}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * The EPG: the one network fact the file does not carry, from
 * segments-manager's record of the file's segment. Never blocks the card.
 */
function EpgValue({ read, isPending, error }: { read: ClusterNetworkRead | undefined; isPending: boolean; error: unknown }) {
  if (isPending) return <Skeleton className="h-3.5 w-28" />;
  if (error || read?.ledger_error) {
    return (
      <span
        data-testid="network-epg-unknown"
        className="text-xs font-normal text-muted-foreground"
        title={read?.ledger_error ?? "The network could not be read"}
      >
        unknown
      </span>
    );
  }
  if (!read?.epg) return <span className="text-muted-foreground">—</span>;
  return <span data-testid="network-epg" className="font-mono text-xs">{read.epg}</span>;
}

export function HostedClusterCard({ cluster, where }: { cluster: ClusterDetail; where: string }) {
  const network = cluster.values?.network;
  const vlan = network?.vlan_id;
  const net = useClusterNetwork(cluster.name, where);
  const problems = net.data?.problems ?? [];
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">HostedCluster &amp; network</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Name"><span className="font-mono text-xs">{cluster.hosted_cluster.name}</span></Row>
        <Row label="Namespace"><span className="font-mono text-xs">{cluster.hosted_cluster.namespace}</span></Row>
        <Row label="clusterName"><span className="font-mono text-xs">{cluster.hosted_cluster.cluster_name}</span></Row>
        {cluster.values && (
          <>
            <Row label="VLAN">
              {vlan !== null && vlan !== undefined && vlan !== ""
                ? <span data-testid="network-vlan" className="font-mono text-xs">{String(vlan)}</span>
                : <Pending what="The allocate-segment workflow writes vlanId on the MR branch" />}
            </Row>
            <Row label="Segment">
              {network?.segment
                ? <span data-testid="network-segment" className="font-mono text-xs">{network.segment}</span>
                : network?.dhcp_network
                  ? <span className="font-mono text-xs" title="Not a /24 network address">{network.dhcp_network}</span>
                  : <Pending what="The allocate-segment workflow writes dhcp_values on the MR branch" />}
            </Row>
            <Row label="EPG">
              <EpgValue read={net.data} isPending={net.isPending} error={net.error} />
            </Row>
            {problems.length > 0 && (
              <ul data-testid="network-problems" className="space-y-1 rounded-md bg-status-warning/10 px-2.5 py-1.5 text-xs text-status-warning-fg">
                {problems.map((p) => (
                  <li key={p} className="flex items-start gap-1.5">
                    <TriangleAlert className="mt-px h-3 w-3 shrink-0" aria-hidden />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <ClusterSegmentsLink name={cluster.name} external={cluster.segments_manager} />
      </CardContent>
    </Card>
  );
}

/** Where the Overview reads the nodes from; without it the card shows the file only. */
export interface NodePoolsNodes {
  /** The cluster file's name and the `?site=&mce=` query the page reads it with. */
  name: string;
  where: string;
  /** The chart's `clusterName`: a nodepool without a name is `<clusterName>-<infraEnv>` on the MCE. */
  clusterName: string;
  onOpenNodesTab: () => void;
}

type PoolRow =
  | { key: string; kind: "file"; index: number; np: ClusterValues["nodepools"][number]; poolName: string | null; pool: NodePoolNodes | null }
  | { key: string; kind: "mce"; pool: NodePoolNodes };

/** The InfraEnv a NodePool draws on, from its selector in words (`…infraenvs.agent-install.openshift.io=<name>`). */
function infraEnvOf(pool: NodePoolNodes): string | null {
  const selector = pool.agent_selector;
  if (!selector) return null;
  const match = /infraenvs\.agent-install\.openshift\.io=([^,\s]+)/.exec(selector);
  return match ? match[1] : null;
}

/**
 * The cluster's nodepools: those its file lists, and those the MCE reports
 * that the file does not (they come from the site or MCE values the platform
 * layers under the file). Each opens to its nodes on the MCE.
 */
export function NodePoolsCard({ values, nodes }: { values: ClusterValues; nodes?: NodePoolsNodes }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  // Read with the page: a nodepool from the site or MCE values is known only from the MCE.
  // The Nodes tab shares the query, and day1 caches the MCE reads.
  const query = useClusterNodes(nodes?.name ?? "", nodes?.where ?? "", { enabled: Boolean(nodes) });
  const read = query.data;
  const pools = nodes && read && !read.off ? read.data.node_pools : [];
  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const rows: PoolRow[] = values.nodepools.map((np, index) => {
    const poolName = np.name ?? (np.infra_env_name && nodes ? `${nodes.clusterName}-${np.infra_env_name}` : null);
    const pool = nodes ? matchPool(pools, { name: np.name, infraEnv: np.infra_env_name, clusterName: nodes.clusterName }) : null;
    return { key: `file-${index}`, kind: "file", index, np, poolName, pool };
  });
  const matched = new Set(rows.flatMap((r) => (r.kind === "file" && r.pool ? [r.pool.name] : [])));
  for (const pool of pools) {
    if (!matched.has(pool.name)) rows.push({ key: `mce-${pool.name}`, kind: "mce", pool });
  }
  // Tuning only when a nodepool sets it: a column of dashes says nothing
  const showTuning = values.nodepools.some((np) => Boolean(np.tuning_config));
  const columns = 3 + (nodes ? 1 : 0) + (showTuning ? 1 : 0);
  const liveKnown = Boolean(read && !read.off);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">Nodepools ({rows.length})</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {rows.length === 0 ? (
          <p className="text-muted-foreground italic">
            {nodes && query.isPending
              ? "Reading the NodePools from the MCE…"
              : "No nodepools in this file (they may come from the site or MCE values)."}
          </p>
        ) : (
          <div className="rounded-lg border overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground">
                  <th className="text-left font-medium px-3 py-2">Nodepool</th>
                  <th className="text-right font-medium px-3 py-2">Replicas</th>
                  {nodes && <th className="text-left font-medium px-3 py-2">Live</th>}
                  <th className="text-left font-medium px-3 py-2">Configs</th>
                  {showTuning && <th className="text-left font-medium px-3 py-2">Tuning</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {/* eslint-disable-next-line complexity -- size baseline (ADR-0056) */}
                {rows.map((row) => {
                  const isOpen = open.has(row.key);
                  const panelId = `nodepool-nodes-${row.key}`;
                  const label = row.kind === "file" ? row.poolName ?? row.np.infra_env_name ?? "this nodepool" : row.pool.name;
                  const infraEnv = row.kind === "file" ? row.np.infra_env_name : infraEnvOf(row.pool);
                  // The NodePool's name on the MCE: the file's own, or the one the chart derives
                  const poolName = row.kind === "file" ? row.np.name ?? row.poolName : row.pool.name;
                  const testId = row.kind === "file" ? `nodepool-row-${row.index}` : `nodepool-row-mce-${row.pool.name}`;
                  return (
                    <Fragment key={row.key}>
                      <tr
                        data-testid={testId}
                        // The whole row opens the nodes; the chevron button is the keyboard and screen-reader path
                        onClick={nodes ? (e) => { if (!(e.target as HTMLElement).closest("a,button")) toggle(row.key); } : undefined}
                        className={cn(
                          "align-middle transition-colors duration-100",
                          nodes && "cursor-pointer hover:bg-muted/30",
                          isOpen && "bg-muted/20"
                        )}
                      >
                        <td className="px-3 py-2.5">
                          <div className="flex items-start gap-1.5">
                            {nodes && (
                              <button
                                type="button"
                                onClick={() => toggle(row.key)}
                                aria-expanded={isOpen}
                                aria-controls={panelId}
                                aria-label={`${isOpen ? "Hide" : "Show"} the nodes of ${label}`}
                                className="-ml-1 mt-px rounded p-0.5 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                              >
                                <ChevronRight
                                  className={cn(
                                    "h-3.5 w-3.5 transition-transform duration-200 ease-out motion-reduce:transition-none",
                                    isOpen && "rotate-90"
                                  )}
                                  aria-hidden
                                />
                              </button>
                            )}
                            <div className="min-w-0 space-y-0.5">
                              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                <span className="font-mono font-medium text-foreground whitespace-nowrap">{infraEnv ?? "—"}</span>
                                {row.kind === "mce" && (
                                  <span className="whitespace-nowrap rounded-full bg-muted px-2 py-px text-[11px] text-muted-foreground">
                                    from site or MCE values
                                  </span>
                                )}
                              </div>
                              {poolName && (
                                <p className="font-mono text-[11px] text-muted-foreground break-words xl:whitespace-nowrap" title="The NodePool's name on the MCE">
                                  {poolName}
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums whitespace-nowrap">
                          {row.kind === "file"
                            ? row.np.replicas ?? "—"
                            : row.pool.wanted ?? (row.pool.autoscaling ? `${row.pool.autoscaling.min}–${row.pool.autoscaling.max}` : "—")}
                        </td>
                        {nodes && (
                          <td className="px-3 py-2.5 whitespace-nowrap">
                            <PoolLiveState
                              pool={row.pool}
                              loading={row.kind === "file" && query.isPending}
                              known={row.kind === "mce" || liveKnown}
                            />
                          </td>
                        )}
                        {row.kind === "file" ? (
                          <>
                            <td className="px-3 py-2.5">
                              {row.np.configs.length === 0 ? <span className="text-muted-foreground">—</span> : (
                                <div className="flex flex-wrap gap-1">
                                  {row.np.configs.map((c) => (
                                    <span key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono whitespace-nowrap">{c}</span>
                                  ))}
                                </div>
                              )}
                            </td>
                            {showTuning && (
                              <td className="px-3 py-2.5 font-mono break-words">
                                {row.np.tuning_config ? String(row.np.tuning_config) : <span className="text-muted-foreground">—</span>}
                              </td>
                            )}
                          </>
                        ) : (
                          <td className="px-3 py-2.5 text-muted-foreground whitespace-nowrap" colSpan={showTuning ? 2 : 1}>
                            Not in this file
                          </td>
                        )}
                      </tr>
                      {nodes && isOpen && (
                        <tr id={panelId} className="bg-muted/20">
                          <td colSpan={columns} className="px-3 pb-3 pt-0">
                            <div className="animate-in fade-in-0 slide-in-from-top-1 duration-150 motion-reduce:animate-none">
                              <PoolNodesInline
                                read={read}
                                isPending={query.isPending}
                                error={query.error}
                                onRetry={() => void query.refetch()}
                                pool={row.pool}
                                poolName={row.kind === "file" ? row.poolName : row.pool.name}
                                onOpenNodesTab={nodes.onOpenNodesTab}
                              />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SpecCard({ cluster }: { cluster: ClusterDetail }) {
  const { spec_name, spec_version, requested_addons } = cluster.metadata;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">Flavor</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {spec_name ? (
          <>
            <Row label="Name">
              <Link href={`/specs/${encodeURIComponent(spec_name)}`} className="hover:underline">{spec_name}</Link>
            </Row>
            {spec_version && <Row label="Version"><Badge variant="outline">v{spec_version}</Badge></Row>}
            {requested_addons.length > 0 && (
              <div className="pt-1 border-t border-border/50">
                <p className="text-xs text-muted-foreground mb-1">Requested addons</p>
                <div className="flex flex-wrap gap-1.5">
                  {requested_addons.map((a) => {
                    const overrides = Object.keys(a.override_values).length;
                    return (
                      <span key={`${a.team}/${a.name}`} className="rounded-lg border px-2 py-1 text-xs">
                        <span className="font-medium">{a.name}</span>
                        <span className="text-muted-foreground"> · {a.team} · {a.version}</span>
                        {overrides > 0 && <span className="text-primary"> · {overrides} override{overrides !== 1 ? "s" : ""}</span>}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="text-muted-foreground italic">Follows no flavor</p>
        )}
      </CardContent>
    </Card>
  );
}
