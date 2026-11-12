"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Link2, Lock, Search, TriangleAlert, X } from "lucide-react";
import { isApiError } from "@/lib/api-client";
import { countCards, filterSections, indexStatus, useQuickLinks, useQuickLinksStatus } from "@/lib/quick-links";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { LinkSection, LinkSectionSkeleton } from "@/components/quick-links/link-section";
import type { QuickLinks } from "@/types";

/** Typing in a field: `/` is a character there, not the shortcut. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** What could not be shown, in one panel: what Wingman could not generate, then the links file's problems. */
function Problems({ data }: { data: QuickLinks }) {
  const file = data.links_file;
  const fileLines = [
    ...(file.state === "invalid" && file.problems.length === 0 ? [`${file.path} could not be read.`] : []),
    ...file.problems,
  ];
  if (data.problems.length === 0 && fileLines.length === 0) return null;
  return (
    <div
      role="status"
      data-testid="quick-links-problems"
      className="rounded-lg border border-status-warning/40 bg-status-warning/10 px-3.5 py-3 text-sm text-status-warning-fg"
    >
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div className="min-w-0 space-y-2">
          {data.problems.length > 0 && (
            <ul className="space-y-0.5">
              {data.problems.map((line, i) => (
                <li key={i} className="break-words">{line}</li>
              ))}
            </ul>
          )}
          {fileLines.length > 0 && (
            <div>
              <p className="font-medium">The links file has problems; the rest is shown.</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {fileLines.map((line, i) => (
                  <li key={i} className="break-words font-mono text-xs">{line}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Quick Links (ADR-0052): the hub Wingman runs on and every MCE, each with
 * its ArgoCD and console, then the team's own links from the links file.
 * day1 checks every link and reads each ArgoCD that has a token; the browser
 * only opens links. Admins only, for now.
 */
export default function QuickLinksPage() {
  const [search, setSearch] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { data, isLoading, error } = useQuickLinks();
  const hasCards = Boolean(data && countCards(data.sections) > 0);
  const status = useQuickLinksStatus(hasCards);
  const index = useMemo(() => indexStatus(status.data), [status.data]);

  // `/` focuses the search from anywhere on the page, as on the team's dashboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      e.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sections = useMemo(() => filterSections(data?.sections ?? [], search), [data, search]);
  const total = data ? countCards(data.sections) : 0;
  const shown = countCards(sections);
  const filtering = search.trim() !== "";
  const forbidden = isApiError(error, "FORBIDDEN");

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 p-6 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Quick Links
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground" data-testid="quick-links-summary">
            {data
              ? filtering
                ? `${shown} of ${total} link${total === 1 ? "" : "s"} match`
                : `${total} link${total === 1 ? "" : "s"} in ${data.sections.length} section${data.sections.length === 1 ? "" : "s"}. Wingman checks each one; your browser never does.`
              : "The hub, every MCE, and the team's links"}
          </p>
        </div>
        {!forbidden && (
          <div className="relative w-full sm:w-80">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              ref={input}
              type="search"
              aria-label="Search links"
              placeholder="Search links..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Escape") return;
                if (search) setSearch("");
                else e.currentTarget.blur();
              }}
              className="w-full rounded-lg border bg-card py-1.5 pl-8 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 [&::-webkit-search-cancel-button]:hidden"
            />
            {search ? (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => {
                  setSearch("");
                  input.current?.focus();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : (
              <kbd
                aria-hidden
                className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border bg-muted px-1.5 font-mono text-[10px] leading-4 text-muted-foreground"
              >
                /
              </kbd>
            )}
          </div>
        )}
      </div>

      {forbidden ? (
        <EmptyState
          icon={Lock}
          bordered
          title="For admins"
          description="Quick Links is for Wingman's admins for now, until Wingman has finer roles."
          data-testid="quick-links-forbidden"
        />
      ) : error ? (
        <ProblemList error={error} title="Quick Links could not be loaded" />
      ) : isLoading || !data ? (
        <div className="space-y-8">
          <LinkSectionSkeleton cards={1} />
          <LinkSectionSkeleton />
        </div>
      ) : (
        <>
          <Problems data={data} />
          {data.sections.length === 0 ? (
            <EmptyState
              icon={Link2}
              bordered
              title="No links yet"
              description="Name the hub (QUICK_LINKS_HUB_NAME) and the apps domain (QUICK_LINKS_DOMAIN, or MCE_API_DOMAIN) to list the hub and every MCE, and add the team's links to the links file (the chart's quickLinks.sections)."
              data-testid="quick-links-empty"
            />
          ) : sections.length === 0 ? (
            <NoMatches what="links" onClear={() => setSearch("")} clearLabel="Clear search" bordered data-testid="quick-links-no-matches" />
          ) : (
            <div className="space-y-8">
              {sections.map((section) => (
                <LinkSection key={section.id} section={section} status={index} statusLoading={status.isLoading} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
