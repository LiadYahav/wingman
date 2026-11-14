"use client";

import { CheckCircle2 } from "lucide-react";
import { RepoBadge } from "@/components/common/repo-badge";
import { ApprovalLink, WorkflowBadge } from "@/components/common/workflow-mr";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState } from "@/components/common/empty-state";
import { mrKey } from "@/lib/approvals";
import { formatDate } from "@/lib/utils";
import type { MRDetail } from "@/types";
import { OverviewCard, RowsSkeleton } from "./overview-card";
import { useOverviewApprovals } from "./use-overview";

function ApprovalRows({ mrs }: { mrs: MRDetail[] }) {
  return (
    <div className="space-y-1">
      {mrs.map((mr) => (
        <ApprovalLink key={mrKey(mr)} mr={mr}
          className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{mr.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">
              by {mr.author.username} · {formatDate(mr.created_at)}
            </p>
          </div>
          <div className="ml-3 flex shrink-0 items-center gap-1.5">
            <WorkflowBadge mr={mr} />
            <RepoBadge repo={mr.repo} />
          </div>
        </ApprovalLink>
      ))}
    </div>
  );
}

/** The newest open MRs of both services; each failed source says so. */
export function ApprovalsCard() {
  const approvals = useOverviewApprovals();
  return (
    <OverviewCard title="Pending Approvals" href="/approvals">
      {(approvals.day1Error || approvals.day2Error) && (
        <div className="mb-3 space-y-2">
          {approvals.day1Error && <ProblemList error={approvals.day1Error} title="Day1 and spec MRs could not be loaded" />}
          {approvals.day2Error && <ProblemList error={approvals.day2Error} title="Day2 team MRs could not be loaded" />}
        </div>
      )}
      {approvals.loading ? (
        <RowsSkeleton className="h-12" />
      ) : approvals.recent.length > 0 ? (
        <ApprovalRows mrs={approvals.recent} />
      ) : approvals.unavailable.length > 0 ? null : (
        <EmptyState
          icon={CheckCircle2}
          tone="success"
          title="All caught up"
          description="No merge request is waiting for an approval."
          data-testid="approvals-empty"
        />
      )}
    </OverviewCard>
  );
}
