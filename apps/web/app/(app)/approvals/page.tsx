"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, CheckCircle2, RefreshCw, Search, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { RepoBadge } from "@/components/common/repo-badge";
import { approvalHref, mrKey } from "@/lib/approvals";
import { useAuthStore } from "@/stores/auth-store";
import { cn, formatDate } from "@/lib/utils";
import type { MRDetail } from "@/types";

const PAGE_SIZE_OPTIONS = [10, 20, 50];

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const username = useAuthStore((s) => s.user?.username);
  const [search, setSearch] = useState("");
  const [repoFilter, setRepoFilter] = useState<"all" | "day1" | "day2" | "specs">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // day1 lists the day1 and specs repos (each MR says which); day2 lists every team repo.
  const { data: day1Mrs, isLoading: loadingDay1, isFetching: fetchingDay1, error: day1Error } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day1"],
    queryFn: () => api.get<MRDetail[]>("/api/day1/approvals"),
    staleTime: 15_000,
  });

  const { data: day2Mrs, isLoading: loadingDay2, isFetching: fetchingDay2, error: day2Error } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day2"],
    queryFn: () => api.get<MRDetail[]>("/api/day2/approvals"),
    staleTime: 15_000,
  });

  const isLoading = loadingDay1 || loadingDay2;
  const isFetching = fetchingDay1 || fetchingDay2;

  const allMrs: MRDetail[] = useMemo(() => [
    ...(day1Mrs ?? []),
    ...(day2Mrs ?? []),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
  [day1Mrs, day2Mrs]);

  const filtered = useMemo(() => {
    let list = allMrs;
    if (repoFilter !== "all") list = list.filter((m) => m.repo === repoFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((m) =>
        m.title.toLowerCase().includes(q) ||
        m.author.username.toLowerCase().includes(q) ||
        (m.team ?? "").toLowerCase().includes(q) ||
        m.labels.some((l) => l.toLowerCase().includes(q))
      );
    }
    return list;
  }, [allMrs, repoFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);
  const hasActiveFilters = search || repoFilter !== "all";
  // A source failed and the others hold nothing: the problems above are the whole
  // answer, so neither an empty table nor a count of zero claims the list is empty.
  const nothingKnown = !isLoading && allMrs.length === 0 && Boolean(day1Error || day2Error);

  function clearFilters() {
    setSearch(""); setRepoFilter("all"); setPage(1);
  }

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Pending Approvals
          </h1>
          {isLoading ? (
            <Skeleton className="mt-1.5 h-4 w-56" />
          ) : (
            <p className="text-sm text-muted-foreground mt-0.5">
              {nothingKnown
                ? "Merge requests awaiting review"
                : `${filtered.length}${hasActiveFilters ? ` of ${allMrs.length}` : ""} merge request${allMrs.length !== 1 ? "s" : ""} awaiting review`}
            </p>
          )}
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ["approvals"] })}
          disabled={isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          title="Refresh approvals"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-40 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search by title or author..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full rounded-lg border bg-card pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium">Repo:</span>
          {(["all", "day1", "day2", "specs"] as const).map((r) => (
            <button
              key={r}
              onClick={() => { setRepoFilter(r); setPage(1); }}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                repoFilter === r
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
              )}
            >{r === "all" ? "All" : r}</button>
          ))}
        </div>
        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3 w-3" />Clear
          </button>
        )}
        {filtered.length > 10 && (
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-xs text-muted-foreground">Rows:</span>
            <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
              {PAGE_SIZE_OPTIONS.map((n) => (
                <button key={n} onClick={() => { setPageSize(n); setPage(1); }}
                  className={cn("rounded-md px-2 py-0.5 text-xs font-medium transition-all",
                    pageSize === n ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >{n}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {day1Error && <ProblemList error={day1Error} title="Day1 and spec MRs could not be loaded" />}
      {day2Error && <ProblemList error={day2Error} title="Day2 team MRs could not be loaded" />}

      {!nothingKnown && (
        <div className="bg-card rounded-xl border shadow-sm overflow-x-auto" data-testid="approvals-table">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Title</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Repo</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Author</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Created</th>
                <th className="w-10 px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 5 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                : paginated.map((mr) => (
                    <tr key={mrKey(mr)} className="hover:bg-primary/[0.03] transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Link
                            href={approvalHref(mr)}
                            className="font-semibold text-foreground hover:text-primary transition-colors break-words"
                          >
                            {mr.title}
                          </Link>
                          {mr.has_conflicts === true && (
                            <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-status-error/10 text-status-error">
                              Conflicted
                            </span>
                          )}
                        </div>
                        {mr.labels.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {mr.labels.map((label) => (
                              <span key={label} className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground">
                                {label}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <RepoBadge repo={mr.repo} team={mr.team} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {mr.author.username}
                        {mr.author.username === username && (
                          <span className="ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium bg-muted text-muted-foreground" title="You requested this change; another admin approves it">
                            you
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(mr.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <a
                          href={mr.web_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground hover:text-foreground transition-colors"
                          title="Open in GitLab"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </td>
                    </tr>
                  ))}
              {!isLoading && allMrs.length === 0 && !day1Error && !day2Error && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      icon={CheckCircle2}
                      tone="success"
                      title="All caught up"
                      description="No merge request is waiting for an approval."
                      data-testid="approvals-empty"
                    />
                  </td>
                </tr>
              )}
              {!isLoading && allMrs.length > 0 && filtered.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <NoMatches what="merge requests" onClear={clearFilters} data-testid="approvals-no-matches" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-xs text-muted-foreground">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}>← Prev</button>
            {(() => {
              const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
              const visible = pages.filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1);
              const withGaps: (number | "...")[] = [];
              let prev = 0;
              for (const p of visible) { if (p - prev > 1) withGaps.push("..."); withGaps.push(p); prev = p; }
              return withGaps.map((p, i) =>
                p === "..." ? <span key={`e-${i}`} className="px-1 text-muted-foreground text-xs">…</span> :
                <button key={p} onClick={() => setPage(p as number)}
                  className={cn(buttonVariants({ variant: p === page ? "default" : "outline", size: "sm" }), "px-2.5 py-1 h-7 text-xs min-w-[28px]")}
                >{p}</button>
              );
            })()}
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}>Next →</button>
          </div>
        </div>
      )}
    </div>
  );
}
