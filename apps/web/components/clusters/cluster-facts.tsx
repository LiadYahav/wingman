"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, Clock3, Copy, ExternalLink, FileWarning, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PoolLiveState, PoolNodesInline, matchPool } from "@/components/clusters/pool-nodes-inline";
import { useClusterNodes } from "@/lib/nodes";
import { cn, formatDate } from "@/lib/utils";
import type { ClusterDetail, ClusterValues, NodePoolNodes, SegmentsManagerLinks } from "@/types";

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

/** A file that does not parse: the problems, in full. */
export function FileProblems({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null;
  return (
    <div role="alert" className="rounded-xl border border-status-error/30 bg-status-error/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold text-status-error-fg">
        <FileWarning className="h-4 w-4 shrink-0" />The cluster file does not parse
      </p>
      <ul className="mt-2 list-disc pl-6 space-y-0.5 text-status-error-fg/90">
        {problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">Its values cannot be shown; the YAML tab has the raw file.</p>
    </div>
  );
}

/** A name off `ocp4-<env>-<name>-<site>[-<seq>]` is flagged, never hidden. */
export function NamingNotice({ cluster }: { cluster: ClusterDetail }) {
  if (cluster.naming.follows_convention) return null;
  return (
    <div className="rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold text-status-warning-fg">
        <TriangleAlert className="h-4 w-4 shrink-0" />Off the naming convention
      </p>
      <ul className="mt-2 list-disc pl-6 space-y-0.5 text-muted-foreground">
        {cluster.naming.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Existing clusters keep working; Wingman only refuses such names for new clusters.
      </p>
    </div>
  );
}

function ownerText(owner: ClusterValues["owner"]): string | null {
  if (!owner) return null;
  const parts = ["merkaz", "anaf", "mador"].map((k) => owner[k]).filter((v) => v !== undefined && v !== null && v !== "");
  return parts.length > 0 ? parts.join(" / ") : null;
}

export function ClusterInfoCard({ cluster }: { cluster: ClusterDetail }) {
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

/** Copies `text`; the icon turns to a check for a moment, and a screen reader hears it. */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), 1500);
    return () => clearTimeout(timer);
  }, [state]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      // No clipboard (not a secure context, or denied): the name stays selectable
      setState("failed");
    }
  };
  const Icon = state === "copied" ? Check : Copy;
  return (
    <>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={label}
        title={state === "failed" ? "Could not copy: select the name instead" : label}
        className="rounded p-0.5 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <Icon className={cn("h-3.5 w-3.5", state === "copied" && "text-status-ready-fg")} aria-hidden />
      </button>
      <span role="status" className="sr-only">
        {state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : ""}
      </span>
    </>
  );
}

/**
 * segments-manager's UI opens no single cluster, so the link opens the UI and
 * names what to search for there: the file stem, its `cluster_name`. Day1
 * builds both URLs (`segments_manager`); the page only shows them.
 */
function SegmentsManagerLink({ name, links }: { name: string; links: SegmentsManagerLinks }) {
  return (
    <div data-testid="segments-manager" className="pt-2 border-t border-border/50 space-y-1">
      <a
        href={links.url}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-center gap-1 font-medium hover:text-primary transition-colors"
      >
        Segments Manager
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden />
      </a>
      <p className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
        search for <span data-testid="segments-manager-search" className="font-mono text-foreground break-all">{name}</span>
        <CopyButton text={name} label={`Copy ${name}`} />
      </p>
      <a
        href={links.search_url}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
      >
        this cluster&apos;s segment (JSON)
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden />
      </a>
    </div>
  );
}

