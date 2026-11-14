"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { FileX2 } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isApiError } from "@/lib/api-client";
import { useServerScanDiagram } from "@/lib/api/server-scan-architecture";
import { DIAGRAMS, diagramHref, diagramOf, withTheme, type DiagramSpec } from "@/lib/server-scan/diagrams";
import { Blocked, isBlocked } from "./blocked";

const FRAME = "h-[85vh] w-full rounded-xl border";

/**
 * The diagram shown, read from the URL (`?diagram=`) and written to it. A
 * change replaces the history entry, as the server page's tabs do, so Back
 * leaves the page.
 */
function useDiagram(): [DiagramSpec, (slug: string) => void] {
  const diagram = diagramOf(useSearchParams().get("diagram"));
  const select = useCallback((slug: string) => {
    const href = diagramHref(slug);
    if (href !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", href);
  }, []);
  return [diagram, select];
}

/**
 * server-scan's page as its UI serves it, in a sandboxed frame: its scripts
 * run (pan, zoom, search, its own toolbar) in an origin of their own, so they
 * reach nothing of Wingman's: not its page, its storage or its session.
 * Downloads stay allowed for the diagram's own export.
 */
function DiagramFrame({ spec, html }: { spec: DiagramSpec; html: string }) {
  const { resolvedTheme } = useTheme();
  const theme = resolvedTheme === "light" ? "light" : "dark";
  const srcDoc = useMemo(() => withTheme(html, theme), [html, theme]);
  return (
    <iframe
      title={`${spec.label} architecture diagram`}
      srcDoc={srcDoc}
      sandbox="allow-scripts allow-downloads"
      allow="clipboard-write"
      referrerPolicy="no-referrer"
      className={`${FRAME} bg-card`}
      data-testid="ss-diagram-frame"
      data-diagram={spec.slug}
    />
  );
}

/** The frame's place: the diagram, a skeleton while it loads, or why it is not there. */
function Diagram({ spec }: { spec: DiagramSpec }) {
  const diagram = useServerScanDiagram(spec.slug);
  if (diagram.isPending) {
    return <Skeleton className={FRAME} aria-busy="true" aria-label={`Loading the ${spec.label} diagram`} data-testid="ss-diagram-loading" />;
  }
  if (diagram.data) return <DiagramFrame spec={spec} html={diagram.data.html} />;
  if (isApiError(diagram.error, "NOT_FOUND")) {
    return (
      <EmptyState
        icon={FileX2}
        bordered
        title={`server-scan serves no ${spec.label} diagram`}
        description={diagram.error.detail}
        data-testid="ss-diagram-missing"
      />
    );
  }
  return <ProblemList error={diagram.error} title={`The ${spec.label} diagram could not be loaded from server-scan`} />;
}

/** The picker and the diagram; nothing but why, when the area cannot be shown (403, 501). */
function Diagrams() {
  const [active, select] = useDiagram();
  const probe = useServerScanDiagram(active.slug);
  if (isBlocked(probe.error)) return <Blocked error={probe.error} />;
  return (
    <div className="space-y-3">
      <Tabs value={active.slug} onValueChange={(value) => select(String(value))}>
        <TabsList aria-label="Diagram" className="h-auto flex-wrap justify-start group-data-horizontal/tabs:h-auto">
          {DIAGRAMS.map((d) => (
            <TabsTrigger key={d.slug} value={d.slug} className="flex-none px-2.5 py-1" data-testid={`ss-diagram-tab-${d.slug}`}>
              {d.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <p className="text-sm text-muted-foreground" data-testid="ss-diagram-description">
        {active.description}
      </p>
      <Diagram key={active.slug} spec={active} />
    </div>
  );
}

/**
 * The Server Scan area's Architecture page (ADR-0048's 3.28.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §11): server-scan's
 * diagrams, one per collector plus the full flow, as server-scan serves them
 * (read through day1, never copied), picked as on its page.
 */
export function ArchitecturePage() {
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 lg:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
          Architecture
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          How data moves through the platform — pan, zoom, search and trace each diagram; every fact is sourced from an ADR or the
          provider it names.
        </p>
      </header>
      <Diagrams />
    </div>
  );
}
