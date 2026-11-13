"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, GitCommitHorizontal, GitPullRequest, ChevronDown, ChevronRight, FilePlus, FileX, FileEdit, RefreshCw, Search, X, Eye } from "lucide-react";
import { api } from "@/lib/api-client";
import { approvalApiPath, approvalHref, mrKey, mrRef } from "@/lib/approvals";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatDateTime } from "@/lib/utils";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { ProblemList } from "@/components/common/problem-list";
import { Pagination, PageSizePicker } from "@/components/common/pagination";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { RepoBadge } from "@/components/common/repo-badge";
import type { ApprovalDetail, CommitRecord, MRDetail, FileDiff } from "@/types";

type RepoFilter = "all" | CommitRecord["repo"];

/** day1 serves the day1 and specs repos (by repo); day2 finds the team repo, hinted by team. */
function commitDiffPath(commit: CommitRecord): string {
  return commit.repo === "day2"
    ? `/api/day2/audit/commits/${commit.id}/diff${commit.team ? `?team=${encodeURIComponent(commit.team)}` : ""}`
    : `/api/day1/audit/commits/${commit.repo}/${commit.id}/diff`;
}

function DiffFileList({ diffs }: { diffs: FileDiff[] }) {
  const [openFiles, setOpenFiles] = useState<Set<number>>(new Set());
  const toggle = (i: number) => setOpenFiles((s) => {
    const n = new Set(s);
    if (n.has(i)) {
      n.delete(i);
    } else {
      n.add(i);
    }
    return n;
  });

  if (diffs.length === 0) {
    return <p className="text-xs text-muted-foreground italic px-6 pb-3">No file changes</p>;
  }

  return (
    <div className="border-t divide-y divide-border/50">
      {diffs.map((diff, i) => {
        const isOpen = openFiles.has(i);
        const badge = diff.new_file
          ? { label: "new", cls: "bg-status-ready/10 text-status-ready-fg", Icon: FilePlus }
          : diff.deleted_file
          ? { label: "deleted", cls: "bg-status-error/10 text-status-error", Icon: FileX }
          : { label: null, cls: "", Icon: FileEdit };
        const filePath = diff.renamed_file
          ? `${diff.old_path} → ${diff.new_path}`
          : diff.new_path || diff.old_path;

        return (
          <div key={i}>
            <button
              className="flex items-center gap-2 w-full px-6 py-2 text-left hover:bg-primary/[0.02] transition-colors"
              onClick={() => toggle(i)}
            >
              <badge.Icon className="h-3 w-3 text-muted-foreground shrink-0" />
              <span className="flex-1 text-xs font-mono truncate">{filePath}</span>
              {badge.label && (
                <span className={cn("rounded-full px-1.5 py-0.5 text-xs font-medium shrink-0", badge.cls)}>
                  {badge.label}
                </span>
              )}
              {isOpen
                ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
              }
            </button>
            {isOpen && diff.diff && (
              <div className="border-t border-border/50">
                <YamlDiffViewer diff={diff.diff} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CommitRow({ commit }: { commit: CommitRecord }) {
  const [expanded, setExpanded] = useState(false);

  const { data: diffs, isLoading: diffsLoading, error: diffsError } = useQuery<FileDiff[]>({
    queryKey: ["audit", commit.repo, "commit-diff", commit.id],
    queryFn: () => api.get<FileDiff[]>(commitDiffPath(commit)),
    enabled: expanded,
    staleTime: 300_000,
    retry: 1,
  });

  return (
    <div className="border-b last:border-0">
      <button
        className="flex items-start gap-3 py-3.5 w-full text-left hover:bg-primary/[0.02] transition-colors px-4 -mx-4"
        onClick={() => setExpanded((v) => !v)}
      >
        <GitCommitHorizontal className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium truncate">{commit.title}</p>
            <RepoBadge repo={commit.repo} team={commit.team} />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 font-mono">
            {commit.author_name} · {formatDateTime(commit.authored_date)} · {commit.short_id}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a
            href={commit.web_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          {expanded
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          }
        </div>
      </button>
      {expanded && (
        <div className="mb-2 -mx-4">
          {diffsLoading ? (
            <div className="px-6 pb-3 space-y-1">
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
          ) : diffsError ? (
            <div className="px-6 pb-3">
              <ProblemList error={diffsError} title="The commit's diff could not be loaded" />
            </div>
          ) : (
            <DiffFileList diffs={diffs ?? []} />
          )}
        </div>
      )}
    </div>
  );
}

function MRRow({ mr }: { mr: MRDetail }) {
  const [expanded, setExpanded] = useState(false);

  const stateColor = mr.state === "merged"
    ? "text-chart-5 dark:text-[#c084fc]"
    : mr.state === "closed"
    ? "text-status-error dark:text-[#f87171]"
    : "text-status-ready";

  const stateBg = mr.state === "merged"
    ? "bg-chart-5/15"
    : mr.state === "closed"
    ? "bg-status-error/15"
    : "bg-status-ready/15";

  const { data: detail, isLoading: detailLoading, error: detailError } = useQuery<ApprovalDetail>({
    queryKey: ["audit", "mr-diff", mrKey(mr)],
    queryFn: () => api.get<ApprovalDetail>(approvalApiPath(mrRef(mr))),
    enabled: expanded,
    staleTime: 300_000,
    retry: 1,
  });

  return (
    <div className="border-b last:border-0">
      <button
        className="flex items-start gap-3 py-3.5 w-full text-left hover:bg-primary/[0.02] transition-colors px-4 -mx-4"
        onClick={() => setExpanded((v) => !v)}
      >
        <GitPullRequest className={cn("h-4 w-4 mt-0.5 shrink-0", stateColor)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium truncate">{mr.title}</p>
            <RepoBadge repo={mr.repo} team={mr.team} />
            <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", stateBg, stateColor)}>
              {mr.state}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {mr.author.username} · {formatDateTime(mr.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {mr.state === "opened" && (
            <Link
              href={approvalHref(mr)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title="Review in Wingman"
              onClick={(e) => e.stopPropagation()}
            >
              <Eye className="h-3.5 w-3.5" />
            </Link>
          )}
          <a
            href={mr.web_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          {expanded
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          }
        </div>
      </button>
      {expanded && (
        <div className="mb-2 -mx-4">
          {detailLoading ? (
            <div className="px-6 pb-3 space-y-1">
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
          ) : detailError ? (
            <div className="px-6 pb-3">
              <ProblemList error={detailError} title="The merge request's diff could not be loaded" />
            </div>
          ) : (
            <DiffFileList diffs={detail?.diffs ?? []} />
          )}
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE_OPTIONS = [10, 20, 50];

export default function AuditPage() {
  const [activeTab, setActiveTab] = useState<"commits" | "mrs">("commits");
  const queryClient = useQueryClient();

  // Filter/pagination state
  const [search, setSearch] = useState("");
  const [repoFilter, setRepoFilter] = useState<RepoFilter>("all");
  const [mrStateFilter, setMrStateFilter] = useState<"all" | "opened" | "merged" | "closed">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Every item says which repo it is from: day1 serves day1 and specs, day2 every team repo.
  const { data: day1Commits, isLoading: loadingD1C, isFetching: fetchingD1C, error: day1CommitsError } = useQuery<CommitRecord[]>({
    queryKey: ["audit", "day1", "commits"],
    queryFn: () => api.get<CommitRecord[]>("/api/day1/audit/commits"),
    staleTime: 30_000,
  });

  const { data: day2Commits, isLoading: loadingD2C, isFetching: fetchingD2C, error: day2CommitsError } = useQuery<CommitRecord[]>({
    queryKey: ["audit", "day2", "commits"],
    queryFn: () => api.get<CommitRecord[]>("/api/day2/audit/commits"),
    staleTime: 30_000,
  });

  const { data: day1Mrs, isLoading: loadingD1M, isFetching: fetchingD1M, error: day1MrsError } = useQuery<MRDetail[]>({
    queryKey: ["audit", "day1", "mrs"],
    queryFn: () => api.get<MRDetail[]>("/api/day1/audit/merge-requests"),
    staleTime: 30_000,
  });

  const { data: day2Mrs, isLoading: loadingD2M, isFetching: fetchingD2M, error: day2MrsError } = useQuery<MRDetail[]>({
    queryKey: ["audit", "day2", "mrs"],
    queryFn: () => api.get<MRDetail[]>("/api/day2/audit/merge-requests"),
    staleTime: 30_000,
  });

  const isFetching = fetchingD1C || fetchingD2C || fetchingD1M || fetchingD2M;

  const allCommits = useMemo(() => [
    ...(day1Commits ?? []),
    ...(day2Commits ?? []),
  ].sort((a, b) => new Date(b.authored_date).getTime() - new Date(a.authored_date).getTime()), [day1Commits, day2Commits]);

  const allMrs = useMemo(() => [
    ...(day1Mrs ?? []),
    ...(day2Mrs ?? []),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()), [day1Mrs, day2Mrs]);

  const commitsLoading = loadingD1C || loadingD2C;
  const mrsLoading = loadingD1M || loadingD2M;
  // A source failed and the others hold nothing: its problem is the whole answer,
  // so neither an empty state nor a count of zero claims the list is empty.
  const commitsUnknown = !commitsLoading && Boolean(day1CommitsError || day2CommitsError) && allCommits.length === 0;
  const mrsUnknown = !mrsLoading && Boolean(day1MrsError || day2MrsError) && allMrs.length === 0;

  // Filtered lists
  const filteredCommits = useMemo(() => {
    let list = allCommits;
    if (repoFilter !== "all") list = list.filter((c) => c.repo === repoFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((c) =>
        c.title.toLowerCase().includes(q) ||
        c.author_name.toLowerCase().includes(q) ||
        c.short_id.toLowerCase().includes(q) ||
        (c.team ?? "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [allCommits, repoFilter, search]);

  const filteredMrs = useMemo(() => {
    let list = allMrs;
    if (repoFilter !== "all") list = list.filter((m) => m.repo === repoFilter);
    if (mrStateFilter !== "all") list = list.filter((m) => m.state === mrStateFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((m) =>
        m.title.toLowerCase().includes(q) ||
        m.author.username.toLowerCase().includes(q) ||
        (m.team ?? "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [allMrs, repoFilter, mrStateFilter, search]);

  const activeList = activeTab === "commits" ? filteredCommits : filteredMrs;
  const paginatedCommits = filteredCommits.slice((page - 1) * pageSize, page * pageSize);
  const paginatedMrs = filteredMrs.slice((page - 1) * pageSize, page * pageSize);

  function changeTab(t: "commits" | "mrs") { setActiveTab(t); setPage(1); }
  function changeFilter<T>(setter: (v: T) => void) { return (v: T) => { setter(v); setPage(1); }; }

  const hasActiveFilters = search || repoFilter !== "all" || mrStateFilter !== "all";
  function clearFilters() {
    setSearch(""); setRepoFilter("all"); setMrStateFilter("all"); setPage(1);
  }

  const tabs = [
    { id: "commits" as const, label: "Commits", count: commitsLoading || commitsUnknown ? null : filteredCommits.length },
    { id: "mrs" as const, label: "Merge Requests", count: mrsLoading || mrsUnknown ? null : filteredMrs.length },
  ];

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Audit Log
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Changes across the day1, specs and day2 team repos — click any entry to view its diff
          </p>
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ["audit"] })}
          disabled={isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          title="Refresh audit log"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Monday.com-style line tabs */}
      <div className="border-b border-border">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => changeTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-all",
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              )}
            >
              {tab.label}
              {tab.count !== null && (
                <span className={cn(
                  "rounded-full px-1.5 py-0.5 text-xs tabular-nums",
                  activeTab === tab.id
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
                )}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-40 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder={activeTab === "commits" ? "Search commits..." : "Search MRs..."}
            value={search}
            onChange={(e) => changeFilter(setSearch)(e.target.value)}
            className="w-full rounded-lg border bg-card pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
        </div>

        {/* Repo filter */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium">Repo:</span>
          {(["all", "day1", "specs", "day2"] as const).map((r) => (
            <button
              key={r}
              onClick={() => changeFilter(setRepoFilter)(r)}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                repoFilter === r
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
              )}
            >{r === "all" ? "All" : r}</button>
          ))}
        </div>

        {/* MR state filter — only shown on MR tab */}
        {activeTab === "mrs" && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground font-medium">State:</span>
            {(["all", "opened", "merged", "closed"] as const).map((s) => (
              <button
                key={s}
                onClick={() => changeFilter(setMrStateFilter)(s)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium transition-all border capitalize",
                  mrStateFilter === s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                )}
              >{s}</button>
            ))}
          </div>
        )}

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3 w-3" />
            Clear
          </button>
        )}

        <PageSizePicker total={activeList.length} sizes={PAGE_SIZE_OPTIONS} pageSize={pageSize} onPageSize={(n) => { setPageSize(n); setPage(1); }} />
      </div>

      {activeTab === "commits" && day1CommitsError && <ProblemList error={day1CommitsError} title="Day1 and spec commits could not be loaded" />}
      {activeTab === "commits" && day2CommitsError && <ProblemList error={day2CommitsError} title="Day2 team commits could not be loaded" />}
      {activeTab === "mrs" && day1MrsError && <ProblemList error={day1MrsError} title="Day1 and spec MRs could not be loaded" />}
      {activeTab === "mrs" && day2MrsError && <ProblemList error={day2MrsError} title="Day2 team MRs could not be loaded" />}

      {activeTab === "commits" && !commitsUnknown && (
        <div className="bg-card rounded-xl border shadow-sm px-4 py-1">
          {commitsLoading
            ? Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="py-3.5 border-b last:border-0">
                  <Skeleton className="h-4 w-3/4 mb-1.5" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              ))
            : paginatedCommits.length > 0
            ? paginatedCommits.map((c) => <CommitRow key={`${c.repo}-${c.team ?? ""}-${c.id}`} commit={c} />)
            : allCommits.length > 0
            ? <NoMatches what="commits" onClear={clearFilters} data-testid="audit-commits-no-matches" />
            : (
              <EmptyState
                icon={GitCommitHorizontal}
                title="No commits yet"
                description="Commits to the day1, specs and day2 team repos are listed here."
                data-testid="audit-commits-empty"
              />
            )}
        </div>
      )}

      {activeTab === "mrs" && !mrsUnknown && (
        <div className="bg-card rounded-xl border shadow-sm px-4 py-1">
          {mrsLoading
            ? Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="py-3.5 border-b last:border-0">
                  <Skeleton className="h-4 w-3/4 mb-1.5" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              ))
            : paginatedMrs.length > 0
            ? paginatedMrs.map((mr) => <MRRow key={mrKey(mr)} mr={mr} />)
            : allMrs.length > 0
            ? <NoMatches what="merge requests" onClear={clearFilters} data-testid="audit-mrs-no-matches" />
            : (
              <EmptyState
                icon={GitPullRequest}
                title="No merge requests yet"
                description="Merge requests in the day1, specs and day2 team repos are listed here."
                data-testid="audit-mrs-empty"
              />
            )}
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={activeList.length} onPage={setPage} />
    </div>
  );
}
