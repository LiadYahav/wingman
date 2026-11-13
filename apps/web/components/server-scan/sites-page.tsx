"use client";

import { Lock, ServerOff, Unplug } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { useServerScanSites } from "@/lib/api/server-scan";
import { fleetCards, siteCards, sitesSummary } from "@/lib/server-scan/sites";
import type { SiteStatsList } from "@/types/server-scan";
import { SiteCardSkeleton, SiteCardView } from "./site-card";

const GRID = "grid gap-4 sm:grid-cols-2 lg:grid-cols-3";

/** Why the page cannot show the sites at all: not an admin, or server-scan not configured. */
function Blocked({ error }: { error: unknown }) {
  if (isApiError(error, "FORBIDDEN")) {
    return (
      <EmptyState
        icon={Lock}
        bordered
        title="For admins"
        description="Server Scan is for Wingman's admins for now, until Wingman has finer roles."
        data-testid="ss-forbidden"
      />
    );
  }
  return (
    <EmptyState
      icon={Unplug}
      bordered
      title="Server Scan is not set up"
      description="Wingman shows server-scan's pages once day1 knows where it is: set serverScan.url in the chart (SERVER_SCAN_URL)."
      data-testid="ss-off"
    />
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title}>
      <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

/** server-scan's "N servers across M sites"; Unassigned is not a site. */
function Summary({ data, pending }: { data: SiteStatsList | undefined; pending: boolean }) {
  if (pending) return <>Loading fleet…</>;
  if (!data) return <>server-scan&apos;s servers, per site</>;
  const { servers, sites } = sitesSummary(data);
  return (
    <>
      <span className="font-medium tabular-nums text-foreground">{servers.toLocaleString()}</span> server
      {servers === 1 ? "" : "s"} across {sites} site{sites === 1 ? "" : "s"}
    </>
  );
}

function Loading() {
  return (
    <div className="space-y-8" aria-busy="true" data-testid="ss-sites-loading">
      <Section title="Fleet">
        <div className={GRID}>{[0, 1, 2].map((i) => <SiteCardSkeleton key={i} />)}</div>
      </Section>
      <Section title="Sites">
        <div className={GRID}>{[0, 1, 2, 3, 4, 5].map((i) => <SiteCardSkeleton key={i} />)}</div>
      </Section>
    </div>
  );
}

/** The fleet-wide cards above a card per site; with no server at all, the fleet row says so instead. */
function Cards({ data }: { data: SiteStatsList }) {
  return (
    <div className="space-y-8">
      <Section title="Fleet">
        {data.fleet.total === 0 ? (
          <EmptyState
            icon={ServerOff}
            bordered
            title="No servers yet"
            description="server-scan has collected no server. Its collectors fill this page, every few hours."
            data-testid="ss-sites-empty"
          />
        ) : (
          <div className={GRID}>
            {fleetCards(data.fleet).map((card) => <SiteCardView key={card.key} card={card} emphasis />)}
          </div>
        )}
      </Section>
      <Section title="Sites">
        <div className={GRID}>
          {siteCards(data.items).map((card) => <SiteCardView key={card.key} card={card} />)}
        </div>
      </Section>
    </div>
  );
}

/**
 * The Server Scan area's first page (ADR-0048,
 * docs/notes/2026-11-13-server-scan-area-api.md §7): server-scan's Sites
 * page, its cards, counts and words, in Wingman's design. Read on open and
 * again when opened after 30 seconds, as the original; never polled.
 */
export function SitesPage() {
  const sites = useServerScanSites();
  const blocked = isApiError(sites.error, "FORBIDDEN") || isApiError(sites.error, "FEATURE_DISABLED");
  const data = blocked ? undefined : sites.data;
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6 lg:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
          Sites
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground" data-testid="ss-sites-summary" aria-live="polite">
          <Summary data={data} pending={sites.isPending} />
        </p>
      </header>
      {blocked ? (
        <Blocked error={sites.error} />
      ) : sites.isPending ? (
        <Loading />
      ) : !data ? (
        <ProblemList error={sites.error} title="The sites could not be loaded from server-scan" />
      ) : (
        <>
          {sites.error !== null && (
            <ProblemList error={sites.error} title="The last read failed; this is the read before it" />
          )}
          <Cards data={data} />
        </>
      )}
    </div>
  );
}
