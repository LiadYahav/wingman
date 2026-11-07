"use client";

import { useEffect, useRef } from "react";
import { ExternalLink, GitPullRequest, X } from "lucide-react";
import { FindingsList } from "@/components/addons/findings";
import { cn } from "@/lib/utils";
import type { BulkResult, ChangeResult } from "@/types/day2";

/** What the last write on the page opened: one MR, or one per team for a bulk install. */
export interface OpenedChanges {
  verb: "Install" | "Update" | "Remove";
  results: ChangeResult[];
  failed: BulkResult["failed"];
}

const ACTION_TONE: Record<string, string> = {
  create: "bg-status-ready/12 text-status-ready-fg",
  update: "bg-primary/12 text-primary",
  delete: "bg-status-error/12 text-status-error-fg",
};

/**
 * The MRs a change opened, with the service's notes: what else it registers,
 * that nothing deploys until someone syncs, and that a removal orphans the
 * workload. Stays until dismissed, because the notes are the point.
 */
export function ChangeResultPanel({ changes, onDismiss }: { changes: OpenedChanges; onDismiss: () => void }) {
  const { results, failed } = changes;
  const ref = useRef<HTMLElement>(null);
  // The write was confirmed in a dialog further down the page: bring its outcome into view.
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [changes]);
  return (
    <section
      ref={ref}
      aria-label="Opened merge requests"
      className="scroll-mt-4 rounded-xl border border-primary/30 bg-primary/[0.04] p-4 shadow-sm animate-in fade-in slide-in-from-top-1 duration-200"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <GitPullRequest className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">
            {results.length === 1 ? "Merge request opened" : `${results.length} merge requests opened`}
            <span className="font-normal text-muted-foreground"> · waiting for approval</span>
          </h2>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-3 space-y-4">
        {results.map((mr) => (
          <article key={`${mr.team}!${mr.iid}`} className="space-y-2">
            <a
              href={mr.web_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex max-w-full items-center gap-1.5 text-sm font-medium hover:text-primary"
            >
              <span className="shrink-0 font-mono text-muted-foreground group-hover:text-primary">
                {mr.team} !{mr.iid}
              </span>
              <span className="truncate">{mr.title}</span>
              <ExternalLink className="h-3.5 w-3.5 shrink-0 opacity-60" />
            </a>
            <ul className="space-y-0.5">
              {mr.files.map((f) => (
                <li key={`${f.action}|${f.path}`} className="flex items-start gap-2 text-xs">
                  <span
                    className={cn(
                      "w-12 shrink-0 rounded px-1 text-center text-[10px] font-medium uppercase leading-4",
                      ACTION_TONE[f.action] ?? "bg-muted text-muted-foreground",
                    )}
                  >
                    {f.action}
                  </span>
                  <code className="break-all font-mono text-[11px] text-muted-foreground">{f.path}</code>
                </li>
              ))}
            </ul>
            <FindingsList findings={mr.warnings} />
            {mr.notes.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-xs text-foreground/90 marker:text-muted-foreground">
                {mr.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
          </article>
        ))}
        {failed.length > 0 && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs">
            <p className="font-medium text-destructive">Not opened (the others were):</p>
            <ul className="mt-1 space-y-0.5">
              {failed.map((f) => (
                <li key={f.team}>
                  <span className="font-medium">{f.team}</span>: {f.detail || f.error}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
