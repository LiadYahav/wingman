"use client";

import { AlertTriangle, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RepoFile } from "@/types/day2";

/**
 * A file of the team repo as it is written, comments included: the text
 * Wingman read, never a re-rendering of its parsed values.
 */
export function RepoFileView({
  file,
  absent = "No such file.",
  className,
  maxHeight = "max-h-80",
}: {
  file: RepoFile;
  /** What to say when the file does not exist. */
  absent?: string;
  className?: string;
  maxHeight?: string;
}) {
  return (
    <div className={cn("space-y-1", className)} data-testid={`file-${file.path}`}>
      <p className="flex items-center gap-1.5 text-xs">
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <code className="break-all font-mono text-[11px]">{file.path}</code>
      </p>
      {file.problem && (
        <p className="flex items-start gap-1.5 rounded-lg border border-status-warning/30 bg-status-warning/8 px-3 py-2 text-xs text-status-warning-fg">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">{file.problem}</span>
        </p>
      )}
      {!file.exists ? (
        <p className="rounded-lg border border-dashed px-3 py-2 text-xs italic text-muted-foreground">{absent}</p>
      ) : file.text && file.text.trim() ? (
        <pre
          className={cn("overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed", maxHeight)}
          aria-label={`Contents of ${file.path}`}
        >
          {file.text}
        </pre>
      ) : (
        <p className="rounded-lg border border-dashed px-3 py-2 text-xs italic text-muted-foreground">Empty file.</p>
      )}
    </div>
  );
}
