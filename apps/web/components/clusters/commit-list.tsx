"use client";

import { ExternalLink, GitCommitHorizontal, History } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState } from "@/components/common/empty-state";
import { formatDate } from "@/lib/utils";

/** One commit, as the History tab lists it (day1's file history and day2's values history). */
export interface CommitEntry {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  web_url: string;
  team?: string;
}

/** One source's commits: skeleton rows, its problem when the read failed, or an empty state. */
export function CommitList({
  commits,
  isLoading,
  error,
  errorTitle,
  empty,
  teamColumn,
}: {
  commits?: CommitEntry[];
  isLoading: boolean;
  error: unknown;
  errorTitle: string;
  empty: { title: string; description: string; testId: string };
  teamColumn?: boolean;
}) {
  if (isLoading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>;
  if (error) return <ProblemList error={error} title={errorTitle} />;
  if (!commits?.length) {
    return (
      <EmptyState
        icon={History}
        title={empty.title}
        description={empty.description}
        bordered
        className="py-8"
        data-testid={empty.testId}
      />
    );
  }
  return (
    <div className="rounded-xl border bg-card overflow-hidden divide-y divide-border">
      {commits.map((c) => (
        <div key={c.sha} className="flex items-start gap-3 px-4 py-3">
          <GitCommitHorizontal className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium line-clamp-1">{c.message}</p>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
              <span className="font-mono">{c.short_sha}</span>
              <span>·</span>
              <span>{c.author}</span>
              <span>·</span>
              <span>{formatDate(c.date)}</span>
              {teamColumn && c.team && <><span>·</span><span className="text-primary/70">{c.team}</span></>}
            </div>
          </div>
          {c.web_url && (
            <a href={c.web_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary transition-colors shrink-0">
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      ))}
    </div>
  );
}
