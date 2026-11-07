"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ExternalLink, GitMerge, GitPullRequest, X, ChevronDown, ChevronRight,
  FilePlus, FileX, FileEdit, Edit2, Eye, RotateCcw, UserX,
} from "lucide-react";
import { toast } from "sonner";
import { api, isApiError } from "@/lib/api-client";
import { approvalApiPath, parseApprovalId, type MRRef } from "@/lib/approvals";
import { useAuthStore, useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { ReviewDialog } from "@/components/common/review-dialog";
import { ProblemList } from "@/components/common/problem-list";
import { RepoBadge } from "@/components/common/repo-badge";
import { computeLineDiff } from "@/lib/diff";
import type { ApprovalDetail, FileDiff, MRDetail, UpdateMRFile } from "@/types";

/** 409 REVISION_CONFLICT on approve or edit: the head is not the one reviewed. */
const BRANCH_MOVED =
  "The branch moved since you loaded this MR (CI or the allocate-segment workflow pushed to it). Nothing was merged. Reload and review the new diff again.";

// ── File diff card ─────────────────────────────────────────────────────────────

function FileDiffCard({ diff }: { diff: FileDiff }) {
  const [open, setOpen] = useState(true);

  const badge = diff.new_file
    ? { label: "new", cls: "bg-status-ready/10 text-status-ready-fg" }
    : diff.deleted_file
    ? { label: "deleted", cls: "bg-status-error/10 text-status-error" }
    : diff.renamed_file
    ? { label: "renamed", cls: "bg-status-warning/10 text-status-warning-fg" }
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
        <span className="flex-1 text-sm font-mono font-medium truncate" title={filePath}>{filePath}</span>
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

/**
 * A new file's diff is its whole content. A changed file's diff holds only
 * hunks, so rebuilding it from the diff would drop every line outside them:
 * only files the MR adds are editable here.
 */
function newFileContent(d: FileDiff): string {
  const body = d.diff.split("\n")
    .filter((l) => l.startsWith("+") && !l.startsWith("+++"))
    .map((l) => l.slice(1))
    .join("\n");
  return d.diff.includes("\\ No newline at end of file") ? body : `${body}\n`;
}

function EditMRPanel({
  mr, mrRef, diffs, onSaved, onCancel,
}: {
  mr: MRDetail;
  mrRef: MRRef;
  diffs: FileDiff[];
  onSaved: (detail: ApprovalDetail) => void;
  onCancel: () => void;
}) {
  const editableDiffs = diffs.filter((d) => d.new_file && d.diff);
  const lockedCount = diffs.filter((d) => !d.deleted_file && !d.new_file).length;

  const [fileContents, setFileContents] = useState<Record<string, string>>(() =>
    Object.fromEntries(editableDiffs.map((d) => [d.new_path, newFileContent(d)]))
  );
  const [message, setMessage] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);

  const updateMutation = useMutation({
    mutationFn: () => {
      const files: UpdateMRFile[] = editableDiffs
        .filter((d) => fileContents[d.new_path] !== newFileContent(d))
        .map((d) => ({ path: d.new_path, content: fileContents[d.new_path] ?? "" }));
      // day1 refuses the commit if the branch moved past the head reviewed here
      const body = mrRef.service === "day1" ? { files, message, sha: mr.sha } : { files, message };
      return api.put<ApprovalDetail>(approvalApiPath(mrRef), body);
    },
    onSuccess: (detail) => {
      toast.success("Changes committed to the MR branch — review them again before approving");
      setReviewOpen(false);
      onSaved(detail);
    },
    onError: (e) => {
      setReviewOpen(false);
      setSaveError(e);
    },
  });

  // A combined diff of the edited files for the review dialog
  const reviewDiff = editableDiffs
    .map((d) => {
      const fileDiff = computeLineDiff(newFileContent(d), fileContents[d.new_path] ?? "");
      if (!fileDiff) return null;
      return `--- a/${d.new_path}\n+++ b/${d.new_path}\n${fileDiff.split("\n").slice(2).join("\n")}`;
    })
    .filter(Boolean)
    .join("\n\n");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Edit MR Files</h2>
        <button onClick={onCancel} aria-label="Close editor" className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
      {lockedCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {lockedCount} changed file{lockedCount !== 1 ? "s" : ""} can only be edited{" "}
          <a href={mr.web_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">in GitLab</a>:
          the diff holds only the changed lines, not the whole file.
        </p>
      )}
      {saveError !== null && (
        isApiError(saveError, "REVISION_CONFLICT")
          ? <ProblemList error={saveError} title={BRANCH_MOVED} />
          : <ProblemList error={saveError} title="The edit was refused" />
      )}
      {editableDiffs.length === 0 ? (
        <div className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
          No file in this MR can be edited here.
        </div>
      ) : (
        <>
          <input
            type="text"
            placeholder="Commit message (optional)"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          {editableDiffs.map((d) => (
            <div key={d.new_path} className="space-y-1.5">
              <label htmlFor={`edit-${d.new_path}`} className="text-xs font-mono font-medium text-muted-foreground break-all">{d.new_path}</label>
              <textarea
                id={`edit-${d.new_path}`}
                className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-3 rounded-lg min-h-[200px] focus:outline-none resize-y leading-5"
                value={fileContents[d.new_path] ?? ""}
                onChange={(e) => setFileContents((prev) => ({ ...prev, [d.new_path]: e.target.value }))}
                spellCheck={false}
              />
            </div>
          ))}
          <button
            onClick={() => { setSaveError(null); setReviewOpen(true); }}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            <Eye className="h-4 w-4" />
            Review & Submit Changes
          </button>
        </>
      )}

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title="Review: Edit MR Files"
        description={
          reviewDiff
            ? "Changed lines are highlighted. Submitting adds a commit on top of the MR branch (never a force-push); the MR then needs a fresh review."
            : "No changes detected — the files are identical to the current MR content."
        }
        diff={reviewDiff || undefined}
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
        confirmLabel="Submit Changes"
        pendingLabel="Committing to the MR branch…"
        confirmDisabled={!reviewDiff}
      >
        {!reviewDiff && (
          <p className="text-sm text-muted-foreground italic text-center py-4">Nothing changed.</p>
        )}
      </ReviewDialog>
    </div>
  );
}

