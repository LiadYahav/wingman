"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ExternalLink, GitMerge, GitPullRequest, X,
  ChevronDown, ChevronRight, FilePlus, FileX, FileEdit, Edit2, Eye,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { ReviewDialog } from "@/components/common/review-dialog";
import { computeLineDiff } from "@/lib/diff";
import type { MRDetail, FileDiff } from "@/types";

interface MRDetailResponse {
  mr: MRDetail;
  diffs: FileDiff[];
}

// ── File diff card ─────────────────────────────────────────────────────────────

function FileDiffCard({ diff }: { diff: FileDiff }) {
  const [open, setOpen] = useState(true);

  const badge = diff.new_file
    ? { label: "new", cls: "bg-[#00c875]/10 text-[#007038] dark:text-[#00c875]" }
    : diff.deleted_file
    ? { label: "deleted", cls: "bg-[#df2f4a]/10 text-[#df2f4a]" }
    : diff.renamed_file
    ? { label: "renamed", cls: "bg-[#fdab3d]/10 text-[#c07800] dark:text-[#fdab3d]" }
    : null;

  const Icon = diff.new_file ? FilePlus : diff.deleted_file ? FileX : FileEdit;
  const filePath = diff.renamed_file
    ? `${diff.old_path} → ${diff.new_path}`
    : diff.new_path || diff.old_path;

  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      <button
        className="flex items-center gap-2 w-full px-4 py-3 hover:bg-primary/[0.02] transition-colors text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="flex-1 text-sm font-mono font-medium truncate">{filePath}</span>
        {badge && (
          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium shrink-0", badge.cls)}>
            {badge.label}
          </span>
        )}
        {open
          ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        }
      </button>
      {open && diff.diff && (
        <div className="border-t">
          <YamlDiffViewer diff={diff.diff} />
        </div>
      )}
      {open && !diff.diff && (
        <p className="px-4 py-3 text-xs text-muted-foreground border-t italic">No diff content</p>
      )}
    </div>
  );
}

// ── Edit MR panel ─────────────────────────────────────────────────────────────

function EditMRPanel({
  diffs, repo, mrIid, onDone,
}: {
  diffs: FileDiff[];
  repo: string;
  mrIid: number;
  onDone: () => void;
}) {
  const editableDiffs = diffs.filter((d) => !d.deleted_file && d.diff);

  // Extract current content of each file from the MR diff (+lines = proposed content)
  const extractContent = (d: FileDiff) =>
    d.diff.split("\n")
      .filter((l) => l.startsWith("+") && !l.startsWith("+++"))
      .map((l) => l.slice(1))
      .join("\n");

  const [fileContents, setFileContents] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of editableDiffs) {
      init[d.new_path] = extractContent(d);
    }
    return init;
  });
  const [message, setMessage] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);

  const updateMutation = useMutation({
    mutationFn: () =>
      api.put<{ mr: MRDetail; diffs: FileDiff[] }>(
        `/api/${repo}/approvals/${mrIid}`,
        {
          files: Object.entries(fileContents).map(([path, content]) => ({ path, content })),
          message: message || undefined,
        }
      ),
    onSuccess: () => {
      toast.success("Changes submitted — awaiting re-approval");
      setReviewOpen(false);
      onDone();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  if (editableDiffs.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
        No editable files in this MR.
      </div>
    );
  }

  // Build a combined diff of all edited files for the review dialog
  const reviewDiff = editableDiffs
    .map((d) => {
      const original = extractContent(d);
      const edited = fileContents[d.new_path] ?? "";
      const fileDiff = computeLineDiff(original, edited);
      if (!fileDiff) return null;
      return `--- a/${d.new_path}\n+++ b/${d.new_path}\n${fileDiff.split("\n").slice(2).join("\n")}`;
    })
    .filter(Boolean)
    .join("\n\n");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Edit MR Files</h2>
        <button onClick={onDone} className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
      <input
        type="text"
        placeholder="Commit message (optional)"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
      {editableDiffs.map((d) => (
        <div key={d.new_path} className="space-y-1.5">
          <label className="text-xs font-mono font-medium text-muted-foreground">{d.new_path}</label>
          <textarea
            className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-3 rounded-lg min-h-[200px] focus:outline-none resize-y leading-5"
            value={fileContents[d.new_path] ?? ""}
            onChange={(e) => setFileContents((prev) => ({ ...prev, [d.new_path]: e.target.value }))}
            spellCheck={false}
          />
        </div>
      ))}
      <button
        onClick={() => setReviewOpen(true)}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-60"
      >
        <Eye className="h-4 w-4" />
        Review & Submit Changes
      </button>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title="Review: Edit MR Files"
        description={
          reviewDiff
            ? "Changed lines are highlighted. Green = added, red = removed. Submitting pushes a new commit to the MR branch and requires re-approval."
            : "No changes detected — the files are identical to the current MR content."
        }
        diff={reviewDiff || undefined}
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
        confirmLabel="Submit Changes"
      >
        {!reviewDiff && (
          <p className="text-sm text-muted-foreground italic text-center py-4">Nothing changed.</p>
        )}
      </ReviewDialog>
    </div>
  );
}

// ── MR detail page ────────────────────────────────────────────────────────────

