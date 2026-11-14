"use client";

import { formatTimestamp } from "@/lib/server-scan/datetime";
import { collectionText, matchedRuleText, profileTemplateLabel } from "@/lib/server-scan/overview";
import type { ServerRecord } from "@/types/server-scan-record";
import { SeverityPill } from "../server-badges";
import { Field, Tag } from "./fields";
import { HealthBreakdown, HostValue, LastSeen, MaintenanceValue, ModelValue, OpenShiftValue } from "./overview-values";

/**
 * The Overview, as server-scan's `OverviewTab.tsx` (team-redbull/server-scan
 * at 92146d3, decision 18; docs/notes/2026-11-13-server-scan-area-api.md
 * §9.1): two columns of fields, kept apart so a field only some vendors have
 * (the template, Collection) never moves the others into the other column.
 * Its one control is the maintenance toggle (§9.8).
 */
export function OverviewTab({ record }: { record: ServerRecord }) {
  const templateLabel = profileTemplateLabel(record.source_provider);
  const rule = matchedRuleText(record.classification);
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-4 rounded-xl border bg-card p-5 sm:grid-cols-2" data-testid="ss-overview">
      <dl className="flex flex-col gap-4">
        <Field label="Name">{record.name}</Field>
        <Field label="Model">
          <ModelValue record={record} />
        </Field>
        <Field label="Serial">{record.identity.serial ?? "—"}</Field>
        <Field label="Manager">{record.manager_id ?? "—"}</Field>
        <Field label="OpenShift">
          <OpenShiftValue record={record} />
        </Field>
        {record.vm_host && (
          <Field label="Host">
            <HostValue serverId={record.id} vmHost={record.vm_host} />
          </Field>
        )}
        <Field label="Health breakdown">
          <HealthBreakdown record={record} />
        </Field>
        <Field label="Last seen">
          <LastSeen record={record} />
        </Field>
      </dl>
      <dl className="flex flex-col gap-4">
        <Field label="Vendor">{record.identity.vendor}</Field>
        {templateLabel && <Field label={templateLabel}>{record.profile_template.name ?? "—"}</Field>}
        <Field label="Site">{record.site_id ?? "—"}</Field>
        <Field label="Classification">
          <Tag title="What the server was named to be, by server-scan's classification rules">{record.classification.installation_type}</Tag>
        </Field>
        {rule && <Field label="Matched rule">{rule}</Field>}
        <Field label="Overall health">
          <SeverityPill severity={record.health.overall} />
        </Field>
        <Field label="Maintenance">
          <MaintenanceValue record={record} />
        </Field>
        {!record.reachable && (
          <Field label="Collection" testId="ss-collection">
            <Tag tone="warning">{collectionText(record.unreachable_reason, record.unreachable_since)}</Tag>
          </Field>
        )}
        <Field label="Last changed">{formatTimestamp(record.updated_at)}</Field>
      </dl>
    </div>
  );
}