// ── MR detail page ────────────────────────────────────────────────────────────

function ActionError({ error, onReload }: { error: unknown; onReload: () => void }) {
  if (isApiError(error, "REVISION_CONFLICT")) {
    return (
      <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
        <p className="text-status-warning-fg">{BRANCH_MOVED}</p>
        <button onClick={onReload} className={buttonVariants({ variant: "outline", size: "sm" })}>
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Reload
        </button>
      </div>
    );
  }
  if (isApiError(error, "SELF_APPROVAL")) {
    return <ProblemList error={error} title="You requested this change, so another admin must approve it." />;
  }
  if (isApiError(error, "NOT_MERGEABLE")) {
    return <ProblemList error={error} title="GitLab cannot merge this MR right now" />;
  }
  return <ProblemList error={error} title="The action failed" />;
}

function MRDetailContent() {
  const params = useParams();
  const id = params.id as string;
  const isAdmin = useIsAdmin();
  const username = useAuthStore((s) => s.user?.username);
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  // The head shown when the approve dialog opened; kept after close for the exit animation.
  const [reviewedSha, setReviewedSha] = useState("");
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectReviewOpen, setRejectReviewOpen] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const ref = parseApprovalId(id);
  const queryKey = ["approvals", "detail", id];

  // No background refetch: an approval names the head shown here, so the diff
  // must not change under the reviewer. A moved branch is a 409 and a reload.
  const { data, isLoading, error, refetch } = useQuery<ApprovalDetail>({
    queryKey,
    queryFn: () => api.get<ApprovalDetail>(approvalApiPath(ref!)),
    enabled: ref !== null,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });

  const afterChange = () => {
    queryClient.invalidateQueries({ queryKey: ["approvals"] });
    queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const approveMutation = useMutation({
    mutationFn: (sha: string) => api.post<MRDetail>(approvalApiPath(ref!, "approve"), { sha }),
    onSuccess: (mr) => {
      toast.success(`!${mr.iid} approved and merged`);
      setApproveOpen(false);
      afterChange();
      // What the merge changed
      queryClient.invalidateQueries({ queryKey: ref?.service === "day2" ? ["clusters"] : ref?.repo === "specs" ? ["specs"] : ["clusters"] });
      refetch();
    },
    onError: (e) => {
      setApproveOpen(false);
      setActionError(e);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => api.post<MRDetail>(approvalApiPath(ref!, "reject")),
    onSuccess: (mr) => {
      toast.success(`!${mr.iid} rejected`);
      setRejectReviewOpen(false);
      afterChange();
      refetch();
    },
    onError: (e) => {
      setRejectReviewOpen(false);
      setActionError(e);
    },
  });

  const reload = async () => {
    setActionError(null);
    setEditing(false);
    await refetch();
  };

  if (!ref) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive break-words">
          Invalid MR ID: <code>{id}</code>. Expected <code>day1-123</code>, <code>specs-45</code> or <code>day2-&lt;team&gt;-67</code>.
        </div>
      </div>
    );
  }

  const mr = data?.mr;
  const diffs = data?.diffs ?? [];
  const isOwnChange = Boolean(mr && username && mr.author.username === username);

  const stateColor = mr?.state === "merged"
    ? "text-chart-5 bg-chart-5/10"
    : mr?.state === "closed"
    ? "text-status-error bg-status-error/10"
    : "text-status-ready bg-status-ready/10";

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
              title={mr?.title}
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
        <ProblemList error={error} title={isApiError(error, 404) ? "This merge request does not exist or is not a Wingman MR" : "Failed to load the MR"} />
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
              <RepoBadge repo={mr.repo} team={mr.team} className="px-2.5 py-1" />
              {mr.has_conflicts === true && (
                <span className="rounded-full px-2.5 py-1 text-xs font-semibold bg-status-error/10 text-status-error">
                  Conflicted
                </span>
              )}
              {mr.labels.map((l) => (
                <span key={l} className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground">{l}</span>
              ))}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 text-sm">
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground mb-0.5">Author</p>
                <p className="font-medium truncate">{mr.author.username}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">{mr.merged_at ? "Merged" : "Created"}</p>
                <p className="font-medium">{new Date(mr.merged_at ?? mr.created_at).toLocaleDateString("en-GB")}</p>
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground mb-0.5">Source branch</p>
                <p className="font-mono text-xs font-medium truncate" title={mr.source_branch}>{mr.source_branch}</p>
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground mb-0.5">Target branch</p>
                <p className="font-mono text-xs font-medium truncate">{mr.target_branch}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Head</p>
                <p className="font-mono text-xs font-medium" title={mr.sha}>{mr.sha.slice(0, 8)}</p>
              </div>
            </div>

            {mr.description && (
              <p className="text-sm text-muted-foreground border-t pt-3 whitespace-pre-line break-words">{mr.description}</p>
            )}

            {isAdmin && mr.state === "opened" && !editing && (
              <div className="flex flex-wrap items-center gap-2 pt-3 border-t">
                <button
                  onClick={() => { setActionError(null); setReviewedSha(mr.sha); setApproveOpen(true); }}
                  disabled={isOwnChange}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-status-ready px-3 py-1.5 text-xs font-semibold text-white hover:bg-status-ready/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Review & Approve
                </button>
                <button
                  onClick={() => { setActionError(null); setEditing(true); }}
                  className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold hover:bg-muted transition-colors"
                >
                  <Edit2 className="h-3.5 w-3.5" />Edit Files
                </button>
                <button
                  onClick={() => { setActionError(null); setRejectReviewOpen(true); }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 text-destructive px-3 py-1.5 text-xs font-semibold hover:bg-destructive/10 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />Reject
                </button>
                {isOwnChange && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    <UserX className="h-3.5 w-3.5" />You requested this change; another admin approves it.
                  </span>
                )}
              </div>
            )}
          </div>

          {actionError !== null && <ActionError error={actionError} onReload={reload} />}

          {editing && (
            <div className="bg-card rounded-xl border shadow-sm p-5">
              <EditMRPanel
                mr={mr}
                mrRef={ref}
                diffs={diffs}
                onSaved={(detail) => { queryClient.setQueryData(queryKey, detail); setEditing(false); afterChange(); }}
                onCancel={() => setEditing(false)}
              />
            </div>
          )}

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

      {/* Approve: names the head shown on this page when the dialog opened */}
      <ReviewDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="Review: Approve & Merge MR"
        description="You are about to approve and merge exactly the commit reviewed here. If anything was pushed to the branch since, nothing is merged and you are asked to review again."
        onConfirm={() => approveMutation.mutate(reviewedSha)}
        isPending={approveMutation.isPending}
        confirmLabel="Approve & Merge"
        pendingLabel="Approving and merging…"
      >
        {mr && (
          <div className="rounded-lg border bg-muted/30 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Title</span>
              <span className="font-semibold break-words min-w-0">{mr.title}</span>
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
              <span className="text-muted-foreground w-28 shrink-0">Commit</span>
              <span className="font-mono text-xs font-medium">{reviewedSha.slice(0, 12)}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Merging into</span>
              <span className="font-mono text-xs font-medium">{mr.target_branch}</span>
            </div>
          </div>
        )}
      </ReviewDialog>

      <ReviewDialog
        open={rejectReviewOpen}
        onOpenChange={setRejectReviewOpen}
        title="Review: Reject MR"
        description="This closes the MR without merging. The requester opens a new one to try again."
        onConfirm={() => rejectMutation.mutate()}
        isPending={rejectMutation.isPending}
        confirmLabel="Confirm — Reject MR"
        confirmVariant="destructive"
        pendingLabel="Closing the MR…"
      >
        {mr && (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-2">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">Title</span>
              <span className="font-semibold break-words min-w-0">{mr.title}</span>
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
