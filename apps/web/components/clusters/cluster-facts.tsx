import Link from "next/link";
import { Clock3, ExternalLink, FileWarning, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import type { ClusterDetail, ClusterValues } from "@/types";

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
      </CardContent>
    </Card>
  );
}

export function NodePoolsCard({ values }: { values: ClusterValues }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">Nodepools ({values.nodepools.length})</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {values.nodepools.length === 0 ? (
          <p className="text-muted-foreground italic">No nodepools in this file (they may come from the site or MCE values).</p>
        ) : (
          <div className="rounded-lg border overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground">
                  <th className="text-left font-medium px-3 py-2">InfraEnv</th>
                  <th className="text-left font-medium px-3 py-2">Name</th>
                  <th className="text-right font-medium px-3 py-2">Replicas</th>
                  <th className="text-left font-medium px-3 py-2">Configs</th>
                  <th className="text-left font-medium px-3 py-2">Tuning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {values.nodepools.map((np, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-mono break-all">{np.infra_env_name ?? "—"}</td>
                    <td className="px-3 py-2 font-mono break-all text-muted-foreground">{np.name ?? "derived"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{np.replicas ?? "—"}</td>
                    <td className="px-3 py-2">
                      {np.configs.length === 0 ? <span className="text-muted-foreground">—</span> : (
                        <div className="flex flex-wrap gap-1">
                          {np.configs.map((c) => (
                            <span key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono break-all">{c}</span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono break-all">
                      {np.tuning_config ? String(np.tuning_config) : <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
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
