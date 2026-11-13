"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, GitCommitHorizontal, GitPullRequest, ChevronDown, ChevronRight, FilePlus, FileX, FileEdit, Search, X, Eye } from "lucide-react";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { approvalHref, mrKey, mrRef } from "@/lib/approvals";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatDateTime, newestFirst } from "@/lib/utils";
import { diffLabel } from "@/lib/diff";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { ProblemList } from "@/components/common/problem-list";
import { RefreshButton } from "@/components/common/refresh-button";
import { Pagination, PageSizePicker } from "@/components/common/pagination";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { RepoBadge } from "@/components/common/repo-badge";
import type { ApprovalDetail, CommitRecord, MRDetail, FileDiff } from "@/types";

type RepoFilter = "all" | CommitRecord["repo"];

function DiffFileList({ diffs }: { diffs: FileDiff[] }) {
  const [openFiles, setOpenFiles] = useState<Set<number>>(new Set());
  const toggle = (i: number) =>
    setOpenFiles((s) => {
      const next = new Set(s);
      if (!next.delete(i)) next.add(i);
      return next;
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
        const filePath = diffLabel(diff);

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

/** An expanded row's diff: loading, why it could not be read, or its files. */
function RowDiffs({ loading, error, problemTitle, diffs }: { loading: boolean; error: unknown; problemTitle: string; diffs: FileDiff[] }) {
  return (
    <div className="mb-2 -mx-4">
      {loading ? (
        <div className="px-6 pb-3 space-y-1">
          <Skeleton className="h-3 w-48" />
          <Skeleton className="h-3 w-64" />
        </div>
      ) : error ? (
        <div className="px-6 pb-3">
          <ProblemList error={error} title={problemTitle} />
        </div>
      ) : (
        <DiffFileList diffs={diffs} />
      )}
    </div>
  );
}

function CommitRow({ commit }: { commit: CommitRecord }) {
  const [expanded, setExpanded] = useState(false);

  const { data: diffs, isLoading: diffsLoading, error: diffsError } = useQuery<FileDiff[]>({
    queryKey: day1Keys.audit.commitDiff(commit.repo, commit.id),
    queryFn: () => day1Api.audit.commitDiff(commit),
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
        <RowDiffs loading={diffsLoading} error={diffsError} problemTitle="The commit's diff could not be loaded" diffs={diffs ?? []} />
      )}
    </div>
  );
}

/** An MR's state colours: merged purple, closed red, opened (or locked) green. */
function stateTone(state: MRDetail["state"]): { text: string; bg: string } {
  if (state === "merged") return { text: "text-chart-5 dark:text-[#c084fc]", bg: "bg-chart-5/15" };
  if (state === "closed") return { text: "text-status-error dark:text-[#f87171]", bg: "bg-status-error/15" };
  return { text: "text-status-ready", bg: "bg-status-ready/15" };
}

function MRRow({ mr }: { mr: MRDetail }) {
  const [expanded, setExpanded] = useState(false);

  const { text: stateColor, bg: stateBg } = stateTone(mr.state);

  const { data: detail, isLoading: detailLoading, error: detailError } = useQuery<ApprovalDetail>({
    queryKey: day1Keys.audit.mrDiff(mrKey(mr)),
    queryFn: () => day1Api.approvals.detail(mrRef(mr)),
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
        <RowDiffs loading={detailLoading} error={detailError} problemTitle="The merge request's diff could not be loaded" diffs={detail?.diffs ?? []} />
      )}
    </div>
  );
}

const PAGE_SIZE_OPTIONS = [10, 20, 50];

// eslint-disable-next-line max-lines-per-function, complexity -- size baseline (ADR-0056)
export default function AuditPage() {
  const [activeTab, setActiveTab] = useState<"commits" | "mrs">("commits");

  // Filter/pagination state
  const [search, setSearch] = useState("");
  const [repoFilter, setRepoFilter] = useState<RepoFilter>("all");
  const [mrStateFilter, setMrStateFilter] = useState<"all" | "opened" | "merged" | "closed">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Every item says which repo it is from: day1 serves day1 and specs, day2 every team repo.
  const { data: day1Commits, isLoading: loadingD1C, isFetching: fetchingD1C, error: day1CommitsError } = useQuery<CommitRecord[]>({
    queryKey: day1Keys.audit.commits("day1"),
    queryFn: () => day1Api.audit.commits("day1"),
    staleTime: 30_000,
  });

  const { data: day2Commits, isLoading: loadingD2C, isFetching: fetchingD2C, error: day2CommitsError } = useQuery<CommitRecord[]>({
    queryKey: day1Keys.audit.commits("day2"),
    queryFn: () => day1Api.audit.commits("day2"),
    staleTime: 30_000,
  });

  const { data: day1Mrs, isLoading: loadingD1M, isFetching: fetchingD1M, error: day1MrsError } = useQuery<MRDetail[]>({
    queryKey: day1Keys.audit.mergeRequests("day1"),
    queryFn: () => day1Api.audit.mergeRequests("day1"),
    staleTime: 30_000,
  });

  const { data: day2Mrs, isLoading: loadingD2M, isFetching: fetchingD2M, error: day2MrsError } = useQuery<MRDetail[]>({
    queryKey: day1Keys.audit.mergeRequests("day2"),
    queryFn: () => day1Api.audit.mergeRequests("day2"),
    staleTime: 30_000,
  });

  const isFetching = fetchingD1C || fetchingD2C || fetchingD1M || fetchingD2M;

  const allCommits = useMemo(() => newestFirst([day1Commits, day2Commits], (c) => c.authored_date), [day1Commits, day2Commits]);

  const allMrs = useMemo(() => newestFirst([day1Mrs, day2Mrs], (mr) => mr.created_at), [day1Mrs, day2Mrs]);

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
        <RefreshButton queryKey={day1Keys.audit.all} fetching={isFetching} title="Refresh audit log" />
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
