"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, CheckCircle2, RefreshCw, Search, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { MRDetail } from "@/types";

const PAGE_SIZE_OPTIONS = [10, 20, 50];

function RepoBadge({ repo }: { repo: string }) {
  const cls = repo === "day1"
    ? "bg-[#0073ea]/10 text-[#0073ea] dark:bg-[#579bfc]/15 dark:text-[#579bfc]"
    : repo === "day2"
    ? "bg-[#00c875]/10 text-[#007038] dark:bg-[#00c875]/15 dark:text-[#00c875]"
    : "bg-muted text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", cls)}>
      {repo}
    </span>
  );
}

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [repoFilter, setRepoFilter] = useState<"all" | "day1" | "day2">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: day1Mrs, isLoading: loadingDay1, isFetching: fetchingDay1 } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day1"],
    queryFn: () => api.get<MRDetail[]>("/api/day1/approvals"),
    staleTime: 15_000,
  });

  const { data: day2Mrs, isLoading: loadingDay2, isFetching: fetchingDay2 } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day2"],
    queryFn: () => api.get<MRDetail[]>("/api/day2/approvals"),
    staleTime: 15_000,
  });

  const isLoading = loadingDay1 || loadingDay2;
  const isFetching = fetchingDay1 || fetchingDay2;

  const allMrs: MRDetail[] = useMemo(() => [
    ...(day1Mrs?.map((mr) => ({ ...mr, repo: "day1" as const })) ?? []),
    ...(day2Mrs?.map((mr) => ({ ...mr, repo: "day2" as const })) ?? []),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
  [day1Mrs, day2Mrs]);

  const filtered = useMemo(() => {
    let list = allMrs;
    if (repoFilter !== "all") list = list.filter((m) => m.repo === repoFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((m) =>
        m.title.toLowerCase().includes(q) ||
        m.author?.username?.toLowerCase().includes(q) ||
        m.labels?.some((l: string) => l.toLowerCase().includes(q))
      );
    }
    return list;
  }, [allMrs, repoFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);
  const hasActiveFilters = search || repoFilter !== "all";

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
          <p className="text-sm text-muted-foreground mt-0.5">
            {isLoading ? "Loading..." : `${filtered.length}${hasActiveFilters ? ` of ${allMrs.length}` : ""} merge request${allMrs.length !== 1 ? "s" : ""} awaiting review`}
          </p>
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
          {(["all", "day1", "day2"] as const).map((r) => (
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
            onClick={() => { setSearch(""); setRepoFilter("all"); setPage(1); }}
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

      <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
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
                  <tr key={`${mr.repo}-${mr.iid}`} className="hover:bg-primary/[0.03] transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        href={`/approvals/${mr.repo}-${mr.iid}`}
                        className="font-semibold text-foreground hover:text-primary transition-colors"
                      >
                        {mr.title}
                      </Link>
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
                      <RepoBadge repo={mr.repo} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{mr.author.username}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(mr.created_at).toLocaleDateString("en-GB")}
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
            {!isLoading && allMrs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-16 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="rounded-full bg-[#00c875]/10 dark:bg-[#00c875]/15 p-3">
                      <CheckCircle2 className="h-7 w-7 text-[#00c875]" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">All caught up!</p>
                      <p className="text-xs text-muted-foreground mt-0.5">No pending approvals</p>
                    </div>
                  </div>
                </td>
              </tr>
            )}
            {!isLoading && allMrs.length > 0 && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground text-sm">
                  No MRs match your filters.{" "}
                  <button onClick={() => { setSearch(""); setRepoFilter("all"); setPage(1); }} className="text-primary hover:underline">Clear filters</button>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

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
