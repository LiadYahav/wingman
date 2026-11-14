"use client";

import { Download, FileQuestion } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api-client";
import { useServerScanSkill, useSkillDownload } from "@/lib/api/server-scan-skill";
import { allowedTools } from "@/lib/server-scan/skill-text";
import type { SkillAnswer } from "@/types/server-scan-skill";
import { Blocked, isBlocked } from "../blocked";
import { McpSection, SetupSteps } from "./claude-setup";
import { SkillSource } from "./skill-source";

const HEADING = { fontFamily: "var(--font-heading, var(--font-sans))" };

function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" data-testid="ss-skill-loading">
      <Skeleton className="h-8 w-80 max-w-full" />
      <Skeleton className="h-4 w-[32rem] max-w-full" />
      <Skeleton className="h-8 w-48" />
      <div className="space-y-4 rounded-xl border bg-card p-6">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
      </div>
    </div>
  );
}

/** Why there is no skill to show: not an admin or not set up, none on server-scan, or server-scan failing. */
function NoSkill({ error }: { error: unknown }) {
  if (isBlocked(error)) return <Blocked error={error} />;
  if (isApiError(error, "NOT_FOUND")) {
    return (
      <EmptyState
        icon={FileQuestion}
        bordered
        title="No Claude skill"
        description="This server-scan carries no skill, so there is nothing to download or connect."
        data-testid="ss-skill-missing"
      />
    );
  }
  return <ProblemList error={error} title="The skill could not be read from server-scan" />;
}

/** The headline, server-scan's words, and the download: server-scan's zip of the skill, through day1. */
function Hero({ skill }: { skill: SkillAnswer }) {
  const download = useSkillDownload(skill.name);
  return (
    <header className="space-y-3">
      <h1 className="text-2xl font-bold tracking-tight" style={HEADING}>
        Ask Claude about Server Scan
      </h1>
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Install the <span className="font-mono text-foreground">{skill.name}</span> skill in Claude Code and ask in plain
        language. It builds the API calls, pages through the results and answers with real data.
      </p>
      <Button onClick={() => download.mutate()} disabled={download.isPending} data-testid="ss-skill-download">
        <Download aria-hidden />
        Download {skill.name}.zip
      </Button>
      {download.isError && <ProblemList error={download.error} title="The zip could not be downloaded from server-scan" />}
    </header>
  );
}

/** "When Claude uses it" and "What it may run", from the skill's frontmatter. */
function About({ skill }: { skill: SkillAnswer }) {
  return (
    <section className="grid gap-8 md:grid-cols-2">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">When Claude uses it</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{skill.description}</p>
        {skill.when_to_use && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{skill.when_to_use}</p>}
      </div>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">What it may run</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Read-only. The skill is limited to these tools and stays on GET requests.
        </p>
        <p className="mt-3 flex flex-wrap gap-2" data-testid="ss-skill-tools">
          {allowedTools(skill.allowed_tools).map((tool) => (
            <span key={tool} className="rounded-md border bg-muted/40 px-2 py-1 font-mono text-xs text-muted-foreground">
              {tool}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}

function Guide({ skill, error }: { skill: SkillAnswer; error: unknown }) {
  return (
    <>
      {error !== null && <ProblemList error={error} title="The last read failed; this is the read before it" />}
      <Hero skill={skill} />
      <SetupSteps skill={skill} />
      <McpSection serverScanUrl={skill.server_scan_url} />
      <About skill={skill} />
      <SkillSource files={skill.files} />
    </>
  );
}

/**
 * The Server Scan area's Claude page (ADR-0048's 3.27.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §12): server-scan's guide to
 * its Claude Code skill, in Wingman's design and server-scan's words. The
 * skill is server-scan's, read through day1 every minute and on focus, as
 * the original; the download is server-scan's zip; the personal token is
 * made on server-scan's own page, which this one links to.
 */
export function ClaudePage() {
  const skill = useServerScanSkill();
  const blocked = isBlocked(skill.error);
  const data = blocked ? undefined : skill.data;
  return (
    <div className="mx-auto max-w-5xl space-y-10 p-6 lg:p-8">
      {skill.isPending ? (
        <Loading />
      ) : !data ? (
        <>
          <h1 className="text-2xl font-bold tracking-tight" style={HEADING}>
            Claude
          </h1>
          <NoSkill error={skill.error} />
        </>
      ) : (
        <Guide skill={data} error={skill.error} />
      )}
    </div>
  );
}
