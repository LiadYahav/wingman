"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, ExternalLink, GitPullRequest, Info } from "lucide-react";
import { approvalHref } from "@/lib/approvals";
import { AMBIGUOUS_WRITE_HINT } from "@/lib/write-errors";
import { cn } from "@/lib/utils";
import type { ImportFailure, ImportResult } from "@/types";

/** What a cluster's failed MR means for the person who asked for it, by its problem code. */
function meaning(code: string): string {
  switch (code) {
    case "AMBIGUOUS_WRITE":
      return AMBIGUOUS_WRITE_HINT;
    case "GIT_UNAVAILABLE":
      return "Nothing was sent for it. Import it again once GitLab answers.";
    case "REVISION_CONFLICT":
      return "Its file changed since the preview, so nothing was written. Preview it again.";
    default:
      return "GitLab refused its merge request, so nothing was written for it.";
  }
}

function Failure({ failure: f }: { failure: ImportFailure }) {
  const unconfirmed = f.code === "AMBIGUOUS_WRITE";
  return (
    <li
      data-testid={`import-failed-${f.name}`}
      data-code={f.code}
      className={cn(
        "space-y-1 rounded-md border p-2.5",
        unconfirmed ? "border-status-warning/30 bg-status-warning/5" : "border-destructive/30 bg-destructive/5"
      )}
    >
      <p className="text-sm font-semibold break-all">{f.name}</p>
      <p className="text-xs text-muted-foreground break-all">
        {f.site} / {f.mce}
      </p>
      <p className={cn("text-xs", unconfirmed ? "text-status-warning-fg" : "text-destructive")}>{meaning(f.code)}</p>
      {f.detail && <p className="font-mono text-[11px] text-muted-foreground break-words">{f.detail}</p>}
    </li>
  );
}

/**
 * Step three: what the import opened (`POST /specs/{name}/import`, ADR-0044).
 * One MR per cluster, each reviewed on its own; the clusters whose MR did
 * not open are listed apart, with what that means.
 */
export function ResultStep({ flavor, result }: { flavor: string; result: ImportResult }) {
  const { merge_requests: opened, failed } = result;
  return (
    <div className="space-y-4" data-testid="import-result">
      <div className="flex items-start gap-2.5">
        <GitPullRequest className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <div className="space-y-1">
          <h3 className="text-sm font-semibold" data-testid="import-result-heading">
            {opened.length === 1 ? "1 merge request opened" : `${opened.length} merge requests opened`}
            <span className="font-normal text-muted-foreground"> · waiting for approval</span>
          </h3>
          <p className="text-xs text-muted-foreground">
            One per cluster: each is approved, merged or rejected on its own, and a cluster follows {flavor} v
            {result.spec_version} once its own merge request merges.
          </p>
        </div>
      </div>

      <ul className="space-y-2" aria-label="Opened merge requests">
        {opened.map(({ name, site, mce, merge_request: mr }) => (
          <li
            key={`${mr.repo}-${mr.iid}`}
            data-testid={`import-opened-${name}`}
            className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5 rounded-lg border p-3"
          >
            <div className="min-w-0 space-y-0.5">
              <p className="text-sm font-semibold break-all">{name}</p>
              <p className="text-xs text-muted-foreground break-all">
                {site} / {mce}
              </p>
              <p className="text-xs break-words">
                <span className="font-mono text-muted-foreground">!{mr.iid}</span> {mr.title}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-3 text-xs font-medium">
              <Link
                href={approvalHref(mr)}
                className="inline-flex items-center gap-0.5 text-primary hover:underline"
                aria-label={`Review !${mr.iid} for ${name}`}
              >
                Review
                <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
              <a
                href={mr.web_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
                aria-label={`Open !${mr.iid} for ${name} in GitLab`}
              >
                GitLab
                <ExternalLink className="h-3 w-3" aria-hidden />
              </a>
            </div>
          </li>
        ))}
      </ul>

      {failed.length > 0 && (
        <section role="alert" aria-label="Not opened" className="space-y-2" data-testid="import-failed">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />
            {failed.length === 1 ? "1 cluster's merge request" : `${failed.length} clusters' merge requests`} did not
            open
          </p>
          <ul className="space-y-2">
            {failed.map((f) => (
              <Failure key={`${f.site}/${f.mce}/${f.name}`} failure={f} />
            ))}
          </ul>
        </section>
      )}

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Until a cluster&apos;s merge request merges, it does not follow the flavor: importing it again opens a second
        merge request.
      </p>
    </div>
  );
}
