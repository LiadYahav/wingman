"use client";

import { ProblemList } from "@/components/common/problem-list";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { AMBIGUOUS_WRITE_HINT, isAmbiguousWrite, problemOf } from "@/lib/day2";
import { asNewFile, computeFullFileDiff } from "@/lib/diff";
import { cn } from "@/lib/utils";

/** A file a change will write, as the review dialog shows it before the MR opens. */
export interface PlannedFile {
  action: "create" | "update" | "delete";
  path: string;
  /** The content today (update, delete). */
  before?: string;
  /** The content after (create, update). */
  after?: string;
}

const LABEL: Record<PlannedFile["action"], [string, string]> = {
  create: ["New", "bg-status-ready/12 text-status-ready-fg"],
  update: ["Modified", "bg-primary/12 text-primary"],
  delete: ["Deleted", "bg-status-error/12 text-status-error-fg"],
};

export function FilePreview({ file }: { file: PlannedFile }) {
  const [label, tone] = LABEL[file.action];
  const diff =
    file.action === "create"
      ? file.after
        ? asNewFile(file.after.trimEnd())
        : ""
      : file.action === "update"
        ? computeFullFileDiff(file.before ?? "", file.after ?? "")
        : "";
  return (
    <div className="space-y-1">
      <p className="flex items-start gap-2 text-xs">
        <span className={cn("shrink-0 rounded px-1.5 py-px text-[10px] font-semibold uppercase", tone)}>{label}</span>
        <code className="break-all font-mono text-[11px] text-foreground">{file.path}</code>
      </p>
      {file.action === "delete" ? null : diff ? (
        <YamlDiffViewer diff={diff} className="max-h-64" />
      ) : (
        <p className="rounded-lg border border-dashed px-3 py-2 text-center text-xs italic text-muted-foreground">
          {file.action === "create" ? "Empty file: every value is inherited" : "No change to this file"}
        </p>
      )}
    </div>
  );
}

/** What a refused write means beyond its detail: an unconfirmed one (ADR-0006) may have happened. */
function refusalTitle(error: unknown): string {
  return isAmbiguousWrite(problemOf(error)) ? AMBIGUOUS_WRITE_HINT : "The change was refused";
}

/**
 * Why the service refused the change, inside the dialog that asked for it.
 * `error` is the thrown error itself, shown in full (every broken rule and
 * the request id); `message` is a sentence already made from one.
 */
export function WriteError({ error, message }: { error?: unknown; message?: string }) {
  if (error) return <ProblemList error={error} title={refusalTitle(error)} />;
  if (!message) return null;
  return (
    <p role="alert" className="whitespace-pre-line break-words rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
      {message}
    </p>
  );
}

export function MessageField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="block space-y-1 text-xs">
      <span className="font-medium text-muted-foreground">Note for the approver (optional, goes in the MR)</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        maxLength={2000}
        className="w-full resize-y rounded-lg border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    </label>
  );
}
