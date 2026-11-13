import Link from "next/link";
import type { ReactNode } from "react";
import { approvalHref } from "@/lib/approvals";
import { cn } from "@/lib/utils";
import type { MRDetail } from "@/types";

type Linked = Pick<MRDetail, "repo" | "iid" | "team" | "web_url" | "opened_by_workflow">;

/**
 * An MR's link in a list: Wingman's review page, or GitLab in a new tab for
 * an MR a platform workflow opened (ADR-0042's amendment), since that one is
 * reviewed and merged in GitLab.
 */
export function ApprovalLink({ mr, className, children }: { mr: Linked; className?: string; children: ReactNode }) {
  if (mr.opened_by_workflow) {
    return (
      <a href={mr.web_url} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </a>
    );
  }
  return (
    <Link href={approvalHref(mr)} className={className}>
      {children}
    </Link>
  );
}

/** Marks an MR the platform workflow opened; nothing for Wingman's own. */
export function WorkflowBadge({ mr, className }: { mr: Pick<MRDetail, "opened_by_workflow">; className?: string }) {
  if (!mr.opened_by_workflow) return null;
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap bg-status-provisioning/10 text-status-provisioning-fg",
        className
      )}
      title={`Opened by the ${mr.opened_by_workflow} workflow: review and merge it in GitLab`}
      data-testid="workflow-badge"
    >
      {mr.opened_by_workflow} workflow
    </span>
  );
}
