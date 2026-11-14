"use client";

import Link from "next/link";
import { useServerScanVmHost } from "@/lib/api/server-scan";
import { formatRelative, formatTimestamp } from "@/lib/server-scan/datetime";
import { inferredGpuModel } from "@/lib/server-scan/hardware";
import { categoryLabel, healthCategories, maintenanceText, maintenanceWhen, raidNote } from "@/lib/server-scan/overview";
import { serverHref } from "@/lib/server-scan/server-page";
import type { ServerRecord, VmHost } from "@/types/server-scan-record";
import { MaintenanceToggle } from "../maintenance-toggle";
import { InstallationBadge, ReservationBadge, SeverityPill } from "../server-badges";
import { Tag } from "./fields";

/**
 * The Overview's richer values, as server-scan's `OverviewTab.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18) shows them; the rules
 * are `lib/server-scan/overview.ts`.
 */

/** The chassis's model, else the GPUs' short name marked "(from GPU)", else a dash. */
export function ModelValue({ record }: { record: ServerRecord }) {
  if (record.model) return <>{record.model}</>;
  const inferred = inferredGpuModel(record.hardware.gpus);
  if (!inferred) return <>—</>;
  return (
    <span className="inline-flex items-center gap-1.5">
      {inferred}
      <span className="text-xs text-muted-foreground">(from GPU)</span>
    </span>
  );
}

/**
 * OpenShift's own report, beside the classification and never instead of it
 * (their disagreeing is how a misnamed server is noticed), with the install
 * lock while one is held, a rename after install and a second claimant.
 */
export function OpenShiftValue({ record }: { record: ServerRecord }) {
  const { lifecycle_state, cluster_name, mce_name, reported_name, contested_with, contested_name } = record.openshift;
  return (
    <div className="flex flex-col gap-1" data-testid="ss-openshift">
      <div className="flex flex-wrap items-center gap-2">
        <InstallationBadge state={lifecycle_state} full />
        {cluster_name && <span className="font-medium">{cluster_name}</span>}
        <ReservationBadge reservation={record.reservation} full />
      </div>
      <span className="text-xs text-muted-foreground">{mce_name ? `MCE ${mce_name}` : "—"}</span>
      {reported_name && (
        <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Tag tone="warning" title="OpenShift reports this node under another name: it was renamed after install">
            Name mismatch
          </Tag>
          Installed as <span className="font-medium text-foreground">{reported_name}</span>
        </span>
      )}
      {contested_with && (
        <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Tag tone="warning" title="Two OpenShift memberships claim this one physical server">
            Duplicate server
          </Tag>
          Also claimed by <span className="font-medium text-foreground">{contested_with}</span>
          {contested_name && (
            <>
              {" "}as <span className="font-medium text-foreground">{contested_name}</span>
            </>
          )}
        </span>
      )}
    </div>
  );
}

/** The node a KubeVirt VM runs on and, when server-scan holds it, that server: the physical machine behind the VM. */
export function HostValue({ serverId, vmHost }: { serverId: string; vmHost: VmHost }) {
  const { data, isError } = useServerScanVmHost(serverId, true);
  const { node_name, cluster_name } = vmHost;
  const host = data?.host;
  const note = "text-xs text-muted-foreground";
  return (
    <div className="flex flex-col gap-1" data-testid="ss-vm-host">
      <span className="font-medium">
        {node_name ?? "Not running"}
        {node_name && cluster_name && <span className="font-normal text-muted-foreground"> · cluster {cluster_name}</span>}
      </span>
      {host && (
        <div className="flex flex-wrap items-center gap-2">
          <Link href={serverHref(host.id)} className="text-primary hover:underline">
            {host.name}
          </Link>
          <SeverityPill severity={host.health} />
          {host.maintenance && <Tag tone="warning">Maintenance</Tag>}
        </div>
      )}
      {host && (
        <span className={note}>
          CPU {host.cpu.model ?? "—"}
          {data.match === "NAME" && " · matched by name only"}
        </span>
      )}
      {node_name && data?.match === "NOT_IN_INVENTORY" && <span className={note}>Node {node_name} is not in the inventory</span>}
      {node_name && data?.match === "AMBIGUOUS" && <span className={note}>Node {node_name} matches more than one server</span>}
      {isError && <span className={note}>Could not look up the host</span>}
    </div>
  );
}

/** A badge per category server-scan can judge here, then the policies that fired, worst first. */
export function HealthBreakdown({ record }: { record: ServerRecord }) {
  const reasons = record.health.reasons;
  const raid = raidNote(record.hardware.storage.raid);
  return (
    <div data-testid="ss-health-breakdown">
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {healthCategories(record).map(({ key, label, severity }) => (
          <span key={key} className="inline-flex items-center gap-1.5 text-xs" data-category={key}>
            <span className="text-muted-foreground">{label}</span>
            <SeverityPill severity={severity} />
            {key === "raid" && raid && (
              <span className="text-muted-foreground" title={record.hardware.storage.raid?.reason ?? undefined}>
                {raid}
              </span>
            )}
          </span>
        ))}
      </div>
      {reasons.length > 0 && (
        <ul aria-label="Why this health" className="mt-2 space-y-1">
          {reasons.map((reason) => (
            <li key={reason.policy_key} className="flex flex-wrap items-center gap-1.5 text-xs" title={reason.policy_name}>
              <SeverityPill severity={reason.severity} />
              <span className="text-muted-foreground">{categoryLabel(reason.category)}</span>
              <span>{reason.message ?? reason.policy_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Whether the server is in maintenance and why, with the Servers page's own
 * toggle beside it (§9.8; server-scan's page shows this read only). Since
 * when and the expected end are the reason's tooltip.
 */
export function MaintenanceValue({ record }: { record: ServerRecord }) {
  const text = maintenanceText(record.maintenance);
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-testid="ss-maintenance">
      {text ? (
        <Tag tone="warning" title={maintenanceWhen(record.maintenance) ?? undefined}>
          {text}
        </Tag>
      ) : (
        <span className="text-muted-foreground">Not in maintenance</span>
      )}
      <MaintenanceToggle server={record} available={record.maintenance_available} detail={record.maintenance_detail} />
    </span>
  );
}

/** Relative, so staleness reads at a glance; the exact instant on hover. */
export function LastSeen({ record }: { record: ServerRecord }) {
  if (!record.last_seen_at) return <Tag tone="warning">Never collected</Tag>;
  return (
    <span className="inline-flex items-center gap-2" title={formatTimestamp(record.last_seen_at)}>
      {formatRelative(record.last_seen_at)}
      {record.stale && <Tag tone="warning">Stale</Tag>}
    </span>
  );
}