function MRDetailContent() {
  const params = useParams();
  const id = params.id as string;
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [approveReviewOpen, setApproveReviewOpen] = useState(false);
  const [rejectReviewOpen, setRejectReviewOpen] = useState(false);

  const match = id.match(/^(day[12])-(\d+)$/);
  const repo = match?.[1] ?? "";
  const mrIid = parseInt(match?.[2] ?? "0", 10);

  const { data, isLoading, error, refetch } = useQuery<MRDetailResponse>({
    queryKey: ["approvals", repo, mrIid],
    queryFn: () => api.get<MRDetailResponse>(`/api/${repo}/approvals/${mrIid}`),
    enabled: Boolean(repo && mrIid),
    staleTime: 15_000,
  });

  const approveMutation = useMutation({
    mutationFn: () => api.post(`/api/${repo}/approvals/${mrIid}/approve`, {}),
    onSuccess: () => {
      toast.success("MR approved and merged");
      setApproveReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      refetch();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  const rejectMutation = useMutation({
    mutationFn: () => api.post(`/api/${repo}/approvals/${mrIid}/reject`, {}),
    onSuccess: () => {
      toast.success("MR rejected");
      setRejectReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      refetch();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  if (!match) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Invalid MR ID format: <code>{id}</code>. Expected format: day1-123 or day2-456.
        </div>
      </div>
    );
  }

  const mr = data?.mr;
  const diffs = data?.diffs ?? [];

  const stateColor = mr?.state === "merged"
    ? "text-[#9b51e0] bg-[#9b51e0]/10"
    : mr?.state === "closed"
    ? "text-[#df2f4a] bg-[#df2f4a]/10"
    : "text-[#00c875] bg-[#00c875]/10";

  const repoCls = repo === "day1"
    ? "bg-[#0073ea]/10 text-[#0073ea]"
    : "bg-[#00c875]/10 text-[#007038] dark:text-[#00c875]";

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/approvals" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1 min-w-0">
          {isLoading ? (
            <Skeleton className="h-7 w-64" />
          ) : (
            <h1
              className="text-2xl font-bold tracking-tight truncate"
              style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
            >
              {mr?.title}
            </h1>
          )}
        </div>
        {mr && (
          <a
            href={mr.web_url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "ghost", size: "icon" })}
            title="Open in GitLab"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </div>

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load MR. Please try again.
        </div>
      ) : isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
        </div>
      ) : mr ? (
        <>
          {/* MR Meta card */}
          <div className="bg-card rounded-xl border shadow-sm p-5 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", stateColor)}>
                {mr.state === "merged"
                  ? <GitMerge className="h-3 w-3" />
                  : <GitPullRequest className="h-3 w-3" />}
                {mr.state}
              </span>
              <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", repoCls)}>{repo}</span>
              {mr.labels.map((l) => (
                <span key={l} className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground">{l}</span>
              ))}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Author</p>
                <p className="font-medium">{mr.author.username}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Created</p>
                <p className="font-medium">{new Date(mr.created_at).toLocaleDateString("en-GB")}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Source branch</p>
                <p className="font-mono text-xs font-medium truncate">{mr.source_branch}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Target branch</p>
                <p className="font-mono text-xs font-medium">{mr.target_branch}</p>
              </div>
            </div>

            {mr.description && (
              <p className="text-sm text-muted-foreground border-t pt-3">{mr.description}</p>
            )}

            {/* Action buttons */}
            {isAdmin && mr.state === "opened" && !editing && (
              <div className="flex gap-2 pt-1 border-t">
                <button
                  onClick={() => setApproveReviewOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#00c875] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#00b368] transition-colors"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Review & Approve
                </button>
                <button
                  onClick={() => setEditing(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold hover:bg-muted transition-colors"
                >
                  <Edit2 className="h-3.5 w-3.5" />Edit Files
                </button>
                <button
                  onClick={() => setRejectReviewOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 text-destructive px-3 py-1.5 text-xs font-semibold hover:bg-destructive/10 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />Reject
                </button>
              </div>
            )}
          </div>

          {/* Edit panel */}
          {editing && (
            <div className="bg-card rounded-xl border shadow-sm p-5">
              <EditMRPanel
                diffs={diffs}
                repo={repo}
                mrIid={mrIid}
                onDone={() => { setEditing(false); refetch(); }}
              />
            </div>
          )}

          {/* File diffs */}
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Changed Files ({diffs.length})
            </h2>
            {diffs.length === 0 ? (
              <div className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
                No file changes in this MR.
              </div>
            ) : (
              diffs.map((diff, i) => <FileDiffCard key={i} diff={diff} />)
            )}
          </div>
        </>
      ) : null}

      {/* Approve review dialog */}
      <ReviewDialog
        open={approveReviewOpen}
        onOpenChange={setApproveReviewOpen}
        title="Review: Approve & Merge MR"
        description="You are about to approve and merge this MR into the target branch. This action triggers a GitOps sync."
        onConfirm={() => approveMutation.mutate()}
        isPending={approveMutation.isPending}
        confirmLabel="Approve & Merge"
      >
        {mr && (
          <div className="rounded-lg border bg-muted/30 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Title</span>
              <span className="font-semibold">{mr.title}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Author</span>
              <span className="font-medium">{mr.author.username}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Files changed</span>
              <span className="font-medium">{diffs.length}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Merging into</span>
              <span className="font-mono text-xs font-medium">{mr.target_branch}</span>
            </div>
          </div>
        )}
      </ReviewDialog>

      {/* Reject review dialog */}
      <ReviewDialog
        open={rejectReviewOpen}
        onOpenChange={setRejectReviewOpen}
        title="Review: Reject MR"
        description="This will close the MR without merging. The author will need to create a new MR to re-submit."
        onConfirm={() => rejectMutation.mutate()}
        isPending={rejectMutation.isPending}
        confirmLabel="Confirm — Reject MR"
        confirmVariant="destructive"
      >
        {mr && (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Title</span>
              <span className="font-semibold">{mr.title}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Author</span>
              <span className="font-medium">{mr.author.username}</span>
            </div>
          </div>
        )}
      </ReviewDialog>
    </div>
  );
}

export default function MRDetailPage() {
  return (
    <Suspense>
      <MRDetailContent />
    </Suspense>
  );
}
