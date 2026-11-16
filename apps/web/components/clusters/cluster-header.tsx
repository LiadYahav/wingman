"use client";

import Link from "next/link";
import { ArrowLeft, Edit2, ExternalLink, Eye, Package, Trash2, X } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FlavorStateBadge } from "@/components/clusters/drift-badge";
import { updateOf } from "@/components/clusters/cluster-drift";
import { chartsHref } from "@/lib/day2";
import type { ClusterDetail, ClusterDrift } from "@/types";

/** What an admin does from the header: edit the file (then cancel or review it), or delete the cluster. */
export interface ClusterHeaderActions {
  editing: boolean;
  /** Editing, and the YAML is the file it started from. */
  unchanged: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onReview: () => void;
  onDelete: () => void;
  deleting: boolean;
}

/** An admin's buttons: Edit and Delete, or while editing, Cancel and Review & Submit. */
function AdminButtons({ actions }: { actions: ClusterHeaderActions }) {
  const { editing, unchanged } = actions;
  if (editing) {
    return (
      <>
        <button onClick={actions.onCancelEdit} className={buttonVariants({ variant: "outline", size: "sm" })}>
          <X className="h-4 w-4 mr-1.5" />Cancel
        </button>
        <button
          onClick={actions.onReview}
          disabled={unchanged}
          title={unchanged ? "No changes to submit" : undefined}
          className={buttonVariants({ size: "sm" })}
        >
          <Eye className="h-4 w-4 mr-1.5" />
          {unchanged ? "No Changes" : "Review & Submit"}
        </button>
      </>
    );
  }
  return (
    <>
      <button className={buttonVariants({ variant: "outline", size: "sm" })} onClick={actions.onEdit}>
        <Edit2 className="h-4 w-4 mr-1.5" />Edit
      </button>
      <button className={buttonVariants({ variant: "destructive", size: "sm" })} onClick={actions.onDelete} disabled={actions.deleting}>
        <Trash2 className="h-4 w-4 mr-1.5" />Delete
      </button>
    </>
  );
}

/**
 * The cluster page's header: back to Clusters, the name and its flavor's
 * state, and once the file is read, its links and an admin's buttons. While
 * `loading`, a placeholder where the name goes (the server's render, too).
 */
export function ClusterHeader({ name, mce, loading = false, cluster, drift, isAdmin = false, actions }: {
  name: string;
  mce?: string;
  loading?: boolean;
  cluster?: ClusterDetail;
  drift?: ClusterDrift;
  isAdmin?: boolean;
  actions?: ClusterHeaderActions;
}) {
  return (
    <div className="flex items-start gap-3 flex-wrap">
      <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })}>
        <ArrowLeft className="h-4 w-4" />
      </Link>
      <div className="flex-1 min-w-0">
        {loading ? (
          <Skeleton className="h-7 w-48" />
        ) : (
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight break-all">{name}</h1>
            {drift && drift.state !== "not_linked" && <FlavorStateBadge row={{ ...drift, update: updateOf(drift) }} />}
          </div>
        )}
      </div>
      {!loading && cluster && (
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
          <Link href={chartsHref(name, mce ?? cluster.mce)} className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Package className="h-4 w-4 mr-1.5" />Addons
          </Link>
          {isAdmin && actions && <AdminButtons actions={actions} />}
        </div>
      )}
    </div>
  );
}
