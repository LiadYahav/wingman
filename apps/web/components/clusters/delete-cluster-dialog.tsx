"use client";

import { useState } from "react";
import { ReviewDialog } from "@/components/common/review-dialog";
import { DeleteWorkflowPanel } from "@/components/clusters/delete-workflow-panel";
import { isKvCluster } from "@/lib/workspaces";
import type { ClusterDetail } from "@/types";

/**
 * Review a cluster's delete: the MR that removes its file. A KV cluster's
 * (ADR-0067) also says the tenants' VM workers it hosts go with it, and asks
 * for its name typed in, which day1 checks too (`confirm`); a tenant's asks
 * nothing more. Everything else about a KV cluster is managed as a tenant's.
 */
export function DeleteClusterDialog({
  open, onOpenChange, name, site, mce, where, cluster, isAdmin, isPending, onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  site: string;
  mce: string;
  where: string;
  cluster: ClusterDetail | undefined;
  isAdmin: boolean;
  isPending: boolean;
  /** `confirm` is the name typed in for a KV cluster, empty for a tenant's. */
  onConfirm: (confirm: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const kv = cluster ? isKvCluster(cluster) : false;
  return (
    <ReviewDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setTyped("");
      }}
      title={`Review: Delete ${kv ? "KV Cluster" : "Cluster"} "${name}"`}
      description="This opens a GitLab MR that removes the cluster file. The change requires approval before merging."
      onConfirm={() => onConfirm(kv ? typed : "")}
      isPending={isPending}
      confirmLabel="Confirm — Delete Cluster MR"
      confirmVariant="destructive"
      confirmDisabled={kv && typed !== name}
    >
      <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-1">
        <p className="break-words">
          Deleting {kv ? "KV cluster" : "cluster"} <strong>{name}</strong> from site <strong>{site}</strong> /{" "}
          {kv ? "seed" : "MCE"} <strong>{mce}</strong>.
        </p>
        {cluster && <p className="font-mono text-xs text-muted-foreground break-all">{cluster.path}</p>}
        <p className="text-muted-foreground text-xs">Once merged, ArgoCD removes the HostedCluster. The network segment is not released: that is the delete-cluster workflow&apos;s job.</p>
      </div>
      {kv && (
        <div className="space-y-3" data-testid="kv-delete-confirm">
          <div className="rounded-lg border border-status-warning/40 bg-status-warning/8 p-3 text-sm" role="note">
            <p className="font-semibold text-status-warning-fg">The tenants&apos; VMs go with it.</p>
            <p className="mt-1 text-xs text-foreground/90">
              A KV cluster&apos;s workers host the tenants&apos; VM workers: deleting it deletes every VM it hosts, and the
              tenant clusters that use them lose those nodes.
            </p>
          </div>
          <label className="block space-y-1.5 text-sm">
            <span>
              Type <code className="rounded bg-muted px-1.5 py-0.5 text-destructive break-all">{name}</code> to confirm
            </span>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={name}
              autoComplete="off"
              spellCheck={false}
              aria-label="The KV cluster's name, to confirm"
              className="w-full rounded-lg border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
            />
          </label>
        </div>
      )}
      <DeleteWorkflowPanel name={name} where={where} isAdmin={isAdmin} />
    </ReviewDialog>
  );
}
