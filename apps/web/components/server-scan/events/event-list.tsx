"use client";

import { useState } from "react";
import type { InfiniteData, UseInfiniteQueryResult } from "@tanstack/react-query";
import { ProblemList } from "@/components/common/problem-list";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { eventPager } from "@/lib/server-scan/events";
import type { AuditEventPage } from "@/types/server-scan-record";
import { EventTimeline } from "./event-timeline";

/**
 * Loading, the problem, none, or one page of events with Previous, "Page X of
 * Y" and Next over server-scan's cursors, as server-scan's `EventList.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18). `testId` prefixes the
 * states' test ids; the words are the page's.
 */
export function EventList({
  query,
  label,
  loading,
  problem,
  testId,
}: {
  query: UseInfiniteQueryResult<InfiniteData<AuditEventPage, unknown>, unknown>;
  /** The table's name. */
  label: string;
  /** What shows while the first page loads. */
  loading: string;
  /** The problem's title when the first page could not be read. */
  problem: string;
  testId: string;
}) {
  const [index, setIndex] = useState(0);
  if (query.isPending) {
    return (
      <div className="space-y-2" aria-busy="true" data-testid={`${testId}-loading`}>
        <p className="text-sm text-muted-foreground">{loading}</p>
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (query.isError) return <ProblemList error={query.error} title={problem} />;
  const pages = query.data.pages;
  if ((pages[0]?.items.length ?? 0) === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid={`${testId}-empty`}>
        No events recorded.
      </p>
    );
  }
  const shown = pages[index] ?? pages[0];
  const { pageCount, canNext } = eventPager(pages, index, query.hasNextPage);
  const next = () => {
    if (index + 1 < pages.length) setIndex(index + 1);
    else void query.fetchNextPage().then(() => setIndex(index + 1));
  };
  return (
    <div className="space-y-3">
      <EventTimeline events={shown.items} label={label} />
      <div className="flex items-center gap-3" data-testid={`${testId}-pager`}>
        <button type="button" disabled={index <= 0} onClick={() => setIndex(index - 1)} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Previous
        </button>
        <span className="text-sm text-muted-foreground">
          Page {index + 1} of {pageCount}
        </span>
        <button type="button" disabled={!canNext || query.isFetchingNextPage} onClick={next} className={buttonVariants({ variant: "outline", size: "sm" })}>
          {query.isFetchingNextPage ? "Loading…" : "Next"}
        </button>
      </div>
    </div>
  );
}
