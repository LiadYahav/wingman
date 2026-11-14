"use client";

import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { useServerScanClassificationRules, useServerScanHealthPolicies } from "@/lib/api/server-scan";
import { Blocked, isBlocked } from "./blocked";
import { PolicySections, RulesTable } from "./rules-tables";

/** server-scan's introduction, in the heading's tooltip. */
const ABOUT =
  "The rules and policies this deployment runs, and every deployment gets the same set. They are defined in code and seeded at startup, not created here: a rule that exists in one estate and not another makes two installations that look identical classify the same server differently. Anything disabled is not listed, because it is not something this deployment does.";

function Loading({ testId }: { testId: string }) {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-3" aria-busy="true" data-testid={testId}>
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-7 w-full" />
      ))}
    </div>
  );
}

/** One section of the page: it loads and fails on its own, as in server-scan. */
function Section<T>({
  title,
  description,
  query,
  what,
  testId,
  children,
}: {
  title: string;
  description: ReactNode;
  query: UseQueryResult<T>;
  /** The section's items, in the problem's title. */
  what: string;
  testId: string;
  children: (data: T) => ReactNode;
}) {
  return (
    <section aria-label={title} className="space-y-3" data-testid={testId}>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      </div>
      {query.isPending ? (
        <Loading testId={`${testId}-loading`} />
      ) : query.data === undefined ? (
        <ProblemList error={query.error} title={`The ${what} could not be loaded from server-scan`} />
      ) : (
        <>
          {query.error !== null && <ProblemList error={query.error} title="The last read failed; this is the read before it" />}
          {children(query.data)}
        </>
      )}
    </section>
  );
}

/**
 * The Server Scan area's Rules & Policies page (ADR-0048's 3.30.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §13): server-scan's enabled
 * classification rules and health policies, its sections, columns, groups
 * and words, in Wingman's design. Read only. Read on open and again when
 * opened after 30 seconds, as the original; never polled.
 */
export function RulesPage() {
  const rules = useServerScanClassificationRules();
  const policies = useServerScanHealthPolicies();
  const blocking = [rules.error, policies.error].find(isBlocked);
  return (
    <div className="mx-auto max-w-7xl space-y-8 p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-1">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Rules &amp; Policies
          </h1>
          <Hint hint={ABOUT} label="About Rules & Policies" testId="ss-rules-about">
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">What this deployment of server-scan runs, read only. Disabled ones are not listed.</p>
      </header>
      {blocking !== undefined ? (
        <Blocked error={blocking} />
      ) : (
        <>
          <Section
            title="Classification rules"
            description="Assign an installation type (HOSTED_CLUSTER / MCE / UPI / UNCLASSIFIED) from a server's own fields."
            query={rules}
            what="classification rules"
            testId="ss-rules"
          >
            {(data) => <RulesTable rules={data.items} />}
          </Section>
          <Section
            title="Health policies"
            description={
              <>
                Assign per-category and overall health severity. Within one <code className="font-mono text-xs">policy_key</code> the
                highest-priority enabled policy wins and the rest are shadowed.
              </>
            }
            query={policies}
            what="health policies"
            testId="ss-policies"
          >
            {(data) => <PolicySections policies={data.items} />}
          </Section>
        </>
      )}
    </div>
  );
}