export function HostedClusterCard({ cluster }: { cluster: ClusterDetail }) {
  const network = cluster.values?.network;
  const vlan = network?.vlan_id;
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
                ? <span className="font-mono text-xs">{String(vlan)}</span>
                : <Pending what="The allocate-segment workflow writes vlanId on the MR branch" />}
            </Row>
            <Row label="DHCP network">
              {network?.dhcp_network
                ? <span className="font-mono text-xs">{network.dhcp_network}</span>
                : <Pending what="The allocate-segment workflow writes dhcp_values on the MR branch" />}
            </Row>
          </>
        )}
        {cluster.segments_manager && <SegmentsManagerLink name={cluster.name} links={cluster.segments_manager} />}
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
  const columns = nodes ? 6 : 5;
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
                  <th className="text-left font-medium px-3 py-2">InfraEnv</th>
                  <th className="text-left font-medium px-3 py-2">Name</th>
                  <th className="text-right font-medium px-3 py-2">Replicas</th>
                  {nodes && <th className="text-left font-medium px-3 py-2">Live</th>}
                  <th className="text-left font-medium px-3 py-2">Configs</th>
                  <th className="text-left font-medium px-3 py-2">Tuning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((row) => {
                  const isOpen = open.has(row.key);
                  const panelId = `nodepool-nodes-${row.key}`;
                  const label = row.kind === "file" ? row.poolName ?? row.np.infra_env_name ?? "this nodepool" : row.pool.name;
                  const infraEnv = row.kind === "file" ? row.np.infra_env_name : infraEnvOf(row.pool);
                  const testId = row.kind === "file" ? `nodepool-row-${row.index}` : `nodepool-row-mce-${row.pool.name}`;
                  return (
                    <Fragment key={row.key}>
                      <tr data-testid={testId} className={cn(isOpen && "bg-muted/20")}>
                        <td className="px-3 py-2 font-mono break-all">
                          <div className="flex items-center gap-1.5">
                            {nodes && (
                              <button
                                type="button"
                                onClick={() => toggle(row.key)}
                                aria-expanded={isOpen}
                                aria-controls={panelId}
                                aria-label={`${isOpen ? "Hide" : "Show"} the nodes of ${label}`}
                                className="-ml-1 rounded p-0.5 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                              >
                                <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", isOpen && "rotate-90")} aria-hidden />
                              </button>
                            )}
                            <span>{infraEnv ?? "—"}</span>
                          </div>
                        </td>
                        {row.kind === "file" ? (
                          <>
                            <td className="px-3 py-2 font-mono break-all text-muted-foreground">{row.np.name ?? "derived"}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{row.np.replicas ?? "—"}</td>
                            {nodes && (
                              <td className="px-3 py-2">
                                <PoolLiveState pool={row.pool} loading={query.isPending} known={liveKnown} />
                              </td>
                            )}
                            <td className="px-3 py-2">
                              {row.np.configs.length === 0 ? <span className="text-muted-foreground">—</span> : (
                                <div className="flex flex-wrap gap-1">
                                  {row.np.configs.map((c) => (
                                    <span key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono break-all">{c}</span>
                                  ))}
                                </div>
                              )}
                            </td>
                            <td className="px-3 py-2 font-mono break-all">
                              {row.np.tuning_config ? String(row.np.tuning_config) : <span className="text-muted-foreground">—</span>}
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="px-3 py-2 font-mono break-all text-muted-foreground">
                              {row.pool.name}
                              <span className="ml-1.5 whitespace-nowrap rounded bg-muted px-1.5 py-0.5 font-sans text-[11px] text-muted-foreground">
                                from site or MCE values
                              </span>
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {row.pool.wanted ?? (row.pool.autoscaling ? `${row.pool.autoscaling.min}–${row.pool.autoscaling.max}` : "—")}
                            </td>
                            <td className="px-3 py-2">
                              <PoolLiveState pool={row.pool} loading={false} known />
                            </td>
                            <td className="px-3 py-2 text-muted-foreground" colSpan={2}>Not in this file</td>
                          </>
                        )}
                      </tr>
                      {nodes && isOpen && (
                        <tr id={panelId} className="bg-muted/20">
                          <td colSpan={columns} className="px-3 pb-3 pt-0">
                            <PoolNodesInline
                              read={read}
                              isPending={query.isPending}
                              error={query.error}
                              onRetry={() => void query.refetch()}
                              pool={row.pool}
                              poolName={row.kind === "file" ? row.poolName : row.pool.name}
                              onOpenNodesTab={nodes.onOpenNodesTab}
                            />
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
